# Firmware e protocolo

## Gravar uma vez

Arduino IDE 2.x com pacote **esp32 by Espressif Systems**, núcleo 3.x. Abra `firmware/iris_esp32/iris_esp32.ino`, selecione **ESP32 Dev Module** para o ESP32 clássico (WROOM / DevKit V1), porta e faça upload. Não selecionar C3/S3/S2: este firmware usa os recursos e pinos do ESP32 clássico.

Ou com Arduino CLI já instalado e core disponível:

```powershell
arduino-cli core update-index
arduino-cli core install esp32:esp32
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/iris_esp32
arduino-cli upload -p COM5 --fqbn esp32:esp32:esp32 firmware/iris_esp32
```

A instalação inicial do core exige rede. A execução posterior é offline. Feche o monitor serial da IDE antes de conectar no aplicativo. Não é preciso alterar/regravar para trocar canal, fazer STAT, CAP, alterar parâmetros ou operar as chaves já montadas.

## Compatibilidade

- Firmware novo **4.1.0**, protocolo de captura **4**. Nomes e formato CFG/CAP/STAT/STEP preservados, campos JSON novos são adicionais.
- Firmware anterior **4.0.0 / 4.0.1** continua atendendo ganho fixo e bancada. 4.0.0 não retorna extremos STAT; interface mostra N/D, sem fabricá-los.
- Ganho/autoranging só são oferecidos se HELLO declarar `gain4` / `auto_pilots`.
- Não há escrita de GPIOs 32/33/26 no boot; somente depois de GAIN ENABLE 1. Pull-downs físicos são obrigatórios no circuito B.
- Uma thread possui a serial; operações não concorrem com uma captura. Após falha de pacote, a conexão é encerrada para evitar reaproveitar bytes fora de sincronismo. O usuário reconecta após conferir o erro.
- Ao reconectar ao firmware novo, o desktop envia AUTO STOP antes de configurar: recupera uma busca interrompida pela queda do aplicativo sem mudar a faixa física existente. Depois, o modo escolhido no novo ensaio define seu controle.

## Comandos reais (ASCII, LF, 115200, 8N1)

| Comando | Resposta / uso |
|---|---|
| HELLO | `HELLO {JSON}` com protocol=4, firmware, board e features |
| CFG MCP3208 100 3000 0 1000000 | `OK CFG MCP3208 100 3000 0 1000000`; fonte/período/n/canal/SPI |
| CFG INTERNO 100 3000 0 1000000 | GPIO34, 12 bits; sem assumir curva calibrada em volts |
| STAT | `STAT {source,mean_raw,min_raw,max_raw,std_raw,n,channel,raw_codes64,t_us64,read_us64,...}` |
| CAP 1 | ARMED, aquisição em RAM, BEGIN+binário+END |
| GAIN? | `GAIN {enabled,range,rf_ideal_ohm,settle_ms,auto_active,locked}` |
| GAIN ENABLE 1 | Habilita controles, seleciona G0 |
| GAIN SET 0 / 1 / 2 / 3 | Comuta uma faixa; recusado durante busca automática |
| GAIN SETTLE 50 | Espera de 20..2000 ms depois da troca |
| GAIN ENABLE 0 | Abre chaves e coloca GPIOs como entrada; físico retorna a G3 pelos pull-downs |
| AUTO START 800 | Inicia pilotos, alvo=80% dos códigos; 500..900 permille |
| AUTO EVAL | Avalia todos os CAP desde a seleção da faixa; TRY / LOCKED / OUT_OF_RANGE / NO_SIGNAL |
| AUTO STOP | Encerra estado automático, mantém a faixa física atual |
| DAC 128 / DAC OFF | Diagnóstico opcional no GPIO25; **não é referência de tensão** |
| STEP 1 64 192 750 | Degrau DAC durante captura; teste elétrico avançado, sem ligação automática |

CFG aceita período 50/100/200 µs (20/10/5 kS/s), 200..6000 amostras, janela ≤600 ms, canal 0..7. 20 kS/s exige SPI 1 MHz; em 500 kHz faltaria margem. Essas são taxas solicitadas; a validade depende dos intervalos reais registrados.

CAP:

```text
ARMED 1\n
BEGIN {"protocol":4,"id":1,"n":3000,"bytes":24000,...}\n
[N registros de 8 bytes, little-endian]
\nEND 1 CRC32_HEX\n
```

Cada registro: uint32 `t_us`, uint16 `adc`, uint16 `leitura_us`. CRC-32/ISO-HDLC cobre apenas o payload binário. Serial é transmitida **depois** da aquisição; não se considera o intervalo de chegada ao PC como instante de amostragem. ID, fonte, configuração, quantidade, bytes, CRC e cronologia são verificados. Dados incompletos não são completados/interpolados.

STAT faz 64 leituras espaçadas de ~1 ms e descarta uma leitura inicial após configuração. Min/max/std pertencem ao mesmo conjunto. A versão 4.1.0 também retorna os 64 códigos, timestamps e durações em arrays JSON, preservados no payload da bancada/CSV/ZIP; o formato é aditivo e não quebra o leitor anterior. O aplicativo valida tamanho, média e cronologia desses arrays quando presentes. A transmissão aumenta o tempo de cada consulta; o gráfico é uma atualização DC lenta, não taxa contínua de kS/s.

No ADC interno, `mv_other_samples` resume **outras** 64 conversões: não é calibração da curva CAP. Para captura contígua de ruído a 5/10/20 kS/s, use **Sinal bruto / ruído**, com o CAP binário.

AUTO exige que o host execute todos os pares e só depois solicite EVAL. O firmware controla fisicamente as chaves. O desktop salva pilotos, controla o estímulo e registra as decisões. Nenhuma seleção se dá durante o laço de amostragem.

## Falha e zero

Pacote ausente/truncado/CRC inválido = falha de aquisição/comunicação, bytes parciais salvos quando disponíveis. Pacote íntegro com todos os códigos zero = transporte íntegro e sinal constante; pode ser normal no GND, mas não mede uma transição. Isso não identifica a causa elétrica. O resultado de G2G permanece N/D, nunca 0 ms.
