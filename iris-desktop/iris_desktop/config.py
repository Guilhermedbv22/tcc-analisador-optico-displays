from dataclasses import asdict, dataclass, field, fields
import math
import random
from .core.nucleo import Criterios
from .core.protocolo import validar_configuracao


@dataclass
class TestConfig:
    __test__ = False
    title: str = "Ensaio de monitor"
    monitor: str = ""
    refresh_hz: float = 180.0
    overdrive: str = ""
    brightness: str = ""
    contrast: str = ""
    resolution: str = ""
    hdr: str = "Não informado"
    vrr: str = "Não informado"
    warmup_min: float = 30.0
    sensor_position: str = "Centro; sensor fixo e protegido da luz ambiente"
    ambient: str = ""
    amplifier: str = "MCP6022"
    adc: str = "MCP3208"
    channel: int = 0
    vref: float = 3.3
    supply_v: float = 3.3
    attenuation_k: float = 1.0
    rf_kohm: float = 235.0
    cf_pf: float = 8.2
    assembly: str = "Protoboard / adaptador SOIC-8"
    gain_mode: str = "Fixo"
    gain_range: int = 0
    auto_target: float = 0.80
    auto_settle_ms: int = 50
    gain_calibration: dict = field(default_factory=dict)
    rate_sps: int = 10000
    window_ms: float = 300.0
    pre_ms: int = 75
    hold_ms: int = 500
    spi_hz: int = 1000000
    levels: int = 6
    repetitions: int = 1
    custom_pairs: str = ""
    randomize: bool = False
    seed: int = 2026
    screen: int = 0
    full_screen: bool = True
    patch_percent: int = 100
    patch_pixels: int | None = None
    patch_area_percent: float | None = None
    background_rgb: int = 0
    static_references: bool = False
    criteria: dict = field(default_factory=lambda: asdict(Criterios()))
    notes: str = ""
    monitor_settings: dict = field(default_factory=dict)
    capacitors: dict = field(default_factory=dict)
    campaign_id: str = ""
    campaign_step: str = ""

    def validate(self):
        if not self.title.strip():
            raise ValueError("Dê um nome ao ensaio.")
        if self.rate_sps not in (5000, 10000, 20000):
            raise ValueError("Taxa permitida: 5, 10 ou 20 kS/s.")
        validar_configuracao(self.adc, 1000000 // self.rate_sps, self.window_ms,
                            self.channel, self.spi_hz)
        if not 0 < self.vref <= 3.6:
            raise ValueError("Informe a referência física do MCP3208 de 0 a 3,6 V (circuito proposto: 3,3 V).")
        if not 0 < self.attenuation_k <= 1:
            raise ValueError("Fator de atenuação físico deve ser >0 e ≤1; V_ADC = k × V_saida.")
        if self.supply_v>3.6 and 5.5*self.attenuation_k>min(self.vref,3.3)+1e-9:
            raise ValueError("Amplificador em 5 V exige proteção física antes do ADC. Informe o divisor realmente montado, dimensionado para até 5,5 V (ex.: k≤0,6 a VREF=3,3 V). O software não limita a tensão.")
        if not (2 <= self.levels <= 17 and 1 <= self.repetitions <= 100):
            raise ValueError("Use 2..17 níveis e 1..100 repetições.")
        if not (40 <= self.pre_ms <= self.window_ms - 80):
            raise ValueError("Pré-estímulo deve ser ≥40 ms e deixar ≥80 ms após a troca.")
        if self.hold_ms < 100 or not 1 <= self.patch_percent <= 100:
            raise ValueError("Espera mínima de 100 ms; área de 1 a 100% da largura/altura.")
        if not 0<=self.background_rgb<=255:raise ValueError("Cinza de fundo: 0..255.")
        if self.patch_area_percent is not None and not (math.isfinite(self.patch_area_percent) and 0 < self.patch_area_percent <= 100):
            raise ValueError("Área do quadrado deve estar entre 0 e 100%.")
        c = self.get_criteria()
        if not 1 <= c.mediana_amostras <= 51 or c.mediana_amostras % 2 != 1:
            raise ValueError("Mediana: número ímpar de 1 (bruto) a 51.")
        if not (0 < c.patamar_inicial_ms < self.pre_ms - 5 and
                0 < c.patamar_final_ms < self.window_ms - self.pre_ms - 10):
            raise ValueError("Janelas dos patamares devem caber antes e depois do estímulo.")
        if not (0 < c.tolerancia_acomodacao < .5 and c.snr_minimo > 0 and
                c.amplitude_minima > 0 and c.persistencia_ms >= 0 and
                c.permanencia_final_ms > 0):
            raise ValueError("Critérios de análise inválidos.")
        numbers = [self.vref, self.supply_v, self.rf_kohm, self.cf_pf, self.refresh_hz,
                   self.warmup_min, *[v for v in asdict(c).values() if v is not None]]
        if not all(math.isfinite(v) and v >= 0 for v in numbers):
            raise ValueError("Há parâmetros não finitos ou negativos.")
        if not .50 <= self.auto_target <= .90 or self.gain_range not in range(4):
            raise ValueError("Margem automática: teto de 50..90% da referência; faixa G0..G3.")
        if self.gain_mode not in ("Fixo", "Manual CD4066", "Automático CD4066"):
            raise ValueError("Modo de ganho inválido.")
        if self.gain_mode != "Fixo" and self.adc != "MCP3208":
            raise ValueError("Autoranging qualificado somente com MCP3208; compare ADCs em ganho fixo.")
        if not 20 <= self.auto_settle_ms <= 2000:
            raise ValueError("Aguardar ganho: 20..2000 ms; validar este tempo fisicamente.")
        self.pairs()
        return self

    def get_criteria(self):
        allowed = {f.name for f in fields(Criterios)}
        return Criterios(**{k: v for k, v in self.criteria.items() if k in allowed})

    def pairs(self):
        if self.custom_pairs.strip():
            pairs = []
            for token in self.custom_pairs.replace("→", "> ").replace(";", ",").split(","):
                token = token.strip().replace(" ", "").replace("->", ">")
                try:
                    a, b = map(int, token.split(">"))
                except ValueError as exc:
                    raise ValueError("Pares: use 0>255, 255>0, 64>192.") from exc
                if not 0 <= a <= 255 or not 0 <= b <= 255 or a == b:
                    raise ValueError("Cada par precisa de RGB 0..255 diferentes.")
                if (a, b) not in pairs:
                    pairs.append((a, b))
        else:
            levels = [round(i * 255 / (self.levels - 1)) for i in range(self.levels)]
            pairs = [(a, b) for a in levels for b in levels if a != b]
        return pairs

    def tasks(self, phase="medicao"):
        tasks = [dict(origin=a, destination=b, repetition=r, phase=phase)
                 for r in range(1, self.repetitions + 1) for a, b in self.pairs()]
        if self.randomize:
            random.Random(self.seed).shuffle(tasks)
        return tasks

    def capture_seconds(self):
        # 8 bytes/amostra, UART 115200 com 10 bits/byte, mais comandos/salvamento.
        samples = self.window_ms*self.rate_sps/1000
        return self.hold_ms/1000 + self.window_ms/1000 + samples*8*10/115200 + .2

    def capture_count(self):
        references = 2*len({v for pair in self.pairs() for v in pair}) if self.static_references else 0
        return len(self.pairs())*self.repetitions + references

    def to_dict(self):
        return asdict(self)

    def patch_dimensions(self, width, height):
        if self.patch_area_percent is not None:
            side = min(width, height, round(math.sqrt(width*height*self.patch_area_percent/100)))
            return side, side
        return round(width*self.patch_percent/100), round(height*self.patch_percent/100)

    @classmethod
    def from_dict(cls, value):
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in value.items() if k in names})


