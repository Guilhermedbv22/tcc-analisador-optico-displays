# Atualizar o site Íris no Netlify

## Atualizar o projeto existente

1. Extraia o ZIP do site e instale Node.js LTS 22 ou mais recente.
2. Execute `publicar_netlify.bat`. Use a conta Netlify responsável por **tcc-iris** e vincule o projeto existente.
3. Abra [Monitores](https://tcc-iris.netlify.app/) e confira os modelos LG, AOC e HQ. Teste também um link individual que já existia, como o [LG Fast a 180 Hz](https://tcc-iris.netlify.app/?relatorio=96c09eaa0e23c5c014be2f412ebdbed5). No AOC, confirme a consulta do ensaio completo a partir das duas partes.
4. Mantenha o deploy anterior disponível no painel do Netlify. Se precisar reverter, restaure aquele deploy no mesmo projeto.

O pacote inclui `public`, as funções `publish` e `reports`, `netlify.toml` e as dependências. Um envio apenas da pasta `public` deixa a API de fora. O deploy no mesmo projeto usa o mesmo armazenamento Netlify Blobs `iris-reports-v1`. O catálogo agrupa os relatórios em tempo de consulta. IDs, rotas individuais e formato `iris-report/1` continuam válidos. Nenhuma migração ou republicação das medições é necessária.

Forma manual, na pasta do site:

```powershell
npm ci
npm test
npx netlify login
npx netlify link --name tcc-iris
npx netlify deploy --prod --no-build --dir public --functions netlify/functions
```

## Incluir o instalador e o portátil

Gere os binários no Windows usando a pasta do Desktop. O arquivo `releases.json` será criado junto aos binários. Em seguida, no site:

```powershell
node scripts/stage-downloads.mjs "C:\caminho\desktop\dist-windows"
```

Passe também o caminho de `Iris_Desktop_1.4.0_Fonte.zip` como segundo argumento para oferecer o código-fonte. O script confirma os hashes dos binários e copia os arquivos aprovados para `public/downloads`. Revise os arquivos e publique o site de novo. A página de download só exibe botões para itens no manifesto que estão disponíveis no servidor. Arquivos grandes podem ser distribuídos separadamente por releases se o plano de hospedagem limitar o envio.

## Verificação local

`npm test` verifica o contrato da API, o agrupamento e a reunião das partes. Execute `npm run dev` para testar em `localhost:3000`. O armazenamento temporário da prévia fica em `.preview-data` fora de `public`.

O catálogo lista medições reais. O site preserva a identificação individual, o acervo inicial existente e a consulta direta aos links antigos. As métricas da página do monitor usam todas as partes disponíveis. O relatório completo só reúne partes com a mesma sessão e revisão, e identifica duplicações ou partes ausentes. O pacote privado da campanha e as chaves de remoção não pertencem à pasta pública.
