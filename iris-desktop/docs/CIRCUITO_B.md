# Circuito B — MCP6022 + CD4066BE, sem SN74HCT125N

Só monte depois de aprovar o Circuito A. Preserve o ADC, alimentação, fotodiodos, isolamento de 100 Ω e canal B em MID. Troque apenas a rede de realimentação. Esquemas: [rede de ganho](esquemas/B_TIA_autoranging.svg) e [ADC / controle](esquemas/ADC_ESP32.svg).

## 1. Compatibilidade elétrica

**CD4066BE em 3,3 V, ESP32 em 3,3 V, MCP6022 e MCP3208 em 3,3 V, mesmo GND.** O CD4066B tem operação nominal a partir de 3 V. Controles em LOW≈GND e HIGH≈VDD dispensam o HCT125 nesta montagem. Não alimente o CD4066 a 5 V esperando comando HIGH garantido por GPIO de 3,3 V; não aplique sinais analógicos acima de 3,3 V.

A alimentação precisa permanecer acima do mínimo de operação do CD4066. RON a 3,3 V é maior, varia com tensão do sinal, temperatura e lote; **125 Ω típico da página comercial não é valor garantido a 3,3 V**. Não use esse número para calibrar o circuito. As tabelas do datasheet se concentram em 5/10/15 V; esta montagem em 3,3 V exige a qualificação abaixo.

## 2. Pinagem completa do CD4066BE (DIP14, vista de cima)

| Pino | Função | Circuito B |
|---|---|---|
| 1 | Analógico chave 1 | OUT=U1.1, antes dos 100 Ω |
| 2 | Analógico chave 1 | Extremidade externa de R0 // C0 |
| 3 | Analógico chave 2 | Extremidade externa de R1 // C1 |
| 4 | Analógico chave 2 | OUT |
| 5 | Controle chave 2 | GPIO33→330 Ω→pino 5; 100 kΩ do pino 5 a GND |
| 6 | Controle chave 3 | GPIO26→330 Ω→pino 6; 100 kΩ do pino 6 a GND |
| 7 | VSS | GND |
| 8 | Analógico chave 3 | OUT |
| 9 | Analógico chave 3 | Extremidade externa de R2 // C2 |
| 10 e 11 | Analógico chave 4 | GND, sem uso |
| 12 | Controle chave 4 | GND |
| 13 | Controle chave 1 | GPIO32→330 Ω→pino 13; 100 kΩ do pino 13 a GND |
| 14 | VDD | 3V3, 100 nF para pino 7 e 2,2 µF no rail próximo |

Os pares analógicos são bidirecionais, mas siga a orientação acima para manter as chaves no lado de OUT. Um CD4066 nunca substitui o operacional; ele só adiciona ramos à realimentação. Confirme o encapsulamento **BE**, a marca do pino 1 e a contagem anti-horária vista de cima.

## 3. Rede de realimentação — ligações exatas

SUM = MCP6022.2; OUT = MCP6022.1. R/C do mesmo ramo são paralelos. Rf permanente **não** passa por chave.

| Ramo | Componentes entre SUM e X | Ligação de X para OUT |
|---|---|---|
| Permanente | 470 kΩ 1% // 4,7 pF C0G | Direto SUM↔OUT, sempre conectado |
| G0 | R0=52,3 kΩ 1% // C0=3,3 pF C0G | X0→CD.2; CD.1→OUT; controle CD.13 |
| G1 | R1=127 kΩ 1% // C1=1,0 pF C0G | X1→CD.3; CD.4→OUT; controle CD.5 |
| G2 | R2=412 kΩ 1% // C2=1,0 pF C0G | X2→CD.9; CD.8→OUT; controle CD.6 |

Esses valores retomam a revisão **R4.1** recuperada, com resistores de série E96. Aproximações 51/130/430 kΩ de propostas anteriores dão outras faixas e não devem receber os mesmos rótulos sem recalcular. Se só tiver E24, registre os valores realmente montados e suas faixas calculadas; o firmware deste pacote informa os valores E96 acima como **ideais**.

| Faixa | GPIO32 | GPIO33 | GPIO26 | Rf efetivo ideal, RON=0 |
|---|---|---|---|---|
| G0 | HIGH | LOW | LOW | 470 kΩ // 52,3 kΩ = 47,063 kΩ |
| G1 | LOW | HIGH | LOW | 470 kΩ // 127 kΩ = 99,983 kΩ |
| G2 | LOW | LOW | HIGH | 470 kΩ // 412 kΩ = 219,546 kΩ |
| G3 | LOW | LOW | LOW | 470,000 kΩ |

