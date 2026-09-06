# Protótipos e experimentos iniciais

Arquivos preservados sem alterações de lógica. O programa atual é `../analisador.py`, em conjunto com `../medidor/medidor.ino`.

| Arquivo | Finalidade original |
|---|---|
| `medidor.py` | Medição inicial de G2G e overshoot; usa também `win32api` (pacote `pywin32`, específico do Windows) |
| `ruido.py` | Diagnóstico de ruído com cor estática e exportação CSV |
| `refreshRate.py` | Experimento com atualização de tela e V-Sync |
| `Código Medição de Ms.txt` | Firmware inicial de aquisição para ESP32 |

Os scripts têm parâmetros próprios, inclusive porta serial fixa, e podem usar protocolos diferentes do firmware atual. Revise o código antes de executar. CSVs históricos de ruído estão em `../dados/ruido/`.
