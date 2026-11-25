"""Análise 4.1.0, diagnóstico e apresentação explícitos dos resultados."""
from dataclasses import asdict
import numpy as np
from scipy.ndimage import median_filter
from .core.nucleo import Criterios, analisar, estatisticas

ANALYSIS_VERSION = "desktop-1.2/core-4.1.0"

REASONS = {
    "pequena_amplitude": "Amplitude pequena: o cálculo usa o SNR e a persistência dos cruzamentos; o pico relativo é mais sensível ao ruído.",
    "preto_inicial_no_limite_adc": "O preto inicial está junto ao limite inferior do ADC. O trecho 10–90% está fora desse limite; o resultado é relativo aos patamares medidos.",
    "sem_amplitude": "Os patamares não se separam o suficiente.",
    "relacao_sinal_ruido_insuficiente": "O ruído é grande em relação à mudança medida.",
    "polaridade_ou_estimulo_incompativel": "A resposta não acompanha a direção do estímulo.",
    "limite_adc_atingido": "O sinal atingiu o limite do ADC: pico ou patamar podem estar cortados.",
    "temporizacao_irregular": "Os intervalos reais de aquisição ficaram irregulares.",
    "conversao_longa": "Uma conversão levou tempo demais para a taxa escolhida.",
    "resposta_sub_resolucao_temporal": "A resposta é rápida demais para esta taxa de amostragem.",
    "legado_sem_timestamps_individuais_verificados": "Este arquivo antigo não permite verificar cada intervalo.",
    "zero_continuo": "Todos os códigos recebidos são zero. Confira GND, entrada, referência, SPI e o estímulo.",
    "codigo_constante": "O código não mudou durante a captura; não há transição mensurável.",
    "estimulo_tardio": "A troca de cinza foi solicitada tarde demais para a janela útil.",
    "overshoot_nao_distinguivel_do_ruido": "O pico não se distingue do piso de ruído indicativo.",
    "pico_sensivel_ao_filtro": "O pico muda de forma relevante ao aplicar o filtro.",
    "adc_interno_sem_linearidade_verificada": "A linearidade do ADC interno ainda precisa ser caracterizada.",
}


def describe(reason):
    return REASONS.get(reason, reason.replace("_", " ").capitalize() + ".")


def health(cap, transition=False):
    x = np.asarray(cap.adc)
    if not len(x):
        return {"state": "sem_dados", "message": "Nenhuma amostra recebida.", "transport_ok": False}
    if np.all(x == 0):
        return {"state": "zero_continuo", "transport_ok": True,
                "message": ("Pacote válido, mas sem resposta mensurável; causa a investigar." if transition
                            else "Zero recebido: pode ser correto com a entrada ligada ao GND.")}
    if np.ptp(x.astype(float)) == 0:
        return {"state": "codigo_constante", "transport_ok": True,
                "message": "Pacote válido com código constante; conferir a condição física."}
    if np.any(x >= 4093):
        return {"state": "limite_alto", "transport_ok": True,
                "message": "Limite alto do ADC atingido; reduzir sinal ou ganho."}
    return {"state": "recebido", "transport_ok": True, "message": "Dados recebidos; validade avaliada separadamente."}


def analyze(cap, origin, destination, criteria=None):
    c = criteria or Criterios()
    result = analisar(cap, origin, destination, c)
    result["desktop_version"] = ANALYSIS_VERSION
    result["health"] = health(cap, origin != destination)
    if origin != destination and result["health"]["state"] in ("zero_continuo", "codigo_constante"):
        result["motivos"] = list(dict.fromkeys([result["health"]["state"], *result["motivos"]]))
        result.update(valida=False, g2g_ms=None)
    # O instante do PC é apenas diagnóstico: não é uma medição de input lag.
    delay = cap.meta.get("host_stimulus_after_arm_ms")
    if delay is not None and delay > cap.meta.get("n", len(cap.adc)) * cap.meta.get("period_us", 100) / 1000 - c.patamar_final_ms - 15:
        result["motivos"].append("estimulo_tardio")
        result.update(valida=False, status="INVALIDA", g2g_ms=None)
    os = result.get("overshoot_pct")
    result["overshoot_luminance_pct"] = os if destination > origin else 0.0 if os is not None else None
    result["undershoot_pct"] = os if destination < origin else 0.0 if os is not None else None
    result["peak_name"] = "Overshoot" if destination > origin else "Undershoot"
    result["meaning"] = interpret(result)
    return result


