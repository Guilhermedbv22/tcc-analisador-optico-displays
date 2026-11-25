"""Fluxo Qt com dispositivo falso explícito: não é validação elétrica."""
from dataclasses import replace
import time
from pathlib import Path
import numpy as np
import pytest
from PySide6.QtCore import QObject,Signal,QTimer
from PySide6.QtTest import QTest
from iris_desktop.acquisition import Acquisition
from iris_desktop.config import TestConfig
from iris_desktop.storage import Store
from iris_desktop.device import synthetic_capture


def until(app,predicate,seconds=12):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline and not predicate():
        app.processEvents();QTest.qWait(5)
    assert predicate(),"Fluxo Qt não concluiu dentro do prazo"


class FakeClient(QObject):
    result=Signal(int,str,object);error=Signal(int,str,object);armed=Signal(object);collected=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.connected=True;self.ident=0;self.calls=[];self.gain=0;self.enabled=False
        self.hello=dict(protocol=4,fw="FAKE_QT",board="ESP32_CLASSIC",features=["gain4","auto_pilots"])
        self.worker=type("NoWorker",(),{"isRunning":lambda self:False})()
    def shutdown(self):pass
    def command(self,text,prefix="GAIN "):return self.submit("command",dict(command=text,prefix=prefix))
    def submit(self,kind,data=None):
        self.ident+=1;ident=self.ident;data=data or {};self.calls.append((kind,data))
        def deliver():
            out={}
            if kind=="configure":self.config=data;out=dict(source=data["fonte"])
            elif kind=="command":
                c=data["command"]
                if c=="GAIN ENABLE 1":self.enabled=True;self.gain=0
                elif c=="GAIN ENABLE 0":self.enabled=False
                elif c.startswith("GAIN SET "):self.gain=int(c.split()[-1])
                if c.startswith("AUTO START"):self.gain=0;out=dict(status="TRY",range=0)
                elif c=="AUTO EVAL":
                    if self.gain<2:self.gain+=1;out=dict(status="TRY",range=self.gain)
                    else:self.gain=1;out=dict(status="LOCKED",range=1)
                elif c=="AUTO STOP":out=dict(status="STOPPED")
                else:out=dict(enabled=self.enabled,range=self.gain)
            elif kind=="stat":
                out=dict(source=data["source"],channel=data["channel"],mean_raw=1000+data["channel"],min_raw=999+data["channel"],max_raw=1001+data["channel"],std_raw=.5,n=64)
            elif kind=="capture":
                self.armed.emit(dict(job=data,monotonic_s=time.monotonic()))
                task=data.get("task",dict(origin=0,destination=0))
                out=synthetic_capture(task["origin"],task["destination"])
                out.meta.update(gain_enabled=self.enabled,gain_range=self.gain)
                def later():self.collected.emit();self.result.emit(ident,kind,out)
                QTimer.singleShot(160,later);return
            self.result.emit(ident,kind,out)
        QTimer.singleShot(0,deliver)
        return ident


def config():
    return TestConfig(custom_pairs="0>255,255>0",hold_ms=100,pre_ms=40,full_screen=False)


def test_qt_fixed_pipeline_and_preserved_packets(qapp,tmp_path):
    d=FakeClient();s=Store(tmp_path);a=Acquisition(d,s);ends=[];a.finished.connect(lambda *x:ends.append(x))
    progress=[];a.progress_detail.connect(progress.append)
    a.start(config());until(qapp,lambda:bool(ends))
    sid,status=ends[0];rows=s.rows(sid)
    assert status=="concluida" and len(rows)==2 and all(r["valida"] for r in rows)
    assert all(r["meta"]["host_stimulus_after_arm_ms"]>=35 for r in rows)
    assert all(len(s.capture(r["capture_id"]).adc)==3000 for r in rows)
    live=[p for p in progress if p["running"] and p["task"]]
    assert live[0]["measurement_done"]==0 and live[0]["measurement_total"]==2
    assert all(p["remaining_s"]>0 for p in live)
    assert progress[-1]["measurement_done"]==2 and not progress[-1]["running"]
    assert not a.progress_timer.isActive()


