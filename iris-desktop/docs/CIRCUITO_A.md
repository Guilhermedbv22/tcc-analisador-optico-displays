# Circuito A — MCP6022 em ganho fixo

Faça o seguidor antes do TIA. Não conecte o CD4066 nesta etapa. Alimentação proposta: **3,3 V em todo o circuito**, ESP32 clássico DevKit V1 via USB. MCP6022 admite 2,5–5,5 V; seu ganho de banda de 10 MHz exige cuidado maior com parasitas que o MCP6002.

Esquemas: [seguidor](esquemas/A0_seguidor.svg), [TIA fixo](esquemas/A1_TIA_fixo.svg), [ADC e ESP32](esquemas/ADC_ESP32.svg). As redes com o mesmo nome estão conectadas.

## 1. Pinagem e orientação

Vista de cima, marca do pino 1 corretamente identificada. No SOIC-8, confirme a marca do encapsulamento e as trilhas do adaptador: **não presuma que o número impresso no adaptador está correto**. A pinagem abaixo é do CI. A validação sem multímetro verifica comportamento, mas não comprova continuidade de cada solda nem ausência de todos os curtos.

| Pino MCP6022-I/SN ou MCP6002 dual | Função |
|---|---|
| 1 | OUT A |
| 2 | IN− A |
| 3 | IN+ A |
| 4 | VSS / GND |
| 5 | IN+ B |
| 6 | IN− B |
| 7 | OUT B |
| 8 | VDD / 3V3 |

Uma protoboard A–E / F–J, com canal central, pode receber o adaptador como DIP8: 1=E10, 2=E11, 3=E12, 4=E13, 5=F13, 6=F12, 7=F11, 8=F10. Isso exige adaptador com saída DIP 1:1 e espaçamento compatível. Se o seu for diferente, siga o pino do CI; as letras não se aplicam. Cada linha tem A–E unidos e F–J unidos; os dois lados do canal **não** se conectam sozinhos. Confira se os barramentos laterais são interrompidos no meio.

## 2. ADC / ESP32 — ligação comum

| MCP3208 DIP16 | Conectar |
|---|---|
| 16 VDD | ESP32 3V3 |
| 15 VREF | Mesmo 3V3; 100 nF para pino 14 |
| 14 AGND e 9 DGND | GND comum, retorno curto ao circuito |
| 13 CLK | GPIO18, fio curto |
| 12 DOUT | GPIO19 |
| 11 DIN | GPIO23 |
| 10 CS/SHDN | GPIO27; 10 kΩ para 3V3 |
| 1 a 8 | CH0 a CH7, respectivamente |

100 nF entre pinos 16 e 14, junto do CI; 4,7 µF entre 3V3 e GND perto do ADC. Fios SPI e de ganho longe do nó SUM. O esquema mostra 47 Ω em série, opcionais para amortecer SPI, junto do transmissor (MISO junto do ADC). Não adicione cargas grandes ou fios longos no SPI de 1 MHz. MCP3208 a 3,3 V evita aplicar 5 V ao MISO do ESP32.

ADC interno para comparação: saída protegida por 100 Ω também pode chegar a GPIO34, apenas se estiver entre 0 e 3,3 V. Prefira capturas sequenciais do mesmo ponto estável, com ambos os caminhos identificados. Não ligue GPIO34 como saída. O software usa canal lógico 0 para o interno.

## 3. Teste do ADC antes do amplificador

1. Desligue. **Desconecte CH0 de qualquer saída ativa** antes de ligá-lo ao GND, para não curto-circuitar o operacional.
2. Ligue CH0 diretamente ao AGND (pino 14). Em Bancada, leia apenas CH0 por 2–5 s, sem tocar na ponta. Marque o ponto e exporte.
3. Espera-se código próximo de zero e baixa dispersão. Referência prática inicial, não especificação garantida: média até poucos códigos; deslocamento de dezenas/centenas ou grande ruído precisa de investigação. Um pacote de zeros é dado válido de transporte; **sozinho não comprova que o ADC funciona**.
4. Monte 3V3 → 10 kΩ → TESTE → 10 kΩ → GND. Ligue CH0 a TESTE. Espere aproximadamente código 2048, respeitando tolerância dos resistores. Depois retorne ao GND.
5. Se os dois testes não se distinguirem, confira pinos e SPI; não avance ao MCP6022.

VREF=VDD comum torna a leitura ratiométrica. Ver aproximadamente metade da escala não mede se a alimentação é exatamente 3,300 V. A tensão exibida usa o valor que você informou. Medir o próprio rail com essa referência leva ao fundo de escala e não fornece uma medida independente de VCC. Sem multímetro, registre `VREF nominal, não calibrada`.

## 4. Seguidor — testar adaptador e os dois canais

Alimentação desligada para montar. Ainda sem fotodiodos nem realimentação de 235 kΩ.

| Conexão | Componentes |
|---|---|
| U1.8→3V3; U1.4→GND | 100 nF entre 8–4, próximo ao adaptador; 2,2–4,7 µF no rail |
| U1.1→U1.2 | Realimentação direta de A |
| U1.7→U1.6 | Realimentação direta de B |
| U1.3 e U1.5→TESTE | Mesma entrada dos seguidores |
| CH0→TESTE | 100 Ω em série com a entrada do ADC |
| CH1→U1.1 | 100 Ω em série |
| CH2→U1.7 | 100 Ω em série |