MATCH_FIELDS = ("monitor", "refresh_hz", "overdrive", "brightness", "contrast", "resolution", "patch_area_percent", "monitor_settings", "capacitors",
                "hdr", "vrr", "sensor_position", "ambient", "assembly", "amplifier", "adc",
                "channel", "vref", "supply_v", "attenuation_k", "rf_kohm", "cf_pf", "gain_mode", "rate_sps",
                "window_ms", "spi_hz", "criteria","patch_percent","patch_pixels","background_rgb","full_screen")


def comparison_conditions(a, b, variable):
    differences = []
    unknown = []
    varying = {"ADC": {"adc"}, "Amplificador": {"amplifier"}, "Rf": {"rf_kohm"},
               "Cf": {"cf_pf"}, "Alimentação": {"supply_v"}, "Overdrive": {"overdrive"},
               "Autoranging": {"gain_mode", "rf_kohm", "gain_range"},
               "Monitor": {"monitor", "refresh_hz", "resolution"}}.get(variable, set())
    for key in MATCH_FIELDS:
        if key=="patch_pixels" and a.get("patch_percent") is not None and b.get("patch_percent") is not None:continue
        if key=="patch_percent" and a.get("patch_pixels") is not None and b.get("patch_pixels") is not None:continue
        va, vb = a.get(key), b.get(key)
        if va is None or vb is None or va == "" or vb == "" or va == "Não informado" or vb == "Não informado":
            unknown.append(key)
        elif va != vb and key not in varying:
            differences.append(key)
    return differences, unknown