def test_qt_autoranging_pilots_then_gain_locked(qapp,tmp_path):
    d=FakeClient();s=Store(tmp_path);a=Acquisition(d,s);ends=[];a.finished.connect(lambda *x:ends.append(x))
    progress=[];a.progress_detail.connect(progress.append)
    a.start(replace(config(),gain_mode="Automático CD4066"));until(qapp,lambda:bool(ends))
    rows=s.rows(ends[0][0]);pilots=[r for r in rows if r["phase"].startswith("piloto")];valid=[r for r in rows if r["phase"]=="medicao"]
    assert len(pilots)==6 and len(valid)==2
    assert {r["meta"]["gain_range"] for r in valid}=={1}
    assert len([e for e in s.events(ends[0][0]) if e["type"]=="auto_decision"])==4
    assert all(p["measurement_done"]==0 for p in progress if p["pilot"])
    assert progress[-1]["measurement_done"]==progress[-1]["measurement_total"]==2


def test_cancel_waits_for_capture_and_saves(qapp,tmp_path):
    d=FakeClient();s=Store(tmp_path);a=Acquisition(d,s);ends=[];a.finished.connect(lambda *x:ends.append(x))
    a.start(config());until(qapp,lambda:a.capture_pending)
    a.cancel();assert a.running
    until(qapp,lambda:bool(ends))
    assert ends[0][1]=="cancelada" and len(s.rows(ends[0][0]))==1
    assert not a.progress_timer.isActive()


def test_full_window_bench_and_raw_capture(qapp,tmp_path,monkeypatch):
    import iris_desktop.ui.window as module
    monkeypatch.setattr(module,"DeviceClient",FakeClient)
    w=module.MainWindow(Store(tmp_path));w.guard=lambda f:f();w.show()
    for index,channel in enumerate(w.bench.channels):channel.setChecked(index<3)
    w.bench.begin()
    until(qapp,lambda:len(w.bench.data)>=3)
    w.bench.end();until(qapp,lambda:not w.bench.running)
    assert len(w.store.bench_rows(w.bench.sid))>=3
    assert w.bench.latest[0]["mean_raw"]==1000
    w.bench.snapshot();until(qapp,lambda:not w.bench.snapshot_pending)
    assert len(w.store.rows(w.bench.sid))==1
    assert w.store.get_session(w.bench.sid)["kind"]=="bancada"
    w.close();qapp.processEvents()


def test_window_real_data_and_resize_without_overlaid_legend(qapp,tmp_path,sample_path):
    from iris_desktop.importers import import_monitor
    from iris_desktop.ui.window import MainWindow
    s=Store(tmp_path);sid=import_monitor(s,sample_path("LG_Fast_medicao_original.zip"))[0]["session_id"]
    w=MainWindow(s);w.guard=lambda f:f();w.show();w.analysis.open_session(sid);w.navigate(2)
    for width,height in [(1280,800),(1024,720)]:
        w.resize(width,height);qapp.processEvents()
        assert w.analysis.view.plot.geometry().bottom()<w.analysis.view.cursor_label.geometry().top()
        assert w.analysis.view.plot.height()>=260
        for i in range(w.analysis.view.legend.count()):
            item=w.analysis.view.legend.itemAt(i)
            assert item.widget().geometry().top()>w.analysis.view.plot.geometry().bottom()
    w.close();until(qapp,lambda:not w.device.worker.isRunning());w.close()


