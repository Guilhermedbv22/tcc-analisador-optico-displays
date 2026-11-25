"""Exportação de campanha com dados originais, comparações e figuras reproduzíveis."""
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
import html
import json
import zipfile
import numpy as np
from .analysis import analyze, curve, plateau_stats
from .config import TestConfig
from .exports import export_native, report_html, report_pdf, write_csv, _figure, _axis_style
from .publication import campaign_packages
from .storage import atomic, json_text, utc


def metrics(values):
    values=[float(x) for x in values if x is not None and np.isfinite(x)]
    return dict(n=len(values),mean=float(np.mean(values)) if values else None,
      std=float(np.std(values,ddof=1)) if len(values)>1 else None,
      min=min(values) if values else None,max=max(values) if values else None)


def pair_table(rows):
    groups=defaultdict(list)
    for r in rows:
        if r['phase']=='medicao':groups[r['origem_rgb'],r['destino_rgb']].append(r)
    out=[]
    for (a,b),group in sorted(groups.items()):
        valid=[r for r in group if r.get('valida')]
        row=dict(origin=a,destination=b,n_total=len(group),n_valid=len(valid))
        for name in ('g2g_ms','overshoot_pct','acomodacao_ms'):
            row.update({name+'_'+k:v for k,v in metrics([r.get(name) for r in valid]).items()})
        out.append(row)
    return out


