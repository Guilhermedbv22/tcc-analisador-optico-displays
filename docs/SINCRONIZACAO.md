# Usar o mesmo projeto no PC e no notebook

Repositório: https://github.com/Guilhermedbv22/tcc-analisador-optico-displays

Cada computador deve ter sua própria cópia Git, na branch `main`. O GitHub funciona como ponto de troca. Salvar um arquivo não o envia automaticamente.

## Pelo GitHub Desktop

1. No notebook, use **File > Add local repository** e selecione `C:\Users\Admin\Documents\TCC`.
2. No PC, adicione a pasta que já está ligada a esse repositório. Se ainda não houver uma cópia Git, use **File > Clone repository > URL**, informe o endereço acima e escolha uma pasta vazia. Preserve os arquivos antigos até conferir se tudo foi incorporado.
3. Antes de trabalhar, clique em **Fetch origin** e, se aparecer, **Pull origin**.
4. Ao terminar, revise os arquivos em **Changes**, escreva uma mensagem, clique em **Commit to main** e depois em **Push origin**.
5. No outro computador, faça **Fetch origin / Pull origin** antes de continuar.

Se existirem alterações locais pendentes, registre-as antes de tentar integrar alterações remotas. Se os dois computadores alterarem a mesma parte de um arquivo, será necessário resolver o conflito, preservando o conteúdo desejado. Não use push forçado para resolver isso.

Documentação: https://docs.github.com/en/desktop/working-with-your-remote-repository-on-github-or-github-enterprise/syncing-your-branch-in-github-desktop

## Pelo terminal

Na pasta do projeto, antes de trabalhar:

```powershell
git status
git pull --ff-only
```

Ao terminar:

```powershell
git status
git add .
git diff --cached --stat
git diff --cached
git commit -m "Descrever as alterações"
git push
```

Revise os arquivos selecionados antes do commit. Se `pull --ff-only` informar que os históricos divergiram, pare e resolva a integração; esse comando não sobrescreve alterações para forçar igualdade.

## O que fica igual

Os arquivos versionados ficam iguais quando os dois computadores estão no mesmo commit e sem alterações locais. Isso inclui código, documentação e resultados enviados. `tcc_config.json`, `.venv/`, `build/`, `dist/` e `.local/` são locais e ficam fora da sincronização. Porta COM e configuração do monitor podem ser diferentes em cada máquina. O perfil recebido do notebook está preservado em `configs/notebook.example.json`.

O Git não espelha a pasta inteira em tempo real. Use uma cópia Git independente em cada computador e a rotina acima para este projeto. Não sincronize a pasta `.git` por serviços de espelhamento de arquivos.

## Integração do notebook em 06/09/2026

- `analisador.py` e `medidor/medidor.ino` eram iguais aos do GitHub.
- `refreshRate.py` e `ruido.py` tinham o mesmo conteúdo dos arquivos em `legado/`, desconsiderando finais de linha; foram consolidados nesses caminhos.
- A versão diferente de `medidor.py` foi preservada em `legado/notebook/medidor.py`, sem substituir a versão anterior em `legado/medidor.py`.
- `tela_branca.py` foi arquivado em `legado/tela_branca.py`. Apesar do nome, seu código original mostra uma tela preta; foi preservado sem alteração.
- As capturas de ruído do notebook estão em `dados/ruido/notebook/`, separadas das capturas já existentes.
- O ensaio `resultados/NOTEBOOK_20260831_162903/` foi incorporado integralmente.
- Uma cópia dos 13 arquivos originais do notebook foi guardada localmente em `.local/backup-notebook-20260906/`, fora do GitHub.

Esta integração organiza e preserva os arquivos. Não altera nem valida a lógica de medição com o hardware.
