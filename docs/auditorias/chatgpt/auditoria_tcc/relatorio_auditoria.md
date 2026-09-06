# Auditoria do analisador óptico de monitores

Guilherme | TCC | 6 de setembro de 2026

**Conclusão:** a aquisição e a exportação já funcionam, mas a matriz atual não deve ser tratada como uma medição validada do painel. Foram encontrados erros reproduzíveis na extração de G2G/overshoot, inconsistência entre patamares de capturas diferentes e divergências na documentação elétrica. Recomendo continuar na protoboard até fechar esses pontos. O MCP3208 é útil para a próxima etapa experimental, porém não resolve sozinho o condicionamento analógico, a temporização e a validação do sinal.

## Escopo e limites dos testes

Foram examinados `analisador.py`, `medidor.ino`, `config_ensaio.json`, os dois CSVs, o painel de resultados, o texto de descrição do projeto e os dois PDFs. As cinco páginas do documento de conexões foram inspecionadas visualmente: parte importante das tabelas não aparecia na extração de texto.

Executei o núcleo matemático e funções de comunicação originais extraídos por AST, sem alterar seu conteúdo. Reproduzi as 36 capturas, apliquei nove casos de sinal controlado, cinco casos de protocolo simulado e 1.000 simulações de ruído. O arquivo Python completo passou na verificação de sintaxe.

Não houve acesso físico ao ESP32, osciloscópio, multímetro ou monitor. A interface Pygame/Tkinter e a comunicação USB real não foram executadas; o ambiente não dispõe de Pygame, pyserial ou toolchain Arduino-ESP32. O firmware foi revisado por leitura, não compilado para a placa. Nenhum resultado abaixo equivale a um teste elétrico da montagem.

## 1. O que foi confirmado nos dados

| Verificação | Resultado |
|---|---:|
| Amostras brutas | 36.000 |
| Capturas | 36, com 1.000 amostras cada |
| Transições entre níveis distintos | 30 |
| Capturas de mesmo nível, úteis para estudar ruído | 6 |
| Repetições por par | 1 |
| Menor/maior código ADC | 384 / 2.358 |
| Média G2G reproduzida, excluindo diagonal | 12,4961 ms |
| Overshoot médio reproduzido | 10,7664% |
| Maior diferença para G2G do resumo arredondado | 0,000498 ms |
| Maior diferença para overshoot do resumo arredondado | 0,004919 ponto percentual |
| Taxa média inferida dos tempos exportados | 9.996,0 a 10.004,9 amostras/s |

A concordância confirma que o resumo corresponde aos dados enviados e ao algoritmo anexado. **Ela não confirma a exatidão física do resultado.** A taxa foi recuperada por ajuste linear dos tempos do CSV. Esses tempos foram produzidos por `índice × duração/N` e arredondados, portanto não são timestamps individuais e não permitem medir jitter ou localizar amostras perdidas.

O CSV bruto usa ponto e vírgula; o resumo usa vírgula. Ambos usam ponto decimal. O exportador anexado usa vírgula nos dois, indicando que o bruto foi reformatado em algum momento ou veio de uma variante do exportador. A auditoria tratou os dois formatos e não encontrou índices faltantes/duplicados dentro das capturas.

## 2. Problema principal: o ruído entra como tempo de resposta e overshoot

Em `processar_curva`, o código procura a primeira amostra que cruza 90% e depois a última amostra anterior abaixo de 10%. Um pico isolado pode encerrar a medição antes de a transição alcançar o patamar final; recrossamentos de 10% também podem encurtar o intervalo. O pico para overshoot é o máximo/mínimo de toda a captura, incluindo ruído e período anterior à transição.

### Evidência direta da captura 0 → 51

