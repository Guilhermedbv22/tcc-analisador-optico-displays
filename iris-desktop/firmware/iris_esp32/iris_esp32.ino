/* Iris - aquisicao optica v4.1.0, ESP32 classico (DevKit / WROOM).
   Arduino-ESP32 3.x. Sem bibliotecas externas, sem display.
   Leia LEIA_ME.md. MCP3208/VREF ficam em 3V3.
   MCP6002 em 5 V somente com divisor adequado entre saida TIA e CH0.
   Extensao compativel de CAP/CFG/STAT: ganho e autoranging por pilotos.
   GPIOs de ganho ficam como entrada no boot: ativar somente com Circuito B montado.
   SPI: SCK=18, MISO=19, MOSI=23, CS=27. ADC interno: GPIO34.
   Aquisicao em RAM; serial somente antes/depois. Interrupcoes habilitadas.
   Cada amostra inclui o inicio e a duracao da chamada de leitura.
   Isso permite diagnosticar jitter; nao garante amostragem perfeita.

   Comandos ASCII terminados em LF:
   HELLO
   CFG MCP3208|INTERNO periodo_us numero_amostras canal clock_spi
   CAP id
   STAT                     (leituras lentas do ADC configurado)
   GAIN? | GAIN ENABLE 0|1 | GAIN SET 0..3 | GAIN SETTLE 20..2000
   AUTO START 500..900 | AUTO EVAL | AUTO STOP
   AUTO recebe CAPs piloto em cada faixa, considera o MAIOR pico e so muda entre CAPs.
   DAC 0..255 | DAC OFF      (teste opcional GPIO25, nao e referencia)
   STEP id inicial final indice  (degrau no DAC durante aquisicao)

   CAP/STEP: ARMED id\n; coleta; BEGIN {JSON}\n; N registros binarios
   de 8 bytes little-endian (uint32 t_us, uint16 adc, uint16 leitura_us);
   \nEND id CRC32_HEX\n. CRC-32/ISO-HDLC sobre o payload.
   Protocolo deliberadamente incompativel com o Python antigo.
*/
#include <Arduino.h>
#include <SPI.h>
#include <WiFi.h>
#include "esp_timer.h"
#include <math.h>
#include "gain_logic.h"

#if !defined(CONFIG_IDF_TARGET_ESP32)
#error "Esta versao usa a pinagem e DAC do ESP32 classico. Nao selecionar C3/S3/S2."
#endif

const char *VERSAO = "4.1.0";
constexpr uint32_t BAUD = 115200;
constexpr uint8_t PINO_CS=27, PINO_ADC=34, PINO_DAC=25;
constexpr uint32_t MAX_AMOSTRAS=6000;
struct Amostra { uint32_t t_us; uint16_t adc; uint16_t leitura_us; };
static_assert(sizeof(Amostra)==8, "Layout do pacote incorreto");
Amostra dados[MAX_AMOSTRAS]; // 48 kB; nao alocar na pilha.
bool externo=true;
uint32_t periodo=100, quantidade=3000, clockSPI=1000000;
uint8_t canal=0;
char comando[128];
size_t tamanhoComando=0;
bool comandoLongo=false;
constexpr uint8_t PINOS_GANHO[3]={32,33,26};
bool ganhoHabilitado=false;
uint8_t faixaGanho=0;
uint16_t esperaGanhoMs=50;
IrisGain::Auto automatico;

