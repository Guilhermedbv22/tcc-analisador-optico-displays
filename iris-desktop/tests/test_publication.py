import json
from pathlib import Path
import numpy as np
import pytest
from iris_desktop.storage import Store
from iris_desktop.config import TestConfig
from iris_desktop.device import synthetic_capture
from iris_desktop.analysis import analyze
from iris_desktop.publication import build_public_report, generate_package, preview_curve, site_url


def session(tmp_path):
    s=Store(tmp_path/'data')
    c=TestConfig(monitor='Monitor teste',overdrive='Fast').to_dict()
    c.update(notes='PRIVATE_NOTE',local_path='C:/PRIVATE_PATH',port='COM77')
    sid=s.session('Teste público',c,simulation=True)
    cap=synthetic_capture();s.save_capture(sid,cap,dict(origin=0,destination=255,repetition=1,phase='medicao'),analyze(cap,0,255));s.finish(sid)
    return s,sid


def test_public_contract_privacy_metrics_and_simulation(tmp_path):
    s,sid=session(tmp_path);r=build_public_report(s,sid)
    assert r['simulation'] is True
    assert r['monitor']['model']=='Monitor teste'
    assert r['results'][0]['g2g_ms']==s.rows(sid)[0]['g2g_ms']
    assert len(r['results'][0]['curve']['points'])<=600
    assert not any(x in json.dumps(r) for x in ('PRIVATE_NOTE','PRIVATE_PATH','COM77','raw_file','capture_id'))


def test_envelope_keeps_raw_and_filtered_extrema(tmp_path):
    s,sid=session(tmp_path);row=s.rows(sid)[0];cap=s.capture(row['capture_id'])
    from iris_desktop.analysis import curve
    _,raw,filtered=curve(cap,row,unit='%')
    public=preview_curve(cap,row,max_points=100)
    pts=np.asarray(public['points'])
    assert len(pts)<=100
    assert pts[:,1].max()==pytest.approx(float(raw.max()),abs=1e-5)
    assert pts[:,1].min()==pytest.approx(float(raw.min()),abs=1e-5)
    assert pts[:,2].max()==pytest.approx(float(filtered.max()),abs=1e-5)
    assert np.all(np.diff(pts[:,0])>0)


def test_package_pdf_and_public_html(tmp_path,qapp):
    s,sid=session(tmp_path);path=generate_package(s,sid,tmp_path/'report')
    r=json.loads(path.read_text())
    assert 'relatorio.pdf' in r['assets']
    assert (path.parent/'relatorio.pdf').read_bytes().startswith(b'%PDF')
    assert 'PRIVATE_NOTE' not in (path.parent/'relatorio.html').read_text()
    assert not (path.parent/'publicacao-recibo.json').exists()


def test_publication_tab_is_connected_to_analysis(tmp_path,qapp):
    from iris_desktop.ui.window import MainWindow
    s,sid=session(tmp_path);window=MainWindow(s)
    try:
        window.navigate(8)
        assert window.publication.sessions.findData(sid)>=0
        window.analysis.open_session(sid);window.analysis.publish_report()
        assert window.stack.currentIndex()==8
        assert window.publication.sessions.currentData()==sid
        assert window.publication.model.text()=='Monitor teste'
    finally:
        window.close();qapp.processEvents()


def test_reject_unidentified_monitor_active_session_and_bad_urls(tmp_path):
    s,sid=session(tmp_path)
    with pytest.raises(ValueError):build_public_report(s,sid,dict(model=''))
    sid2=s.session('Andamento',TestConfig(monitor='Test',overdrive='Fast').to_dict())
    with pytest.raises(ValueError,match='Encerre'):build_public_report(s,sid2)
    for url in ('http://example.com','https://x.com/api','https://u:p@x.com','https://x.com/?secret=abc'):
        with pytest.raises(ValueError):site_url(url)
    assert site_url('https://tcc-iris.netlify.app/')=='https://tcc-iris.netlify.app'


def test_client_upload_headers_receipt_and_retry(tmp_path,monkeypatch):
    from iris_desktop.publication import publish_package
    import urllib.request
    path=tmp_path/'relatorio.iris.json';path.write_text(json.dumps({'schema':'iris-report/1','assets':{}}))
    requests=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return json.dumps({'id':'a'*32,'duplicate':len(requests)>1,'can_delete':True}).encode()
    def opener(request,timeout):
        requests.append(request);assert timeout==60;assert request.full_url=='https://tcc-iris.netlify.app/api/publish'
        assert request.get_method()=='POST'
        assert request.get_header('Content-type')=='application/json'
        assert request.data==path.read_bytes()
        return Response()
    monkeypatch.setattr(urllib.request,'urlopen',opener)
    first=publish_package(path);second=publish_package(path)
    assert first['delete_token']==second['delete_token']
    assert requests[0].get_header('X-iris-delete-token')==first['delete_token']
    assert second['duplicate'] is True
    assert second['url']=='https://tcc-iris.netlify.app/?relatorio='+'a'*32
    saved=json.loads((tmp_path/'publicacao-recibo.json').read_text())
    assert saved['state']=='publicado'
    assert saved['delete_token'] not in path.read_text()


def test_client_network_failure_keeps_receipt(tmp_path,monkeypatch):
    from iris_desktop.publication import publish_package
    import urllib.request, urllib.error
    path=tmp_path/'relatorio.iris.json';path.write_text(json.dumps({'schema':'iris-report/1'}))
    def fail(*args,**kwargs):raise urllib.error.URLError('offline')
    monkeypatch.setattr(urllib.request,'urlopen',fail)
    with pytest.raises(ValueError,match='tente novamente'):publish_package(path)
    receipt=json.loads((tmp_path/'publicacao-recibo.json').read_text())
    assert len(receipt['delete_token'])>=32
    assert path.exists()