| Quantidade | Valor |
|---|---:|
| Média inicial | 483,66 contagens |
| Média final | 554,06 contagens |
| Amplitude | 70,40 contagens |
| Desvio padrão inicial/final | 15,58 / 11,91 contagens |
| Limiar de 10% | 490,70 contagens |
| Limiar de 90% | 547,02 contagens |
| Primeiro cruzamento de 90% | índice 383, 38,29 ms |
| Amostras próximas do cruzamento | 497, 510, **555**, 496, 500 |

O ponto de 555 é um pico isolado: a amostra seguinte volta a 496. Mesmo assim, o programa reporta **1,20 ms**. Isso demonstra um erro de escolha do cruzamento nessa captura. Não é necessário supor que o painel inteiro tenha resposta de 1,20 ms para explicar a célula.

O overshoot de 53,89% também é muito sensível ao ruído, pois sua divisão é por apenas 70,40 contagens. Isso não prova ausência de overdrive real; prova que o estimador atual não o separa adequadamente do ruído.

### Teste controlado de ruído

Foi gerada uma resposta exponencial de constante de tempo de 5 ms: seu G2G teórico é `5 × ln(9) = 10,986 ms`, sem overshoot. Foram adicionados ruídos gaussianos independentes com desvio padrão de 12 contagens a uma amplitude de 70 contagens. Semente: 20260906; 1.000 realizações.

| Métrica | Valor verdadeiro simulado | Mediana produzida pelo código | Percentis 5–95 dos resultados |
|---|---:|---:|---:|
| G2G | 10,986 ms | 3,10 ms | 1,00–5,30 ms |
| Overshoot | 0% | 51,35% | 41,13–64,86% |

**Esses percentis descrevem a simulação, não a incerteza do notebook.** Ruído gaussiano é um modelo de teste; a captura real também contém picos e variações que não precisam seguir esse modelo.

### Sensibilidade a suavização: diagnóstico, sem substituir o resultado

| Processamento da captura 0 → 51 | G2G | Overshoot |
|---|---:|---:|
| Bruto original | 1,20 ms | 53,89% |
| Média móvel de 5 pontos, aproximadamente 0,5 ms | 17,00 ms | 26,77% |
| Média móvel de 11 pontos, aproximadamente 1,1 ms | 21,09 ms | 10,07% |

Os valores filtrados **não são uma correção validada**. A comparação mostra a fragilidade da medição. Escolher um filtro porque o gráfico ficou bonito pode apagar overshoot verdadeiro. Primeiro caracterize o ruído e a banda, preserve as curvas brutas e obtenha repetições; depois compare critérios de cruzamento e médias de curvas alinhadas com sinais de referência conhecidos.

## 3. Outros testes do software

| Caso controlado | Resultado do código | Interpretação |
|---|---|---|
| Exponencial limpa de subida, G2G 10,986 ms | 11,10 ms | Comportamento coerente com quantização temporal e ausência de interpolação |
| Exponencial limpa de descida | 11,10 ms | Mesma conclusão |
| Transição limpa de apenas 20 contagens | 0 ms, 0% | O limite fixo de 30 transforma baixa amplitude em resposta perfeita |
| Sinal constante com origem diferente de destino | 0 ms, 0% | Deveria ser transição ausente/inválida |
| Rampa de 20 ms começando em 0,5 ms | 14,50 ms, em vez de 16 ms | As primeiras 50 amostras já contêm a transição |
| Exponencial lenta iniciada em 85 ms | 9,50 ms; referência 21,972 ms | A janela termina antes de estabilizar, mas é aceita |
| Recorte analógico imposto em 2.400 contagens | 4,00 ms e sem saturação | O detector só olha limites digitais |
| Pico de uma amostra antes da transição | 0,10 ms | Um pico é interpretado como a própria transição |
| Uma única amostra em 4.095 | Sem saturação; overshoot de 259,5% | Exigir mais de 2% no limite deixa passar picos recortados |

Os cinco testes de protocolo usaram objetos simulados para serial, relógio e tela:

| Pacote | Comportamento |
|---|---|
| META correto, 1.000 leituras, FIM | Aceito |
| META correto, 1.000 leituras, sem FIM | Aceito após timeout |
| Leituras iguais a 5.000 | Aceitas, embora excedam 12 bits |
| Duração META negativa | Aceita, produzindo tempo por amostra negativo |
| Janela de 20 ms / 200 leituras | Rejeitada, embora o firmware permita essa janela |

### Mudanças prioritárias no Python

1. Separar **captura recebida**, **sinal utilizável** e **métrica válida**. Quando faltar uma transição, retornar estado de falha e `NaN`/vazio; não incluir zero na média. Manter as diagonais como ensaios de ruído.
2. Exigir `FIM`, duração positiva, contagem esperada, valores finitos dentro de 0–4095 e janela realmente confirmada pelo firmware. O parser de `JANELA:` deve conferir o número, não apenas o prefixo.
3. Detectar patamares por janelas definidas em tempo, verificar estabilidade e registrar seu ruído. O número fixo de 50 amostras muda de significado quando a taxa muda.
4. Garantir pré-gatilho suficiente e patamar final estabilizado. Um modo de armar captura com confirmação e buffer circular é mais confiável que presumir simultaneidade entre USB e `flip()`.
5. Detectar o evento antes de procurar cruzamentos; avaliar persistência/histerese e interpolação linear entre pontos. Calibrar o critério com sinais conhecidos: persistência excessiva também pode introduzir atraso.
6. Restringir picos ao intervalo pertinente, distinguir sobressinal de ruído e registrar separadamente recorte digital e suspeita de compressão analógica. Um teto analógico precisa de ensaio de linearidade; um patamar plano, sozinho, não distingue estabilização normal de saturação.
7. Salvar resultado individual de cada repetição, razões de rejeição, número real de tentativas, média, mediana, desvio padrão e quantidade válida. Não excluir resultados automaticamente por uma regra de 3 sigma escolhida depois de olhar os dados.
8. Validar campos da interface, tratar desconexões com `try/finally`, implementar cancelamento e salvar progresso a cada captura. Hoje um erro/interrupção antes do dashboard pode perder a sessão em memória; chamadas recursivas de `iniciar_interface` também acumulam pilha.
9. Registrar identificação/seleção real da tela. Atualmente o nome do monitor é um rótulo; `pygame.display.set_mode((0,0), FULLSCREEN)` não seleciona explicitamente o monitor informado no menu. Tela cheia também não prova sincronização de quadros ou ausência de gerenciamento de cor.
10. Corrigir rótulos: o gráfico “RGB” é um remapeamento linear do ADC, não RGB medido; “bits ADC” deveria ser “contagens ADC”; “amostragem: 1 ciclos” é repetição, não taxa. O gráfico detalhado mostra a última curva, mas seus títulos usam médias das repetições.

## 4. Patamares incoerentes entre capturas

| Destino RGB | Menor média final | Maior média final |
|---|---:|---:|
| 0 | 410,94 | 533,86 |
| 51 | 411,08 | 564,66 |
| 102 | 722,48 | 848,44 |
| 153 | 790,32 | 1.145,56 |
| 204 | 1.580,66 | 1.752,70 |
| 255 | 2.301,50 | 2.307,04 |

Nos ensaios que partem de branco, RGB 153 terminou em 790,32, abaixo de RGB 102, que terminou em 848,44. RGB 51 terminou em 411,08, abaixo do preto de outra captura, 533,86. São medições distintas; não se pode interpretar isso como uma curva de transferência válida sob condições constantes.

Hipóteses a investigar: mudança de ganho/posição/vedação durante o ensaio, brilho adaptativo ou controle de contraste dependente do conteúdo, alimentação por bateria, deriva da cadeia, instabilidade ou estado final incompleto. O arquivo não permite escolher uma causa. Em particular, a estabilidade do branco perto de 2.305 não comprova que esse seja um teto do ADC.

