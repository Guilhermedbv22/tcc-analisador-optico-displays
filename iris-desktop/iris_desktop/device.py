"""Único proprietário da serial: fila em QThread; widgets só na thread principal."""
from dataclasses import asdict
import json
import queue
import time
import numpy as np
from PySide6.QtCore import QObject, QThread, Signal
from .core.protocolo import Dispositivo, Captura, ErroProtocolo

RF = (470000*52300/522300, 470000*127000/597000, 470000*412000/882000, 470000.)
RANGE_NAMES = tuple(f"G{i} · {r/1000:.2f} kΩ ideal" for i, r in enumerate(RF))


def ports():
    from serial.tools.list_ports import comports
    return [(p.device, p.description) for p in comports()]


class Worker(QThread):
    done = Signal(int, str, object)
    failed = Signal(int, str, object)
    armed = Signal(object)
    collected = Signal()

    def __init__(self):
        super().__init__()
        self.jobs = queue.Queue()
        self.device = None
        self._stopping = False

    def run(self):
        while not self._stopping:
            ident, kind, data = self.jobs.get()
            try:
                if kind == "quit":
                    self._stopping = True
                    continue
                result = self.execute(kind, data)
                self.done.emit(ident, kind, result)
            except Exception as exc:
                wire = getattr(exc, "wire", b"")
                # Após falha de enquadramento a porta não é reutilizada às cegas.
                if self.device is not None:
                    self.device.fechar()
                    self.device = None
                self.failed.emit(ident, kind, {"message": str(exc), "wire": wire})
        if self.device:
            self.device.fechar()
            self.device = None

    def execute(self, kind, data):
        if kind == "connect":
            if self.device:
                self.device.fechar()
            self.device = Dispositivo(data["port"])
            if "auto_pilots" in self.device.hello.get("features",[]):
                # Reabrir a UART não garante reset do ESP32. Encerra busca antiga
                # após queda do aplicativo, mantendo a faixa física já selecionada.
                self.device.comando("AUTO STOP","AUTO ")
            return self.device.hello
        if kind == "disconnect":
            if self.device:
                self.device.fechar()
                self.device = None
            return {}
        if self.device is None:
            raise RuntimeError("Conecte o ESP32 primeiro.")
        if kind == "configure":
            self.device.configurar(**data)
            return dict(self.device.config)
        if kind == "capture":
            def on_arm():
                at = time.monotonic()
                self.armed.emit({"job": data, "monotonic_s": at})
                return {"worker_arm_monotonic_s": at}
            return self.device.capturar(ao_armar=on_arm, apos_coleta=self.collected.emit)
        if kind == "stat":
            # Mudar canal não exige regravar firmware e descarta a primeira leitura.
            if self.device.config is None or self.device.config["source"] != data["source"] or self.device.config["channel"] != data["channel"]:
                self.device.configurar(data["source"], 100, 300, data["channel"], data.get("spi_hz", 1000000))
            return self.device.estatica()
        if kind == "command":
            command = data["command"]
            feature = "gain4" if command.startswith("GAIN") else "auto_pilots" if command.startswith("AUTO") else None
            if feature and feature not in self.device.hello.get("features", []):
                raise RuntimeError("Este firmware não oferece controle de ganho. O firmware v4 antigo continua funcionando em ganho fixo.")
            response = self.device.comando(command, data["prefix"], timeout=5)
            value = response[len(data["prefix"]):]
            return json.loads(value) if value.startswith("{") else value
        raise ValueError(f"Operação desconhecida: {kind}")


class DeviceClient(QObject):
    result = Signal(int, str, object)
    error = Signal(int, str, object)
    armed = Signal(object)
    collected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = Worker()
        self.worker.done.connect(self._done)
        self.worker.failed.connect(self._error)
        self.worker.armed.connect(self.armed)
        self.worker.collected.connect(self.collected)
        self.connected = False
        self.hello = {}
        self.counter = 0
        self.worker.start()

    def submit(self, kind, data=None):
        self.counter += 1
        self.worker.jobs.put((self.counter, kind, data or {}))
        return self.counter

    def command(self, text, prefix="GAIN "):
        return self.submit("command", {"command": text, "prefix": prefix})

    def _done(self, ident, kind, result):
        if kind == "connect":
            self.connected, self.hello = True, result
        elif kind == "disconnect":
            self.connected, self.hello = False, {}
        self.result.emit(ident, kind, result)

    def _error(self, ident, kind, error):
        self.connected = False
        self.error.emit(ident, kind, error)

    def shutdown(self):
        self.worker.jobs.put((0, "quit", {}))


def synthetic_capture(origin=0, destination=255, seed=1, period=100, n=3000):
    """Fixture explícita para testes e exemplo offline; nunca representa uma captura física."""
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=np.int64)*period
    a, b = 250+origin*9, 250+destination*9
    x = np.maximum(t/1000-75, 0)
    response = (1-np.exp(-x/2.4)) + .08*np.exp(-((x-9)/2.5)**2)
    y = np.clip(np.rint(a+(b-a)*response+rng.normal(0, 2, n)), 0, 4095).astype(np.uint16)
    return Captura(t, y, np.full(n, 27, np.uint16),
                   dict(protocol=4, fw="FIXTURE", source="MCP3208", channel=0, n=n,
                        period_us=period, spi_hz=1000000, missed=0, max_late_us=0,
                        bytes=n*8, simulation=True))
