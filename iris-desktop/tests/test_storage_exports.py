from pathlib import Path
import json
import zipfile
import numpy as np
import pytest
from iris_desktop.storage import Store
from iris_desktop.config import TestConfig
from iris_desktop.device import synthetic_capture
from iris_desktop.analysis import analyze,summary
from iris_desktop.importers import import_monitor,import_bench_csv,import_native_session
from iris_desktop.importers import old_config
from iris_desktop.exports import export_csv,export_native,export_curve,export_overview,report_html,report_pdf

ROOT=Path(__file__).parents[1]

def make(store):
    sid=store.session("Teste",TestConfig().to_dict(),simulation=True)
    cap=synthetic_capture();cid=store.save_capture(sid,cap,dict(origin=0,destination=255,repetition=1,phase="medicao"),analyze(cap,0,255))
    store.finish(sid);return sid,cid

def test_raw_hash_and_revisions(tmp_path):
    s=Store(tmp_path/"data");sid,cid=make(s)
    path=s.root/s.rows(sid)[0]["raw_file"];before=path.read_bytes()
    s.save_analysis(cid,analyze(s.capture(cid),0,255))
    assert len(s.revisions(cid))==2 and before==path.read_bytes()
    path.write_bytes(before+b"x")
    with pytest.raises(ValueError,match="SHA-256"):s.capture(cid)

def test_ground_stat_and_legacy_extrema(tmp_path):
    s=Store(tmp_path);sid=s.session("GND",{},kind="bancada")
    assert s.bench_add(sid,0,0,dict(source="MCP3208",mean_raw=0),3.3)==0
    row=s.bench_rows(sid)[0];assert row["min_raw"] is None and row["max_raw"] is None
    assert s.bench_add(sid,1,0,dict(source="MCP3208",mean_raw=0,min_raw=None,max_raw=None),3.3)==0
    with pytest.raises(ValueError):s.bench_add(sid,1,0,dict(source="MCP3208",mean_raw=5000),3.3)
    with pytest.raises(ValueError):s.bench_add(sid,1,0,dict(source="MCP3208",mean_raw=100,channel=1),3.3)

def test_real_legacy_30_curves_reproduce(tmp_path,sample_path):
    s=Store(tmp_path)
    imported=import_monitor(s,sample_path("LG_Fast_medicao_original.zip"))
    assert len(imported)==1 and imported[0]["captures"]==30 and imported[0]["failures"]==0
    sid=imported[0]["session_id"];rows=s.rows(sid);stats=summary(rows)
    assert stats["valid"]==30
    assert stats["g2g_ms"]["mean"]==pytest.approx(3.71828,abs=1e-5)
    assert stats["overshoot_pct"]["mean"]==pytest.approx(2.26783,abs=1e-5)
    assert s.get_session(sid)["config"]["amplifier"]==""
    assert s.get_session(sid)["config"]["patch_pixels"]==480
    assert s.get_session(sid)["config"]["patch_percent"] is None
    assert s.get_session(sid)["config"]["seed"]==42
    assert import_monitor(s,sample_path("LG_Fast_medicao_original.zip"))==[]
    assert len(s.revisions(rows[0]["capture_id"]))==3

def test_actual_voltmeter_csv_39_readings(tmp_path,sample_path):
    s=Store(tmp_path);out=import_bench_csv(s,sample_path("pontos_seguidor_originais.csv"))
    assert sum(i["readings"] for i in out)==39 and len(out)>3
    sid=out[0]["session_id"];rows=s.bench_rows(sid)
    assert s.get_session(sid)["kind"]=="bancada"
    assert rows[0]["value_v"]==pytest.approx(1.774984,abs=1e-7)
    assert json.loads(rows[0]["payload"])["original"]["rotulo"].startswith("MCP6022")
    assert rows[1]["elapsed_s"]==pytest.approx(.083)

def test_native_export_import_roundtrip(tmp_path):
    s=Store(tmp_path/"a");sid,cid=make(s);s.event(sid,"teste",{"x":1})
    export_native(s,sid,tmp_path/"session.zip")
    dst=Store(tmp_path/"b");new=import_native_session(dst,tmp_path/"session.zip")
    assert np.array_equal(s.capture(cid).adc,dst.capture(dst.rows(new)[0]["capture_id"]).adc)
    assert dst.get_session(new)["simulation"]
    assert dst.events(new)[0]["payload"]=={"x":1}

def test_reports_and_options(tmp_path,qapp):
    s=Store(tmp_path/"data");sid,cid=make(s);row=s.rows(sid)[0]
    export_curve(s.capture(cid),row,tmp_path/"curve.png",options={"raw":True,"plateaus":False,"references":True})
    export_overview(s,sid,tmp_path/"all.png")
    p=report_html(s,sid,tmp_path/"report","Conclusão registrada pelo operador.")
    report_pdf(p,tmp_path/"report.pdf")
    assert (tmp_path/"report.pdf").read_bytes().startswith(b"%PDF")
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtCore import QSize
    document=QPdfDocument();document.load(str(tmp_path/"report.pdf"))
    blue_pixels=0
    for i in range(document.pageCount()):
        image=document.render(i,QSize(700,990)).convertToFormat(__import__('PySide6.QtGui',fromlist=['QImage']).QImage.Format.Format_RGBA8888)
        pixels=np.frombuffer(image.bits(),np.uint8).reshape(image.height(),image.width(),4)
        blue_pixels+=int(np.count_nonzero((pixels[:,:,2].astype(float)>1.2*pixels[:,:,0])&(pixels[:,:,0]<100)))
    assert blue_pixels>20000,"Gráficos devem estar incorporados e renderizados, não ícones de imagem ausente"
    assert "SIMULAÇÃO" in p.read_text() and "Conclusão registrada" in p.read_text()
    export_csv(s,sid,tmp_path/"csv")
    assert len(list((tmp_path/"csv/amostras").glob("*.csv")))==1