def interpret(result):
    if result.get("status") == "ESTATICA":
        return "Leitura estática: útil para patamar e ruído; sem tempo G2G."
    if not result.get("valida"):
        msg = "Tempo não calculado como resultado válido. " + " ".join(describe(v) for v in result.get("motivos", [])[:3])
        if "sem_amplitude" in result.get("motivos", []):
            msg += f" Amplitude: {abs(result['amplitude_adc']):.1f} códigos; mínimo configurado: {result['criterios']['amplitude_minima']:g}."
        if "relacao_sinal_ruido_insuficiente" in result.get("motivos", []):
            msg += f" SNR: {result['snr']:.1f}; mínimo configurado: {result['criterios']['snr_minimo']:g}."
        return msg
    g = result["g2g_ms"]
    os = result["overshoot_pct"]
    msg = f"A mudança percorreu de 10% a 90% em {g:.3f} ms. "
    if result.get("overshoot_detectado"):
        msg += f"O sinal ultrapassou o alvo em {os:.2f}% da amplitude desta transição. "
    else:
        msg += "O pico não se distingue do ruído pelo critério atual. "
    if result.get("acomodacao_ms") is not None:
        msg += f"Entrou e permaneceu na faixa de acomodação após {result['acomodacao_ms']:.3f} ms desde t10."
    else:
        msg += "A acomodação não foi confirmada nesta janela ou está limitada pelo ruído."
    for reason in ("pequena_amplitude", "preto_inicial_no_limite_adc"):
        if reason in result.get("avisos", []):
            msg += " " + describe(reason)
    return msg


def curve(cap, result, median=None, unit="ADC", vref=3.3, align=False):
    t = np.asarray(cap.t_us, float) / 1000
    t -= t[0]
    y = np.asarray(cap.adc, float)
    k = median or result.get("criterios", {}).get("mediana_amostras", 3)
    f = median_filter(y, size=k, mode="nearest")
    if unit == "%":
        delta = result.get("amplitude_adc", 0)
        if not delta:
            raise ValueError("Normalização indisponível: patamares sem amplitude.")
        a = result["inicial_adc"]
        y, f = (y-a)*100/delta, (f-a)*100/delta
    elif unit == "V":
        if vref is None:raise ValueError("Referência física não informada neste arquivo; use ADC ou %.")
        if cap.meta.get("source") == "INTERNO":
            raise ValueError("A curva interna não possui calibração em volts; use ADC ou %.")
        y, f = y * vref/4096, f * vref/4096
    if align and result.get("t10_ms") is not None:
        t -= result["t10_ms"]
    return t, y, f


def summary(rows):
    valid = [r for r in rows if r.get("valida") and r.get("phase", "medicao") == "medicao"]
    out = {"valid": len(valid), "total": len([r for r in rows if r.get("phase", "medicao") == "medicao"])}
    for name in ("g2g_ms", "overshoot_pct", "acomodacao_ms"):
        values = [r[name] for r in valid if r.get(name) is not None]
        out[name] = {"mean": float(np.mean(values)), "median": float(np.median(values)),
                     "min": float(min(values)), "max": float(max(values))} if values else None
    for direction, pred in (("subidas", lambda r:r["destino_rgb"]>r["origem_rgb"]),
                            ("descidas", lambda r:r["destino_rgb"]<r["origem_rgb"])):
        vals = [r["g2g_ms"] for r in valid if pred(r)]
        out[direction] = float(np.mean(vals)) if vals else None
    if valid:
        out["fastest"] = min(valid, key=lambda r:r["g2g_ms"])
        out["slowest"] = max(valid, key=lambda r:r["g2g_ms"])
        out["peak"] = max(valid, key=lambda r:r["overshoot_pct"])
    return out


def matrix_values(rows, metric):
    """Linhas = origem, colunas = destino; mesma orientação na tela e no PNG."""
    rows = [r for r in rows if r.get("phase", "medicao") == "medicao"]
    levels = sorted({v for r in rows for v in (r["origem_rgb"], r["destino_rgb"])})
    data = np.full((len(levels), len(levels)), np.nan)
    for i, a in enumerate(levels):
        for j, b in enumerate(levels):
            values = [r[metric] for r in rows if r["origem_rgb"] == a and r["destino_rgb"] == b
                      and r.get("valida") and r.get(metric) is not None and a != b]
            if values:
                data[i, j] = np.mean(values)
    return levels, data


def matrix_text(value):
    if not np.isfinite(value):
        return "—"
    return f"{value:.2f}" if abs(value) < 10000 else f"{value:.1e}"


def matrix_text_color(rgb):
    return "#0b1120" if sum(v*w for v,w in zip(rgb[:3], (.2126,.7152,.0722))) > .5 else "#ffffff"


def plateau_stats(cap, result, vref=3.3):
    t = (np.asarray(cap.t_us)-cap.t_us[0])/1000
    c = result.get("criterios", asdict(Criterios()))
    mask = np.ones(len(t),dtype=bool) if result.get("status")=="ESTATICA" else t < c["patamar_inicial_ms"]
    x = np.asarray(cap.adc, float)[mask]
    if len(x) < 2:
        return {}
    delta = abs(result.get("amplitude_adc", 0))
    sigma = float(np.std(x, ddof=1))
    return {"sigma_adc": sigma, "pp_adc": float(np.ptp(x)), "sigma_mv": sigma*vref/4096*1000 if cap.meta.get("source")=="MCP3208" and vref is not None else None,
            "noise_relative_pct": 100*sigma/delta if delta else None,
            "distinct": len(np.unique(x)), "rail_pct": 100*float(np.mean((cap.adc<=2)|(cap.adc>=4093)))}
