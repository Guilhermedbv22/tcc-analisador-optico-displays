# Método, interpretação e limites

## O que foi reaproveitado

`core/nucleo.py` deriva da revisão CIA de 08/10 (análise 4.0.2) e foi atualizado para **4.1.0 no Desktop 1.2**: amplitude mínima padrão de 4 códigos e tratamento específico de saídas do preto junto ao limite inferior no MCP3208. Os cruzamentos interpolados 10–90% permanecem. `core/protocolo.py` continua preservado, protocolo v4. Os hashes original e atual e o motivo da adaptação constam em `PROVENIENCIA.json`. A camada `analysis.py` acrescenta diagnóstico, nomes de picos e interpretação.

Decisões recuperadas da conversa **“Principal - Chat - Dúvidas”**, especialmente 07/10: aplicação Python/PySide6/PyQtGraph, preservação dos dados brutos, reanálise, comparação de curvas/matrizes, dados locais e ganho fixo durante a aquisição válida após pilotos. A montagem com CD4066 usa a revisão posterior R4.1 disponível, em vez de misturar os valores de propostas mais antigas.

## Cálculo aplicado

1. Tempo é o timestamp de cada conversão registrado no ESP32, em µs; `leitura_us` informa a duração da chamada. A abertura do sample-and-hold ocorre dentro desse intervalo, não no instante em que o USB entrega o pacote.
2. Patamares: medianas dos primeiros 30 ms e últimos 40 ms, ajustáveis. Não se supõe gamma do monitor nem relação linear entre RGB e luminância.
3. Resposta relativa `p=(sinal−inicial)/(final−inicial)` funciona para ambos os sentidos. Correntes fotométricas absolutas e correção espectral não são inferidas.
4. Mediana de 3 amostras por padrão, ímpar de 1 a 51 ajustável. Implementação SciPy `median_filter`, borda nearest; tamanho 1 preserva o bruto. Dados armazenados não são filtrados destrutivamente.
5. G2G = primeiro cruzamento persistente de 90% menos o de 10%, interpolados entre amostras. Persistência padrão 0,3 ms confirma o evento, sem ser somada ao tempo. Respostas abaixo de três intervalos amostrais são rejeitadas pela resolução temporal do método.
6. `overshoot_pct` legado é o **excesso no alvo no sentido da transição**, normalizado pela amplitude. Em uma subida, é overshoot de luminância relativa; em descida, é undershoot. Campos `overshoot_luminance_pct` e `undershoot_pct` explicitam isso. A excursão do lado inicial é outro campo e não recebe automaticamente o nome de undershoot.
7. Pico relativo considera o trecho entre t10 e o início da janela final de patamar. O resultado bruto e o após filtro são registrados. Piso indicativo = 3×σ / amplitude; não é uma incerteza metrológica completa. Pico abaixo desse piso é descrito como não distinguível do ruído, não como prova de inexistência.
8. Acomodação: desde t10 até a última entrada na faixa final ±5% da amplitude, permanecendo em toda a cauda observada por pelo menos 20 ms. Se o ruído exceder a faixa ou a janela não confirmar permanência, mostra N/D/status, não zero.

Os defaults são escolhas exploratórias documentadas do projeto, não substituem todos os requisitos de uma norma.

## Validade separada de transporte

CRC/ID/quantidade/configuração/cronologia inválidos geram erro de comunicação/aquisição. Não se completa payload nem se substitui por zeros. Bytes parciais ficam associados ao evento.

Pacote íntegro com zeros é recebido como tal. No GND, pode ser leitura correta; em uma transição solicitada não contém amplitude e não fornece G2G. Ruído, referência, fio desconectado, SPI, montagem e estímulo são hipóteses a testar. O programa não escolhe a causa sem evidência.

O núcleo rejeita: amplitude abaixo do mínimo configurado (**4 códigos por padrão na versão 1.2**), SNR <20 por padrão, polaridade incompatível, limites do ADC/analógicos, patamar com deriva, conversão demorada e temporização irregular. O SNR utiliza a dispersão bruta dos patamares e piso de σ=0,5 código; na prática, o padrão SNR≥20 ainda exige pelo menos 10 códigos mesmo para patamares muito limpos. Amplitudes abaixo de 20 códigos recebem aviso, inclusive quando aprovadas. Alterar apenas o filtro não relaxa o SNR.

Há uma exceção ao limite inferior (código ≤2): na **subida a partir de RGB 0, com MCP3208**, aceita-se o preto inicial junto ao rail se o limiar óptico de 10% estiver acima de 2 códigos e não houver retorno ao rail após t10 + persistência. O resultado recebe aviso e continua relativo aos patamares observados. Isso não comprova ausência de corte abaixo de 10%. Alvo escuro no rail em descida, outros níveis de origem, limites analógicos informados e limite superior (≥4093) continuam invalidando a captura. O pico em uma descida cortada não é tratado como zero. Dados e versões anteriores permanecem disponíveis.

Intervalos reais devem ficar entre 0,5 e 1,5 do período nominal, média dentro de ±5%, nenhum período perdido; conversão deve caber no período. Uma revisão futura pode refinar isso, preservando as versões.