def export_campaign(campaign, progress=lambda text:None):
    store=campaign.store
    # Diretório novo a cada exportação; nunca mistura resultados de revisões diferentes.
    folder=campaign.folder/('export_'+utc().replace(':','').replace('.','').replace('+','_'))
    folder.mkdir(parents=True,exist_ok=False)
    all_results=[];filter_rows=[];noise=[];timing=[];sessions=[];main=[];processed=0
    for s in campaign.data['steps']:
        for sid in s['attempts']:
            progress('Exportando '+s['title'])
            session=store.get_session(sid)
            if session['status']=='em_andamento':raise ValueError('Encerre as aquisições antes de exportar.')
            rows=store.rows(sid);cfg=TestConfig.from_dict(session['config'])
            dest=folder/'sessoes'/s['id']/sid;dest.mkdir(parents=True,exist_ok=True)
            export_native(store,sid,dest/'sessao_original.zip')
            table=pair_table(rows);write_csv(dest/'transicoes_resumo.csv',table)
            items=[]
            for row in rows:
                cap=store.capture(row['capture_id']);st=row.get('estatisticas',{})
                item=dict(step=s['id'],session_id=sid,capture_id=row['capture_id'],origin=row['origem_rgb'],destination=row['destino_rgb'],
                  repetition=row['repetition'],phase=row['phase'],valid=row.get('valida'),g2g_ms=row.get('g2g_ms'),
                  overshoot_pct=row.get('overshoot_pct'),undershoot_pct=row.get('undershoot_pct'),
                  acomodacao_ms=row.get('acomodacao_ms'),reasons=row.get('motivos',[]),warnings=row.get('avisos',[]))
                all_results.append(item)
                timing.append(dict(session_id=sid,capture_id=row['capture_id'],**{k:st.get(k) for k in ('taxa_media_sps','dt_mediano_us','dt_p01_us','dt_p99_us','dt_max_us','jitter_std_us','leitura_p99_us','temporizacao_valida')}))
                if row['origem_rgb']==row['destino_rgb']:
                    noise.append(dict(step=s['id'],session_id=sid,capture_id=row['capture_id'],rgb=row['origem_rgb'],
                      repetition=row['repetition'],adc=cfg.adc,caps=cfg.capacitors,
                      mean_adc=st.get('media'),std_adc=st.get('desvio_padrao'),pp_adc=st.get('pico_a_pico'),
                      p01=st.get('p01'),p99=st.get('p99'),rail_fraction=st.get('fracao_rail')))
                else:
                    for k in (1,3,5,9):
                        result=analyze(cap,row['origem_rgb'],row['destino_rgb'],replace(cfg.get_criteria(),mediana_amostras=k))
                        plateau=plateau_stats(cap,result,cfg.vref)
                        # Métricas calculadas com TODOS os pontos; a revisão ativa não é alterada.
                        t,raw,filtered=curve(cap,result,median=k)
                        mask=t<cfg.get_criteria().patamar_inicial_ms
                        filter_rows.append(dict(session_id=sid,capture_id=row['capture_id'],origin=row['origem_rgb'],destination=row['destino_rgb'],
                          median_samples=k,valid=result.get('valida'),g2g_ms=result.get('g2g_ms'),overshoot_pct=result.get('overshoot_pct'),
                          acomodacao_ms=result.get('acomodacao_ms'),raw_std_adc=plateau.get('sigma_adc'),
                          filtered_initial_std_adc=float(np.std(filtered[mask],ddof=1)) if mask.sum()>1 else None,reasons=result.get('motivos',[])))
                    if len(items)<2 and row.get('valida'):items.append(row)
            if rows and any(r['phase']=='medicao' for r in rows):
                path=report_html(store,sid,dest,include_samples=False)
                report_pdf(path,dest/'relatorio.pdf')
            if sid==s['session_id']:
                sessions.append(dict(step=s['id'],title=s['title'],session_id=sid,status=s['status'],pairs=table,config=session['config']))
                if s['kind']=='monitor' and not campaign.remaining(s):
                    paths=campaign_packages(store,sid,dest)
                    import hashlib
                    previous={p.get('sha256'):p for p in s['publications']}
                    publications=[]
                    for p in paths:
                        digest=hashlib.sha256(p.read_bytes()).hexdigest()
                        old=previous.get(digest,{})
                        # Reenvio usa o recibo original e a mesma chave de remoção.
                        publications.append({**old,'path':old['path'] if old.get('state')=='publicado' else str(p),
                          'sha256':digest,'state':old.get('state','pronto')})
                    s['publications']=publications
                    main.append((s,rows))
            for index,row in enumerate(items):
                cap=store.capture(row['capture_id']);fig=_figure(11,5);ax=fig.add_subplot()
                for k,color in [(1,'#7da9d1'),(3,'#53dbd1'),(5,'#ffc778'),(9,'#e998db')]:
                    t,raw,filt=curve(cap,row,median=k)
                    ax.plot(t,filt,lw=.9,label='Bruto' if k==1 else f'Mediana {k}',color=color)
                ax.set(xlabel='Tempo (ms)',ylabel='Código ADC',title=f"{s['title']} · {row['origem_rgb']} → {row['destino_rgb']}")
                _axis_style(ax);ax.legend();fig.savefig(dest/f'filtros_{index+1}.png',dpi=160);fig.clear()
            processed+=1
    # Comparações usam a média de cada par e somente pares comuns válidos.
    common=set.intersection(*[{(r['origem_rgb'],r['destino_rgb']) for r in rows if r.get('valida') and r['phase']=='medicao'} for _,rows in main]) if main else set()
    compare=[]
    for s,rows in main:
        pairs=pair_table(rows)
        matched=[p for p in pairs if (p['origin'],p['destination']) in common]
        compare.append(dict(step=s['id'],common_pairs=len(common),total_pairs=len(pairs),
          gtg_equal_pair_mean=metrics([p['g2g_ms_mean'] for p in matched])['mean'],
          peak_equal_pair_mean=metrics([p['overshoot_pct_mean'] for p in matched])['mean']))
    # Curvas com o MESMO par, normalizadas e alinhadas em t10. Sem inferir input lag.
    compare_groups=defaultdict(list)
    for info in sessions:
        c=info['config']
        if info['step'].startswith('adc_dynamic'):group='ADCs'
        elif info['step'].startswith('overdrive_'):group='Overdrive'
        elif info['step'].startswith('repeat_'):group='Reposicionamento'
        elif info['step'].startswith('monitor_') and c['refresh_hz']==60:group='Monitores_60Hz'
        else:continue
        compare_groups[group].append(info)
    for group,infos in compare_groups.items():
        for a,b in [(0,32),(0,153),(255,204),(0,255)]:
            fig=_figure(10,5);ax=fig.add_subplot();count=0
            for info in infos:
                rows=store.rows(info['session_id']);r=next((r for r in rows if r.get('valida') and r['phase']=='medicao' and (r['origem_rgb'],r['destino_rgb'])==(a,b)),None)
                if r:
                    t,raw,filt=curve(store.capture(r['capture_id']),r,unit='%',align=True)
                    ax.plot(t,filt,lw=1,label=info['title']);count+=1
            if count:
                ax.set(xlabel='Tempo desde t10 (ms)',ylabel='Progresso da transição (%)',title=f'{group} · {a} → {b} · primeira repetição válida de cada sessão')
                ax.set_xlim(-5,60);_axis_style(ax);ax.legend(fontsize=7)
                fig.savefig(folder/f'{group}_{a}_{b}.png',dpi=160)
            fig.clear()
    write_csv(folder/'resultados_capturas.csv',all_results)
    write_csv(folder/'processamento_comparacao.csv',filter_rows)
    write_csv(folder/'patamares_ruido.csv',noise)
    write_csv(folder/'temporizacao.csv',timing)
    write_csv(folder/'comparacao_pares_comuns.csv',compare)
    if noise:
        fig=_figure(12,5);ax=fig.add_subplot();groups=defaultdict(list)
        for row in noise:
            if row['step'].startswith('caps_'):groups[row['step'],row['rgb']].append(row['std_adc'])
        for rgb,color in [(32,'#64b5f6'),(128,'#e998db'),(224,'#71e0b8')]:
            names=sorted({name for name,level in groups})
            vals=[metrics(groups.get((name,rgb),[]))['mean'] for name in names]
            if any(v is not None for v in vals):ax.plot(range(len(names)),[np.nan if v is None else v for v in vals],marker='o',label=f'RGB {rgb}',color=color)
        if groups:
            ax.set_xticks(range(len(names)),names,rotation=25,ha='right');ax.set_ylabel('Média do desvio padrão de cada captura (códigos ADC)');_axis_style(ax);ax.legend();fig.savefig(folder/'capacitores_ruido.png',dpi=160)
        fig.clear()
    campaign.save()
    atomic(folder/'campanha.json',json_text(campaign.data).encode('utf8'))
    atomic(folder/'sessoes_resumo.json',json_text(sessions).encode('utf8'))
    urls=[p['url'] for s in campaign.data['steps'] for p in s['publications'] if p.get('url')]
    (folder/'links_publicados.txt').write_text('\n'.join(urls),encoding='utf8')
    def e(x):return html.escape(str(x))
    text='<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Campanha Íris</title><style>body{font:15px sans-serif;max-width:1100px;margin:32px auto}td,th{padding:9px;border:1px solid #bbc}table{border-collapse:collapse;width:100%}img{max-width:100%}</style><h1>Campanha Íris</h1>'
    text+='<p>As amostras originais estão em sessoes/.../sessao_original.zip e podem ser importadas no Íris Desktop. Os CSV resumem todos os ensaios e reanálises. Tentativas anteriores são preservadas.</p>'
    text+='<p>Mediana 3 é a análise principal. Comparações 1/3/5/9 não sobrescrevem revisões. Flutuação de patamar inclui eletrônica e emissão do display; não representa ruído eletrônico isolado. Sem calibração fotométrica ou certificação VESA. Valores indisponíveis permanecem ausentes.</p>'
    text+='<h2>Estado do roteiro</h2><table><tr><th>Etapa</th><th>Estado</th><th>Capturas</th></tr>'
    for s in campaign.data['steps']:text+=f"<tr><td>{e(s['title'])}</td><td>{e(s['status'])}</td><td>{e(campaign.report(s))}</td></tr>"
    text+='</table><h2>Relatórios completos</h2><ul>'
    for p in folder.glob('sessoes/*/*/relatorio.html'):text+=f'<li><a href="{p.relative_to(folder).as_posix()}">{e(p.parent.parent.name)} · {e(p.parent.name)}</a></li>'
    text+='</ul><h2>Publicações no site</h2><ul>'+''.join(f'<li><a href="{e(url)}">{e(url)}</a></li>' for url in urls)+'</ul>'
    for p in sorted(folder.glob('*.png')):text+=f'<h2>{e(p.stem)}</h2><img src="{p.name}">'
    (folder/'ABRIR_CAMPANHA.html').write_text(text,encoding='utf8')
    (folder/'LEIA_PRIMEIRO.txt').write_text('Abra ABRIR_CAMPANHA.html.\nPacote completo de pesquisa: contém condições, aquisições originais e publicações.\nImporte cada sessao_original.zip pelo Histórico do Íris.\nOs JSON relatorio.iris.json podem ser enviados pela aba Enviar relatório do site atualizado.\nNão trate dados simulados como ensaios físicos; a marcação original é preservada.\n',encoding='utf8')
    path=campaign.folder/(folder.name+'.zip')
    progress('Compactando dados e relatórios…')
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(folder))
    campaign.data['exports'].append(dict(time=utc(),zip=str(path),folder=str(folder)))
    campaign.save()
    return dict(path=str(path),folder=str(folder),sessions=processed)
