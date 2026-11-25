import {buildCatalog,modelIdentity,matchesSession,sessionHref,sessionSummary} from './catalog.mjs';
import {combineParts,sameDataset} from './campaign-reports.mjs';
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,n=2)=>v==null||!Number.isFinite(v)?'—':v.toLocaleString('pt-BR',{maximumFractionDigits:n,minimumFractionDigits:n});
const date=v=>Number.isFinite(Date.parse(v))?new Date(v).toLocaleDateString('pt-BR'):'Data não informada';
const state={cards:[],seeds:new Map(),selected:new Set(),next:null,report:null,upload:null,token:null,receipt:null,sequence:0, catalogRequest:0, loading:false, model:null};
const conditionNames={resolution:'Resolução',brightness:'Brilho',contrast:'Contraste',hdr:'HDR',vrr:'VRR / Adaptive Sync',warmup_min:'Aquecimento (min)',sensor_position:'Posição do sensor',ambient:'Ambiente',amplifier:'Amplificador',adc:'ADC',channel:'Canal',vref:'Referência do ADC (V)',supply_v:'Alimentação (V)',attenuation_k:'Atenuação física',rf_kohm:'Resistência de realimentação (kΩ)',cf_pf:'Capacitância de realimentação (pF)',assembly:'Montagem',gain_mode:'Modo de ganho',rate_sps:'Amostragem (S/s)',window_ms:'Janela (ms)',pre_ms:'Pré-estímulo (ms)',hold_ms:'Espera inicial (ms)',spi_hz:'SPI (Hz)',levels:'Níveis de cinza',repetitions:'Repetições por par',patch_percent:'Área do estímulo (%)',patch_pixels:'Lado do estímulo (px)',background_rgb:'Cinza de fundo',static_references:'Referências estáticas',patch_area_percent:'Área do quadrado central (%)',monitor_settings:'Ajustes do monitor',capacitors:'Capacitores instalados',campaign_id:'Campanha',campaign_step:'Etapa',campaign_session:'Sessão',campaign_dataset:'Revisão dos resultados',report_part:'Parte do relatório',report_parts:'Total de partes'};
async function api(path,options={}) {
  let response;
  try {response=await fetch(path,{...options,headers:{...options.headers},cache:'no-store'});} catch {throw new Error('Sem conexão com o servidor. Seu arquivo continua disponível para tentar novamente.');}
  const type=response.headers.get('content-type')||'';
  if(!type.includes('application/json')) throw new Error('A API de relatórios ainda não está disponível neste endereço. O site precisa ser publicado com as funções do pacote Netlify.');
  let data;
  try {data=await response.json();} catch {throw new Error('O servidor retornou uma resposta inválida. Tente novamente.');}
  if(!response.ok) throw new Error(data.error||`O servidor recusou a solicitação (HTTP ${response.status}).`);
  return data;
}
function download(name,data,type='application/json') {
  const blob=new Blob([data],{type}),url=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);
}
function assetDownload(report,name) {
  const encoded=report.assets?.[name];if(!encoded)return;
  const data=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
  download(`Iris-${report.id||'relatorio'}-${name}`,data,name.endsWith('.pdf')?'application/pdf':'image/png');
}
function cardFrom(r,seed=false) {
  return {id:r.id,title:r.title,monitor:r.monitor,measured_at:r.measured_at,published_at:r.published_at,
    simulation:r.simulation,summary:r.summary,operator:r.operator,conditions:r.conditions,method:r.method,seed,has_pdf:!!r.assets?.['relatorio.pdf']};
}
function badge(r){return `<span class="badge${r.simulation?' sim':''}">${r.simulation?'Simulação':r.seed?'Acervo inicial Íris':'Comunidade'}</span>`;}
function measure(v,unit,n=2){return `${fmt(v,n)}${v==null?'':` <small>${unit}</small>`}`;}
function catalog() { return buildCatalog(state.cards.filter(report => !report.simulation)); }
function modelHref(key) { return '?monitor=' + encodeURIComponent(key); }

