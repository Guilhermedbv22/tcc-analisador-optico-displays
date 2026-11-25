# Arquitetura e continuidade do projeto

## Base existente, preservada

| Origem disponível | Integração |
|---|---|
| CIA v2 `nucleo.py` (4.0.2) | Copiado integralmente; cruzamentos, persistência, SNR, acomodação, estatísticas e espectro |
| CIA v2 `protocolo.py` | Copiado integralmente; CRC32, registros de 8 bytes e validação |
| CIA v2 `medidor.ino` (4.0.1) | Evolução para 4.1.0; aquisição e formato CAP mantidos; ganho e STAT ampliados |
| `ensaio_iris.py` / `analisador.py` / comparador CIA | Fluxo de matriz, repetições, estímulo após ARMED, referências e metadados reorganizados em Qt |
| Íris — voltímetro MCP3208 | HELLO/CFG/STAT, /4096, CH0–CH7, atualização DC, seguidor e exportação incorporados |
| Sessões/CSV originais | Importador mantém identificação original, resultados anteriores e metadados; não infere montagem pelo nome |
| Guia R4.1 | Base da pinagem e rede de realimentação do CD4066 |

Os módulos antigos de Tk/Pygame não são executados por trás de uma tela decorativa. A GUI Qt chama o protocolo e o núcleo reais por módulos próprios. Hashes de origem em `PROVENIENCIA.json`. Este trabalho não importou screenshots como se fossem aquisições.

## Módulos

```text
iris_desktop/
  __main__.py        inicialização e pasta de dados
  config.py          contrato de ensaio e equivalência de condições
  core/nucleo.py     análise existente sem alterações
  core/protocolo.py  comunicação existente sem alterações
  device.py          proprietário da porta serial em QThread
  acquisition.py     sequência, estímulo Qt, pilotos e salvamento
  analysis.py        diagnóstico adicional e interpretação
  storage.py         SQLite, arquivos brutos, hashes e revisões
  importers.py       ensaios CIA/v4, CSV voltímetro e ZIP nativo
  exports.py         CSV, gráficos, sessão ZIP, HTML e PDF
  ui/               navegação, medição, análise, comparação e bancada
```

Widgets pertencem à thread principal. `DeviceClient` envia jobs a uma fila e `Worker` mantém uma única porta aberta. Sinais Qt devolvem resultados e ARMED; a troca de cinza é solicitada no evento principal, sem acesso a widgets na thread serial. Aquisição em RAM no ESP32 impede que atualização gráfica seja usada como relógio de amostragem.

Uma captura em andamento não é truncada ao clicar Encerrar: recebe e salva o pacote antes de encerrar. Fechar a janela aguarda esse encerramento. Falha de protocolo desconecta a porta; o próximo ensaio precisa reconectar. O firmware não é regravado para alternar bancada/monitor.

## Persistência

```text
IrisDesktop/
  iris.sqlite3
  sessions/<id>/session.json
  sessions/<id>/raw/<uuid>.npz
  sessions/<id>/raw/<uuid>.json
  sessions/<id>/raw/<uuid>.wire    quando houve recebimento binário original
  sessions/<id>/falha_<uuid>.wire quando houver pacote parcial
  erros.log
```

NPZ contém timestamps, códigos originais e duração de leitura; carregamento sem pickle. O índice guarda SHA-256. O JSON lateral contém os metadados recebidos e tarefa; o banco é a fonte do índice. O dado bruto é salvo **antes** de calcular resultados. A análise tem tabela de revisões append-only; reanálise adiciona e não sobrescreve. Capturas em andamento ou inválidas não são removidas.

Tabelas: `sessions`, `captures`, `analyses`, `bench`, `events`, `settings`, `schema_info`. Conexões SQLite são curtas, com transação e WAL; não se compartilha conexão entre threads. Não se faz migração destrutiva de banco desconhecido. ZIP de sessão inclui amostras, metadados, hashes, revisões e eventos; importa em uma nova identidade.

Em STAT antigo, só existe a média de 64 conversões, não as 64 amostras individuais. No firmware novo 4.1.0, códigos/timestamps/durações das 64 conversões também vêm no JSON e ficam preservados no payload SQLite/CSV/ZIP. O dado que não existe no firmware antigo não é inventado. A captura rápida usa CAP para amostras contíguas a kS/s.

## Abrir os dados antigos

Histórico → Importar ZIP/JSON/CSV ou pasta antiga. São reconhecidos `ensaio.json` do CIA, `sessao.json` do analisador v4 e CSV do voltímetro. O importador mantém os resultados antigos como revisões, depois executa o núcleo atual. Se faltar CSV bruto, registra importação incompleta. Um `.sqlite` antigo isolado não contém a aquisição; é preciso a pasta original com seus arquivos.

Sessões marcadas SIMULAÇÃO continuam assim; duplicatas de um mesmo manifesto CIA são ignoradas por hash. Não se deduz ADC, operacional ou tensão a partir de nomes como `1.png`. Condições faltantes permanecem ausentes e são exibidas na comparação.

## Expansão

Para outro firmware, mantenha o `Captura` e crie um transporte/adaptador com capacidade anunciada. Para outro método científico, adicione versão e resultados em `analyses`, preservando a anterior. Para autoranging por transição, será necessário qualificar cada faixa e aplicar pilotos/lock por par; esta versão utiliza uma faixa por ensaio para reduzir mudanças na cadeia durante a comparação.

Referências de implementação: [QThread Qt](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html), [PyQtGraph](https://pyqtgraph.readthedocs.io/), [SQLite](https://www.sqlite.org/docs.html). Sem serviços de rede em tempo de execução.