## Curvas e cores

Bruto azul, processado lilás, partida turquesa, alvo amarelo, 10% azul claro, 90% violeta, acomodação verde, referência de tempo laranja. Legendas ficam fora da área de dados.

Uma linha de 5 ms pode ser exibida como **referência configurada pelo operador**, desde t10. Ela não transforma um ensaio em aprovação VESA. Nome e valor são ajustáveis. 10/90% são níveis do método, não limites de qualidade. As cores opcionais dos indicadores representam metas pessoais configuradas; não classificam um monitor como bom/ruim.

Matrizes contêm média de repetições **válidas**, com números em todas as células de resultado e “—” para faltante/inválido/diagonal, inclusive nas exportações. Linhas representam origem e colunas, destino. As médias no topo da Análise usam todas as capturas válidas de medição, com peso igual por captura; pilotos e referências ficam fora. “Overshoot médio” é o excesso no alvo no sentido de cada transição, incluindo undershoot nas descidas, sem subtrair o piso indicativo do ruído. A imagem de todos os pares mostra cada repetição, média e marca de resultado indisponível.

O progresso é atualizado a cada 250 ms no PC, sem alterar timestamps ou amostras. A sobreposição fica no canto inferior esquerdo, fora do centro do estímulo. A estimativa inicial inclui tempo de espera, janela, transferência serial (8 bytes/amostra, UART 115200) e margem para comandos/salvamento; depois usa a duração média das últimas 12 capturas. Referências entram no total de capturas, mas não no contador de transições. Em autoranging, a estimativa dos pilotos cobre a faixa atual, sem prever quantas faixas ainda serão necessárias. Essa atualização é visual e não acrescenta sincronismo físico com o monitor.

## Ruído e comparação justa

Desvio padrão e pico a pico de uma curva inteira misturam a transição com o ruído. Nos indicadores de comparação de monitores, calcula-se ruído no patamar inicial, e também σ/amplitude. No sinal de bancada DC usa-se a janela completa. STAT fornece min/max/std de 64 amostras; sua série temporal registra **médias** de blocos, portanto o desvio dessas médias não equivale ao ruído amostra a amostra.

ΔV do seguidor usa canais lidos sequencialmente. VREF não aferida e erros do ADC limitam a exatidão. Um teste ratiométrico comprova acompanhamento, não a tensão absoluta da fonte.

Ao comparar ADCs ou operacionais, o aplicativo lista condições também diferentes e desconhecidas. Registre o mesmo Rf/Cf, VCC/VREF, Hz, OD, brilho, patch, sensor/posição, temperatura/montagem e taxa. Ordem dos ensaios, deriva e repetições também importam. Uma diferença de atraso no gráfico não é automaticamente do ADC; alinhar em t10 serve apenas para forma. Não se fornece medição de input lag.

## Limitações que precisam constar no TCC

- Cadeia BPW34 + TIA + ADC e largura de banda ainda em caracterização. O tempo medido inclui a resposta do instrumento.
- Dois fotodiodos e protoboard acrescentam capacitância. O MCP3208 não exclui oscilação acima da frequência de Nyquist.
- Estímulo QWidget/QTimer não tem sincronismo físico de varredura comprovado. O timestamp do repaint não é o instante de emissão de luz. O G2G usa os cruzamentos ópticos, mas tearing, varredura e campo do sensor podem afetar a forma.
- Fonte de tensão absoluta e fotometria/linearidade precisam de instrumentos/referências adequados. O ADC interno não recebe conversão dinâmica em volts por VREF nominal.
- Mediana pode atenuar overshoot e alterar tempos. Comparar bruto e processado e declarar o tamanho.
- 1 repetição é triagem, não estimativa robusta de repetibilidade. Não há Delta-PQ nem classificação automática de conformidade.
- Autoranging escolhe uma faixa para o conjunto do ensaio; banda/offset de cada faixa precisam ser caracterizados.

## Referências consultadas

- IDMS v1.3 r6, §10.2, 10.2.1 e diagnósticos temporais: arquivo fornecido no projeto. G2G relativo 10–90% é uma parte do método; resposta do detector e atualização espacial importam.
- VESA Adaptive-Sync Display CTS r1.1a, §7, especialmente §7.5/7.6: arquivo fornecido. Plano com 64 pares e ≥20 aquisições por par, tratamento próprio de overshoot/undershoot em Delta-PQ; o ensaio rápido Íris não equivale a esse procedimento.
- [Microchip MCP6022 / DS20001685E](https://www.microchip.com/content/dam/mchp/documents/APID/ProductDocuments/DataSheets/20001685E.pdf).
- [TI CD4066B Rev. J](https://www.ti.com/lit/ds/symlink/cd4066b.pdf).
- Microchip MCP3204/3208 DS21298E e MCP6002 DS20001733L: arquivos fornecidos.

Os PDFs dos fabricantes/normas não são redistribuídos neste pacote. O método do Íris, seus valores iniciais e testes propostos estão explicitamente separados das especificações desses documentos.
