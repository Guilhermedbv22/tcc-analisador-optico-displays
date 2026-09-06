/*
================================================================================
 TCC - FIRMWARE DO ANALISADOR OPTICO (ESP32) - v3 (definitiva)
--------------------------------------------------------------------------------
 Protocolo serial (par do "analisador.py"), a 115200 baud:

   PC -> ESP32
     "F\n"        -> handshake: pede a versao do firmware
     "W:<ms>\n"   -> (opcional) redefine a janela de captura, em milissegundos
     "T:l1|l2\n"  -> (opcional) atualiza o display de status (2 linhas) -
                      so tem efeito se TEM_DISPLAY estiver ligado
     "I\n"        -> dispara uma captura

   ESP32 -> PC
     "FW:<versao>\n"                  -> resposta ao handshake
     "JANELA:<ms>\n"                  -> confirmacao do comando W
     "META:<duracao_us>,<contagem>\n" -> tempo real decorrido e quantas
                                          amostras foram tiradas nesse tempo
     <amostra0>\n .. <amostraN-1>\n   -> uma leitura crua do ADC (0-4095) por linha
     "FIM\n"                           -> encerra a captura

 O QUE MUDOU NESTA VERSAO (juntando o seu "medidor.ino" com as versoes
 anteriores que eu tinha passado):
--------------------------------------------------------------------------------
 - Amostragem disparada por um TIMER DE HARDWARE (igual ao seu medidor.ino),
   que e mais determinístico que um laco de espera ativa (busy-wait) em
   software. IMPORTANTE: a interrupcao do timer so ARMA UM SINALIZADOR
   (sinalizadorAmostra = true); quem efetivamente chama analogRead() e o
   loop() principal, nunca a propria ISR. Isso e proposital — chamar
   analogRead() diretamente de dentro de uma interrupcao pode travar o
   ESP32 em alguns cores do Arduino-ESP32 (internamente a funcao pode tentar
   tomar um mutex, o que nao e seguro em contexto de interrupcao). Na
   pratica a precisao fica quase identica a ler direto na ISR, so que sem
   esse risco de crash no meio de um ensaio de horas.
 - Continua reportando o tempo real decorrido e a contagem de amostras
   (META) a cada captura, em vez de simplesmente assumir uma taxa fixa - o
   analisador.py usa isso para calcular o tempo por amostra individualmente.
 - Wi-Fi desligado no boot (como no seu medidor.ino) para reduzir ruido
   eletromagnetico no ADC.
 - Display de status (LCD 16x2 I2C) de volta, mas isolado atras de
   TEM_DISPLAY: se um dia quiser tirar o display, e so trocar o 1 por 0
   logo abaixo — nenhum outro trecho do codigo precisa mudar.
================================================================================
*/

#include <WiFi.h>

// ---------------- CONFIGURACAO GERAL ----------------------------------------
#define TEM_DISPLAY          1            // 1 = tenho um LCD 16x2 I2C ligado | 0 = sem display
#define PINO_SENSOR          34           // D34 - entrada do sensor de luz (ADC1_CH6)
#define BAUD_RATE             115200
#define FIRMWARE_VERSAO      "3.0-ESP32"

#define PERIODO_AMOSTRA_US    100         // 100 us fixos = 10 kHz nominal (o timer de hardware garante a precisao)
#define AMOSTRAS_ALVO_PADRAO  1000        // 1000 amostras x 100 us = 100 ms (janela padrao)
#define AMOSTRAS_ALVO_MIN      200        //  20 ms
#define CAPACIDADE_BUFFER     6000        // teto de amostras (ate 600 ms) - nunca estoura RAM

#if TEM_DISPLAY
  #include <Wire.h>
  #include <LiquidCrystal_I2C.h>          // Biblioteca "LiquidCrystal I2C" (Frank de Brabander) via Library Manager
  LiquidCrystal_I2C lcd(0x27, 16, 2);      // troque para 0x3F se o seu modulo usar esse endereco
#endif

uint16_t bufferADC[CAPACIDADE_BUFFER];
volatile uint16_t indice = 0;
volatile uint16_t amostrasAlvo = AMOSTRAS_ALVO_PADRAO;
volatile bool sinalizadorAmostra = false;
volatile int estado = 0;   // 0 = repouso | 1 = capturando | 2 = pronto para enviar

uint32_t tempoInicioCaptura = 0;
uint32_t tempoFimCaptura = 0;

hw_timer_t *timer = NULL;

void tratarComando(String linha);
void atualizarDisplay(String linha1, String linha2);
String ajustarLinha(String txt);

