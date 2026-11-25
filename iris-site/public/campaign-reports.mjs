export function sameDataset(a,b){
 const x=a.conditions||{},y=b.conditions||{};
 return !!x.campaign_dataset && ['campaign_id','campaign_step','campaign_session','campaign_dataset'].every(k=>x[k]===y[k]);
}
function metric(rows,key){const v=rows.map(r=>r[key]).filter(v=>Number.isFinite(v)).sort((a,b)=>a-b),n=v.length;
 return n?{mean:v.reduce((a,b)=>a+b,0)/n,min:v[0],max:v[n-1],median:n%2?v[(n-1)/2]:(v[n/2-1]+v[n/2])/2}:null;
}
export function combineParts(base,reports){
 const parts=new Map();
 for(const r of [base,...reports])if(sameDataset(base,r)){
  const n=r.conditions.report_part;
  if(parts.has(n)&&parts.get(n).id!==r.id)throw new Error('Há partes conflitantes. Abra uma revisão individual.');
  parts.set(n,r);
 }
 const total=base.conditions.report_parts;
 if(!Number.isInteger(total)||total<1||parts.size!==total||Array.from({length:total},(_,i)=>i+1).some(i=>!parts.has(i)))throw new Error('Ainda faltam partes deste ensaio no site. Envie as partes restantes pelo programa.');
 const ordered=[...parts].sort((a,b)=>a[0]-b[0]).map(([,r])=>r);
 if(ordered.some(r=>r.simulation!==base.simulation||r.conditions.report_parts!==total||r.monitor.model!==base.monitor.model||r.monitor.refresh_hz!==base.monitor.refresh_hz||r.monitor.overdrive!==base.monitor.overdrive))throw new Error('As condições das partes divergem.');
 const results=ordered.flatMap(r=>r.results),valid=results.filter(r=>r.valid),frame_ms=1000/base.monitor.refresh_hz;
 const keys=results.map(r=>`${r.origin}/${r.destination}/${r.repetition}`);
 if(new Set(keys).size!==keys.length)throw new Error('Há capturas duplicadas entre as partes.');
 return {...base,title:base.title.replace(/ · parte \d+\/\d+$/,''),combined:total,results,
  summary:{valid:valid.length,total:results.length,g2g_ms:metric(valid,'g2g_ms'),overshoot_pct:metric(valid,'overshoot_pct'),acomodacao_ms:metric(valid,'acomodacao_ms'),frame_ms,within_frame:valid.filter(r=>r.g2g_ms<=frame_ms).length}};
}
