from copy import deepcopy
from pathlib import Path
import json
import subprocess
import zipfile
import numpy as np
import pytest
from iris_desktop.campaign import Campaign,planned_steps,PROFILES,LEVELS,CAPS,task
from iris_desktop.campaign_export import export_campaign
from iris_desktop.storage import Store
from iris_desktop.device import synthetic_capture
from iris_desktop.analysis import analyze
from iris_desktop.config import TestConfig
from iris_desktop.publication import campaign_packages


def small_session(c,step,tasks=None):
    s=c.step(step);s['tasks']=tasks or [task(0,255),task(255,0)]
    cfg=c.config(s,0,'1920×1080');sid=c.store.session(cfg.title,cfg.to_dict(),simulation=True)
    c.attach(s,sid)
    for t in s['tasks']:
        cap=synthetic_capture(t['origin'],t['destination']);c.store.save_capture(sid,cap,t,analyze(cap,t['origin'],t['destination']))
    c.store.finish(sid);c.complete(s,'concluida');return s,sid


def test_plan_uses_exact_settings_seven_complete_matrices_and_isolated_caps(tmp_path):
    c=Campaign.create(Store(tmp_path));steps=c.data['steps']
    main=[s for s in steps if s['kind']=='monitor']
    assert len(main)==7
    assert sum(sum(t['phase']=='medicao' for t in s['tasks']) for s in main)==2520
    for s in main:
        assert len(s['tasks'])==378
        assert len({(t['origin'],t['destination']) for t in s['tasks'] if t['phase']=='medicao'})==72
        cfg=c.config(s,0,'1920×1080');cfg.validate()
        w,h=cfg.patch_dimensions(1920,1080)
        assert w==h and abs(w*h/(1920*1080)-.1)<.001
        if s['monitor']=='LG':
            assert cfg.monitor_settings['adaptive_sync']=='Extended'
            assert cfg.monitor_settings['R']==45 and cfg.contrast=='50'
        if s['monitor']=='AOC':assert cfg.brightness==cfg.contrast==''
    for s in steps:
        c.config(s,0,'1920×1080').validate()
        if s['id'].startswith('caps_') and s['id'] not in ('caps_reference','caps_restored'):
            assert sum(s['caps'][k]!=v for k,v in CAPS.items())==1
            assert s['caps']['C_MID_100nF'] is True
    cfg=c.config(c.step('caps_bulk_uF'),0,'1920×1080')
    assert cfg.capacitors['bulk_uF']==0 and cfg.cf_pf==8.2


def test_checkpoint_recovers_by_saved_task_and_preserves_attempt(tmp_path):
    store=Store(tmp_path);c=Campaign.create(store);s=c.data['steps'][0]
    cfg=c.config(s,0,'1920×1080');sid=store.session(cfg.title,cfg.to_dict());c.attach(s,sid)
    t=s['tasks'][0];cap=synthetic_capture(t['origin'],t['destination'])
    cid=store.save_capture(sid,cap,t)  # queda entre salvar bruto e analisar
    digest=store.rows(sid)[0]['raw_file'];before=(store.root/digest).read_bytes()
    loaded=Campaign.load(store,c.data['id']);s=loaded.data['steps'][0]
    assert s['status']=='interrompida' and len(loaded.remaining(s))==len(s['tasks'])-1
    loaded.prepare_resume(s);assert store.rows(sid)[0]['analysis_version']
    assert (store.root/digest).read_bytes()==before
    loaded.repeat(s)
    assert s['session_id'] is None and sid in s['attempts'] and len(loaded.remaining(s))==len(s['tasks'])
    assert store.capture(cid).adc.shape==(3000,)


def test_resume_qt_keeps_session_and_does_not_duplicate_saved_capture(qapp,tmp_path):
    from test_qt_integration import FakeClient,until,config
    from iris_desktop.acquisition import Acquisition
    store=Store(tmp_path);device=FakeClient();acq=Acquisition(device,store);ends=[]
    acq.finished.connect(lambda *x:ends.append(x));cfg=config()
    tasks=[task(0,255),task(255,0)]
    acq.start(cfg,tasks=tasks);until(qapp,lambda:acq.capture_pending);acq.cancel();until(qapp,lambda:bool(ends))
    sid=ends[0][0];original=store.rows(sid)[0]['capture_id']
    progress=[];acq.progress_detail.connect(progress.append)
    acq.start(cfg,sid=sid,tasks=tasks[1:]);until(qapp,lambda:len(ends)==2)
    assert len(store.rows(sid))==2 and store.rows(sid)[0]['capture_id']==original
    assert ends[-1]==(sid,'concluida')
    assert progress[-1]['measurement_done']==progress[-1]['measurement_total']==2
    assert progress[-1]['completed']==progress[-1]['total']==2


