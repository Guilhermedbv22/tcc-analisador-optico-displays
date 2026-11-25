"""Regressões das alterações 1.2: amplitude pequena, progresso, médias e grades."""
from dataclasses import replace
import numpy as np
import pytest
from iris_desktop.analysis import analyze, summary, matrix_values, matrix_text
from iris_desktop.core.nucleo import Criterios
from iris_desktop.core.protocolo import Captura
from iris_desktop.config import TestConfig
from iris_desktop.storage import Store
from iris_desktop.device import synthetic_capture
from iris_desktop.acquisition import Acquisition, Stimulus
from test_qt_integration import FakeClient, config, until


def small_capture(a=100, b=116, noise=0):
    t=np.arange(3000,dtype=np.int64)*100
    elapsed=np.maximum(t/1000-75,0)
    response=1-np.exp(-elapsed/3)
    y=a+(b-a)*response+np.random.default_rng(1).normal(0,noise,len(t))
    return Captura(t,np.clip(np.rint(y),0,4095).astype(np.uint16),
                   np.full(len(t),27,np.uint16),dict(period_us=100,source="MCP3208"))


@pytest.mark.parametrize("a,b,origin,destination",[(100,116,0,32),(116,100,32,0)])
def test_small_clean_transition_uses_snr(a,b,origin,destination):
    cap=small_capture(a,b);before=cap.adc.copy()
    old=analyze(cap,origin,destination,Criterios(amplitude_minima=20))
    new=analyze(cap,origin,destination)
    assert not old["valida"] and "sem_amplitude" in old["motivos"]
    assert new["valida"] and 5.5<new["g2g_ms"]<7.5
    assert "pequena_amplitude" in new["avisos"]
    assert np.array_equal(before,cap.adc)


def test_noise_and_unresolved_amplitude_remain_invalid():
    noisy=analyze(small_capture(noise=2),0,32)
    assert not noisy["valida"] and "relacao_sinal_ruido_insuficiente" in noisy["motivos"]
    tiny=analyze(small_capture(100,103),0,32)
    assert not tiny["valida"] and "sem_amplitude" in tiny["motivos"]
    assert noisy["g2g_ms"] is None and tiny["g2g_ms"] is None


def test_black_origin_allowed_only_when_measured_region_is_clear():
    result=analyze(small_capture(0,32),0,32)
    assert result["valida"] and "preto_inicial_no_limite_adc" in result["avisos"]
    assert not analyze(small_capture(0,16),0,32)["valida"] # limiar 10% junto ao rail
    assert not analyze(small_capture(32,0),32,0)["valida"] # pico de descida pode estar cortado
    assert not analyze(small_capture(4060,4095),32,255)["valida"]
    cap=small_capture(0,32);cap.adc[1200]=0
    assert "limite_adc_atingido" in analyze(cap,0,32)["motivos"]


def test_references_do_not_increment_measurement_progress(qapp,tmp_path):
    a=Acquisition(FakeClient(),Store(tmp_path));events=[];end=[]
    a.progress_detail.connect(events.append);a.finished.connect(lambda *args:end.append(args))
    cfg=replace(config(),static_references=True)
    assert cfg.capture_count()==6
    a.start(cfg);until(qapp,lambda:bool(end))
    before=[p for p in events if p["running"] and p["phase"]=="Referências iniciais"]
    after=[p for p in events if p["running"] and p["phase"]=="Referências finais"]
    assert before and all(p["measurement_done"]==0 for p in before)
    assert after and all(p["measurement_done"]==2 for p in after)
    assert events[-1]["completed"]==6 and events[-1]["measurement_done"]==2


def test_timer_counts_down_while_waiting_for_one_capture(qapp,tmp_path):
    class WaitingClient(FakeClient):
        def submit(self,kind,data=None):
            if kind=="capture":
                self.ident+=1
                return self.ident
            return super().submit(kind,data)
    a=Acquisition(WaitingClient(),Store(tmp_path));events=[]
    a.progress_detail.connect(events.append);a.start(config())
    until(qapp,lambda:a.capture_pending)
    until(qapp,lambda:len([p for p in events if p["task"]])>=3)
    live=[p for p in events if p["task"]]
    assert live[-1]["remaining_s"]<live[0]["remaining_s"]
    assert "RGB 0 → 255" in a.stimulus.hud and "Tempo restante" in a.stimulus.hud
    a._error(0,"capture",dict(message="timeout simulado"))
    assert not a.progress_timer.isActive() and not events[-1]["running"]


