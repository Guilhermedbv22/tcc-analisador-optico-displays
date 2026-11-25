from collections import deque
from math import ceil
import time
from PySide6.QtCore import QObject, QTimer, Signal, Qt, QRect
from PySide6.QtGui import QColor, QPainter, QShortcut, QKeySequence, QFont
from PySide6.QtWidgets import QWidget, QApplication
from .analysis import analyze
from .core.nucleo import avaliar_varredura


def duration(seconds):
    if seconds is None:
        return "calculando…"
    seconds = max(0, ceil(seconds))
    h, tail = divmod(seconds, 3600)
    m, s = divmod(tail, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def progress_text(data):
    if not data["running"]:
        state = {"concluida":"concluído", "cancelada":"encerrado", "falha":"interrompido"}.get(data['result'], data['result'])
        return (f"Ensaio {state} · {data['measurement_done']}/{data['measurement_total']} transições salvas\n"
                f"Tempo decorrido: {duration(data['elapsed_s'])}")
    task = data.get("task")
    pair = f"RGB {task['origin']} → {task['destination']} · repetição {task['repetition']}" if task else "Preparando aquisição"
    remaining = "Restante nesta faixa" if data["pilot"] else "Tempo restante"
    return (f"{data['phase']} · {pair}\n"
            f"Transições concluídas: {data['measurement_done']}/{data['measurement_total']} · "
            f"Capturas da etapa: {data['completed']}/{data['total']}\n"
            f"{remaining} ≈ {duration(data['remaining_s'])} · Decorrido: {duration(data['elapsed_s'])}"
            + (" · Encerrando…" if data['cancelled'] else ""))


class Stimulus(QWidget):
    escaped = Signal()

    def __init__(self, cfg):
        super().__init__(None, Qt.WindowType.Window)
        self.cfg, self.gray = cfg, 0
        self.hud = "Preparando ensaio…"
        self.setWindowTitle("Íris · estímulo — Esc encerra após receber o pacote")
        self.setMinimumSize(320, 240)
        self.shortcut = QShortcut(QKeySequence("Esc"), self)
        self.shortcut.activated.connect(self.escaped)

    def open_screen(self):
        screen = QApplication.screens()[self.cfg.screen]
        self.setGeometry(screen.geometry())
        self.winId()
        self.windowHandle().setScreen(screen)
        if self.cfg.full_screen:
            self.showFullScreen()
        else:
            self.resize(640, 480)
            self.show()
        self.raise_()

    def set_gray(self, gray):
        self.gray = int(gray)
        self.repaint()
        return time.monotonic()

    def paintEvent(self, event):
        p = QPainter(self)
        bg=self.cfg.background_rgb
        p.fillRect(self.rect(), QColor(bg,bg,bg))
        w, h = self.cfg.patch_dimensions(self.width(), self.height())
        p.fillRect(QRect((self.width()-w)//2, (self.height()-h)//2, w, h), QColor(self.gray, self.gray, self.gray))
        rect = self.hud_rect()
        p.fillRect(rect, QColor("#0b1120"))
        p.setPen(QColor("#e1e9f5"));p.setFont(QFont("Segoe UI", 11 if self.width()>800 else 9))
        p.drawText(rect.adjusted(10,6,-10,-6), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, self.hud)

    def hud_rect(self):
        height=min(104,self.height()//3)
        return QRect(12, self.height()-height-12, min(self.width()-24, 1000), height)

    def set_progress(self, text):
        self.hud = text
        self.update(self.hud_rect())

    def closeEvent(self, event):
        if self.isVisible():
            self.escaped.emit()
        event.accept()


class Acquisition(QObject):
    status = Signal(str)
    progress = Signal(int, int)
    progress_detail = Signal(object)
    captured = Signal(int)
    session_started = Signal(str)
    finished = Signal(str, str)
    busy_changed = Signal(bool)

    def __init__(self, device, store):
        super().__init__()
        self.device, self.store = device, store
        self.running = False
        self.cancelled = False
        self.callbacks = {}
        self.stimulus = None
        self.current_task = None
        self.capture_pending = False
        self.timer_token = 0
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(250)
        self.progress_timer.timeout.connect(self._emit_progress)
        device.result.connect(self._result)
        device.error.connect(self._error)
        device.armed.connect(self._armed)

    def request(self, kind, data, callback):
        ident = self.device.submit(kind, data)
        self.callbacks[ident] = callback
        return ident

    def command(self, command, callback, prefix="GAIN "):
        return self.request("command", dict(command=command, prefix=prefix), callback)

    def start(self, cfg, *, sid=None, tasks=None, provenance=None):
        cfg.validate()
        if self.running:
            raise RuntimeError("Já há um ensaio em execução.")
        if not self.device.connected:
            raise RuntimeError("Conecte o ESP32 na página Início.")
        if not 0 <= cfg.screen < len(QApplication.screens()):
            raise ValueError("Monitor de estímulo não está disponível.")
        if cfg.gain_mode != "Fixo" and "gain4" not in self.device.hello.get("features", []):
            raise ValueError("Atualize o firmware para usar CD4066. Ganho fixo é compatível com v4.0.x.")
        self.cfg = cfg
        self.override_tasks = tasks
        self.started_at = time.monotonic()
        self.task_started_at = None
        self.current_task = None
        self.tasks = deque()
        self.batch_total = self.batch_completed = self.measurement_done = 0
        self.durations = deque(maxlen=12)
        self.running, self.cancelled, self.capture_pending = True, False, False
        self.busy_changed.emit(True)
        if sid is not None:
            original = self.store.get_session(sid)
            # A tela pode ter sido renumerada após reconectar; as condições físicas não.
            old, new = original['config'].copy(), cfg.to_dict()
            for key in ('screen',):
                old.pop(key, None); new.pop(key, None)
            if old != new:
                self.running = False
                self.busy_changed.emit(False)
                raise ValueError("As condições mudaram. Repita a etapa em uma nova sessão.")
            self.sid = sid
            self.store.finish(sid, 'em_andamento')
            self.store.event(sid, 'retomada', {'remaining_tasks':len(tasks or [])})
        else:
            self.sid = self.store.session(cfg.title, cfg.to_dict(), provenance={"hello": self.device.hello, "host_timing": "QTimer/repaint, sem sincronismo físico de vsync; G2G usa a curva óptica", **(provenance or {})})
        self.session_started.emit(self.sid)
        self.count = 0
        self.gain = None
        self.references = []
        self.prior_task_count = 0
        self.prior_measurement_done = 0
        if sid is not None:
            previous_rows = self.store.rows(sid)
            self.prior_task_count = len(previous_rows)
            self.prior_measurement_done = sum(row['phase']=='medicao' for row in previous_rows)
            for row in previous_rows:
                if row['phase'].startswith('referencia') and row.get('estatisticas'):
                    self.references.append(dict(rgb=row['origem_rgb'], phase=row['phase'], **row['estatisticas']))
        self.initial_references = {}
        self.pending_refs = False
        self.timer_token += 1
        self.stimulus = Stimulus(cfg)
        self.stimulus.escaped.connect(self.cancel)
        self.stimulus.open_screen()
        self.progress.emit(0, cfg.capture_count())
        self._emit_progress()
        self.progress_timer.start()
        screen=QApplication.screens()[cfg.screen]
        self.store.event(self.sid,"stimulus_geometry",dict(widget_width=self.stimulus.width(),widget_height=self.stimulus.height(),
            screen_name=screen.name(),device_pixel_ratio=screen.devicePixelRatio(),os_refresh_hz=screen.refreshRate(),
            patch_percent=cfg.patch_percent,patch_area_percent=cfg.patch_area_percent,
            patch_dimensions=cfg.patch_dimensions(self.stimulus.width(),self.stimulus.height()),background_rgb=cfg.background_rgb))
        self.store.event(self.sid, "stimulus_progress_overlay", dict(position="inferior esquerdo", outside_sensor_center=True))
        self.status.emit("Configurando aquisição…")
        self.request("configure", dict(fonte=cfg.adc, periodo_us=1000000//cfg.rate_sps,
            janela_ms=cfg.window_ms, canal=cfg.channel, spi_hz=cfg.spi_hz), self._configured)

    def _configured(self, _):
        if self.cancelled:
            return self._finish("cancelada")
        if self.cfg.gain_mode == "Fixo":
            if "gain4" in self.device.hello.get("features", []):
                self.command("GAIN ENABLE 0", lambda _:self._begin_measurements())
            else:
                self._begin_measurements()
        else:
            self.command(f"GAIN SETTLE {self.cfg.auto_settle_ms}", lambda _:self.command("GAIN ENABLE 1", self._gain_enabled))

    def _gain_enabled(self, result):
        self.store.event(self.sid, "gain_enabled", result)
        if self.cfg.gain_mode == "Manual CD4066":
            self.command(f"GAIN SET {self.cfg.gain_range}", self._manual_set)
        else:
            self.command(f"AUTO START {round(self.cfg.auto_target*1000)}", self._auto_decision, "AUTO ")

    def _manual_set(self, result):
        self.gain = result["range"]
        self.store.event(self.sid, "gain_manual", result)
        self._begin_measurements()

    def _auto_decision(self, result):
        self.store.event(self.sid, "auto_decision", result)
        self.gain = result.get("range")
        if self.cancelled:
            return self._finish("cancelada")
        if result["status"] == "TRY":
            self.tasks = deque(dict(origin=a, destination=b, repetition=1, phase=f"piloto_G{self.gain}") for a,b in self.cfg.pairs())
            self.batch_total = len(self.tasks)
            self.batch_completed = 0
            self.progress.emit(0, self.batch_total)
            self.status.emit(f"Pilotos de G{self.gain}: verificando patamares e picos com margem.")
            self._next()
        elif result["status"] == "LOCKED":
            self.status.emit(f"G{self.gain} selecionado e fixo para o ensaio.")
            self._begin_measurements()
        else:
            self.store.event(self.sid, "auto_nao_aprovado", result)
            self.status.emit("Autoranging interrompido: " + {"NO_SIGNAL":"sem variação mensurável; confira sinal e montagem.",
                "OUT_OF_RANGE":"o menor ganho já excede a margem. Reduza a luz ou revise o circuito."}.get(result["status"], str(result)))
            self._finish("auto_nao_aprovado")

    def _begin_measurements(self):
        if self.cancelled:
            return self._finish("cancelada")
        tasks = self.cfg.tasks()
        if self.cfg.static_references:
            levels = sorted({v for p in self.cfg.pairs() for v in p})
            before = [dict(origin=v, destination=v, repetition=1, phase="referencia_antes") for v in levels]
            after = [dict(origin=v, destination=v, repetition=1, phase="referencia_depois") for v in reversed(levels)]
            tasks = before + tasks + after
        if self.override_tasks is not None:
            tasks = self.override_tasks
        self.tasks = deque(tasks)
        self.batch_total = len(tasks)
        self.batch_completed = 0
        self.progress.emit(0, self.batch_total)
        self._next()

    def _next(self):
        if not self.running:
            return
        if self.cancelled:
            return self._finish("cancelada")
        if not self.tasks:
            if self.current_task and self.current_task["phase"].startswith("piloto"):
                return self.command("AUTO EVAL", self._auto_decision, "AUTO ")
            if self.references:
                review = avaliar_varredura(self.references)
                self.store.event(self.sid, "referencias_estaticas", review)
                if not review["aprovada_relativamente"]:
                    self.status.emit("Ensaio salvo; revisão necessária: referências apresentam deriva, ruído ou compressão.")
                    return self._finish("revisar_referencias")
            return self._finish("concluida")
        self.current_task = self.tasks.popleft()
        self.task_started_at = time.monotonic()
        self.host = {}
        self.arm_at = None
        task = self.current_task
        self.status.emit(f"{task['phase']} · RGB {task['origin']} → {task['destination']} · repetição {task['repetition']}" + (f" · G{self.gain}" if self.gain is not None else " · ganho fixo"))
        self.stimulus.set_gray(task["origin"])
        self._emit_progress()
        token = self.timer_token
        QTimer.singleShot(self.cfg.hold_ms, lambda:self._capture_if(token))

    def _capture_if(self, token):
        if not self.running or token != self.timer_token:
            return
        if self.cancelled:
            return self._finish("cancelada")
        self.capture_pending = True
        self.capture_ident = self.request("capture", dict(task=self.current_task.copy()), self._received)

    def _armed(self, data):
        if not self.running or not self.capture_pending:
            return
        self.arm_at = data["monotonic_s"]
        token = self.timer_token
        def change():
            if self.running and self.capture_pending and token == self.timer_token and self.stimulus:
                changed = self.stimulus.set_gray(self.current_task["destination"])
                self.host = {"host_stimulus_after_arm_ms": (changed-self.arm_at)*1000,
                             "host_stimulus_monotonic_s": changed, "requested_pre_ms": self.cfg.pre_ms}
        QTimer.singleShot(self.cfg.pre_ms, change)

    def _received(self, cap):
        self.capture_pending = False
        task = self.current_task.copy()
        cap.meta.update(self.host)
        if self.arm_at is not None and "host_stimulus_after_arm_ms" not in self.host:
            cap.meta["host_stimulus_after_arm_ms"] = self.cfg.window_ms + 1
        cap.meta.update(configured_gain_mode=self.cfg.gain_mode, declared_vref=self.cfg.vref)
        cid = self.store.save_capture(self.sid, cap, task)
        try:
            r = analyze(cap, task["origin"], task["destination"], self.cfg.get_criteria())
            self.store.save_analysis(cid, r)
        except Exception as exc:
            self.store.event(self.sid, "falha_analise", {"capture_id":cid,"error":str(exc)})
            r = {}
        if task["phase"].startswith("referencia") and r.get("estatisticas"):
            self.references.append(dict(rgb=task["origin"], phase=task["phase"], **r["estatisticas"]))
        self.count += 1
        self.batch_completed += 1
        if task["phase"] == "medicao":
            self.measurement_done += 1
        if self.task_started_at is not None:
            self.durations.append(time.monotonic()-self.task_started_at)
        self.task_started_at = None
        self.progress.emit(self.batch_total-len(self.tasks), self.batch_total)
        self.captured.emit(cid)
        if (self.cfg.gain_mode == "Automático CD4066" and task["phase"] == "medicao" and
                any(cap.adc >= 4093)):
            self.store.event(self.sid, "saturacao_apos_pilotos", {"capture_id":cid,"gain":self.gain})
            self.status.emit("Saturação após os pilotos: dados salvos; ensaio interrompido para revisão.")
            return self._finish("saturacao_apos_pilotos")
        QTimer.singleShot(0, self._next)

    def _result(self, ident, kind, result):
        cb = self.callbacks.pop(ident, None)
        if cb and self.running:
            try:
                cb(result)
            except Exception as exc:
                self._error(ident, kind, {"message":str(exc),"wire":getattr(exc,"wire",b"")})

    def _error(self, ident, kind, error):
        if not self.running:
            return
        self.callbacks.clear()
        try:
            self.store.failure(self.sid, error["message"], error.get("wire",b""), self.current_task)
        finally:
            self.status.emit("Ensaio interrompido: " + error["message"])
            self._finish("falha")

    def cancel(self):
        if self.running:
            self.cancelled = True
            self._emit_progress()
            self.status.emit("Encerrando após receber o pacote atual; os dados serão preservados…")
            if not self.capture_pending and not self.callbacks:
                self._finish("cancelada")

    def _finish(self, status):
        if not self.running:
            return
        sid = self.sid
        self.running = False
        self.progress_timer.stop()
        self._emit_progress(status)
        self.timer_token += 1
        self.callbacks.clear()
        if self.stimulus:
            self.stimulus.hide()
            self.stimulus.deleteLater()
            self.stimulus = None
        self.store.finish(sid, status)
        if self.cfg.gain_mode != "Fixo" and self.device.connected:
            # Apenas encerra o modo automático. Mantém a última faixa física, registrada.
            self.device.command("AUTO STOP", "AUTO ")
        self.busy_changed.emit(False)
        self.finished.emit(sid, status)

    def _emit_progress(self, result=None):
        if not hasattr(self, "started_at"):
            return
        now = time.monotonic()
        task = self.current_task
        phase = task["phase"] if task else "configuracao"
        pilot = phase.startswith("piloto")
        phase_name = {"medicao":"Medição", "estatica":"Patamares estáticos", "referencia_antes":"Referências iniciais",
                      "referencia_depois":"Referências finais", "configuracao":"Configuração"}.get(phase, phase.replace("piloto_", "Pilotos · "))
        per = sum(self.durations)/len(self.durations) if self.durations else self.cfg.capture_seconds()
        active = self.task_started_at is not None
        task_elapsed = now-self.task_started_at if active else 0
        # Não anuncia zero enquanto o pacote atual ainda não chegou.
        remaining = len(self.tasks)*per + max(.5, per-task_elapsed) if active else len(self.tasks)*per
        if not self.batch_total:
            remaining = self.cfg.capture_count()*per
        if self.cancelled:
            remaining = max(.5, per-task_elapsed) if self.capture_pending else 0
        data = dict(running=self.running, cancelled=self.cancelled, result=result,
                    task=dict(task) if task else None, phase=phase_name, pilot=pilot,
                    measurement_done=self.measurement_done+self.prior_measurement_done, measurement_total=(sum(t['phase']=='medicao' for t in self.override_tasks)+self.prior_measurement_done if self.override_tasks is not None else len(self.cfg.pairs())*self.cfg.repetitions),
                    completed=self.batch_completed+self.prior_task_count, total=(self.batch_total or self.cfg.capture_count())+self.prior_task_count,
                    elapsed_s=now-self.started_at, remaining_s=remaining if self.running else None)
        self.progress_detail.emit(data)
        if self.stimulus and self.running:
            self.stimulus.set_progress(progress_text(data))