def test_reject_zip_path_traversal_and_preserve_error(tmp_path):
    path=tmp_path/"bad.zip"
    with zipfile.ZipFile(path,"w") as z:
        z.writestr("ensaio.json",json.dumps({"config":{},"capturas":[{"arquivo":"../../foo.csv"}]}))
    s=Store(tmp_path/"data");out=import_monitor(s,path)
    assert out[0]["failures"]==1 and s.events(out[0]["session_id"])

def test_bench_raw_capture_export_is_not_empty(tmp_path,qapp):
    s=Store(tmp_path/"data");sid=s.session("Ruído",TestConfig().to_dict(),kind="bancada",simulation=True)
    c=synthetic_capture(0,0);s.save_capture(sid,c,dict(origin=0,destination=0,repetition=1,phase="sinal_bancada"),analyze(c,0,0))
    export_csv(s,sid,tmp_path/"csv")
    assert len(list((tmp_path/"csv/amostras").glob("*.csv")))==1
    p=report_html(s,sid,tmp_path/"report")
    assert "Desvio padrão ADC" in p.read_text() and (tmp_path/"report/bancada_sinal_1.png").exists()

def test_internal_stat_csv_roundtrip_never_fabricates_volts(tmp_path):
    s=Store(tmp_path/"a");sid=s.session("Interno",{},kind="bancada")
    s.bench_add(sid,0,0,dict(source="INTERNO",mean_raw=1234),3.3)
    export_csv(s,sid,tmp_path/"csv")
    dst=Store(tmp_path/"b");out=import_bench_csv(dst,tmp_path/"csv/bancada.csv")
    row=dst.bench_rows(out[0]["session_id"])[0]
    assert row["value_v"] is None and json.loads(row["payload"])["source"]=="INTERNO"
    assert dst.get_session(out[0]["session_id"])["config"]["adc"]=="INTERNO"

def test_stat_individual_codes_integrity_and_roundtrip(tmp_path):
    s=Store(tmp_path/"a");sid=s.session("GND",{},kind="bancada")
    payload=dict(source="MCP3208",mean_raw=0,min_raw=0,max_raw=0,std_raw=0,
                 raw_codes64=[0]*64,t_us64=list(range(0,64000,1000)),read_us64=[27]*64)
    s.bench_add(sid,0,0,payload,3.3)
    with pytest.raises(ValueError):s.bench_add(sid,1,0,{**payload,"raw_codes64":[0]*63},3.3)
    export_native(s,sid,tmp_path/"bench.zip")
    dst=Store(tmp_path/"b");new=import_native_session(dst,tmp_path/"bench.zip")
    assert json.loads(dst.bench_rows(new)[0]["payload"])["raw_codes64"]==[0]*64

def test_unknown_legacy_conditions_are_not_new_app_defaults():
    cfg=old_config({})
    assert cfg.vref is None and cfg.rf_kohm is None and cfg.cf_pf is None
    assert cfg.full_screen is None and cfg.patch_percent is None


def test_import_native_windows_paths_keep_hash_metrics_and_wire(tmp_path):
    import json
    import zipfile
    from iris_desktop.device import synthetic_capture
    from iris_desktop.analysis import analyze
    from iris_desktop.exports import export_native
    from iris_desktop.importers import import_native_session

    store=Store(tmp_path/'original')
    sid=store.session('Sessão Windows', TestConfig().to_dict())
    cap=synthetic_capture(0,255)
    cap.wire=b'original serial bytes'
    result=analyze(cap,0,255)
    store.save_capture(sid,cap,dict(origin=0,destination=255,repetition=1,phase='medicao'),result)
    store.finish(sid)
    source=tmp_path/'native.zip'
    export_native(store,sid,source)
    windows_archive=tmp_path/'windows.zip'
    with zipfile.ZipFile(source) as original,zipfile.ZipFile(windows_archive,'w') as output:
        info=json.loads(original.read('export.json'))
        for row in info['captures']:
            row['raw_file']=row['raw_file'].replace('/',chr(92))
        output.writestr('export.json',json.dumps(info))
        for name in original.namelist():
            if name!='export.json':output.writestr(name,original.read(name))
    imported=Store(tmp_path/'imported')
    reconstructed=import_native_session(imported,windows_archive)
    row=imported.rows(reconstructed)[0]
    assert row['g2g_ms']==result['g2g_ms']
    assert imported.capture(row['capture_id']).wire==cap.wire
