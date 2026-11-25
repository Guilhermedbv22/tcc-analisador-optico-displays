from collections import defaultdict
from dataclasses import replace
from pathlib import Path
import csv
import html
import json
import zipfile
import numpy as np
from .analysis import curve, summary, describe, matrix_values, matrix_text, matrix_text_color
from . import __version__
from .storage import json_text

LIMITATIONS = ("Ensaio exploratório do Íris; não certifica conformidade VESA. "
    "G2G relativo de 10–90%, sem calibração fotométrica absoluta, Delta-PQ ou largura de banda validada. "
    "A resposta do sensor, TIA, ADC, montagem e sincronismo do estímulo compõe o resultado. "
    "O relógio do PC não mede input lag. O filtro de mediana pode mudar picos e deve ser declarado. "
    "Uma repetição não caracteriza repetibilidade; CTS Adaptive-Sync 1.1a utiliza outro plano de ensaio, "
    "com ao menos 20 aquisições de cada par e critérios próprios.")


def write_csv(path, rows):
    path = Path(path)
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({k:json_text(v) if isinstance(v,(dict,list)) else v for k,v in row.items()})


def export_csv(store, sid, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    session = store.get_session(sid)
    if session["kind"] == "bancada":
        write_csv(folder/"bancada.csv", store.bench_rows(sid))
    rows = store.rows(sid)
    if rows:
        write_csv(folder/"resultados.csv", rows)
        raw = folder/"amostras"
        raw.mkdir(exist_ok=True)
        for r in rows:
            cap = store.capture(r["capture_id"])
            filename = f"{r['capture_id']:05d}_{r['origem_rgb']}_{r['destino_rgb']}_r{r['repetition']}.csv"
            source = cap.meta.get("source", session["config"].get("adc"))
            vref = session["config"].get("vref",3.3)
            write_csv(raw/filename, [dict(indice=i,tempo_us=float(t),adc_bruto=int(v),leitura_us=float(d),
                tensao_adc_V=float(v)*vref/4096 if source=="MCP3208" and vref is not None else None)
                for i,(t,v,d) in enumerate(zip(cap.t_us, cap.adc, cap.leitura_us))])
    (folder/"sessao_exportada.json").write_text(json_text(session),encoding="utf8")
    return folder


def export_native(store, sid, path):
    session = store.get_session(sid)
    info = dict(format="iris-desktop-1", session=session, captures=[],
                bench=store.bench_rows(sid), events=store.events(sid))
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as z:
        for r in store.rows(sid):
            store.capture(r["capture_id"])  # verifica a integridade antes de exportar
            with store.db() as db:
                row = dict(db.execute("SELECT * FROM captures WHERE id=?",(r["capture_id"],)).fetchone())
            row["meta"] = json.loads(row["meta"])
            row["revisions"] = store.revisions(r["capture_id"])
            p = store.root/row["raw_file"]
            row["raw_file"] = p.relative_to(store.root).as_posix()
            info["captures"].append(row)
            for f in (p,p.with_suffix(".json"),p.with_suffix(".wire")):
                if f.exists():
                    z.write(f,f.relative_to(store.root).as_posix())
        z.writestr("export.json",json_text(info))


def _figure(width=13, height=7):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig = Figure(figsize=(width,height), facecolor="#0c1424", layout="constrained")
    FigureCanvasAgg(fig)
    return fig


def _axis_style(ax):
    ax.set_facecolor("#111d31")
    ax.tick_params(colors="#d2ddeb",labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#39516d")
    for text in (ax.title,ax.xaxis.label,ax.yaxis.label):
        text.set_color("#e2eaf6")
    ax.grid(alpha=.18,color="#9eb5d2")


def export_curve(cap, result, path, vref=3.3, unit="%", options=None):
    opt = dict(raw=True, filtered=True, plateaus=True, thresholds=True, settling=True,
               references=False, reference_ms=5.0, reference_label="Referência do projeto")
    opt.update(options or {})
    fig = _figure(13,6)
    ax = fig.add_subplot()
    try:
        t,y,f = curve(cap,result,unit=unit,vref=vref)
    except ValueError:
        unit="ADC"; t,y,f = curve(cap,result,unit=unit,vref=vref)
    if opt["raw"]:
        ax.plot(t,y,color="#64b5f6",lw=.8,alpha=.7,label="Sinal bruto")
    if opt["filtered"]:
        ax.plot(t,f,color="#e9a8ff",lw=1.7,label=f"Mediana {result.get('criterios',{}).get('mediana_amostras',3)}")
    a,b = result.get("inicial_adc"),result.get("final_adc")
    if a is not None and b is not None:
        start,end = (0,100) if unit=="%" else (a*vref/4096,b*vref/4096) if unit=="V" else (a,b)
        if opt["plateaus"]:
            ax.axhline(start,color="#21d4c8",ls="--",lw=1,label="Patamar inicial")
            ax.axhline(end,color="#ffd166",ls="--",lw=1,label="Alvo final")
        if opt["thresholds"]:
            for v,col in ((.1,"#80d8ff"),(.9,"#c5a3ff")):
                ax.axhline(start+v*(end-start),color=col,ls=":",lw=1,label=f"{v*100:.0f}% da transição")
        if result.get("t10_ms") is not None:
            ax.axvspan(result["t10_ms"],result["t90_ms"],alpha=.13,color="#71c3ff",label="Intervalo G2G 10–90%")
            if opt["references"]:
                ax.axvline(result["t10_ms"]+opt["reference_ms"],color="#ffab66",ls="-.",label=f"{opt['reference_label']} · {opt['reference_ms']:g} ms desde t10")
            if opt["settling"]:
                band=result["criterios"]["tolerancia_acomodacao"]*abs(end-start)
                ax.axhspan(end-band,end+band,alpha=.08,color="#64e4ac",label=f"Faixa de acomodação ±{result['criterios']['tolerancia_acomodacao']*100:g}%")
    g=result.get("g2g_ms"); os=result.get("overshoot_pct")
    title=(f"RGB {result['origem_rgb']} → {result['destino_rgb']}   |   G2G {g:.3f} ms   |   {result.get('peak_name','Pico')} {os:.2f}%" if result.get("valida") else
           "Sinal estático · análise de ruído, sem G2G" if result.get("status")=="ESTATICA" else
           f"RGB {result['origem_rgb']} → {result['destino_rgb']} · medição não válida")
    ax.set_title(title,loc="left",pad=16,color="#e2eaf6")
    ax.set_xlabel("Tempo desde a primeira amostra (ms)");ax.set_ylabel("Resposta relativa (%)" if unit=="%" else "Tensão no ADC (V)" if unit=="V" else "Código ADC")
    _axis_style(ax)
    ax.legend(loc="upper center",bbox_to_anchor=(.5,-.16),ncol=3,fontsize=8,
              facecolor="#111d31",labelcolor="#e2eaf6",edgecolor="#39516d")
    fig.savefig(path,dpi=160,facecolor=fig.get_facecolor())


def export_overview(store,sid,path):
    rows=[r for r in store.rows(sid) if r["phase"]=="medicao"]
    pairs=sorted(set((r["origem_rgb"],r["destino_rgb"]) for r in rows))
    if not pairs:
        raise ValueError("Sessão sem transições de medição; pilotos e referências ficam fora do resumo.")
    fig=_figure(max(13,len(pairs)*.25),11)
    axes=fig.subplots(3,1)
    for ax,metric,label,col in ((axes[0],"g2g_ms","G2G 10–90% (ms)","#64b5f6"),
                                (axes[1],"overshoot_pct","Excesso no alvo (%) · overshoot / undershoot","#ffa9db"),
                                (axes[2],"acomodacao_ms","Acomodação desde t10 (ms)","#64e4ac")):
        for i,pair in enumerate(pairs):
            group=[r for r in rows if (r["origem_rgb"],r["destino_rgb"])==pair]
            valid=[r for r in group if r.get("valida") and r.get(metric) is not None]
            if valid:
                vals=[r[metric] for r in valid]
                ax.bar(i,float(np.mean(vals)),width=.68,color=col,alpha=.22)
                ax.scatter(np.linspace(i-.14,i+.14,len(vals)) if len(vals)>1 else [i],vals,s=18,color=col,zorder=3)
            if len(valid)<len(group):
                ax.scatter(i,0,marker="x",color="#ffb454",s=35,zorder=4)
        ax.plot([],[],"o",color=col,label="Cada repetição válida; barra = média do par")
        ax.plot([],[],"x",color="#ffb454",label="Resultado inválido ou indisponível (não significa zero)")
        ax.set_xticks(range(len(pairs)),[f"{a}→{b}" for a,b in pairs],rotation=75,ha="right")
        ax.set_ylabel(label);ax.set_ylim(bottom=0)
        _axis_style(ax)
        ax.legend(loc="upper left",fontsize=8,facecolor="#111d31",labelcolor="#e2eaf6",edgecolor="#39516d")
    s=store.get_session(sid)
    fig.suptitle(("SIMULAÇÃO · " if s["simulation"] else "")+s["title"]+" · todas as transições",color="#e2eaf6",fontsize=16)
    fig.savefig(path,dpi=150,facecolor=fig.get_facecolor())


def export_heatmap(store,sid,path):
    rows=[r for r in store.rows(sid) if r["phase"]=="medicao"]
    levels=sorted({v for r in rows for v in (r["origem_rgb"],r["destino_rgb"])})
    if not levels:
        raise ValueError("Sem transições para matriz.")
    fig=_figure(max(13,len(levels)*1.1+2),max(6,len(levels)*.55+1.8))
    axes=fig.subplots(1,2)
    for ax,key,title in ((axes[0],"g2g_ms","G2G médio (ms)"),(axes[1],"overshoot_pct","Excesso médio no alvo (%)")):
        _,data=matrix_values(rows,key)
        image=ax.imshow(np.ma.masked_invalid(data),cmap="viridis",vmin=0)
        for (i,j),val in np.ndenumerate(data):
            color=matrix_text_color(image.cmap(image.norm(val))) if np.isfinite(val) else "#9eb1cc"
            ax.text(j,i,matrix_text(val),ha="center",va="center",color=color,fontsize=8)
        ax.set_xticks(range(len(levels)),levels);ax.set_yticks(range(len(levels)),levels)
        ax.set_xlabel("Cinza de destino");ax.set_ylabel("Cinza inicial");ax.set_title(title+" · — = sem resultado válido")
        _axis_style(ax);ax.grid(False)
        ax.set_xticks(np.arange(len(levels)+1)-.5,minor=True)
        ax.set_yticks(np.arange(len(levels)+1)-.5,minor=True)
        ax.grid(which="minor",color="#506070",linewidth=.4)
        ax.tick_params(which="minor",bottom=False,left=False)
        cb=fig.colorbar(image,ax=ax,shrink=.8);cb.ax.tick_params(colors="#d2ddeb")
    fig.savefig(path,dpi=160,facecolor=fig.get_facecolor())


def report_html(store,sid,folder,conclusion="",include_samples=True):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    session=store.get_session(sid); rows=store.rows(sid); stats=summary(rows)
    def e(x):
        if x is None or x=="":return "Não informado"
        if isinstance(x,bool):return "Sim" if x else "Não"
        if isinstance(x,(float,np.floating)):return f"{x:.6g}"
        return html.escape(str(x))
    def table(items):
        return '<table width="100%">'+"".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k,v in items)+"</table>"
    images=""
    if any(r["phase"]=="medicao" for r in rows):
        export_overview(store,sid,folder/"transicoes.png")
        export_heatmap(store,sid,folder/"matrizes.png")
        images='<h2 style="page-break-before:always">Todas as transições</h2><img src="transicoes.png"><h2 style="page-break-before:always">Matrizes</h2><img src="matrizes.png">'
        chosen=next((r for r in rows if r.get("valida") and r["phase"]=="medicao"),None)
        if chosen:
            export_curve(store.capture(chosen["capture_id"]),chosen,folder/"exemplo.png",session["config"].get("vref",3.3))
            images+='<h2>Exemplo de leitura</h2><img src="exemplo.png"><p>'+e(chosen.get("meaning",""))+"</p>"
    technical = ""
    if session["kind"]=="bancada":
        bench=store.bench_rows(sid)
        channels=sorted({r["channel"] for r in bench})
        technical="<h2>Bancada · médias temporais por canal</h2>"
        for ch in channels:
            group=[r for r in bench if r["channel"]==ch]
            vals=[r["value_v"] for r in group if r["value_v"] is not None]
            technical+=table([("Canal",ch),("Registros STAT",len(group)),("Média das médias (V)",f"{np.mean(vals):.6f}" if vals else "N/D"),
                              ("Observação","Canais sequenciais; cada STAT resume 64 conversões. CSV original preservado no payload quando importado.")])
        if rows:
            for index,r in enumerate(rows):
                cap=store.capture(r["capture_id"])
                filename=f"bancada_sinal_{index+1}.png"
                export_curve(cap,r,folder/filename,session["config"].get("vref",3.3),unit="ADC")
                images+=f'<h2>Sinal bruto de bancada {index+1}</h2><img src="{filename}">'
                st=r.get("estatisticas",{})
                technical+=table([("Captura",r["capture_id"]),("Amostras",len(cap.adc)),("Desvio padrão ADC",st.get("desvio_padrao")),
                                  ("Pico a pico ADC",st.get("pico_a_pico")),("Fração no rail",st.get("fracao_rail")),
                                  ("Temporização válida no critério",st.get("temporizacao_valida")),("Metadados",cap.meta)])
    else:
        table_rows=[("Capturas válidas / totais",f"{stats['valid']} / {stats['total']}"),
                    ("Média G2G (ms)",stats["g2g_ms"]["mean"] if stats["g2g_ms"] else "N/D"),
                    ("Média subidas (ms)",stats["subidas"]),("Média descidas (ms)",stats["descidas"]),
                    ("Média excesso no alvo (%)",stats["overshoot_pct"]["mean"] if stats["overshoot_pct"] else "N/D")]
        technical="<h2>Resultados</h2>"+table(table_rows)
        technical+="<p>Subidas e descidas agrupam pares diferentes. A diferença entre as médias não isola uma causa física.</p>"
        technical+='<table width="100%"><tr><th>Transição / rep.</th><th>Fase</th><th>G2G ms</th><th>Pico %</th><th>Validade / motivo</th></tr>'
        for r in rows:
            good=r.get("valida",False)
            g=f"{r['g2g_ms']:.3f}" if good else "N/D";pk=f"{r['overshoot_pct']:.2f}" if good else "N/D"
            technical+=f"<tr><td>{r['origem_rgb']}→{r['destino_rgb']} / {r['repetition']}</td><td>{e(r['phase'])}</td><td>{g}</td><td>{pk}</td><td>{e('Válida no algoritmo' if good else '; '.join(describe(v) for v in r.get('motivos',[])))}</td></tr>"
        technical+="</table>"
        from dataclasses import replace
        from .analysis import analyze
        from .config import TestConfig
        delta=[]
        for r in rows:
            if r["phase"]!="medicao" or not r.get("valida"):continue
            from .core.nucleo import Criterios
            c=Criterios(**r.get("criterios",{}))
            raw_result=analyze(store.capture(r["capture_id"]),r["origem_rgb"],r["destino_rgb"],replace(c,mediana_amostras=1))
            if raw_result.get("valida"):
                delta.append((r["g2g_ms"]-raw_result["g2g_ms"],r["overshoot_pct"]-raw_result["overshoot_pct"]))
        if delta:
            d=np.asarray(delta)
            technical+="<h2>Efeito do processamento em relação ao bruto</h2>"+table([
                ("Capturas comparáveis",len(delta)),("Δ G2G médio (processado − bruto), ms",float(np.mean(d[:,0]))),
                ("Maior |Δ G2G|, ms",float(np.max(abs(d[:,0])))),("Δ pico médio, pontos percentuais",float(np.mean(d[:,1]))),
                ("Maior |Δ pico|, pontos percentuais",float(np.max(abs(d[:,1]))))])
    names={"monitor":"Monitor","refresh_hz":"Atualização (Hz)","overdrive":"Overdrive","brightness":"Brilho","contrast":"Contraste","resolution":"Resolução","warmup_min":"Aquecimento registrado (min)","sensor_position":"Posição do sensor","ambient":"Ambiente","amplifier":"Amplificador","adc":"ADC","channel":"Canal","vref":"VREF informada (V)","supply_v":"Alimentação do operacional (V)","attenuation_k":"Fator físico V_ADC / V_saida","rf_kohm":"Rf fixo (kΩ)","cf_pf":"Cf fixo (pF)","assembly":"Montagem","gain_mode":"Modo de ganho","gain_range":"Faixa manual","auto_target":"Teto relativo dos pilotos","auto_settle_ms":"Espera de ganho (ms)","rate_sps":"Taxa solicitada (S/s)","window_ms":"Janela (ms)","pre_ms":"Pré-estímulo (ms)","hold_ms":"Espera inicial (ms)","spi_hz":"SPI (Hz)","levels":"Níveis da matriz","repetitions":"Repetições por par","custom_pairs":"Pares personalizados","randomize":"Ordem aleatória","seed":"Semente da ordem","screen":"Tela do estímulo","full_screen":"Tela cheia","patch_percent":"Largura/altura do retângulo (%)","static_references":"Referências antes/depois","notes":"Notas"}
    names.update(patch_pixels="Lado do retângulo original (px)",background_rgb="Cinza do fundo",hdr="HDR",vrr="VRR")
    skip={"criteria","gain_calibration","title"}
    if session["config"].get("gain_mode")=="Fixo":skip.update(("gain_range","auto_target","auto_settle_ms"))
    condition_items=[(names.get(k,k),v) for k,v in session["config"].items() if k not in skip]
    condition_items.append(("Critérios da configuração",session["config"].get("criteria",{})))
    revisions={r.get("analysis_version") or "N/D" for r in rows}
    criteria={json_text(r.get("criterios",{})) for r in rows}
    condition_items += [("Versões das análises exportadas",", ".join(sorted(revisions))),
                        ("Critérios efetivamente aplicados", " | ".join(sorted(criteria)))]
    text=f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>{e(session['title'])}</title>
    <style>body{{font:14px 'Segoe UI',sans-serif;color:#172c45;max-width:1100px;margin:32px auto}}h1{{color:#087bb6}}h2{{margin-top:28px}}table{{border-collapse:collapse;width:100%;font-size:11px}}td,th{{border:1px solid #d2deeb;padding:7px;text-align:left;overflow-wrap:anywhere}}th{{background:#eaf3fb}}img{{max-width:100%;height:auto}}.notice{{padding:14px;background:#eef5fc;border-left:4px solid #087bb6}}@media print{{body{{margin:0}}h2{{page-break-after:avoid}}tr,img{{page-break-inside:avoid}}}}</style>
    <h1>Íris · {e(session['title'])}</h1><p>{e(sid)} · {e(session['created'])} · {e(session['status'])}</p>
    {'<p class="notice"><b>SIMULAÇÃO — sem aquisição física.</b></p>' if session['simulation'] else ''}
    <p class="notice">{e(LIMITATIONS)}</p><h2>Objetivo e condições</h2>{table(condition_items)}
    {technical}<h2>Referências de método</h2><p>IDMS v1.3, seção 10.2 (resposta temporal); VESA Adaptive-Sync Display CTS r1.1a, seção 7. O Íris utiliza referências parciais desses métodos, com critérios próprios documentados.</p>
    {images}<h2>Conclusão do operador</h2><p>{e(conclusion or 'Pendente: revisar identificação da montagem, dados inválidos e limitações antes de concluir. Nenhuma superioridade de componente é inferida automaticamente.')}</p>
    <h2>Rastreabilidade</h2><p>Dados brutos com SHA-256; análises em revisões. Os CSV e a sessão ZIP permitem reabrir as aquisições. Referências e pilotos ficam separados dos resultados finais.</p>
    </html>'''
    path=folder/"relatorio.html";path.write_text(text,encoding="utf8")
    if include_samples:
        export_csv(store,sid,folder/"dados")
    else:
        write_csv(folder/'resultados.csv',rows)
    return path


def report_pdf(html_path,pdf_path):
    from PySide6.QtCore import QUrl, QMarginsF
    from PySide6.QtGui import QTextDocument, QPageSize
    from PySide6.QtPrintSupport import QPrinter
    doc=QTextDocument()
    doc.setBaseUrl(QUrl.fromLocalFile(str(Path(html_path).resolve().parent)+"/"))
    doc.setHtml(Path(html_path).read_text(encoding="utf8").replace("margin:32px auto","margin:0"))
    doc.setDocumentMargin(0)
    # QTextDocument não aplica max-width de CSS. Limita cada imagem à largura A4 útil.
    from PySide6.QtGui import QTextBlock, QTextImageFormat
    block=doc.begin()
    while block.isValid():
        it=block.begin()
        while not it.atEnd():
            fragment=it.fragment()
            if fragment.isValid() and fragment.charFormat().isImageFormat():
                fmt=fragment.charFormat().toImageFormat()
                from PySide6.QtGui import QImage, QTextCursor
                im=QImage(str(Path(html_path).parent/fmt.name()))
                if not im.isNull():
                    name=(Path(html_path).parent/fmt.name()).resolve().as_uri()
                    doc.addResource(QTextDocument.ResourceType.ImageResource,QUrl(name),im)
                    fmt.setName(name);fmt.setWidth(680);fmt.setHeight(680*im.height()/im.width())
                    cursor=QTextCursor(doc);cursor.setPosition(fragment.position());cursor.movePosition(QTextCursor.MoveOperation.NextCharacter,QTextCursor.MoveMode.KeepAnchor);cursor.setCharFormat(fmt)
            it+=1
        block=block.next()
    printer=QPrinter(QPrinter.PrinterMode.HighResolution)
    # QTextDocument mede tamanhos CSS em pixels no dispositivo de impressão.
    # Usar 1200 dpi encolheria fontes px das tabelas. PDF mantém texto vetorial e
    # imagens originais; 96 dpi aqui define apenas a unidade lógica do layout.
    printer.setResolution(96)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat);printer.setOutputFileName(str(pdf_path))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageMargins(QMarginsF(12,14,12,14))
    # Documento já paginado: evita a margem adicional de 2 cm que print_ aplica
    # a um QTextDocument sem pageSize, o que cortaria gráficos lateralmente.
    from PySide6.QtCore import QSizeF,QRectF,Qt
    from PySide6.QtGui import QPainter,QFont,QColor
    size=printer.pageRect(QPrinter.Unit.DevicePixel).size()
    width,height=size.width(),size.height()-32
    doc.setPageSize(QSizeF(width,height))
    printer.setDocName(doc.metaInformation(QTextDocument.MetaInformation.DocumentTitle) or "Relatório Íris")
    printer.setCreator(f"Íris Desktop {__version__}")
    painter=QPainter(printer)
    if not painter.isActive():raise OSError("Não foi possível iniciar o PDF. Confira o caminho e se o arquivo está aberto em outro programa.")
    pages=doc.pageCount()
    try:
        for page in range(pages):
            if page and not printer.newPage():raise OSError("Falha ao criar página do PDF.")
            painter.save();painter.setClipRect(QRectF(0,0,width,height));painter.translate(0,-page*height)
            doc.drawContents(painter,QRectF(0,page*height,width,height));painter.restore()
            painter.setFont(QFont("Segoe UI",8));painter.setPen(QColor("#61758b"))
            painter.drawText(QRectF(0,height+8,width,20),Qt.AlignmentFlag.AlignCenter,f"Íris Desktop {__version__}  |  {page+1} / {pages}")
    finally:painter.end()