def test_progress_overlay_keeps_sensor_center_plain(qapp):
    from PySide6.QtGui import QColor
    for width,height in ((320,240),(640,480),(1920,1080)):
        stimulus=Stimulus(config());stimulus.resize(width,height);stimulus.set_gray(128)
        assert not stimulus.hud_rect().contains(stimulus.rect().center())
        image=stimulus.grab().toImage()
        assert image.pixelColor(width//2,height//2)==QColor(128,128,128)
        stimulus.deleteLater()


@pytest.mark.parametrize("levels",[9,17])
def test_large_matrix_labels_averages_and_orientation(qapp,tmp_path,monkeypatch,levels):
    import iris_desktop.ui.window as window_module
    monkeypatch.setattr(window_module,"DeviceClient",FakeClient)
    store=Store(tmp_path);cfg=TestConfig(levels=levels)
    # Verifica migração apenas da configuração padrão, mantendo sessões antigas.
    saved=cfg.to_dict();saved["criteria"]["amplitude_minima"]=20.0
    if levels==17:saved["criteria"]["snr_minimo"]=21.0 # ajuste personalizado preservado
    store.set_setting("last_config",saved)
    sid=store.session("Grade",saved,simulation=True)
    grays=[round(i*255/(levels-1)) for i in range(levels)]
    for i,a in enumerate(grays):
        b=grays[(i+1)%levels];cap=synthetic_capture(a,b);result=analyze(cap,a,b)
        result.update(g2g_ms=i+1.25,overshoot_pct=i+2.5)
        store.save_capture(sid,cap,dict(origin=a,destination=b,repetition=1,phase="medicao"),result)
    invalid=synthetic_capture();invalid.adc[:]=0
    store.save_capture(sid,invalid,dict(origin=0,destination=255,repetition=2,phase="medicao"),analyze(invalid,0,255))
    store.save_capture(sid,synthetic_capture(),dict(origin=0,destination=255,repetition=1,phase="piloto_G0"),analyze(synthetic_capture(),0,255))
    w=window_module.MainWindow(store)
    try:
        w.guard=lambda f:f();w.show();w.analysis.open_session(sid);w.navigate(2)
        assert w.measure.config(technical=True).get_criteria().amplitude_minima==(4 if levels==9 else 20)
        assert store.get_session(sid)["config"]["criteria"]["amplitude_minima"]==20
        stats=summary(store.rows(sid))
        assert w.analysis.average_response.value.text()==f"{stats['g2g_ms']['mean']:.3f} ms"
        assert w.analysis.average_overshoot.value.text()==f"{stats['overshoot_pct']['mean']:.2f}%"
        assert w.analysis.valid_count.value.text()==f"{levels} / {levels+1}"
        w.analysis.tabs.setCurrentIndex(2);qapp.processEvents()
        for metric in ("g2g_ms","overshoot_pct"):
            w.analysis.metric.setCurrentIndex(w.analysis.metric.findData(metric));qapp.processEvents()
            matrix_levels,values=matrix_values(store.rows(sid),metric)
            labels=w.analysis.heat_labels
            assert matrix_levels==grays and len(labels)==levels**2
            for text in labels:
                j,i=int(text.pos().x()),int(text.pos().y())
                assert text.toPlainText()==matrix_text(values[i,j])
        # Reanálise cria revisão e conserva o bruto, mesmo para o item antes inválido.
        before=store.capture(store.rows(sid)[0]["capture_id"]).adc.copy()
        revisions=len(store.revisions(store.rows(sid)[0]["capture_id"]))
        w.analysis.reanalyze_current()
        assert len(store.revisions(store.rows(sid)[0]["capture_id"]))==revisions+1
        assert np.array_equal(before,store.capture(store.rows(sid)[0]["capture_id"]).adc)
    finally:
        w.close();qapp.processEvents()


def test_exported_large_matrix_includes_every_cell(tmp_path,monkeypatch):
    import iris_desktop.exports as exports
    store=Store(tmp_path/"data");sid=store.session("Grade 9",TestConfig(levels=9).to_dict(),simulation=True)
    gray=[round(i*255/8) for i in range(9)]
    for a,b in zip(gray,gray[1:]+gray[:1]):
        cap=synthetic_capture(a,b)
        store.save_capture(sid,cap,dict(origin=a,destination=b,repetition=1,phase="medicao"),analyze(cap,a,b))
    figures=[];original=exports._figure
    def capture(*args,**kwargs):
        fig=original(*args,**kwargs);figures.append(fig);return fig
    monkeypatch.setattr(exports,"_figure",capture)
    exports.export_heatmap(store,sid,tmp_path/"matrizes.png")
    assert (tmp_path/"matrizes.png").stat().st_size>1000
    assert all(len(ax.texts)==81 for ax in figures[0].axes[:2])