Os controles não são um endereço binário; são três chaves individuais. O software/firmware usa somente essas quatro combinações. Na troca: todos LOW → espera 20 µs → liga o ramo escolhido → espera configurável, inicialmente 50 ms. A realimentação permanente continua fechada durante a troca, mas nesse intervalo o ganho é alto; transientes podem saturar. A espera inicial precisa ser validada.

No reset, GPIOs de ganho permanecem como entrada; os pull-downs externos abrem as chaves: **G3, maior ganho**. Ao habilitar o circuito pelo comando, o firmware seleciona G0 antes dos pilotos. Não trate o estado de reset como proteção contra saturação.

Em DC: `Rf_eff = 470000 || (Ri + RON)`. Exemplo de sensibilidade, não medição: RON=2 kΩ elevaria G0 de aproximadamente 47,06 para 48,68 kΩ. Na aplicação, RON não é constante; calibre a faixa em condições reais. O ramo capacitivo também passa por RON: sua admitância é `Yramo=(1/Ri + s·Ci)/(1 + RON·(1/Ri + s·Ci))`. Portanto somar capacitores como se as chaves fossem ideais não caracteriza a banda.

**Cf são valores iniciais para qualificação.** Base 4,7 pF e ramos 3,3/1/1 pF dão totais ideais de baixa frequência 8,0/5,7/5,7/4,7 pF, mas parasitas, capacitância OFF/ON e a resistência da chave alteram a resposta. A capacitância típica de chave é da ordem de pF, comparável aos próprios Cf; não prometa as mesmas bandas entre faixas. Capacitância OFF pode manter ramos parcialmente acoplados em alta frequência. Se houver ringing, comece testando base de 8,2/10 pF, uma alteração por vez, e refaça os ensaios de todas as faixas. Escolha final exige osciloscópio/avaliação de banda, não apenas diminuir ruído no ADC.

## 4. Montagem na protoboard

MCP6022 pode ficar nas linhas 10–13, como A. CD4066 perto dele, por exemplo 1=E16, 2=E17, …, 7=E22; 8=F22, 9=F21, …, 14=F16. MCP3208 em outro trecho, por exemplo 1=E30…8=E37; 9=F37…16=F30. Confirme largura e barramentos da sua placa; estas coordenadas são sugestões para DIP, não substituem a pinagem.

Coloque Rbase/Cbase junto de SUM/OUT. Minimize SUM e os três ramos; não leve o nó SUM por cabos longos até as chaves. Passe GPIOs e SPI pelo lado externo, afastados do sensor. Fuga de fluxo de solda, umidade, protoboard suja e contato intermitente são relevantes em centenas de kΩ. Limpe o adaptador. Poucos pF podem mudar o resultado; uma PCB será preferível após a qualificação.

## 5. Validar o CD4066 separado do TIA

1. **Ainda sem ligar os ramos a SUM.** Alimente CD.14 em 3V3 e CD.7 em GND; monte desacoplamento, controles e pull-downs.
2. Use o seguidor já aprovado para gerar ~VDD/2 de baixa impedância. Leve essa saída por 1 kΩ ao pino 1 da chave 1. Ligue pino 2 a GND por carga de 47 kΩ.
3. CH0 no pino 1 e CH1 no pino 2 (nunca ligar CH1 ao controle). Em Bancada, habilite o Circuito B e aplique G3: a saída carregada da chave 1 deve ficar próxima de GND. G0: pino 2 deve acompanhar pino 1, com pequena queda devido a RON.
4. Calcule `RON ≈ 47000 × (Ventrada/Vsaida − 1)` usando as tensões diretamente nos pinos 1 e 2. A queda no resistor de 1 kΩ fica fora dessa expressão. Não calcule com Vsaida≈0, nem use a média de instantes instáveis. Para poucos códigos de diferença, a estimativa será imprecisa.
5. Desligue e repita o teste nos pares **4→3** (ligado em G1) e **8→9** (ligado em G2). G3 deve deixar todos abertos. Não use saída flutuante sem os 47 kΩ.
6. Repita próximo de 25/50/75% do rail; a resistência muda com o sinal. Registre cada condição e o lote, se conhecido. Aprovação prática inicial: chave OFF próxima do GND carregado, ON seguindo a entrada e resposta coerente aos comandos. Isso não qualifica fuga de pA nem capacitância.