function renderCards() {
  const filters = {query:$('#search').value, hz:$('#hz-filter').value};
  const sort = $('#sort').value;
  const models = catalog().map(model => ({
    ...model, sessions:model.sessions.filter(session => matchesSession(session,filters)),
  })).filter(model => model.sessions.length);
  models.sort((a,b) => {
    if (sort === 'model') return a.name.localeCompare(b.name,'pt-BR');
    if (sort === 'count') return b.sessions.length-a.sessions.length || a.name.localeCompare(b.name,'pt-BR');
    return b.sessions[0].lead.measured_at.localeCompare(a.sessions[0].lead.measured_at);
  });
  const count=models.reduce((n,model)=>n+model.sessions.length,0);
  $('#report-count').textContent=`${models.length} ${models.length===1?'modelo':'modelos'} · ${count} ${count===1?'ensaio':'ensaios'}`;
  $('#empty').hidden=!!models.length || state.loading;
  $('#cards').innerHTML=models.map(model => {
    const hz=[...new Set(model.sessions.map(s=>s.lead.monitor.refresh_hz))].sort((a,b)=>a-b);
    return `<a class="model-row" href="${modelHref(model.key)}"><span class="model-glyph" aria-hidden="true">◈</span><span class="model-name">${model.brand ? `<small>${esc(model.brand)}</small>` : ''}<strong>${esc(model.name)}</strong></span><span class="model-count">${model.sessions.length} ${model.sessions.length===1?'ensaio':'ensaios'}</span><span class="model-hz">${hz.map(h=>fmt(h,0)+' Hz').join(' · ')}</span><span aria-hidden="true">→</span></a>`;
  }).join('');
}

function bindComparison(root) {
  for (const el of root.querySelectorAll('[data-compare]')) el.addEventListener('change', () => {
    if (el.checked && state.selected.size>=3) {
      el.checked=false; $('#model-status').textContent='Selecione até três ensaios.';
      return;
    }
    el.checked ? state.selected.add(el.dataset.compare) : state.selected.delete(el.dataset.compare);
    renderCompareBar();
  });
}