**Teste sugerido:** fixar sonda e ganho, desabilitar ajustes automáticos de brilho/contraste, usar alimentação e configurações constantes e registrar a sequência 0, 51, 102, 153, 204, 255 e a sequência inversa. Guardar janelas longas dos patamares em várias passagens, sem mexer no aparelho. Investigar qualquer inversão ou deriva relevante antes da matriz G2G completa.

## 5. Diagnóstico do limite próximo de 2.400

O máximo observado foi 2.358; não há evidência de recorte digital em 4.095. **Não alcançar o código máximo não é, por si só, defeito.** É desejável reservar margem para o pico de overdrive. Não aumente o ganho até o branco encostar no limite.

O ADC interno do ESP32 retorna valores crus não calibrados. Para o ESP32 clássico, a documentação lista aproximadamente 150–3.100 mV com atenuação de 11 dB; portanto `ADC × 3,3/4095` não é uma calibração válida dessa cadeia. Use `analogReadMilliVolts` como diagnóstico adicional e compare com multímetro. Essa função executa outra conversão: não deve ser confundida com a conversão calibrada do mesmo dado já armazenado. [Espressif: ADC](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html)

| Teste de bancada | Como fazer | O que separa |
|---|---|---|
| Alimentação | Medir diretamente entre pinos 8 e 4 do operacional | Fonte real versus rótulo “3,3 V” |
| Saída do TIA | Medir pino 1 em sonda coberta, preto e branco | Offset, faixa de saída e resposta à luz |
| Carga do ADC | Comparar saída com e sem ligação ao ADC, sem alterar o restante | Carga, mau contato ou conexão errada |
| ADC sozinho | Desconectar a saída do TIA e aplicar tensões conhecidas dentro da faixa válida, verificadas com multímetro | Conversão ADC versus sensor/amplificador |
| Ganho | Reduzir Rf e repetir o mesmo estímulo, registrando a alteração | Compressão e saturação do amplificador |
| Luz adicional | Aplicar um estímulo óptico controlado de maior intensidade, sem exceder a faixa elétrica | Limite real do front-end versus branco simplesmente limitado |