## 6. Integrar e testar cada faixa manual

1. Desligue, retire o circuito isolado e monte a rede de feedback da seção 3. Mantenha 470 kΩ e Cbase conectados antes de energizar.
2. Use luz fraca e selecione G0 no início. Aponte para um patamar de monitor constante. Leia OUT/CH0.
3. Passe G0→G1→G2→G3, aguardando a estabilização real. Se saturar, reduza a luz para repetir todas as faixas no regime linear; não use o dado saturado para calcular razão de ganhos.
4. Relações ideais em relação a G0: ~1 / 2,124 / 4,665 / 9,987. Corrija o offset escuro **de cada faixa**: compare `(Vclaro−Vescuro)`; não use só a tensão absoluta.
5. Capture ruído e transições em cada faixa. Compare σ relativo à amplitude, clipping, patamares e taxas reais. Use a mesma luz, sensor, VREF e montagem.
6. Avance somente se nenhuma faixa apresentar comportamento inesperado, instabilidade ou resposta incompatível com seu ganho. Identifique a espera mínima real após as trocas. Com o ADC lento, oscilação rápida pode permanecer invisível; a banda precisa ser verificada externamente antes de sustentar precisão do G2G.

## 7. Seleção automática implementada

Em Medições, escolha **Automático CD4066**. Teto padrão dos pilotos: **80% do fundo de escala**, ajustável de 50 a 90%. Isso é margem de engenharia do projeto, não norma VESA.

Para comparar sem seleção automática no circuito B, use **Manual CD4066** e fixe a faixa desejada. O modo **Fixo** é para o circuito A: ele desativa os controles; se as chaves do B estiverem montadas, isso deixa somente a base de 470 kΩ conectada.

1. Firmware habilita G0. O computador repete **todos os pares planejados**, uma vez por faixa; salva cada piloto separadamente.
2. Firmware observa mínimo e **máximo de todas as amostras**, incluindo patamares e overshoot. Não decide só pela média do branco.
3. Se houver variação mensurável e o maior pico ficar abaixo do teto, tenta a próxima faixa. Se ultrapassar o teto, volta à última faixa aprovada. Se G0 já ultrapassar, interrompe. Sinal constante/sem amplitude não é aprovado automaticamente.
4. Ao escolher a faixa, o firmware a fixa; o software mede a sequência válida com as repetições solicitadas. Não há comutação durante uma transição válida.
5. Se ocorrer saturação real mesmo depois dos pilotos, salva a captura inválida e interrompe para revisão. Não recorta nem troca de ganho no meio para salvar o resultado.
6. Faixa, ideal de Rf, decisões e pilotos ficam no histórico. Referências antes/depois ajudam a detectar deriva. Compare sessões com ganho fixo e automático nas mesmas condições; faixas diferentes também mudam a banda da cadeia.

O algoritmo atual escolhe **uma faixa segura para todo o conjunto de pares**. Não alterna ganho a cada amostra nem mistura códigos de faixas diferentes em uma curva. Se nenhum ganho cobre simultaneamente amplitude pequena e pico alto, a medida precisa ser redesenhada; não há correção científica automática para sinal já saturado.

## Critérios para avançar

| Etapa | Evidência necessária | Se falhar |
|---|---|---|
| A fixo | ADC GND/meia escala, seguidores, resposta óptica linear sem teto inesperado | Corrigir antes de adicionar chaves |
| CD isolado | ON/OFF correto nos três pares; nível lógico rail a rail | Rever pinagem/controle/alimentação |
| TIA manual | Todas as faixas ordenadas, offset escuro e razão de ganhos registrados | Rever feedback, RON, fuga e Cf |
| Estabilidade | Caudas estáveis e verificação externa da oscilação/banda | Ajustar layout/compensação e repetir |
| Pilotos | Faixa final mantém todos os picos abaixo do teto | Reduzir ganho/luz ou ampliar o diagnóstico |
| Ensaio real | Curvas sem clipping/tempo irregular; ganho constante | Manter dado inválido e corrigir causa |

Fonte principal: [TI CD4066B, datasheet Rev. J](https://www.ti.com/lit/ds/symlink/cd4066b.pdf). A topologia e os critérios práticos são decisões de engenharia do Íris que ainda dependem de validação física.
