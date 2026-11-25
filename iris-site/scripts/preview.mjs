// Servidor local de desenvolvimento. Produção usa exclusivamente Netlify Blobs.
import http from 'node:http';
import {readFile,writeFile,mkdir,readdir,unlink} from 'node:fs/promises';
import {resolve,extname} from 'node:path';
import {createAPI} from '../server/api.mjs';
const root=resolve('.preview-data');await mkdir(root,{recursive:true});
class LocalStore {
  path(key){if(!/^reports\/[a-f0-9]{32}$/.test(key))throw new Error('Chave inválida');return resolve(root,key.split('/')[1]+'.json');}
  async setJSON(key,data,{metadata,onlyIfNew}){try{await writeFile(this.path(key),JSON.stringify({data,metadata}),{flag:onlyIfNew?'wx':'w'});return {modified:true};}catch(e){if(e.code==='EEXIST')return {modified:false};throw e;}}
  async record(key){try{return JSON.parse(await readFile(this.path(key),'utf8'));}catch(e){if(e.code==='ENOENT')return null;throw e;}}
  async get(key){return (await this.record(key))?.data??null;}
  async getMetadata(key){const r=await this.record(key);return r?{metadata:r.metadata,etag:'local'}:null;}
  async list(){return {blobs:(await readdir(root)).filter(n=>/^[a-f0-9]{32}\.json$/.test(n)).map(n=>({key:'reports/'+n.slice(0,-5)}))};}
  async delete(key){await unlink(this.path(key));}
}
const store=new LocalStore(),api=createAPI(()=>store);
const types={'.mjs':'application/javascript; charset=utf-8','.exe':'application/octet-stream','.zip':'application/zip','.html':'text/html; charset=utf-8','.js':'application/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp'};
const server=http.createServer(async(req,res)=>{
  try{
    const url=new URL(req.url,'http://'+req.headers.host);
    if(url.pathname.startsWith('/api/')){
      const body=['GET','HEAD'].includes(req.method)?undefined:req;
      const request=new Request(url,{method:req.method,headers:req.headers,body,...(body?{duplex:'half'}:{})});
      const response=await api(request);res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));return;
    }
    const file=resolve('public','.'+decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname));
    if(!file.startsWith(resolve('public')+'/')){res.writeHead(403).end();return;}
    res.writeHead(200,{'Content-Type':types[extname(file)]||'application/octet-stream','Cache-Control':'no-store'});res.end(await readFile(file));
  }catch(e){if(!res.headersSent)res.writeHead(404,{'Content-Type':'text/plain'});res.end('Não encontrado');}
});
const args=process.argv.slice(2),portIndex=args.indexOf('--port');
const port=Number(process.env.PORT||(portIndex>=0?args[portIndex+1]:3000));
server.listen(port,'0.0.0.0',()=>console.log('Íris preview em '+port));
