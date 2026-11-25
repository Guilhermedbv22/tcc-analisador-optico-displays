import { createHash } from 'node:crypto';
export const MAX_BYTES = 4_000_000;
export class InputError extends Error { constructor(message, status=400) { super(message); this.status=status; } }
const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
function text(v, n=500, fallback='') { if(v == null) return fallback; if(typeof v !== 'string' || v.length>n) throw new InputError('Campo de texto inválido ou muito longo.'); return v.trim(); }
function num(v, min=0, max=1e9, nullable=true) { if(v==null && nullable) return null; if(typeof v!=='number'||!Number.isFinite(v)||v<min||v>max) throw new InputError('Valor numérico fora da faixa permitida.'); return v; }
function scalarMap(value, allowed=null) {
  if(!object(value)) return {};
  const out={};
  for(const key of (allowed || Object.keys(value).slice(0,40))) {
    if(['__proto__','constructor','prototype'].includes(key)) continue;
    const v=value[key];
    if(v==null) { if(key in value) out[key]=null; }
    else if(typeof v==='string') out[key]=text(v,600);
    else if(typeof v==='boolean') out[key]=v;
    else if(typeof v==='number') out[key]=num(v,-1e9,1e9);
  }
  return out;
}
const conditionKeys='resolution brightness contrast hdr vrr warmup_min sensor_position ambient amplifier adc channel vref supply_v attenuation_k rf_kohm cf_pf assembly gain_mode rate_sps window_ms pre_ms hold_ms spi_hz levels repetitions patch_percent patch_pixels patch_area_percent background_rgb static_references monitor_settings capacitors campaign_id campaign_step campaign_session campaign_dataset report_part report_parts'.split(' ');
export function validateReport(input) {
  if(!object(input)||input.schema!=='iris-report/1') throw new InputError('Selecione um arquivo relatorio.iris.json gerado pelo Íris Desktop atualizado.');
  if(!object(input.monitor)||typeof input.simulation!=='boolean') throw new InputError('Identificação do monitor ou da simulação ausente.');
  const monitor={model:text(input.monitor.model,160),overdrive:text(input.monitor.overdrive,80),refresh_hz:num(input.monitor.refresh_hz,1,2000,false)};
  if(!monitor.model || !monitor.overdrive) throw new InputError('Informe o modelo exato e o overdrive no programa.');
  const measured_at=text(input.measured_at,60);
  if(!measured_at || !Number.isFinite(Date.parse(measured_at))) throw new InputError('Data de medição inválida.');
  if(!Array.isArray(input.results)||input.results.length<1||input.results.length>512) throw new InputError('O relatório deve conter de 1 a 512 capturas.');
  let pointCount=0;
  const results=input.results.map(r=>{
    if(!object(r)||typeof r.valid!=='boolean') throw new InputError('Resultado sem validade declarada.');
    const origin=num(r.origin,0,255,false), destination=num(r.destination,0,255,false);
    if(!Number.isInteger(origin)||!Number.isInteger(destination)||origin===destination) throw new InputError('Transição RGB inválida.');
    const repetition=num(r.repetition,1,10000,false);
    if(!Number.isInteger(repetition)) throw new InputError('Repetição inválida.');
    let curve=null;
    if(r.curve) {
      if(!object(r.curve)||!['%','ADC'].includes(r.curve.unit)||!Array.isArray(r.curve.points)||r.curve.points.length<2||r.curve.points.length>610) throw new InputError('Curva inválida.');
      let last=-1;
      const points=r.curve.points.map(p=>{
        if(!Array.isArray(p)||p.length!==3) throw new InputError('Ponto de curva inválido.');
        const t=num(p[0],0,120000,false);
        if(t<last) throw new InputError('Curva fora da ordem temporal.'); last=t;
        return [t,num(p[1],-1e7,1e7,false),num(p[2],-1e7,1e7,false)];
      });
      pointCount+=points.length;
      const original_samples=num(r.curve.original_samples,points.length,1e8,false);
      curve={unit:r.curve.unit,original_samples,reduced:original_samples>points.length,points};
    }
    const valid=r.valid;
    const g2g_ms=valid?num(r.g2g_ms,0,120000,false):null;
    const overshoot_pct=valid?num(r.overshoot_pct,0,1e7,false):null;
    return {origin,destination,repetition,valid,g2g_ms,overshoot_pct,
      acomodacao_ms:valid?num(r.acomodacao_ms,0,120000):null,
      t10_ms:num(r.t10_ms,0,120000), t90_ms:num(r.t90_ms,0,120000),
      status:text(r.status,80),peak_name:destination>origin?'Overshoot':'Undershoot',
      meaning:text(r.meaning,1500), reasons:Array.isArray(r.reasons)?r.reasons.slice(0,30).map(x=>text(x,160)):[],
      criteria:scalarMap(r.criteria),analysis_version:text(r.analysis_version,120),
      sha256:/^[a-f0-9]{64}$/.test(r.sha256)?r.sha256:'',curve};
  });
  if(pointCount>150000) throw new InputError('Há pontos demais no relatório. Divida o ensaio em sessões menores.');
  const assets={};
  for(const [name,signature] of [['relatorio.pdf','25504446'],['transicoes.png','89504e47'],['matrizes.png','89504e47']]) {
    const encoded=input.assets?.[name];
    if(encoded==null) continue;
    if(typeof encoded!=='string'||encoded.length>2_150_000||encoded.length%4!==0||!/^[A-Za-z0-9+/]*={0,2}$/.test(encoded)) throw new InputError('Anexo inválido ou muito grande.');
    const data=Buffer.from(encoded,'base64');
    if(data.subarray(0,4).toString('hex')!==signature) throw new InputError('O tipo do anexo não corresponde ao arquivo.');
    assets[name]=encoded;
  }
  return {schema:'iris-report/1',title:text(input.title,180)||monitor.model,measured_at,
    simulation:input.simulation,operator:text(input.operator,120),conclusion:text(input.conclusion,4000),monitor,
    conditions:scalarMap(input.conditions,conditionKeys),
    method:{version:text(input.method?.version,120),g2g:'10–90% da amplitude da transição',
      peak:'Excesso relativo à amplitude; overshoot nas subidas e undershoot nas descidas',
      scope:'Resposta óptica temporal; não mede input lag nem constitui certificação VESA'},results,assets};
}
function metric(rows,key) {
  const v=rows.map(r=>r[key]).filter(v=>v!=null).sort((a,b)=>a-b);
  if(!v.length) return null;
  const n=v.length;
  return {mean:v.reduce((a,b)=>a+b,0)/n,min:v[0],max:v[n-1],median:n%2?v[(n-1)/2]:(v[n/2-1]+v[n/2])/2};
}
export function summary(report) {
  const valid=report.results.filter(r=>r.valid), frame_ms=1000/report.monitor.refresh_hz;
  return {valid:valid.length,total:report.results.length,g2g_ms:metric(valid,'g2g_ms'),
    overshoot_pct:metric(valid,'overshoot_pct'),acomodacao_ms:metric(valid,'acomodacao_ms'),frame_ms,
    within_frame:valid.filter(r=>r.g2g_ms<=frame_ms).length};
}
const canonical = value => Array.isArray(value)?value.map(canonical):object(value)?Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])])):value;
export function reportId(report) {
  const {assets,summary,published_at,id,...content}=report;
  return createHash('sha256').update(JSON.stringify(canonical(content))).digest('hex').slice(0,32);
}
export function card(report) {
  // Metadados do Netlify Blobs têm limite de 2 KB; o relatório guarda o texto completo.
  const clip=(v,max)=>{let out='';for(const c of String(v||'')){if(Buffer.byteLength(out+c)>max)break;out+=c;}return out;};
  const conditions={};
  for(const k of ['adc','resolution','brightness','contrast','hdr','vrr','rate_sps','campaign_id','campaign_step','campaign_session','campaign_dataset','report_part','report_parts']) {
    const v=report.conditions?.[k];if(v!=null)conditions[k]=typeof v==='string'?clip(v,48):v;
  }
  return {id:report.id,title:clip(report.title,120),monitor:{model:clip(report.monitor.model,180),overdrive:clip(report.monitor.overdrive,80),refresh_hz:report.monitor.refresh_hz},simulation:report.simulation,
    measured_at:report.measured_at,published_at:report.published_at,operator:clip(report.operator,80),
    conditions,method:{version:clip(report.method?.version,60)},summary:report.summary||summary(report),
    has_pdf:!!report.assets?.['relatorio.pdf']};
}
