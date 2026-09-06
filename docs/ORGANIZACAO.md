# Organização realizada em 06/09/2026

| Local anterior | Local atual |
|---|---|
| `analisador.py` | Mantido na raiz |
| `medidor/medidor.ino` | Mantido; a pasta continua com o nome do sketch Arduino |
| `analisador.spec` | Mantido na raiz para preservar o caminho do script |
| `medidor.py`, `ruido.py`, `refreshRate.py` | `legado/` |
| `Código Medição de Ms.txt` | `legado/` |
| `dados_ruido.csv`, `diagnostico_ruido.csv` | `dados/ruido/` |
| `GPT/` | `docs/auditorias/chatgpt/` |
| CSVs em `dist/` | Copiados para `resultados/historicos/`; originais mantidos |
| `resultados/` | Mantido, inclusive o ensaio completo existente |

O material da auditoria mantém a estrutura interna original. A cópia adicional do relatório foi conservada para não descartar material recebido. Os snapshots de código em `entradas/` são referências históricas, não os arquivos a editar no desenvolvimento atual.

`build/`, `dist/` e a configuração pessoal `tcc_config.json` continuam no computador, mas não são enviados ao GitHub. `.local/` fica reservado a verificações e saídas locais. Dados de ensaios não foram ignorados globalmente: podem ser versionados após revisão do tamanho e do conteúdo.

Não foi atribuída uma licença de reutilização nesta organização. Essa escolha fica com o autor.