TESTE: cadeia **3V3 → 10 kΩ → P75 → 10 kΩ → P50 → 10 kΩ → P25 → 10 kΩ → GND**. Comece em P50; com o USB desligado, leve TESTE a P25 e depois P75. Não deixe as entradas flutuantes. Use resistores 1%. Os nós fornecem aproximadamente 25/50/75% do rail (0,825/1,650/2,475 V nominais a 3,3 V).

No aplicativo: Bancada → Seguidor CH0/1/2; 500 ms por ciclo; VREF nominal. Registre cada ponto por 2–5 s, com rótulo. Leituras dos canais são **sequenciais**, não simultâneas.

| Teste | Comportamento esperado | Decisão |
|---|---|---|
| P25, P50 e P75 | A e B acompanham CH0, sem teto próximo de 1,9 V | Prosseguir se repetível |
| Desvio A/B−entrada | Pequeno frente ao sinal; alvo prático inicial ≤máx.(10 mV, 1% da entrada) | Investigar se exceder; não é limite de datasheet nem diagnóstico isolado |
| Ambos os canais fixos em rail | Entrada, realimentação, alimentação ou adaptador podem estar incorretos | Desligar e conferir |
| Um canal acompanha, outro não | Conferir pinos 5/6/7 e soldas específicas, sem assumir CI defeituoso | Repetir ligação e ponto |
| Ruído alto no ADC até com CH0 direto no AGND | A origem pode estar no ADC/SPI/GND/referência | Resolver antes de atribuir ao operacional |

Depois dos três pontos, pode testar perto de 90% do rail com divisor 10 kΩ em cima e 90,9 kΩ embaixo, sem carga na saída além do ADC. A proximidade do rail depende da carga e não se exige saída idêntica a VDD. Troque o MCP6022 pelo MCP6002, desligado, e repita com os mesmos fios e resistores. O teto anterior de aproximadamente 1,95 V observado no MCP6002 **não é tratado como característica normal garantida desse modelo**; causas e montagem seguem em investigação.

## 5. Converter em TIA fixo

Desligue e **retire as pontes 1–2 e a ligação TESTE→3/5** do seguidor. Para o canal B, faça a configuração abaixo; não deixe a entrada antiga ligada ao divisor de testes.

| Elemento / pino | Ligação exata |
|---|---|
| U1.8 / U1.4 | 3V3 / GND, desacoplamento mantido |
| U1.3 IN+ A | GND |
| Dois BPW34 | Ambos os ânodos no GND; ambos os cátodos em SUM=U1.2 |
| Rf1 e Rf2 | Cada 470 kΩ, 1%, de U1.1 para U1.2; em paralelo = 235 kΩ nominal |
| Cf | 8,2 pF C0G/NP0 de U1.1 para U1.2; em paralelo a Rf |
| ADC CH0 | U1.1→100 Ω→MCP3208.1 |
| MID | 3V3→100 kΩ→MID→100 kΩ→GND; MID→100 nF→GND |
| U1.5 IN+ B | MID |
| U1.6 / U1.7 | Unidos; saída B sem carga externa |

A polaridade física do BPW34 deve ser conferida pelo desenho do fabricante / marca A/K, não apenas pelo comprimento das pernas. Com os ânodos em GND e cátodos no nó virtual, mais luz deve aumentar OUT A. `Vout ≈ Iphoto_total × 235 kΩ` é relação ideal no regime linear; offsets, banda e corrente de entrada limitam a aplicação.

Coloque Rf/Cf colados aos pinos 1/2 do adaptador, terminais mínimos; nó SUM curto, limpo e sem cabos de teste. **Não use o ADC ou uma ponta comum no SUM durante a qualificação**: a capacitância adicional altera o circuito. Realimentação vem de U1.1, **antes** dos 100 Ω, nunca do CH0. Mantenha os retornos analógicos curtos; evite compartilhar o caminho do sensor com corrente dos fios SPI.

Cf de 8,2 pF é o ponto de comparação com os seus ensaios anteriores, não uma compensação garantida. Faça ensaios separados com 15 pF e 22 pF se houver ruído/instabilidade; aumentar Cf reduz banda e pode alterar a transição medida. Dois BPW34 em paralelo aumentam área e capacitância; são necessários teste de estabilidade e banda da montagem real. A observação anterior de redução de ruído com 8,2 pF não comprova a resposta em frequência.

## 6. Qualificar e comparar

1. Bancada: preto, cinza e branco, sensor parado. Anote patamares, ruído e amplitude. Se encostar em fundo de escala, reduza luz/Rf; não altere VREF só no software.
2. Captura rápida: patamares de mesma luminosidade, 10 kS/s e mesma janela. Compare σ e pp, declarando que FFT/ADC não detectam toda oscilação fora da banda.
3. Medições: 0→255, 255→0, 51→102 e 102→204, 1 repetição para triagem. Depois 3 por par para observar dispersão, quando possível.
4. Troque **apenas** o operacional, desligado. Mesma Cf, Rf, montagem, VCC/VREF, sensor, overdrive e taxa. Nomeie as duas sessões.
5. Avance se os seguidores passaram, o TIA responde monotonicamente e as capturas não têm clipping/temporização inválida. Use o SNR e estabilidade dos patamares declarados pelo algoritmo. Atribuição de melhoria ao operacional só com condições equivalentes e repetibilidade; estabilidade de alta frequência continua pendente sem osciloscópio.

Referências: Microchip DS20001685E (MCP6022), DS20001733L (MCP6002), DS21298E (MCP3208). Ligações são uma proposta revisada do projeto para validar, não um circuito fisicamente certificado.