// ---------------- INTERRUPCAO DO TIMER --------------------------------------
// So sinaliza; a leitura do ADC acontece no loop() (ver comentario no topo).
void IRAM_ATTR onTimer() {
  if (estado == 1 && indice < amostrasAlvo) {
    sinalizadorAmostra = true;
  }
}

// ---------------- SETUP ------------------------------------------------------
void setup() {
  Serial.begin(BAUD_RATE);

  WiFi.mode(WIFI_OFF);   // reduz ruido eletromagnetico no ADC

  pinMode(PINO_SENSOR, INPUT);
  analogReadResolution(12);        // 0-4095, igual ao que analisador.py espera
  analogSetAttenuation(ADC_11db);  // faixa de entrada ~0-3,3 V

#if TEM_DISPLAY
  Wire.begin();                    // SDA=21, SCL=22 no ESP32 DevKit padrao
  lcd.init();
  lcd.backlight();
#endif
  atualizarDisplay("Aguardando PC..", "");

  // Sintaxe do core arduino-esp32 3.x (baseado no ESP-IDF 5.x). Se voce
  // estiver num core 2.x mais antigo, a assinatura de timerBegin() muda
  // (timerBegin(numero, divisor, contagemCrescente)).
  timer = timerBegin(1000000);              // base de 1 MHz (1 tick = 1 us)
  timerAttachInterrupt(timer, &onTimer);
  timerAlarm(timer, PERIODO_AMOSTRA_US, true, 0);
}

// ---------------- LOOP PRINCIPAL ---------------------------------------------
void loop() {
  // 1) Atende o sinalizador do timer o mais rapido possivel (fora da ISR)
  if (sinalizadorAmostra) {
    sinalizadorAmostra = false;
    if (estado == 1) {
      bufferADC[indice] = analogRead(PINO_SENSOR);
      indice++;
      if (indice >= amostrasAlvo) {
        tempoFimCaptura = micros();
        estado = 2;
      }
    }
  }

  // 2) Comandos vindos do PC (nunca durante uma captura em andamento, para
  //    nao atrasar o atendimento do sinalizador acima)
  if (estado != 1 && Serial.available()) {
    String linha = Serial.readStringUntil('\n');
    linha.trim();
    if (linha.length() > 0) {
      tratarComando(linha);
    }
  }

  // 3) Aquisicao concluida: escoa os dados pela serial
  if (estado == 2) {
    Serial.print("META:");
    Serial.print(tempoFimCaptura - tempoInicioCaptura);
    Serial.print(",");
    Serial.println(indice);

    for (uint16_t i = 0; i < indice; i++) {
      Serial.println(bufferADC[i]);
    }
    Serial.println("FIM");

    estado = 0;
  }
}

// ---------------- COMANDOS ---------------------------------------------------
void tratarComando(String linha) {
  if (linha == "F") {
    Serial.print("FW:");
    Serial.println(FIRMWARE_VERSAO);
  }
  else if (linha == "I") {
    indice = 0;
    tempoInicioCaptura = micros();
    estado = 1;
  }
  else if (linha.startsWith("W:")) {
    long ms = linha.substring(2).toInt();
    long alvo = (ms * 1000L) / PERIODO_AMOSTRA_US;
    if (alvo < AMOSTRAS_ALVO_MIN) alvo = AMOSTRAS_ALVO_MIN;
    if (alvo > CAPACIDADE_BUFFER) alvo = CAPACIDADE_BUFFER;
    amostrasAlvo = (uint16_t)alvo;
    Serial.print("JANELA:");
    Serial.println((uint32_t)amostrasAlvo * PERIODO_AMOSTRA_US / 1000UL);
  }
  else if (linha.startsWith("T:")) {
    String corpo = linha.substring(2);
    int pos = corpo.indexOf('|');
    if (pos >= 0) atualizarDisplay(corpo.substring(0, pos), corpo.substring(pos + 1));
    else          atualizarDisplay(corpo, "");
  }
}

// ---------------- DISPLAY -----------------------------------------------------
void atualizarDisplay(String linha1, String linha2) {
#if TEM_DISPLAY
  lcd.setCursor(0, 0); lcd.print(ajustarLinha(linha1));
  lcd.setCursor(0, 1); lcd.print(ajustarLinha(linha2));
#else
  (void)linha1; (void)linha2;  // sem display: comando "T:" e ignorado de proposito
#endif
}

String ajustarLinha(String txt) {
  if (txt.length() > 16) txt = txt.substring(0, 16);
  while (txt.length() < 16) txt += ' ';
  return txt;
}
