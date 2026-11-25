import {createHash} from 'node:crypto';
import {createReadStream} from 'node:fs';
import {copyFile, mkdir, readFile, rename, stat, writeFile} from 'node:fs/promises';
import {basename, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const argv=process.argv.slice(2);
if(argv.length<1 || argv.length>2) {
  console.error('Uso: node scripts/stage-downloads.mjs CAMINHO_DIST_WINDOWS [ZIP_FONTE]');
  process.exit(2);
}
const input=resolve(argv[0]);
const manifest=JSON.parse(await readFile(join(input,'releases.json'),'utf8'));
const version=manifest.version;
if(!/^\d+\.\d+\.\d+$/.test(version))throw new Error('Versão de distribuição inválida.');
const names={
  installer:`IrisDesktop-Setup-${version}-x64.exe`,
  portable:`IrisDesktop-Portable-${version}-x64.zip`,
  source:`Iris_Desktop_${version}_Fonte.zip`,
};
const output=fileURLToPath(new URL('../public/downloads/',import.meta.url));
await mkdir(output,{recursive:true});

async function digest(path){
  const hash=createHash('sha256');
  for await(const chunk of createReadStream(path))hash.update(chunk);
  return hash.digest('hex');
}

const items=[];
for(const type of ['installer','portable']){
  const item=manifest.files?.[type];
  if(!item)continue;
  if(item.name!==names[type])throw new Error('Nome incompatível: '+type);
  items.push({type,source:join(input,item.name),name:item.name,expected:item.sha256});
}
if(argv[1]){
  const source=resolve(argv[1]);
  if(basename(source)!==names.source)throw new Error('O nome do ZIP do fonte deve ser '+names.source);
  items.push({type:'source',source,name:names.source});
}
if(!items.length)throw new Error('Nenhum arquivo de distribuição disponível.');

const files={};
for(const item of items){
  const sha256=await digest(item.source);
  if(item.expected && sha256!==item.expected)throw new Error('SHA-256 divergente: '+item.name);
  const bytes=(await stat(item.source)).size;
  if(bytes<1)throw new Error('Arquivo vazio: '+item.name);
  files[item.type]={name:item.name,sha256,bytes};
}
for(const item of items)await copyFile(item.source,join(output,item.name));
const temp=join(output,'releases.json.tmp');
await writeFile(temp,JSON.stringify({version,files},null,2)+'\n');
await rename(temp,join(output,'releases.json'));
console.log('Arquivos disponíveis para publicação em',output);