function renderModel(key) {
  const root=$('#monitor-content');
  const model=catalog().find(item=>item.key===key);
  if (!model) {
    root.innerHTML=state.loading ? '<h1>Carregando monitor…</h1>' : '<h1>Monitor indisponível</h1><p>Confira o endereço ou volte ao catálogo.</p>';
    return;
  }
  const previousHz=$('#model-hz')?.value ?? '';
  const previousOd=$('#model-overdrive')?.value ?? '';
  const hz=[...new Set(model.sessions.map(s=>s.lead.monitor.refresh_hz))].sort((a,b)=>a-b);
  const od=[...new Set(model.sessions.map(s=>s.lead.monitor.overdrive))].sort((a,b)=>a.localeCompare(b,'pt-BR'));
  root.innerHTML=`<div class="monitor-heading">${model.brand?`<p class="eyebrow">${esc(model.brand)}</p>`:''}<h1>${esc(model.name)}</h1><p class="lead">${model.sessions.length} ${model.sessions.length===1?'ensaio disponível':'ensaios disponíveis'}</p></div>
  <div class="filters model-filters"><label>Frequência<select id="model-hz"><option value="">Todas</option>${hz.map(v=>`<option value="${v}">${fmt(v,0)} Hz</option>`).join('')}</select></label><label>Overdrive<select id="model-overdrive"><option value="">Todos</option>${od.map(v=>`<option>${esc(v)}</option>`).join('')}</select></label></div>
  <p id="model-status" role="status"></p><div class="session-list" id="session-list"></div>`;
  if(hz.map(String).includes(previousHz)) $('#model-hz').value=previousHz;
  if(od.includes(previousOd)) $('#model-overdrive').value=previousOd;
  function renderSessions(){
    const sessions=model.sessions.filter(s=>matchesSession(s,{hz:$('#model-hz').value,overdrive:$('#model-overdrive').value}));
    const list=$('#session-list');
    list.innerHTML=sessions.map(s=>{
      const r=s.lead, summary=sessionSummary(s);
      const parts=s.size>1?` · ${s.parts.length}/${s.size} partes`:'';
      return `<article class="session-row"><div><a class="session-name" href="${sessionHref(s)}">${esc(r.monitor.overdrive)} · ${fmt(r.monitor.refresh_hz,0)} Hz</a><p>${date(r.measured_at)}${r.conditions?.resolution?' · '+esc(r.conditions.resolution):''} · ${summary.valid}/${summary.total} válidas${parts}</p>${r.title?`<p class="session-title">${esc(r.title.replace(/ · parte \d+\/\d+$/,''))}</p>`:''}</div><div class="session-metric"><small>GtG médio</small><strong>${measure(summary.g2g_ms?.mean,'ms')}</strong></div><div class="session-metric"><small>Excesso médio</small><strong>${measure(summary.overshoot_pct?.mean,'%')}</strong></div><label class="check"><input type="checkbox" data-compare="${s.id}" ${state.selected.has(s.id)?'checked':''}>Comparar</label></article>`;
    }).join('') || '<p>Nenhum ensaio corresponde aos filtros.</p>';
    bindComparison(list);
  }
  for (const id of ['model-hz','model-overdrive']) $('#'+id).addEventListener('change',renderSessions);
  renderSessions();
}
function renderCompareBar(){const count=state.selected.size;$('#compare-bar').hidden=!count;$('#compare-count').textContent=`${count} ${count===1?'ensaio selecionado':'ensaios selecionados'}`;$('#compare-open').disabled=count<2;}
async function loadSeed(){
  try {
    const index=await fetch('data/index.json').then(r=>r.json());
    for(const item of index.reports){state.seeds.set(item.id,item);}
    state.cards=index.reports.map(r=>({...r,seed:true}));renderCards();
    if(index.reports[0]){
      fetch('data/hero.json').then(response=>response.json()).then(({id,monitor,result:r})=>{
        $('#hero-model').textContent=monitor.model;
        $('#hero-settings').textContent=`${fmt(monitor.refresh_hz,0)} Hz · ${monitor.overdrive} · RGB ${r.origin} → ${r.destination}`;
        $('#hero-plot').innerHTML=plot(r,{compact:true});$('#hero-g2g').textContent=fmt(r.g2g_ms)+' ms';$('#hero-peak').textContent=fmt(r.overshoot_pct)+'%';$('#hero-report').href='?relatorio='+id;
      }).catch(()=>{$('#hero-plot').textContent='Abra um relatório para explorar suas curvas.';});
    }
  }catch{$('#hero-plot').textContent='As curvas aparecem após a publicação de um ensaio.';}
}
async function loadRemote() {
  const request=++state.catalogRequest;
  state.loading=true;$('#refresh').disabled=true;
  if (state.model) renderModel(state.model);
  try {
    let offset=0;
    const map=new Map([...state.seeds.values()].map(r=>[r.id,{...r,seed:true}]));
    do {
      const data=await api('/api/reports?limit=100&offset='+offset);
      if(request!==state.catalogRequest)return;
      for (const r of data.reports) map.set(r.id,{...r,seed:state.seeds.has(r.id)});
      offset=data.next_offset;
    } while (offset!=null);
    state.cards=[...map.values()];
    $('#connection-state').textContent='';
  } catch(error) {
    if(request===state.catalogRequest) $('#connection-state').textContent=error.message;
  } finally {
    if(request===state.catalogRequest) {
      state.loading=false;$('#refresh').disabled=false;updateHz();renderCards();
      if(state.model)renderModel(state.model);
    }
  }
}
function updateHz(){const value=$('#hz-filter').value;$('#hz-filter').innerHTML='<option value="">Todas as frequências</option>'+[...new Set(state.cards.map(r=>r.monitor.refresh_hz))].sort((a,b)=>a-b).map(v=>`<option value="${v}">${fmt(v,0)} Hz</option>`).join('');$('#hz-filter').value=value;}
async function getReport(id){
  if(!/^[a-f0-9]{32}$/.test(id))throw new Error('O identificador deste relatório é inválido.');
  if(state.seeds.has(id)){
    const response=await fetch(`data/${id}.json`);if(!response.ok)throw new Error('Relatório do acervo não encontrado.');return response.json();
  }
  return api('/api/reports/'+id);
}
function plot(row,{full=false,raw=true,filtered=true,compact=false}={}){
  if(!row?.curve?.points?.length)return '<p class="muted">Curva indisponível neste relatório.</p>';
  const all=row.curve.points;let points=all;
  if(!full&&row.t10_ms!=null){const lo=Math.max(all[0][0],row.t10_ms-5),hi=Math.min(all.at(-1)[0],Math.max((row.t90_ms??row.t10_ms)+15,row.t10_ms+25));
    points=all.filter(p=>p[0]>=lo&&p[0]<=hi);if(points.length<3)points=all;}
  const w=700,h=compact?290:320,L=58,R=24,T=22,B=46;
  let xmin=points[0][0],xmax=points.at(-1)[0];if(xmax===xmin)xmax=xmin+1;
  const vals=points.flatMap(p=>[p[1],p[2]]),relative=row.curve.unit==='%';
  let ymin=Math.min(...vals,...(relative?[0]:[])),ymax=Math.max(...vals,...(relative?[100]:[]));
  const pad=Math.max(1,(ymax-ymin)*.12);ymin-=pad;ymax+=pad;
  const x=v=>L+(v-xmin)/(xmax-xmin)*(w-L-R),y=v=>T+(ymax-v)/(ymax-ymin)*(h-T-B);
  const path=k=>points.map((p,i)=>(i?'L':'M')+x(p[0]).toFixed(2)+','+y(p[k]).toFixed(2)).join(' ');
  let grid='';for(let i=0;i<=4;i++){const v=ymin+(ymax-ymin)*i/4,py=y(v);grid+=`<line class="grid" x1="${L}" y1="${py}" x2="${w-R}" y2="${py}"/><text x="${L-10}" y="${py+4}" text-anchor="end">${fmt(v,0)}${relative?'%':''}</text>`;}
  for(let i=0;i<=4;i++){const v=xmin+(xmax-xmin)*i/4,px=x(v);grid+=`<line class="grid" x1="${px}" y1="${T}" x2="${px}" y2="${h-B}"/><text x="${px}" y="${h-B+23}" text-anchor="middle">${fmt(v,1)}</text>`;}
  const target=relative?`<line class="target-path" x1="${L}" y1="${y(100)}" x2="${w-R}" y2="${y(100)}"/>`:'';
  const span=row.valid&&row.t10_ms!=null&&row.t90_ms!=null?`<rect x="${Math.max(L,x(row.t10_ms))}" y="${T}" width="${Math.max(0,Math.min(w-R,x(row.t90_ms))-Math.max(L,x(row.t10_ms)))}" height="${h-T-B}" fill="#38bdf8" opacity=".07"/>`:'';
  return `<svg class="plot" viewBox="0 0 ${w} ${h}" role="img" aria-label="Curva da transição RGB ${row.origin} para ${row.destination}; eixo horizontal em milissegundos e vertical em ${relative?'resposta relativa':'códigos ADC'}"><title>RGB ${row.origin} → ${row.destination}</title>${grid}${span}${target}${raw?`<path class="raw-path" d="${path(1)}"/>`:''}${filtered?`<path class="filtered-path" d="${path(2)}"/>`:''}<text x="${w-R}" y="${h-3}" text-anchor="end">tempo desde a primeira amostra (ms)</text></svg>`;
}
function showView(view){for(const name of ['catalog','monitor','detail','upload'])$('#'+name+'-view').hidden=name!==view;for(const link of document.querySelectorAll('nav [data-tab]')){
  const active=link.dataset.tab===(view==='monitor'||view==='detail'?'catalog':view);
  link.classList.toggle('active',active);
  if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
}}
async function route(){
  const sequence=++state.sequence, params=new URLSearchParams(location.search), id=params.get('relatorio');
  state.model=params.get('monitor');
  if(id) {
    showView('detail');$('#detail-content').innerHTML='<div class="panel"><p>Carregando relatório…</p></div>';
    try {
      let report=await getReport(id);
      if(params.get('completo')==='1' && report.conditions?.report_parts>1)report=await completeReport(report);
      if(sequence!==state.sequence)return;
      $('#detail-back').href=modelHref(modelIdentity(report).key);
      $('#detail-back').textContent='← Ensaios do monitor';
      state.report=report;renderDetail(report);
    } catch(error) {
      if(sequence===state.sequence)$('#detail-content').innerHTML=`<div class="panel"><h1>Não foi possível abrir</h1><p class="error">${esc(error.message)}</p><a class="button quiet" href="?relatorio=${encodeURIComponent(id)}">Abrir relatório individual</a></div>`;
    }
  } else if(state.model) {
    showView('monitor');renderModel(state.model);
  } else showView(params.get('aba')==='enviar'?'upload':'catalog');
}
async function completeReport(base){
  const cards=[];let offset=0;
  do{const page=await api('/api/reports?limit=100&offset='+offset);cards.push(...page.reports);offset=page.next_offset;}while(offset!=null);
  const ids=[...new Set(cards.filter(r=>sameDataset(base,r)).map(r=>r.id))];
  const parts=await Promise.all(ids.map(id=>getReport(id)));
  return combineParts(base,parts);
}
function conditionTable(r){return Object.entries(r.conditions||{}).filter(([,v])=>v!==null&&v!=='').map(([k,v])=>`<div><dt>${esc(conditionNames[k]||k)}</dt><dd>${esc(typeof v==='boolean'?(v?'Sim':'Não'):v)}</dd></div>`).join('');}
function renderDetail(r){
  const s=r.summary||{},seed=state.seeds.has(r.id);r.seed=seed;
  $('#detail-content').innerHTML=`<div class="detail-heading"><div>${badge(r)}<h1>${esc(r.monitor.model)}</h1><p>${fmt(r.monitor.refresh_hz,0)} Hz · Overdrive ${esc(r.monitor.overdrive)} · Medido em ${date(r.measured_at)}</p><p>${esc(r.title)}${r.operator?' · '+esc(r.operator):''}</p></div><span class="badge">${esc(r.conditions?.adc||'ADC não informado')}</span></div>
  ${r.conditions?.report_parts>1&&!r.combined?`<p class="notice">Parte ${r.conditions.report_part}/${r.conditions.report_parts} deste ensaio. <a href="?relatorio=${r.id}&completo=1">Reunir todas as partes e ver a matriz completa</a>.</p>`:''}${r.combined?`<p class="notice">Ensaio reunido: ${r.combined} partes · todas as capturas e métricas disponíveis.</p>`:''}${r.simulation?'<p class="notice">SIMULAÇÃO: este ensaio não contém aquisição física de um monitor.</p>':''}
  <div class="metrics"><div class="metric"><small>GtG médio · 10–90%</small><strong>${fmt(s.g2g_ms?.mean)} ms</strong><span>${fmt(s.g2g_ms?.min)} a ${fmt(s.g2g_ms?.max)} ms</span></div><div class="metric"><small>Excesso médio no alvo</small><strong>${fmt(s.overshoot_pct?.mean)}%</strong><span>Maior excesso: ${fmt(s.overshoot_pct?.max)}%</span></div><div class="metric"><small>Capturas válidas</small><strong>${s.valid??0} / ${s.total??0}</strong><span>Resultados inválidos ficam fora das médias</span></div><div class="metric"><small>Intervalo entre quadros</small><strong>${fmt(s.frame_ms)} ms</strong><span>${s.within_frame??0} GtG válidos dentro desse intervalo</span></div></div>

  <div class="detail-actions">${r.assets?.['relatorio.pdf']?'<button class="button primary" id="download-pdf">Baixar PDF completo</button>':''}<button class="button quiet" id="download-json">Pacote do relatório</button><button class="button quiet" id="download-csv">Resultados CSV</button><button class="button quiet" id="copy-url">Copiar link</button></div><p id="detail-message" role="status" class="muted"></p>
  <section class="panel"><h2>Curva da transição</h2><div class="panel-tools"><label>Transição <select id="transition">${r.results.map((v,i)=>`<option value="${i}">RGB ${v.origin} → ${v.destination} · rep. ${v.repetition}${v.valid?'':' · revisar'}</option>`).join('')}</select></label><label class="check"><input id="curve-raw" type="checkbox" checked>Bruto</label><label class="check"><input id="curve-filtered" type="checkbox" checked>Processado</label><label class="check"><input id="curve-full" type="checkbox">Janela completa</label></div><div id="detail-plot" class="detail-plot"></div><div id="transition-metrics" class="transition-info"></div><p id="transition-meaning" class="muted" style="margin-top:18px"></p><p id="curve-info" class="muted" style="margin-top:12px"></p></section>
  <section class="panel"><div class="section-title"><h2>Matriz de transições</h2><select id="heat-metric" aria-label="Métrica da matriz"><option value="g2g_ms">GtG médio (ms)</option><option value="overshoot_pct">Excesso médio (%)</option><option value="acomodacao_ms">Acomodação média (ms)</option></select></div><div id="heatmap" class="table-wrap"></div><p class="muted" style="margin-top:18px">Linhas: cinza inicial. Colunas: cinza final. Cada célula resume as repetições válidas do par. Células vazias não significam zero.</p></section>
  <section class="panel"><h2>Condições do ensaio</h2><dl class="conditions">${conditionTable(r)}</dl><details><summary>Critérios e versão da análise</summary><p class="muted" style="margin:14px 0">${esc(r.method?.version)} · ${esc(r.method?.g2g)}. Excesso relativo à amplitude da transição, separado do cálculo Delta-PQ.</p><div class="table-wrap"><table><thead><tr><th>Captura</th><th>Critérios registrados</th><th>Versão</th></tr></thead><tbody>${r.results.map(v=>`<tr><td>${v.origin} → ${v.destination} / ${v.repetition}</td><td>${esc(JSON.stringify(v.criteria))}</td><td>${esc(v.analysis_version)}</td></tr>`).join('')}</tbody></table></div></details></section>
  <section class="panel"><h2>Resultados por captura</h2><div class="table-wrap"><table><thead><tr><th>RGB</th><th>Rep.</th><th>GtG (ms)</th><th>Excesso (%)</th><th>Acomodação (ms)</th><th>Estado</th><th>Interpretação</th></tr></thead><tbody>${r.results.map(v=>`<tr><td>${v.origin} → ${v.destination}</td><td>${v.repetition}</td><td>${fmt(v.g2g_ms)}</td><td>${fmt(v.overshoot_pct)}</td><td>${fmt(v.acomodacao_ms)}</td><td class="${v.valid?'status-valid':'status-invalid'}">${v.valid?'Válida':'Revisar'}</td><td class="reason">${esc(v.meaning||v.reasons?.join(', ')||'Sem interpretação adicional.')}</td></tr>`).join('')}</tbody></table></div></section>
  ${r.conclusion?`<section class="panel"><h2>Conclusão do operador</h2><p style="white-space:pre-wrap">${esc(r.conclusion)}</p></section>`:''}
  <div class="reading-note"><span class="note-icon">i</span><p><strong>O que este ensaio mede.</strong> Resposta óptica temporal, GtG 10–90%, excesso relativo e acomodação. O sistema não mede input lag e estes resultados não constituem certificação VESA. Curvas, critérios e condições acompanham as métricas. ID do relatório: ${esc(r.id)}.</p></div>`;
  $('#download-pdf')?.addEventListener('click',()=>assetDownload(r,'relatorio.pdf'));
  $('#download-json').addEventListener('click',()=>download('relatorio.iris.json',JSON.stringify(r)));
  $('#download-csv').addEventListener('click',()=>{
    const quote=v=>{let value=String(v??'');if(typeof v==='string'&&/^[=+@\-\t\r]/.test(value))value="'"+value;return '"'+value.replaceAll('"','""')+'"';};
    const rows=[['origem_rgb','destino_rgb','repeticao','valida','g2g_ms','excesso_pct','acomodacao_ms','interpretacao'],...r.results.map(v=>[v.origin,v.destination,v.repetition,v.valid,v.g2g_ms,v.overshoot_pct,v.acomodacao_ms,v.meaning])];
    download('resultados_iris.csv','\uFEFF'+rows.map(row=>row.map(quote).join(';')).join('\r\n'),'text/csv;charset=utf-8');
  });
  $('#copy-url').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(location.href);$('#detail-message').textContent='Link copiado.';}catch{$('#detail-message').textContent=location.href;}});
  for(const id of ['transition','curve-raw','curve-filtered','curve-full'])$('#'+id).addEventListener('change',updatePlot);
  $('#heat-metric').addEventListener('change',()=>renderHeat(r));updatePlot();renderHeat(r);
}
function updatePlot(){const r=state.report.results[Number($('#transition').value)];$('#detail-plot').innerHTML=plot(r,{raw:$('#curve-raw').checked,filtered:$('#curve-filtered').checked,full:$('#curve-full').checked});
  $('#transition-metrics').innerHTML=`<div><span>GtG 10–90%</span><strong>${fmt(r.g2g_ms,3)} ms</strong></div><div><span>${esc(r.peak_name)} relativo</span><strong>${fmt(r.overshoot_pct)}%</strong></div><div><span>Acomodação desde t10</span><strong>${fmt(r.acomodacao_ms)} ms</strong></div>`;
  $('#transition-meaning').textContent=r.meaning||'Sem interpretação registrada.';
  $('#curve-info').textContent=r.curve?`${r.curve.original_samples} amostras originais · ${r.curve.points.length} pontos na visualização${r.curve.reduced?' · redução com preservação dos extremos':''}. As métricas são calculadas no Python com as amostras completas.`:'Sem curva neste relatório.';
}
function renderHeat(report) {
  const key=$('#heat-metric').value;
  const levels=[...new Set(report.results.flatMap(r=>[r.origin,r.destination]))].sort((a,b)=>a-b);
  const cells=new Map();
  let max=1;
  for(const row of report.results){
    const value=row[key];
    if(!row.valid||!Number.isFinite(value)) continue;
    const id=row.origin+'/'+row.destination;
    const cell=cells.get(id)??{sum:0,n:0};
    cell.sum+=value;cell.n+=1;cells.set(id,cell);
  }
  for(const c of cells.values())max=Math.max(max,c.sum/c.n);
  $('#heatmap').innerHTML=`<table class="heatmap"><thead><tr><th scope="col">Inicial / final</th>${levels.map(l=>`<th scope="col">${l}</th>`).join('')}</tr></thead><tbody>${levels.map(a=>`<tr><th scope="row">${a}</th>${levels.map(b=>{
    const cell=cells.get(a+'/'+b),mean=cell?cell.sum/cell.n:null;
    const style=mean==null?'':`background:rgba(26,133,191,${(.12+.5*mean/max).toFixed(3)})`;
    return `<td style="${style}" title="${a} para ${b} · ${cell?.n??0} valores válidos">${fmt(mean)}</td>`;
  }).join('')}</tr>`).join('')}</tbody></table>`;
}
function compare(){
  const sessions=catalog().flatMap(model=>model.sessions);
  const reports=[...state.selected].map(id=>sessions.find(s=>s.id===id)).filter(Boolean)
    .map(s=>({...s.lead,summary:sessionSummary(s),href:sessionHref(s)}));
  if(reports.length<2)return;
  const rows=[['Configuração',r=>`${r.monitor.refresh_hz} Hz · ${r.monitor.overdrive}`],['Medição',r=>date(r.measured_at)],['GtG médio (ms)',r=>fmt(r.summary.g2g_ms?.mean,3)],['GtG mínimo / máximo (ms)',r=>`${fmt(r.summary.g2g_ms?.min)} / ${fmt(r.summary.g2g_ms?.max)}`],['Excesso médio (%)',r=>fmt(r.summary.overshoot_pct?.mean)],['Maior excesso (%)',r=>fmt(r.summary.overshoot_pct?.max)],['Capturas válidas / total',r=>`${r.summary.valid} / ${r.summary.total}`],['Resolução',r=>r.conditions?.resolution||'Não informado'],['Brilho / contraste',r=>`${r.conditions?.brightness??'—'} / ${r.conditions?.contrast??'—'}`],['HDR / VRR',r=>`${r.conditions?.hdr??'—'} / ${r.conditions?.vrr??'—'}`],['Amostragem (S/s)',r=>r.conditions?.rate_sps??'—'],['Método',r=>r.method?.version||'—'],['Origem',r=>r.simulation?'Simulação':r.seed?'Acervo inicial Íris':'Comunidade']];
  $('#compare-content').innerHTML=`<p class="notice">As médias dependem dos pares de cinza, repetições, filtros e condições. Confira se são equivalentes antes de comparar. Esta tabela não atribui uma classificação automática de qualidade.</p><div class="table-wrap"><table><thead><tr><th>Métrica / condição</th>${reports.map(r=>`<th><a href="${r.href}">${esc(r.monitor.model)}</a></th>`).join('')}</tr></thead><tbody>${rows.map(([label,value])=>`<tr><th>${label}</th>${reports.map(r=>`<td>${esc(value(r))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  $('#compare-dialog').showModal();
}
function randomToken(){const bytes=crypto.getRandomValues(new Uint8Array(32));return Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');}
function publishEnabled(){$('#publish').disabled=!state.upload||!$('#upload-consent').checked;}
async function selectFile(file){
  state.upload=null;state.token=null;$('#upload-preview').hidden=true;$('#upload-success').hidden=true;$('#upload-consent').checked=false;publishEnabled();
  try{
    if(!file) return;if(file.size>4_000_000)throw new Error('O arquivo excede 4 MB. Gere um pacote menor no Íris Desktop.');
    const report=JSON.parse(await file.text());
    if(report.schema!=='iris-report/1'||!report.monitor?.model||!report.monitor?.overdrive||!Array.isArray(report.results)||typeof report.simulation!=='boolean')throw new Error('Selecione o arquivo relatorio.iris.json gerado pelo Íris Desktop atualizado.');
    if(report.simulation)throw new Error('Selecione um ensaio realizado com o equipamento Íris.');
    state.upload=report;state.token=randomToken();
    $('#upload-preview').innerHTML=`<div class="panel">${badge(report)}<h3 style="margin:14px 0 8px">${esc(report.monitor.model)}</h3><p>${esc(report.monitor.refresh_hz)} Hz · ${esc(report.monitor.overdrive)} · ${report.results.length} capturas</p><p>Autor: ${esc(report.operator||'Não informado')}</p><p>Medido em ${date(report.measured_at)}. ${report.assets?.['relatorio.pdf']?'Inclui PDF.':'Sem PDF anexado.'}</p></div>`;$('#upload-preview').hidden=false;$('#upload-status').textContent='Arquivo carregado. Confira os dados antes de publicar.';
  }catch(error){$('#upload-status').textContent=error instanceof SyntaxError?'O arquivo selecionado não contém um JSON válido.':error.message;}
}
async function publish(){if(!state.upload||!$('#upload-consent').checked)return;
  $('#publish').disabled=true;$('#upload-file').disabled=true;$('#upload-status').textContent='Enviando relatório…';
  try{
    const data=await api('/api/publish',{method:'POST',headers:{'Content-Type':'application/json','X-Iris-Delete-Token':state.token},body:JSON.stringify(state.upload)});
    const url=location.origin+'/?relatorio='+data.id,receipt={...data,url,site:location.origin,delete_token:state.token};
    // O recibo fica apenas neste navegador e no arquivo baixado pelo operador.
    try{const receipts=JSON.parse(localStorage.getItem('iris-receipts')||'[]');receipts.push(receipt);localStorage.setItem('iris-receipts',JSON.stringify(receipts.slice(-100)));}catch{}
    state.receipt=receipt;
    $('#upload-status').textContent=data.duplicate?'Este relatório já está no acervo.':'Relatório publicado.';
    $('#upload-success').innerHTML=`<div class="notice"><p class="success">${data.can_delete?'Guarde o recibo privado para remover sua publicação.':'Este conteúdo já foi publicado com outra chave; este recibo não permite removê-lo.'}</p><a class="button primary" href="?relatorio=${data.id}">Consultar relatório</a> <button id="save-receipt" class="button quiet">Baixar recibo privado</button></div>`;
    $('#upload-success').hidden=false;$('#save-receipt').addEventListener('click',()=>download('publicacao-recibo.json',JSON.stringify(receipt,null,2)));
    await loadRemote();
  }catch(error){$('#upload-status').textContent=error.message;}
  finally{$('#upload-file').disabled=false;publishEnabled();}
}
let removal=null;
$('#receipt-file').addEventListener('change',async event=>{removal=null;$('#remove-report').disabled=true;try{const file=event.target.files[0];if(!file)return;if(file.size>65536)throw new Error('Recibo inválido.');const data=JSON.parse(await file.text());if(!/^[a-f0-9]{32}$/.test(data.id)||!/^[A-Za-z0-9_-]{32,128}$/.test(data.delete_token))throw new Error('O recibo precisa incluir o ID e a chave de remoção.');if(data.site?.replace(/\/$/,'')!==location.origin)throw new Error('Este recibo pertence a outro endereço. Abra o site no qual o relatório foi enviado.');removal=data;$('#remove-report').disabled=false;$('#remove-status').textContent='Recibo carregado. A remoção será definitiva ao clicar no botão.';}catch(error){$('#remove-status').textContent=error.message;}});
$('#remove-report').addEventListener('click',async()=>{if(!removal)return;$('#remove-report').disabled=true;try{await api('/api/reports/'+removal.id,{method:'DELETE',headers:{'X-Iris-Delete-Token':removal.delete_token}});$('#remove-status').textContent='Sua publicação foi removida.';removal=null;await loadRemote();}catch(error){$('#remove-status').textContent=error.message;$('#remove-report').disabled=false;}});
$('#upload-file').addEventListener('change',event=>selectFile(event.target.files[0]));
const drop=$('#drop-zone');for(const type of ['dragenter','dragover'])drop.addEventListener(type,event=>{event.preventDefault();drop.classList.add('drag');});for(const type of ['dragleave','drop'])drop.addEventListener(type,event=>{event.preventDefault();drop.classList.remove('drag');});drop.addEventListener('drop',event=>selectFile(event.dataTransfer.files[0]));
$('#upload-consent').addEventListener('change',publishEnabled);$('#publish').addEventListener('click',publish);
for(const id of ['search','hz-filter','sort'])$('#'+id).addEventListener(id==='search'?'input':'change',renderCards);
$('#refresh').addEventListener('click',()=>loadRemote());
$('#compare-open').addEventListener('click',compare);$('#compare-close').addEventListener('click',()=>$('#compare-dialog').close());$('#compare-clear').addEventListener('click',()=>{state.selected.clear();renderCompareBar();if(state.model)renderModel(state.model);});
document.addEventListener('click',event=>{const a=event.target.closest('a');if(!a||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;const url=new URL(a.href,location.href);if(url.origin!==location.origin||url.pathname!==location.pathname||url.hash||a.download)return;event.preventDefault();$('#compare-dialog').close();history.pushState(null,'',url);route();window.scrollTo({top:0,behavior:'instant'});});
window.addEventListener('popstate',route);
state.loading=true;await loadSeed();updateHz();await route();loadRemote();
