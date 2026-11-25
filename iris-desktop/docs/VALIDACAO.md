# Verificação da entrega 1.0

**Esta entrega é uma implementação integrada com validação de software. Não é uma declaração de validação física do instrumento.**

## Verificado no ambiente desta entrega

Linux x86-64, Python 3.12, PySide6 6.12.0 e PyQtGraph 0.14.0. Demais versões em `requirements-tested-linux.txt`.

| Verificação | Evidência |
|---|---|
| Núcleo reaproveitado | Hashes idênticos ao `nucleo.py`/`protocolo.py` da revisão CIA; sem alteração dos cruzamentos |
| Reanálise real | 30/30 transições do ensaio 953f26; G2G médio **3,7182805105 ms** e excesso no alvo médio **2,2678314081%** reproduzidos |
| Comparação real dos ADCs | 36 capturas importadas, 6 pares × 3 repetições por ADC a 10 kS/s; 18/18 MCP3208 aceitas e 0/18 interno aceitas nos critérios. Isto não identifica a causa elétrica das rejeições |
| Voltímetro anterior | 39 registros importados, separados por rótulo/condição, com timestamps e referências originais |
| Falhas e zero | CRC corrompido/truncado, ID/configuração, sinal constante, rail, tempo irregular; N/D para G2G inválido. Zero estático é dado, não erro automático |
| Persistência | Hash do bruto, nova revisão sem sobrescrever, exportação/importação ZIP e CSV, STAT antigo sem extremos e interno sem volts inventados |
| Firmware | `.ino` completo compilado por g++ com periféricos falsos; Python real lê HELLO/CFG/STAT/CAP/ganho pelo mesmo parser v4 |
| Serial / Qt | PySerial e QThread reais comunicando com o `.ino` no harness através de PTY; interface e estado de conexão exercitados |
| Autoranging lógico | Pilotos, comparação do maior pico, falta de sinal, menor ganho insuficiente, retorno à última faixa segura e lock durante o ensaio |
| Fluxos Qt | Ganho fixo, pilotos/lock, cancelamento preservando captura, bancada e captura rápida; dispositivo físico substituído explicitamente nos testes de interface |
| Interface | Sete áreas renderizadas; 1280×800 e 1024×720; legenda fora da área de dados, rolagem para conteúdo que não cabe |
| Exportação | PNG de curva/todos os pares/matrizes, CSV, ZIP, HTML e PDF; PDF de exemplo de cinco páginas renderizado e conferido visualmente |
| Empacotamento | PyInstaller gerou aplicação independente **Linux**; ela iniciou sem Python externo e importou as 30 curvas reais |

Suíte: **38 testes automatizados**, além da inspeção visual de páginas e esquemas. O arquivo `verificacao_software.txt` registra a execução final. Dados utilizados nos testes de interface sintéticos são marcados como fixtures; não são resultados novos do monitor.

## O que não foi validado aqui

- Compilação pelo núcleo **Arduino-ESP32** real: não havia toolchain Arduino instalado. O harness de periféricos falsos verifica C++ e protocolo, não substitui esse build.
- Gravação no ESP32 e operação com USB/ADC/sensor reais nesta nova versão.
- Soldas, continuidade do adaptador, VREF absoluta, offset e linearidade do MCP3208.
- Estabilidade/banda do MCP6022 com dois BPW34, especialmente oscilação acima da banda amostrada.
- RON/fuga/capacitância das chaves CD4066 a 3,3 V e adequação final de Cf em cada faixa.
- Recuperação/tempo de estabilização após a comutação e autoranging com overshoot real do monitor.
- Executável **Windows**, drivers USB, DPI/telas múltiplas e execução sem Python nesse sistema. O pacote inclui scripts para gerar e testar no Windows, não um `.exe` pronto desta máquina.
- Calibração fotométrica, Delta-PQ, sincronismo físico do estímulo e conformidade VESA/IDMS.

## Ordem de aprovação física

1. ADC: CH0–AGND direto, depois divisor de meia escala; registrar condições padronizadas.
2. MCP6022: seguidores dos dois canais em 25/50/75% do rail, comparados com MCP6002 sem alterar os outros componentes.
3. TIA fixo: patamares, ruído e transições, sem clipping, com estabilidade/banda qualificadas.
4. CD4066 isolado: cada chave ON/OFF e medição inicial de RON sob carga conhecida.
5. TIA com faixas manuais: ganho, offset escuro, banda e ruído por faixa; determinar espera real de comutação.
6. Pilotos automáticos e margem dos picos; só depois ensaio completo em ganho fixado.
7. Build e ensaio de aceitação no Windows.

Não publicar melhoria de um componente baseada apenas na troca de um número ou na aparência de um gráfico. Condições ausentes ficam ausentes; resultados inválidos permanecem no histórico para diagnóstico.