def test_export_keeps_raw_revisions_and_includes_filter_comparison_and_public_packets(qapp,tmp_path):
    c=Campaign.create(Store(tmp_path/'data'));s,sid=small_session(c,'monitor_LG_180_Fast')
    ids=[r['capture_id'] for r in c.store.rows(sid)];revisions=[c.store.revisions(i) for i in ids]
    original=[c.store.capture(i).adc.copy() for i in ids]
    result=export_campaign(c);folder=Path(result['folder']);path=Path(result['path'])
    assert path.is_file() and (folder/'ABRIR_CAMPANHA.html').exists()
    assert (folder/'processamento_comparacao.csv').read_text(encoding='utf-8-sig').count('\n')==9
    assert list(folder.rglob('relatorio.pdf'))
    assert len(s['publications'])>=1
    report=json.loads(Path(s['publications'][0]['path']).read_text())
    assert report['simulation'] and len(report['results'])==2
    assert report['conditions']['campaign_id']==c.data['id']
    assert 'DAS Mode: On' in report['conditions']['monitor_settings']
    with zipfile.ZipFile(path) as z:assert any(n.endswith('sessao_original.zip') for n in z.namelist())
    assert [c.store.revisions(i) for i in ids]==revisions
    assert all(np.array_equal(c.store.capture(i).adc,raw) for i,raw in zip(ids,original))


def test_public_split_keeps_all_repetitions_under_limit(tmp_path,monkeypatch):
    import iris_desktop.publication as module
    c=Campaign.create(Store(tmp_path/'data'))
    s,sid=small_session(c,'monitor_LG_180_Fast',[task(0,255,r) for r in range(1,31)])
    monkeypatch.setattr(module,'MAX_BYTES',100000)
    paths=campaign_packages(c.store,sid,tmp_path/'public')
    assert len(paths)>1
    results=[]
    for i,path in enumerate(paths,1):
        assert path.stat().st_size<=100000
        p=json.loads(path.read_text());assert p['conditions']['report_part']==i
        assert p['conditions']['report_parts']==len(paths)
        assert len(p['results'])<=512;results.extend(p['results'])
    assert sorted(r['repetition'] for r in results)==list(range(1,31))


def test_wizard_runs_without_setting_technical_parameters(qapp,tmp_path,monkeypatch):
    from test_qt_integration import FakeClient,until
    import iris_desktop.ui.window as module
    monkeypatch.setattr(module,'DeviceClient',FakeClient)
    w=module.MainWindow(Store(tmp_path));w.guard=lambda f:f();w.show()
    page=w.campaign;page.create();c=page.campaign;s=c.data['steps'][0]
    s['tasks']=[task(0,255)];s['hz']=round(qapp.screens()[0].refreshRate());c.save();page.select(s)
    page.autorun.setChecked(False);page.warmed.setChecked(True);page.confirm.setChecked(True)
    page.begin();until(qapp,lambda:page.active is None)
    assert len(w.store.rows(s['session_id']))==1
    assert s['status']=='concluida'
    cfg=w.store.get_session(s['session_id'])['config']
    assert cfg['rf_kohm']==235 and cfg['patch_area_percent']==10
    assert cfg['monitor_settings']['DAS Mode']=='On'
    w.close();qapp.processEvents()


def test_diagnostic_adapts_once_without_relaxing_criteria_and_retry_preserves_source(tmp_path):
    c=Campaign.create(Store(tmp_path/'data'));s,sid=small_session(c,'diag_LG')
    cid=c.store.rows(sid)[0]['capture_id'];r=c.store.rows(sid)[0]
    r.update(valida=False,motivos=['patamar_final_instavel']);c.store.save_analysis(cid,r)
    criteria=c.store.get_session(sid)['config']['criteria']
    assert c.adapt_diagnostic(s,'concluida')
    assert s['window_ms']==600 and s['session_id'] is None and sid in s['attempts']
    cfg=c.config(s,0,'1920×1080');assert cfg.criteria==criteria
    assert not c.adapt_diagnostic(s,'concluida')
    s['session_id']=sid
    new=c.retry_invalid(s)
    assert new['source_session']==sid and new['kind']=='reteste'
    assert len(new['tasks'])==1 and new['tasks'][0]['origin']==0
    assert len(c.store.rows(sid))==2


def test_export_job_runs_in_background_with_pdf_and_survives_ui_events(qapp,tmp_path):
    from test_qt_integration import until
    from iris_desktop.ui.campaign_page import CampaignJob
    c=Campaign.create(Store(tmp_path/'data'));small_session(c,'monitor_LG_180_Fast')
    result=[];errors=[]
    worker=CampaignJob(lambda progress:export_campaign(c,progress))
    worker.completed.connect(result.append);worker.failed.connect(errors.append);worker.start()
    from PySide6.QtCore import QEventLoop,QTimer
    loop=QEventLoop();worker.completed.connect(loop.quit);worker.failed.connect(loop.quit)
    deadline=QTimer();deadline.setSingleShot(True);deadline.timeout.connect(loop.quit);deadline.start(30000)
    loop.exec();deadline.stop()
    worker.wait(5000)
    assert not errors
    assert Path(result[0]['path']).exists()