void aplicarGanho(uint8_t faixa) {
  // R base 470k permanece sempre conectado. Desliga antes de ligar outro ramo.
  for(uint8_t p:PINOS_GANHO) digitalWrite(p,LOW);
  delayMicroseconds(20);
  if(faixa<3) digitalWrite(PINOS_GANHO[faixa],HIGH);
  faixaGanho=faixa;
  delay(esperaGanhoMs); // fora do burst; valor deve ser validado na montagem.
}
void habilitarGanho(bool habilitar) {
  automatico.active=false; automatico.locked=false;
  if(habilitar) {
    for(uint8_t p:PINOS_GANHO) { digitalWrite(p,LOW); pinMode(p,OUTPUT); }
    ganhoHabilitado=true; aplicarGanho(0);
  } else {
    if(ganhoHabilitado) for(uint8_t p:PINOS_GANHO) { digitalWrite(p,LOW); pinMode(p,INPUT); }
    ganhoHabilitado=false; faixaGanho=3;
  }
}
void estadoGanho() {
  Serial.printf("GAIN {\"enabled\":%s,\"range\":%u,\"rf_ideal_ohm\":%.3f,\"settle_ms\":%u,\"auto_active\":%s,\"locked\":%s}\n",
    ganhoHabilitado?"true":"false",faixaGanho,IrisGain::effective(faixaGanho),esperaGanhoMs,
    automatico.active?"true":"false",automatico.locked?"true":"false");
}


bool fimComando(const char *s, int n) {
  if(n<=0) return false;
  while(s[n]==' ' || s[n]=='\r' || s[n]=='\t') ++n;
  return s[n]=='\0';
}
void erro(const char *texto) { Serial.print("ERR "); Serial.println(texto); }

uint16_t lerMCP() {
  // Conversao single-ended: START=1, SGL=1, selecao D2/D1/D0.
  uint8_t tx[3]={uint8_t(0x06 | (canal>>2)), uint8_t((canal&3)<<6), 0};
  uint8_t rx[3]={0,0,0};
  digitalWrite(PINO_CS, LOW);
  delayMicroseconds(1); // tSUCS minimo, margem para protoboard.
  SPI.transferBytes(tx, rx, 3); // 24 clocks continuos, SPI mode 0.
  digitalWrite(PINO_CS, HIGH);
  return (uint16_t(rx[1]&0x0F)<<8) | rx[2];
}
uint16_t lerADC() { return externo ? lerMCP() : analogRead(PINO_ADC); }

uint32_t crc32(const uint8_t *p, size_t n) {
  uint32_t crc=0xFFFFFFFFu;
  while(n--) {
    crc ^= *p++;
    for(uint8_t b=0;b<8;++b) crc=(crc>>1) ^ ((crc&1) ? 0xEDB88320u : 0u);
  }
  return ~crc;
}

// Prototipo explicito evita depender da geracao automatica de argumentos padrao da IDE.
void capturar(uint32_t id, bool degrau=false, uint8_t inicial=64,
              uint8_t final=192, uint32_t indiceDegrau=750);