def test_comparison_keeps_zero_signal_visible_and_help_offline(qapp,tmp_path,monkeypatch):
    import iris_desktop.ui.window as module
    from iris_desktop.analysis import analyze
    from iris_desktop.ui.help_viewer import HelpViewer
    monkeypatch.setattr(module,"DeviceClient",FakeClient)
    s=Store(tmp_path);ids=[]
    for zero in (False,True):
        cfg=config().to_dict();cfg["adc"]="INTERNO" if zero else "MCP3208"
        sid=s.session("ZERO" if zero else "Sinal",cfg,simulation=True);ids.append(sid)
        c=synthetic_capture();c.meta["source"]=cfg["adc"]
        if zero:c.adc[:]=0
        s.save_capture(sid,c,dict(origin=0,destination=255,repetition=1,phase="medicao"),analyze(c,0,255))
    w=module.MainWindow(s);w.guard=lambda f:f();w.show();w.navigate(3)
    for cb,sid in zip(w.compare.selectors,ids):cb.setCurrentIndex(cb.findData(sid))
    qapp.processEvents()
    assert len(w.compare.export_rows)==2
    assert w.compare.export_rows[1]["g2g_ms"] is None
    assert w.compare.export_rows[1]["rail_pct"]==100
    assert "códigos ADC" in w.compare.warning.text()
    d=HelpViewer(Path(__file__).parents[1]/"docs/CIRCUITO_A.md",w);d.show();qapp.processEvents()
    assert "MCP6022" in d.browser.toPlainText()
    d.close();w.close();qapp.processEvents()

def test_actual_two_adc_session_filters_same_rate(qapp,tmp_path,monkeypatch,sample_path):
    import iris_desktop.ui.window as module
    from iris_desktop.importers import import_monitor
    monkeypatch.setattr(module,"DeviceClient",FakeClient)
    s=Store(tmp_path);out=import_monitor(s,sample_path("ADC_MCP3208_INTERNO_original.zip"))
    assert out[0]["captures"]==36 and out[0]["failures"]==0
    sid=out[0]["session_id"];rows=s.rows(sid,False)
    assert len([r for r in rows if r["meta"]["source"]=="MCP3208" and r["valida"]])==18
    assert not any(r["valida"] for r in rows if r["meta"]["source"]=="INTERNO")
    w=module.MainWindow(s);w.guard=lambda f:f();w.show();w.navigate(3)
    for cb in w.compare.selectors:cb.setCurrentIndex(cb.findData(sid))
    w.compare.source_filters[0].setCurrentText("MCP3208");w.compare.source_filters[1].setCurrentText("INTERNO")
    w.compare.rate_filter.setCurrentIndex(w.compare.rate_filter.findData(100));qapp.processEvents()
    assert len(w.compare.export_rows)==2
    for row in w.compare.export_rows:assert s.capture(row["capture_id"]).meta["period_us"]==100
    assert "A 18/18" in w.compare.interpretation.text() and "B 0/18" in w.compare.interpretation.text()
    w.close();qapp.processEvents()


def test_standard_capture_ignores_advanced_settings_and_opens_results(qapp,tmp_path,monkeypatch):
    import iris_desktop.ui.window as module
    monkeypatch.setattr(module,"DeviceClient",FakeClient)
    store=Store(tmp_path)
    cfg=TestConfig(monitor="Monitor de teste",overdrive="Normal",adc="INTERNO",custom_pairs="0>255")
    store.set_setting("last_config",cfg.to_dict())
    w=module.MainWindow(store)
    try:
        w.show();w.navigate(1)
        assert not w.technical_mode.isChecked()
        assert not w.measure.tabs.isTabVisible(2)
        assert w.measure.config().adc=="MCP3208"
        assert w.measure.config().rate_sps==10000
        w.measure.low.setText("entrada parcial")  # Hidden advanced entry cannot stop a standard capture.
        w.measure.begin()
        until(qapp,lambda:not w.acquisition.running)
        assert w.stack.currentIndex()==2
        assert w.analysis.rows[0]["valida"]
        assert store.setting("last_config")["adc"]=="INTERNO"
        w.technical_mode.setChecked(True)
        assert w.measure.tabs.isTabVisible(2)
        w.measure.low.clear()
        assert w.measure.config().adc=="INTERNO"
    finally:
        w.close();qapp.processEvents()
