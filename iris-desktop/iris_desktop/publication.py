"""Contrato público Íris v1. Aquisição e análise continuam inteiramente locais."""
from datetime import datetime, timezone
from pathlib import Path
import base64
import hashlib
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
import numpy as np
from .analysis import ANALYSIS_VERSION, curve
from . import __version__
from .storage import atomic, json_text

SCHEMA = "iris-report/1"
DEFAULT_SITE = "https://tcc-iris.netlify.app"
MAX_BYTES = 4_000_000
CONDITIONS = ("resolution", "brightness", "contrast", "hdr", "vrr", "warmup_min",
    "sensor_position", "ambient", "amplifier", "adc", "channel", "vref", "supply_v",
    "attenuation_k", "rf_kohm", "cf_pf", "assembly", "gain_mode", "rate_sps",
    "window_ms", "pre_ms", "hold_ms", "spi_hz", "levels", "repetitions", "patch_percent",
    "patch_pixels", "patch_area_percent", "background_rgb", "static_references",
    "monitor_settings", "capacitors", "campaign_id", "campaign_step", "campaign_session", "campaign_dataset", "report_part", "report_parts")


def clean(value):
    """JSON estrito, sem NaN/Infinity nem valores específicos do NumPy."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def preview_curve(cap, result, max_points=600):
    """Envelope com extremos: apenas a visualização é reduzida, nunca as métricas."""
    unit = "%" if result.get("amplitude_adc") else "ADC"
    t, raw, filtered = curve(cap, result, unit=unit)
    indices = {0, len(t)-1}
    if len(t) <= max_points:
        indices.update(range(len(t)))
    else:
        for bucket in np.array_split(np.arange(len(t)), max(1, (max_points-8)//4)):
            for y in (raw, filtered):
                indices.update((int(bucket[np.argmin(y[bucket])]), int(bucket[np.argmax(y[bucket])])))
        for key in ("t10_ms", "t90_ms"):
            if result.get(key) is not None:
                indices.add(int(np.argmin(abs(t-result[key]))))
    idx = sorted(indices)
    return dict(unit=unit, original_samples=len(t), reduced=len(idx)<len(t),
                points=[[round(float(t[i]), 5), round(float(raw[i]), 5),
                         round(float(filtered[i]), 5)] for i in idx])


def build_public_report(store, sid, metadata=None):
    metadata = metadata or {}
    session = store.get_session(sid)
    if session["kind"] != "monitor":
        raise ValueError("Publique uma sessão de monitor; bancada não é relatório de monitor.")
    if session["status"] == "em_andamento":
        raise ValueError("Encerre a medição antes de gerar o relatório público.")
    config = session["config"]
    model = str(metadata.get("model", config.get("monitor", ""))).strip()
    overdrive = str(metadata.get("overdrive", config.get("overdrive", ""))).strip()
    hz = float(metadata.get("refresh_hz", config.get("refresh_hz") or 0))
    if not model or not overdrive or not math.isfinite(hz) or not 1 <= hz <= 2000:
        raise ValueError("Informe o modelo exato, o modo de overdrive e a frequência (Hz).")
    rows = [r for r in store.rows(sid) if r["phase"] == "medicao"]
    if not rows:
        raise ValueError("A sessão não contém transições de medição.")
    if len(rows) > 512:
        raise ValueError("O relatório público aceita até 512 capturas. Divida o ensaio em sessões menores.")
    with store.db() as db:
        hashes = {r["id"]: r["sha256"] for r in db.execute("SELECT id,sha256 FROM captures WHERE session_id=?", (sid,))}
    results = []
    for r in rows:
        valid = bool(r.get("valida"))
        keys = ("g2g_ms", "overshoot_pct", "acomodacao_ms", "t10_ms", "t90_ms")
        result = dict(origin=r["origem_rgb"], destination=r["destino_rgb"],
            repetition=r["repetition"], valid=valid, status=r.get("status", ""),
            peak_name=r.get("peak_name", "Excesso no alvo"),
            meaning=r.get("meaning", ""), reasons=r.get("motivos", []),
            criteria=r.get("criterios", {}), analysis_version=r.get("analysis_version", ANALYSIS_VERSION),
            sha256=hashes.get(r["capture_id"], ""), curve=preview_curve(store.capture(r["capture_id"]), r,
                max_points=min(600, 140000//len(rows))))
        result.update({k: r.get(k) if valid or k in ("t10_ms", "t90_ms") else None for k in keys})
        results.append(result)
    measured_at = session["created"]
    manifest = session.get("provenance", {}).get("manifest", "")
    match = re.match(r"(\d{8}T\d{6}Z)_", str(manifest))
    if match:
        measured_at = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
    measured_at = metadata.get("measured_at") or measured_at
    report = dict(schema=SCHEMA, title=str(metadata.get("title") or session["title"])[:180],
        measured_at=measured_at, simulation=bool(session["simulation"]),
        operator=str(metadata.get("operator", "")).strip()[:120],
        conclusion=str(metadata.get("conclusion", "")).strip()[:4000],
        monitor=dict(model=model[:160], refresh_hz=hz, overdrive=overdrive[:80]),
        conditions={k: config[k] for k in CONDITIONS if k in config},
        method=dict(version=ANALYSIS_VERSION, g2g="10–90% da amplitude da transição",
            peak="Excesso relativo à amplitude; overshoot nas subidas e undershoot nas descidas",
            scope="Resposta óptica temporal; não mede input lag nem constitui certificação VESA"),
        results=results, assets={})
    for field in ('monitor_settings', 'capacitors'):
        if isinstance(report['conditions'].get(field), dict):
            report['conditions'][field] = '; '.join(f'{k}: {v}' for k,v in report['conditions'][field].items())[:600]
    return clean(report)


def campaign_packages(store, sid, folder, metadata=None, *, documents=False):
    """Divide automaticamente sem descartar capturas. Contrato iris-report/1 preservado."""
    folder = Path(folder)
    rows = [r for r in store.rows(sid) if r['phase']=='medicao']
    if not rows:
        return []
    dataset=hashlib.sha256(json_text([rows,metadata or {}]).encode('utf8')).hexdigest()[:20]

    class Subset:
        def __init__(self, subset): self.subset = subset
        def __getattr__(self, name): return getattr(store, name)
        def rows(self, _sid): return self.subset

    def fit(subset):
        if len(subset) > 512:
            n=len(subset)//2;return fit(subset[:n])+fit(subset[n:])
        report = build_public_report(Subset(subset), sid, metadata)
        # Reserva espaço para o título e a identificação das partes.
        if len(json_text(report).encode('utf8')) > MAX_BYTES-2000:
            if len(subset)==1: raise ValueError('Uma captura excede o limite de publicação.')
            n=len(subset)//2;return fit(subset[:n])+fit(subset[n:])
        return [report]

    reports=fit(rows);paths=[]
    if documents:
        render_public_documents(store,sid,folder,reports[0])
    for index,report in enumerate(reports,1):
        report['conditions'].update(report_part=index,report_parts=len(reports),campaign_session=sid,campaign_dataset=dataset)
        if len(reports)>1:
            report['conditions'].setdefault('campaign_id',sid)
            report['conditions'].setdefault('campaign_step','medicao')
        if len(reports)>1:
            report['title']=report['title'][:140]+f' · parte {index}/{len(reports)}'
        part=folder/f'parte_{index:02d}';part.mkdir(parents=True,exist_ok=True)
        for name in ('relatorio.pdf','matrizes.png'):
            item=folder/name
            if index==1 and item.exists() and item.stat().st_size<=1_600_000:
                report['assets'][name]=base64.b64encode(item.read_bytes()).decode('ascii')
                if len(json_text(report).encode('utf8'))>MAX_BYTES:report['assets'].pop(name)
        path=part/'relatorio.iris.json';atomic(path,json_text(report).encode('utf8'))
        paths.append(path)
    return paths


def render_public_documents(store,sid,folder,report):
    from .exports import report_html, report_pdf
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    original = store.get_session(sid)

    class PublicStore:
        def __getattr__(self, name):
            return getattr(store, name)

        def get_session(self, _sid):
            return {**original, "created": report["measured_at"], "title": report["title"], "config": {
                **report["conditions"], "monitor": report["monitor"]["model"],
                "refresh_hz": report["monitor"]["refresh_hz"],
                "overdrive": report["monitor"]["overdrive"],
                "criteria": original["config"].get("criteria", {})}}

    path = report_html(PublicStore(), sid, folder, report["conclusion"],include_samples=False)
    report_pdf(path, folder/"relatorio.pdf")



def generate_package(store, sid, folder, metadata=None):
    """Gera o relatório individual compatível com fluxos anteriores."""
    report = build_public_report(store, sid, metadata)
    folder = Path(folder)
    render_public_documents(store,sid,folder,report)
    for filename in ("relatorio.pdf", "transicoes.png", "matrizes.png"):
        p = folder/filename
        if p.exists() and p.stat().st_size <= 1_600_000:
            report["assets"][filename] = base64.b64encode(p.read_bytes()).decode("ascii")
    output = folder/"relatorio.iris.json"
    content = json_text(report).encode("utf8")
    # O PDF permanece disponível localmente se for grande demais para o envio.
    if len(content) > MAX_BYTES:
        report["assets"].clear()
        content = json_text(report).encode("utf8")
    if len(content) > MAX_BYTES:
        raise ValueError("Relatório excede 4 MB. Divida o ensaio em sessões menores.")
    atomic(output, content)
    return output


def site_url(value):
    value = value.strip().rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    local = parsed.hostname in ("localhost", "127.0.0.1")
    if parsed.scheme != "https" and not (local and parsed.scheme == "http"):
        raise ValueError("Use a URL HTTPS do site.")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Informe apenas o endereço principal do site, sem caminhos ou parâmetros.")
    return value


def publish_package(path, site=DEFAULT_SITE, delete_token=None):
    """Operação de rede isolada, usada pelo QThread e pela interface de linha de comando."""
    import secrets
    path = Path(path)
    content = path.read_bytes()
    if len(content) > MAX_BYTES:
        raise ValueError("Arquivo maior que 4 MB.")
    report = json.loads(content)
    if report.get("schema") != SCHEMA:
        raise ValueError("Este arquivo não é um relatório público Íris v1.")
    site = site_url(site)
    receipt_path = path.with_name("publicacao-recibo.json")
    existing = {}
    if receipt_path.exists():
        existing = json.loads(receipt_path.read_text(encoding="utf8"))
    token = delete_token or existing.get("delete_token") or secrets.token_urlsafe(32)
    # Grava antes da rede: mesmo após perda de resposta, a chave continua recuperável.
    receipt = dict(site=site, delete_token=token, package_sha256=hashlib.sha256(content).hexdigest(), state="enviando")
    atomic(receipt_path, json_text(receipt).encode("utf8"))
    request = urllib.request.Request(site+"/api/publish", data=content, method="POST",
        headers={"Content-Type": "application/json", "X-Iris-Delete-Token": token,
                 "User-Agent": f"IrisDesktop/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read(65536))
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read(65536)).get("error")
        except (ValueError, AttributeError):
            message = None
        raise ValueError(message or f"O site recusou o envio (HTTP {exc.code}). Confira se o pacote completo foi publicado no Netlify.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValueError("Não foi possível concluir o envio. O relatório está salvo; tente novamente com internet. O reenvio não duplica o mesmo relatório.") from exc
    if not isinstance(result, dict) or not result.get("id"):
        raise ValueError("O site não retornou um recibo válido. Confira a instalação da API.")
    receipt.update(result, state="publicado", received_at=datetime.now(timezone.utc).isoformat())
    receipt["url"] = site+"/?relatorio="+str(result["id"])
    atomic(receipt_path, json_text(receipt).encode("utf8"))
    return receipt


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enviar relatório público do Íris")
    parser.add_argument("arquivo")
    parser.add_argument("--site", default=DEFAULT_SITE)
    args = parser.parse_args()
    print(publish_package(args.arquivo, args.site)["url"])