void capturar(uint32_t id, bool degrau, uint8_t inicial,
              uint8_t final, uint32_t indiceDegrau) {
  if(degrau) { dacWrite(PINO_DAC,inicial); delay(100); }
  if(externo) SPI.beginTransaction(SPISettings(clockSPI, MSBFIRST, SPI_MODE0));
  lerADC(); // descarta a primeira leitura apos troca de canal/configuracao.
  Serial.printf("ARMED %lu\n", (unsigned long)id);
  Serial.flush(); // a coleta comeca apos o marcador sair da UART.
  const int64_t inicio=esp_timer_get_time();
  int64_t proxima=inicio;
  uint32_t perdidos=0, atrasoMax=0;
  int64_t degrauAntes=-1, degrauDepois=-1;
  for(uint32_t i=0;i<quantidade;++i) {
    int64_t agora;
    do { agora=esp_timer_get_time(); } while(agora<proxima);
    // Nao inventa amostras nem tenta recuperar periodos lendo em rajada.
    if(agora-proxima >= periodo) {
      uint32_t atrasadas=(agora-proxima)/periodo;
      perdidos+=atrasadas;
      proxima+=int64_t(atrasadas)*periodo;
    }
    atrasoMax=max(atrasoMax,uint32_t(agora-proxima));
    if(degrau && i==indiceDegrau) {
      degrauAntes=esp_timer_get_time()-inicio;
      dacWrite(PINO_DAC,final);
      degrauDepois=esp_timer_get_time()-inicio;
    }
    const int64_t a=esp_timer_get_time();
    const uint16_t valor=lerADC();
    const int64_t b=esp_timer_get_time();
    dados[i]={uint32_t(a-inicio),valor,uint16_t(min(int64_t(65535),b-a))};
    proxima+=periodo;
  }
  if(externo) SPI.endTransaction();
  // A abertura real do sample-and-hold ocorre dentro de [t_us,t_us+leitura_us].
  const size_t bytes=quantidade*sizeof(Amostra);
  const uint32_t crc=crc32(reinterpret_cast<uint8_t*>(dados),bytes);
  uint16_t lo=4095,hi=0;
  for(uint32_t i=0;i<quantidade;++i) { lo=min(lo,dados[i].adc); hi=max(hi,dados[i].adc); }
  automatico.observe(lo,hi);
  Serial.printf("BEGIN {\"protocol\":4,\"fw\":\"%s\",\"id\":%lu,\"source\":\"%s\","
                "\"channel\":%u,\"n\":%lu,\"period_us\":%lu,\"spi_hz\":%lu,"
                "\"missed\":%lu,\"max_late_us\":%lu,\"bytes\":%u,"
                "\"step_before_us\":%lld,\"step_after_us\":%lld,"
                "\"gain_enabled\":%s,\"gain_range\":%u,\"rf_ideal_ohm\":%.3f,"
                "\"auto_pilot\":%s,\"auto_locked\":%s}\n",
                VERSAO,(unsigned long)id,externo?"MCP3208":"INTERNO",canal,
                (unsigned long)quantidade,(unsigned long)periodo,(unsigned long)clockSPI,
                (unsigned long)perdidos,(unsigned long)atrasoMax,unsigned(bytes),
                (long long)degrauAntes,(long long)degrauDepois,
                ganhoHabilitado?"true":"false",faixaGanho,IrisGain::effective(faixaGanho),
                automatico.active?"true":"false",automatico.locked?"true":"false");
  Serial.write(reinterpret_cast<uint8_t*>(dados),bytes);
  Serial.printf("\nEND %lu %08lX\n",(unsigned long)id,(unsigned long)crc);
  Serial.flush();
}

