# Como salvar novas versões

Execute os comandos na pasta do TCC. O Git registra alterações quando você cria um commit; o envio ao GitHub acontece com `push`.

```powershell
git status
git diff
git add analisador.py medidor/medidor.ino
git commit -m "Descrever o que mudou e por que"
git push
```

Inclua no `git add` os demais arquivos que deseja salvar, como documentação e resultados selecionados. Confira a seleção com `git diff --cached` antes do commit. Configurações locais, ambientes e executáveis estão no `.gitignore`.

Para consultar o histórico:

```powershell
git log --oneline
git log --follow -- medidor/medidor.ino
```

Para trabalhar em uma alteração separada:

```powershell
git switch -c melhoria-captura
```

O GitHub não recebe mudanças automaticamente ao salvar um arquivo. Use commits com mensagens claras e envie-os ao final de cada etapa do trabalho.