A marcação do CI é importante: o texto antigo fala em LM358; o PDF de conexões descreve MCP6002. O LM358 não tem saída rail-to-rail, podendo limitar a excursão superior de forma dependente da alimentação/carga. O MCP6002 tem excursão próxima aos trilhos, mas isso não garante linearidade até exatamente 0 V ou VDD. Não atribuir um teto universal de “2 V” a qualquer um desses casos. [TI: LM358](https://www.ti.com/lit/ds/symlink/lm358.pdf), [Microchip: MCP6002](https://ww1.microchip.com/downloads/aemDocuments/documents/MSLD/ProductDocuments/DataSheets/MCP6001-1R-1U-2-4-1-MHz-Low-Power-Op-Amp-DS20001733L.pdf)

O texto que sugere segurança automática ao alimentar LM358 em 5 V porque sua saída “satura em 2 V” precisa ser corrigido. A saída deve ser limitada/compatível com a entrada usada por projeto, não por essa suposição.

## 6. Montagem e MCP3208

Há três versões diferentes de pinagem/interface nos anexos:

| Fonte | Descrição |
|---|---|
| Firmware | LCD I²C, `TEM_DISPLAY=1`, SDA/SCL padrão 21/22 |
| PDF de conexões | LCD paralelo; depois removido para liberar SPI 18/19/23/5 |
| Texto antigo | LCD paralelo e MCP3208 em 14/12/13/15 |

Escolha uma única revisão documentada. Para o primeiro teste do MCP3208, desligar e desconectar o LCD simplifica a bancada. O firmware anexado continua lendo GPIO34 com `analogRead`; conectar o conversor externo não faz esse firmware passar a usá-lo.

**Proposta de pinagem para ESP32 DevKit clássico, sem LCD:**

| Pino MCP3208 | Sinal | Ligação proposta |
|---|---|---|
| 1 | CH0 | Saída do TIA ou fonte de teste |
| 9 e 14 | DGND e AGND | GND comum |
| 10 | CS | GPIO27; resistor de 10 kΩ para 3,3 V |
| 11 | DIN | GPIO23 / MOSI |
| 12 | DOUT | GPIO19 / MISO |
| 13 | CLK | GPIO18 / SCK |
| 15 e 16 | VREF e VDD | 3,3 V; desacoplamento local |

GPIO27 é uma proposta nova, para evitar um pino de seleção de boot. Se usar GPIO5 conforme o PDF, ajustar CS no código e conferir o estado durante a inicialização. Evitaria a pinagem antiga com GPIO12, cujo nível no boot pode selecionar uma tensão inadequada para a flash do ESP32 clássico. [Espressif: boot](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html)

O MCP3208 tem 12 bits, até 100 kS/s a 5 V e 50 kS/s a 2,7 V. Começar com VDD/VREF de 3,3 V e SPI de 1 MHz é uma escolha conservadora. Não conectar uma interface alimentada em 5 V diretamente ao ESP32: o nível alto exigido em suas entradas é 0,7×VDD, além da tensão de DOUT. [Microchip: MCP3208](https://ww1.microchip.com/downloads/aemDocuments/documents/APID/ProductDocuments/DataSheets/21298e.pdf)

Para testar primeiro em DC, medir GND, VREF/4, VREF/2 e 3VREF/4: códigos ideais aproximados 0, 1024, 2048, 3072, sujeitos a erros da referência, resistores, fonte e ADC. Usar divisor de baixa impedância ou fonte adequada; não usar um potenciômetro de 1 MΩ diretamente como fonte rápida do ADC. A referência real deve ser medida, e a conversão ideal usa aproximadamente `4096 × Vin/VREF`, limitada aos códigos disponíveis.

Uma transação SPI de três bytes a 1 MHz já consome 24 µs, antes do overhead de software e do tempo de CS. Por cálculo, não permite assumir 50 mil capturas/s. Começar em 10 mil, validar a temporização, depois experimentar 20 mil; taxas maiores precisam de orçamento temporal e medição próprios.

### Polaridade e realimentação do TIA

O texto antigo liga os ânodos dos BPW34 ao pino 2; o PDF liga os cátodos. Na topologia descrita, com entrada não inversora em GND e saída positiva crescente com luz, a configuração coerente é **cátodo no nó inversor e ânodo no GND**. A fotocorrente sai do nó inversor e a saída fornece corrente pelo resistor de realimentação. A orientação inversa exigiria excursão negativa nesse modelo. Confirmar a identificação dos terminais no desenho do fabricante, sem depender de descrições informais sobre o formato das pernas. [Vishay: BPW34](https://www.vishay.com/docs/81521/bpw34.pdf)

Confirmar Rf efetivo, ligação do cursor do potenciômetro e Cf entre pinos 1 e 2. O capacitor de feedback não deve ser aumentado arbitrariamente para “limpar” o gráfico. Como estimativa do polo de realimentação, `f ≈ 1/(2πRfCf)`:

| Rf | Cf | Polo aproximado |
|---|---:|---:|
| 1 MΩ | 22 pF | 7,23 kHz |
| 1 MΩ | 47 pF | 3,39 kHz |

Isso é um cálculo do modelo ideal de feedback, não uma medição da banda completa. GBW, ganho de ruído, capacitância dos diodos e parasitas também importam. O BPW34 apresenta capacitância típica de 70 pF sem polarização reversa; dois/quatro em paralelo adicionam aproximadamente 140/280 pF antes de considerar a montagem. Sua especificação de 100 ns foi obtida sob condições particulares de polarização e carga, não prova a velocidade da sonda montada. [Vishay: características e condições de teste](https://www.vishay.com/docs/81521/bpw34.pdf)

## 7. VESA e calibração: o necessário para decidir o próximo passo

O PDF teórico anexado acerta ao separar Adaptive-Sync, ClearMR e IDMS. O texto antigo mistura essas finalidades e descreve processamento que não existe no código atual. O IDMS é da SID/ICDM e define métodos de medição; o fabricante da norma informa revisões em 2021, 2023 e 2025. [SID/ICDM](https://www.sid.org/Standards/ICDM)

**Conferência no CTS oficial disponibilizado, identificado no corpo como revisão 1.1:**

| Item | Referência | Projeto enviado |
|---|---|---|
| DAQ | ≥10 kS/s; ≥16 bits | Cerca de 10 kS/s; 12 bits |
| Sonda | Banda >20 kHz | Não caracterizada |
| Repetição/intervalo | ≥20; ≥250 ms | 1; espera configurada de 500 ms |
| Padrão | Matriz 9×9; patch central de 10% | Matriz 6×6; tela inteira |
| Condição inicial | 60 min; cinza 127 a 40 cd/m² | 30 min declarados; sem luminância medida |
| G2G/overdrive | 10–90% óptico; Delta-PQ | ADC bruto; percentual simples |

Consultar seções 3.4–3.5 e 7, especialmente 7.5–7.6. A resolução de 16 bits aparece na alternativa DAQ; o documento também oferece uma rota com osciloscópio. [VESA: CTS oficial](https://vesa.org/wp-content/uploads/2023/05/Adaptive-Sync-Display-CTS-r1.1.pdf)

Não apresentar a saída atual como conformidade ClearMR: esse programa usa câmera rápida e avaliação de padrões em movimento. [VESA: método ClearMR](https://vesa.org/featured-articles/vesa-brings-clarity-to-motion-blur-in-digital-displays-with-new-compliance-test-specification-and-logo-program/)

**Mantenha o MCP3208 como etapa experimental se essa for a escolha de escopo.** Para o TCC, é defensável apresentar um instrumento de baixo custo, método definido, validação contra referência e limitações medidas. Se o objetivo for cumprir integralmente a rota DAQ do CTS, os 12 bits precisam ser tratados como desvio. Não comprar um ADC só pelo número de bits: o ADS1115 proposto no texto antigo chega a apenas 860 amostras/s, cerca de 1,16 ms por amostra, inadequado para substituir a aquisição rápida pretendida. [TI: ADS1115](https://www.ti.com/product/ADS1115)

### Por que não aplicar gamma 2,2 diretamente ao ADC

O display transforma códigos RGB em luz de maneira não linear. O detector já mede uma resposta à luz. Se a cadeia tiver resposta aproximadamente `V = aL + b`, com ganho e offset constantes, a normalização

`p(t) = [V(t) − V0] / [V1 − V0]`

é igual a `[L(t) − L0]/[L1 − L0]`. Os fatores de ganho e offset se cancelam. Isso permite obter 10% e 90% relativos sem converter necessariamente cada ponto para cd/m². **A condição é a linearidade validada da cadeia**, além de banda, ruído e patamares adequados.

Aplicar uma potência de 2,2 ao ADC sem um modelo comprovado altera os cruzamentos. O remapeamento para RGB do código é apenas visual e não lineariza nem calibra a eletrônica. Gamma deve ser caracterizada no caminho apropriado; a função sRGB também não é exatamente uma potência única de 2,2.

Para a bancada, separar:

1. **Offset eletrônico/óptico:** medir a sonda fisicamente coberta. Tela preta não é ausência garantida de luz e não deve ser confundida com corrente de escuro.
2. **Calibração elétrica:** comparar tensões conhecidas com códigos ADC e avaliar ganho, offset, monotonicidade, compressão e ruído.
3. **Linearidade óptica:** usar estímulo independente e estável. A soma de dois LEDs estáveis, medidos separadamente e juntos na mesma geometria, pode ajudar a verificar aditividade. Não prova resposta espectral fotométrica nem rastreabilidade absoluta.
4. **Calibração fotométrica:** comparar com luminancímetro/colorímetro de referência para expressar luminância absoluta. BPW34 sem correção espectral não é automaticamente um instrumento ponderado pela sensibilidade visual humana; a resposta aos canais R/G/B pode diferir.
5. **Calibração temporal:** usar gerador/LED rápido e osciloscópio para medir atraso, subida/descida e banda da cadeia, em todos os ganhos utilizados. O driver óptico precisa ser mais rápido que a sonda ou ter sua contribuição conhecida.

### Amostras por segundo, sem confundir com banda

| Taxa | Intervalo | Intervalos em uma transição de 1 ms |
|---|---:|---:|
| 10 kS/s | 100 µs | 10 |
| 20 kS/s | 50 µs | 20 |
| 50 kS/s | 20 µs | 50 |
| 100 kS/s | 10 µs | 100 |

São relações aritméticas, não garantias de exatidão. O requisito de banda da sonda e a taxa do conversor respondem a problemas diferentes. Uma aquisição de 10 kS/s não reconstrói arbitrariamente um sinal de 20 kHz; sua frequência de Nyquist é 5 kHz. PWM ou ruído acima dela podem aparecer em frequências falsas. A estratégia de banda/anti-alias deve ser projetada e documentada, sem apenas colocar um capacitor grande na entrada.

Em um modelo de primeira ordem, banda de 20 kHz corresponde aproximadamente a subida 10–90% de 17,5 µs. Não é possível demonstrar esse desempenho com pontos separados por 100 µs. Para caracterizar a sonda, a instrumentação de referência precisa ser mais rápida.

## 8. Firmware e protocolo de aquisição

O firmware evita `analogRead()` dentro da ISR e guarda as leituras em RAM antes de transmiti-las: são escolhas úteis. Contudo, a interrupção só atribui `true` a um booleano. Se duas interrupções ocorrerem antes de o laço consumi-lo, elas ficam indistinguíveis e só uma leitura é feita. O timer determina o momento da sinalização, não o instante exato de cada conversão.

`META` guarda o tempo desde o comando até o fim, não o timestamp da primeira e da última amostra. A fase do timer e as latências do laço/conversão entram nesse total. Assim, `META/N` é uma aproximação da taxa média; não corrige espaçamento irregular. Não há evidência para afirmar perdas de amostras nesta sessão, nem dados para descartá-las.

Para a próxima revisão:

- Registrar timestamps reais ou estatísticas de intervalo, contador de ticks perdidos/overruns e configuração efetiva da aquisição. Começar medindo o custo de SPI/conversão e a distribuição dos intervalos.
- Limpar flags na preparação da captura; adicionar estado “armado”, confirmação, identificação da captura e detecção explícita de sobrecarga.
- Se mantiver ADC interno, avaliar aquisição contínua/DMA com acesso a amostras individuais; não substituir por uma API que entregue somente médias e perder a forma de onda. Para MCP3208, temporizar as transações SPI e verificar seu orçamento de execução.
- Continuar transmitindo após a captura em blocos. A 115.200 baud, números de quatro dígitos com CRLF custam aproximadamente 0,52 s por mil amostras; imprimir durante cada conversão inviabilizaria esse ritmo.
- Se aumentar a taxa, recalcular buffer, janela mínima/máxima e timeout. O buffer atual tem 6.000 posições, a ISR continua ativa fora da aquisição e os comentários que prometem precisão “garantida” precisam ser revisados.
- Incluir no registro versão/hash de firmware e Python, modelo de ESP32/ADC, taxa solicitada/efetiva, VREF, Rf/Cf, número de diodos, gain setting, tela selecionada, Hz, resolução, brilho, contraste, HDR/VRR, overdrive, alimentação, posição e temperatura. Atualmente `warmup` é texto declarado; não é aquecimento controlado pelo programa.

## 9. Sequência proposta antes da placa universal

| Ordem | Trabalho | Evidência para avançar |
|---|---|---|
| 1 | Confirmar CI, polaridade, Rf/Cf, tensões e revisão de pinagem | Esquema único que corresponda à montagem |
| 2 | Testar MCP3208 sozinho com tensões conhecidas | Conversão monotônica e coerente; ruído registrado |
| 3 | Testar TIA com sonda coberta e luz controlada | Offset estável, resposta crescente, ausência de compressão na faixa usada |
| 4 | Medir temporização e resposta rápida da sonda | Taxa/intervalos documentados; comparação com referência |
| 5 | Corrigir validação e cruzamentos no Python | Passar sinais conhecidos e recusar capturas inválidas |
| 6 | Repetir patamares do notebook, ida e volta | Sem inversões inexplicadas ou mudanças de ganho/posição |
| 7 | Repetir transições selecionadas | Distribuições e curvas repetidas compatíveis com a referência |
| 8 | Soldar e repetir a mesma caracterização | Montagem soldada preserva ou melhora o desempenho observado |

Para a etapa 7, priorizar 0↔51 para testar ruído, 0↔255 para faixa dinâmica e 102↔153 ou 153↔204 para comportamento intermediário. Fazer comparação com overdrive desligado/normal/rápido quando o monitor tiver esse controle real. O campo “Normal” no software não configura nem comprova overdrive do notebook.

A placa universal 10×10 cm pode servir mecanicamente, mas a validação depende do layout real. Manter fotodiodos, nó inversor, Rf e Cf próximos; usar ligações curtas, desacoplamento junto a cada CI e caminhos de retorno que não façam corrente de SPI/LCD passar pelo nó analógico sensível. AGND e DGND devem ter referência comum bem conectada. Evitar fios longos no nó de alta impedância, limpar resíduos de fluxo e reservar pontos de teste em VDD, VREF, saída do TIA e GND. Usar soquetes e permitir troca de Rf/Cf ajuda a caracterização, desde que os parasitas sejam considerados.

Uma caixa opaca só elimina interferência da luz que realmente bloqueia. Se o programa alternar a tela inteira, uma pequena capa sobre o sensor não encobre o restante da tela. O patch central e um anteparo adequado tornam a bancada mais controlável. Não pressionar o painel com a sonda.

**Informação de bancada que falta para resolver o teto:** marcação exata do operacional instalado, Rf efetivo/Cf e tensões de alimentação e saída com sonda coberta, tela preta e tela branca. Com esses números, será possível distinguir faixa normal do sinal de limitação do amplificador ou conversor.

## Arquivos e reprodução

`auditar.py` é uma ferramenta de auditoria offline, não uma nova versão do medidor. Use a cópia original dos anexos em uma pasta e execute:

```bash
python auditar.py --entrada /caminho/para/os/anexos --saida resultados_auditoria
```

O ZIP inclui as cinco entradas de código/configuração/dados em `entradas`, preservadas byte a byte. Depois de extrair e abrir o terminal na pasta `auditoria_tcc`, também é possível usar `python auditar.py --entrada entradas --saida nova_auditoria`.

Dependências: Python 3.10+, NumPy, pandas, SciPy e Matplotlib. Os resultados gerados incluem tabelas de recálculo/sensibilidade, casos de teste, estatísticas com hashes SHA-256 dos arquivos de entrada e três figuras de diagnóstico. A saída zero do script significa que a auditoria terminou; não significa que o analisador passou nos testes. Os casos que expõem falhas ficam explicitamente identificados nos CSVs. A análise de patamares foi feita sobre as capturas individuais anexadas; com múltiplas repetições, a comparação do resumo deverá agregá-las antes de interpretar diferenças.
