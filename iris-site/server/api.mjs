import { createHash, timingSafeEqual } from 'node:crypto';
import { InputError, MAX_BYTES, validateReport, reportId, card, summary } from './schema.mjs';
const headers={'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store',
  'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Content-Type, X-Iris-Delete-Token, Authorization',
  'Access-Control-Allow-Methods':'GET, POST, DELETE, OPTIONS','X-Content-Type-Options':'nosniff'};
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers});
const digest=token=>createHash('sha256').update(token).digest('hex');
const same=(a,b)=>typeof a==='string'&&typeof b==='string'&&a.length===b.length&&timingSafeEqual(Buffer.from(a),Buffer.from(b));
const idOK=id=>/^[a-f0-9]{32}$/.test(id||'');
async function readBody(request) {
  if(!request.headers.get('content-type')?.startsWith('application/json')) throw new InputError('Envie o pacote no formato JSON.',415);
  if(Number(request.headers.get('content-length'))>MAX_BYTES) throw new InputError('O limite do pacote é 4 MB.',413);
  const reader=request.body?.getReader();
  if(!reader) throw new InputError('Relatório vazio.');
  const chunks=[]; let length=0;
  for(;;) {const {done,value}=await reader.read();if(done) break;length+=value.length;
    if(length>MAX_BYTES) {await reader.cancel();throw new InputError('O limite do pacote é 4 MB.',413);}chunks.push(value);}
  try {return JSON.parse(Buffer.concat(chunks).toString('utf8'));} catch {throw new InputError('Arquivo JSON inválido.');}
}
export function createAPI(storeFactory,{adminToken=''}={}) {
  return async request=>{
    try {
      if(request.method==='OPTIONS') return new Response(null,{status:204,headers});
      const url=new URL(request.url), path=url.pathname;
      if(path==='/api/health') return json({service:'iris-reports',schema:'iris-report/1',max_bytes:MAX_BYTES});
      const store=await storeFactory();
      if(path==='/api/publish' && request.method==='POST') {
        const token=request.headers.get('x-iris-delete-token')||'';
        if(!/^[A-Za-z0-9_-]{32,128}$/.test(token)) throw new InputError('Chave de remoção ausente. Atualize o Íris Desktop ou recarregue o site.');
        const report=validateReport(await readBody(request));
        report.id=reportId(report);report.published_at=new Date().toISOString();report.summary=summary(report);
        const key='reports/'+report.id;
        const metadata={...card(report),delete_hash:digest(token)};
        const {modified}=await store.setJSON(key,report,{metadata,onlyIfNew:true});
        const saved=modified?metadata:await store.getMetadata(key);
        return json({id:report.id,url:url.origin+'/?relatorio='+report.id,
          duplicate:!modified,can_delete:same(saved?.metadata?.delete_hash||saved?.delete_hash,digest(token))},modified?201:200);
      }
      if(path==='/api/reports' && request.method==='GET') {
        const offset=Math.max(0,Number.parseInt(url.searchParams.get('offset')||'0')||0);
        const limit=Math.min(100,Math.max(1,Number.parseInt(url.searchParams.get('limit')||'100')||100));
        const {blobs}=await store.list({prefix:'reports/'});
        const cards=[];
        for(let i=0;i<blobs.length;i+=24) {
          const batch=await Promise.all(blobs.slice(i,i+24).map(b=>store.getMetadata(b.key)));
          for(const m of batch) {
            const data=m?.metadata||m;
            if(data?.id) {const {delete_hash,...safe}=data;cards.push(safe);}
          }
        }
        cards.sort((a,b)=>b.published_at.localeCompare(a.published_at));
        return json({reports:cards.slice(offset,offset+limit),total:cards.length,next_offset:offset+limit<cards.length?offset+limit:null});
      }
      const match=path.match(/^\/api\/reports\/([a-f0-9]{32})(?:\/(asset))?$/);
      if(match && idOK(match[1])) {
        const key='reports/'+match[1];
        if(request.method==='DELETE'&&!match[2]) {
          const metadata=await store.getMetadata(key);
          if(!metadata) throw new InputError('Relatório não encontrado.',404);
          const token=request.headers.get('x-iris-delete-token')||'';
          const admin=request.headers.get('authorization')?.replace(/^Bearer /,'')||'';
          if(!(same((metadata.metadata||metadata).delete_hash,digest(token))||(adminToken&&same(admin,adminToken)))) throw new InputError('A chave de remoção não corresponde a este relatório.',403);
          await store.delete(key); return json({deleted:true});
        }
        if(request.method==='GET') {
          const report=await store.get(key,{type:'json'});
          if(!report) throw new InputError('Relatório não encontrado.',404);
          if(match[2]) {
            const file=url.searchParams.get('file');
            if(!['relatorio.pdf','transicoes.png','matrizes.png'].includes(file)||!report.assets[file]) throw new InputError('Anexo não encontrado.',404);
            return new Response(Buffer.from(report.assets[file],'base64'),{headers:{...headers,
              'Content-Type':file.endsWith('.pdf')?'application/pdf':'image/png',
              'Content-Disposition':`attachment; filename="iris-${report.id}-${file}"`,
              'Content-Security-Policy':"sandbox; default-src 'none'"}});
          }
          return json(report);
        }
      }
      throw new InputError('Rota não encontrada.',404);
    } catch(error) {
      if(error instanceof InputError) return json({error:error.message},error.status);
      console.error('Íris API:',error.message);
      return json({error:'O armazenamento de relatórios está indisponível. Confira se as funções e o Netlify Blobs foram publicados no projeto.'},503);
    }
  };
}