void tratar(const char *s) {
  if(strchr(s,'-')) { erro("VALOR_NEGATIVO"); return; }
  if(strcmp(s,"HELLO")==0) {
    Serial.printf("HELLO {\"protocol\":4,\"fw\":\"%s\",\"board\":\"ESP32_CLASSIC\","
                  "\"max_samples\":6000,\"record_bytes\":8,\"baud\":115200,"
                  "\"features\":[\"stat_extrema\",\"stat_std\",\"stat_samples64\",\"gain4\",\"auto_pilots\"]}\n",VERSAO);
    return;
  }
  int gfim=0; long valorGanho=0;
  if(!strcmp(s,"GAIN?")) { estadoGanho(); return; }
  if(sscanf(s,"GAIN ENABLE %ld %n",&valorGanho,&gfim)==1 && fimComando(s,gfim)) {
    if(valorGanho!=0 && valorGanho!=1) { erro("GAIN_ENABLE_INVALIDO"); return; }
    habilitarGanho(valorGanho==1); estadoGanho(); return;
  }
  gfim=0;
  if(sscanf(s,"GAIN SETTLE %ld %n",&valorGanho,&gfim)==1 && fimComando(s,gfim)) {
    if(valorGanho<20 || valorGanho>2000) { erro("GAIN_SETTLE_INVALIDO"); return; }
    esperaGanhoMs=uint16_t(valorGanho); estadoGanho(); return;
  }
  gfim=0;
  if(sscanf(s,"GAIN SET %ld %n",&valorGanho,&gfim)==1 && fimComando(s,gfim)) {
    if(!ganhoHabilitado || automatico.active || valorGanho<0 || valorGanho>3) { erro("GAIN_SET_INVALIDO"); return; }
    automatico.locked=false; aplicarGanho(uint8_t(valorGanho)); estadoGanho(); return;
  }
  gfim=0;
  if(sscanf(s,"AUTO START %ld %n",&valorGanho,&gfim)==1 && fimComando(s,gfim)) {
    if(!ganhoHabilitado || !externo || valorGanho<500 || valorGanho>900) { erro("AUTO_START_INVALIDO"); return; }
    automatico.start(uint16_t(valorGanho)); aplicarGanho(0);
    Serial.printf("AUTO {\"status\":\"TRY\",\"range\":0,\"target_raw\":%u}\n",automatico.target); return;
  }
  if(!strcmp(s,"AUTO STOP")) {
    automatico.active=false; automatico.locked=false;
    Serial.println("AUTO {\"status\":\"STOPPED\"}"); return;
  }
  if(!strcmp(s,"AUTO EVAL")) {
    if(!automatico.active) { erro("AUTO_NAO_ATIVO"); return; }
    uint16_t lo=automatico.minimum,hi=automatico.maximum;
    uint32_t capturas=automatico.captures;
    auto decisao=automatico.evaluate();
    const char *status="NO_CAPTURES";
    switch(decisao) {
      case IrisGain::Decision::TRY_NEXT: status="TRY"; aplicarGanho(automatico.range); break;
      case IrisGain::Decision::LOCKED: status="LOCKED"; aplicarGanho(automatico.range); break;
      case IrisGain::Decision::OUT_OF_RANGE: status="OUT_OF_RANGE"; aplicarGanho(0); break;
      case IrisGain::Decision::NO_SIGNAL: status="NO_SIGNAL"; aplicarGanho(0); break;
      default: break;
    }
    Serial.printf("AUTO {\"status\":\"%s\",\"range\":%u,\"target_raw\":%u,\"min_raw\":%u,\"max_raw\":%u,\"captures\":%lu}\n",
      status,faixaGanho,automatico.target,lo,hi,(unsigned long)capturas); return;
  }
  char fonte[16]; long p=0,n=0,c=0,hz=0; int fim=0;
  if(sscanf(s,"CFG %15s %ld %ld %ld %ld %n",fonte,&p,&n,&c,&hz,&fim)==5 && fimComando(s,fim)) {
    if((strcmp(fonte,"MCP3208") && strcmp(fonte,"INTERNO")) ||
       (p!=50 && p!=100 && p!=200) || n<200 || n>MAX_AMOSTRAS ||
       c<0 || c>7 || (hz!=500000 && hz!=1000000) || n*p>600000) {
      erro("CFG_INVALIDA"); return;
    }
    // 24 clocks a 500 kHz = 48 us, alem de CS e chamadas: sem margem a 20 kS/s.
    if(!strcmp(fonte,"MCP3208") && p==50 && hz==500000) {
      erro("20KSPS_EXIGE_SPI_1MHZ"); return;
    }
    if(!strcmp(fonte,"INTERNO") && c!=0) {
      erro("INTERNO_USA_GPIO34_CANAL0"); return;
    }
    if(automatico.active) { erro("AUTO_BLOQUEIA_CFG"); return; }
    externo=!strcmp(fonte,"MCP3208"); periodo=p; quantidade=n; canal=c; clockSPI=hz;
    Serial.printf("OK CFG %s %lu %lu %u %lu\n",fonte,(unsigned long)periodo,
                  (unsigned long)quantidade,canal,(unsigned long)clockSPI);
    return;
  }
  unsigned long id=0; fim=0;
  if(sscanf(s,"CAP %lu %n",&id,&fim)==1 && fimComando(s,fim) && id>0) {
    capturar(id); return;
  }
  long a=0,b=0,k=0; fim=0;
  if(sscanf(s,"STEP %lu %ld %ld %ld %n",&id,&a,&b,&k,&fim)==4 && fimComando(s,fim)) {
    if(!id || a<0 || a>255 || b<0 || b>255 || k<1 || k>=quantidade) {erro("STEP_INVALIDO");return;}
    capturar(id,true,a,b,k); return;
  }
  if(!strcmp(s,"DAC OFF")) { dacDisable(PINO_DAC); Serial.println("OK DAC OFF"); return; }
  fim=0;
  if(sscanf(s,"DAC %ld %n",&a,&fim)==1 && fimComando(s,fim) && a>=0 && a<=255) {
    dacWrite(PINO_DAC,a); Serial.printf("OK DAC %ld\n",a); return;
  }
  if(!strcmp(s,"STAT")) {
    uint32_t soma=0,mv=0; double somaQuadrados=0; uint16_t minimo=4095,maximo=0;
    Amostra estaticas[64];
    if(externo) SPI.beginTransaction(SPISettings(clockSPI,MSBFIRST,SPI_MODE0));
    lerADC();
    const int64_t estInicio=esp_timer_get_time();
    for(int i=0;i<64;++i) {
      int64_t antes=esp_timer_get_time();
      uint16_t valor=lerADC();
      int64_t depois=esp_timer_get_time();
      estaticas[i]={uint32_t(antes-estInicio),valor,uint16_t(min(int64_t(65535),depois-antes))};
      soma+=valor; somaQuadrados+=double(valor)*valor;
      minimo=min(minimo,valor); maximo=max(maximo,valor); delay(1);
    }
    if(externo) SPI.endTransaction();
    // Sao OUTRAS 64 conversoes; nao aplicar esses mV a uma curva dinamica.
    if(!externo) for(int i=0;i<64;++i) { mv+=analogReadMilliVolts(PINO_ADC); delay(1); }
    Serial.printf("STAT {\"source\":\"%s\",\"mean_raw\":%.4f,\"min_raw\":%u,"
                  "\"max_raw\":%u,\"mv_other_samples\":%ld,\"std_raw\":%.4f,"
                  "\"n\":64,\"channel\":%u,\"gain_enabled\":%s,\"gain_range\":%u,\"raw_codes64\":[",
                  externo?"MCP3208":"INTERNO",soma/64.0,minimo,maximo,externo?-1L:long(mv/64),
                  sqrt(max(0.0,(somaQuadrados-double(soma)*soma/64.0)/63.0)),
                  canal,ganhoHabilitado?"true":"false",faixaGanho);
    for(int i=0;i<64;++i) Serial.printf("%s%u",i?",":"",estaticas[i].adc);
    Serial.print("],\"t_us64\":[");
    for(int i=0;i<64;++i) Serial.printf("%s%lu",i?",":"",(unsigned long)estaticas[i].t_us);
    Serial.print("],\"read_us64\":[");
    for(int i=0;i<64;++i) Serial.printf("%s%u",i?",":"",estaticas[i].leitura_us);
    Serial.println("]}");
    return;
  }
  erro("COMANDO_INVALIDO");
}

void setup() {
  Serial.begin(BAUD);
  WiFi.mode(WIFI_OFF); // Bluetooth nao e inicializado por este firmware.
  digitalWrite(PINO_CS,HIGH); pinMode(PINO_CS,OUTPUT);
  SPI.begin(18,19,23,PINO_CS);
  pinMode(PINO_ADC,INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(PINO_ADC,ADC_11db);
  // GPIO25 permanece sem DAC ativo ate um comando de diagnostico.
}
void loop() {
  while(Serial.available()) {
    char c=char(Serial.read());
    if(c=='\n') {
      if(comandoLongo) erro("LINHA_LONGA");
      else { comando[tamanhoComando]='\0'; if(tamanhoComando) tratar(comando); }
      tamanhoComando=0; comandoLongo=false;
    } else if(c!='\r') {
      if(tamanhoComando<sizeof(comando)-1) comando[tamanhoComando++]=c;
      else comandoLongo=true;
    }
  }
  delay(1); // sistema respira entre capturas; nunca dentro do burst.
}
