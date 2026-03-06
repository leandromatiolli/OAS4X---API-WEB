"""
Rotas REST: acquisition (start/stop/status/preview/metrics), files (list/download), monitor (WebSocket).
"""
import asyncio
import uuid
from datetime import datetime
from typing import Optional

import numpy as np

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from acquisition.daq_runner import (
    get_state,
    run_acquisition,
    stop_acquisition,
    AcquisitionStatus,
)
from acquisition.ranges import ADC_RANGES, VALID_RANGE_IDS, range_id_to_volts
from config import SENSOR_CHANNELS
from processing.metrics import compute_channel_metrics, downsample
from processing.analysis import (
    downsample_for_plot,
    fft_magnitude,
    rms_sliding_window,
    percentiles_per_channel,
    MAX_PLOT_POINTS,
)
from storage.runs import list_runs, get_run_metadata, get_run_bin_path, read_run_bin, delete_run
from storage.processed import read_demod
from acquisition.monitor import (
    start_monitor,
    stop_monitor,
    is_monitor_running,
    get_last_frame,
    get_monitor_sensor,
)
from acquisition.spectrum import (
    start_spectrum,
    stop_spectrum,
    is_spectrum_running,
    get_last_spectrum_frame,
    get_spectrum_sensor,
    get_spectrum_interval_s,
)

router = APIRouter(prefix="/api", tags=["api"])

# Qual conexão WebSocket "dona" do monitor/espectro; evita que um finally atrasado (conexão antiga) pare o serviço iniciado por outra.
_monitor_stream_owner: Optional[int] = None
_spectrum_stream_owner: Optional[int] = None


# --- Calibração (Etapa 4) ---

class CalibrationStartBody(BaseModel):
    rate_hz: float = 1000
    chunk_duration_s: float = 1
    interval_s: float = 5
    fit_points: int = 50000
    sensors: Optional[list[str]] = None


class FitFromRunBody(BaseModel):
    run_id: str
    sensor: str


class CalibrationResetBody(BaseModel):
    restart: bool = False
    rate_hz: float = 1000
    chunk_duration_s: float = 1
    interval_s: float = 5
    fit_points: int = 50000
    sensors: Optional[list[str]] = None


class AcquisitionStartBody(BaseModel):
    channels: Optional[list[int]] = None
    sensors: Optional[list[str]] = None
    sample_rate_hz: float = 200000
    duration_s: float = 5
    test_name: str = ""
    range_id: Optional[str] = "UNI5VOLTS"


def _channels_from_sensors(sensors: list[str]) -> list[int]:
    """Converte lista de sensores S1..S4 em lista de canais."""
    ch_set = set()
    for s in sensors or []:
        if s in SENSOR_CHANNELS:
            ch_set.update(SENSOR_CHANNELS[s])
    return sorted(ch_set)


@router.post("/acquisition/start")
async def acquisition_start(body: AcquisitionStartBody):
    """
    Inicia uma aquisição em background.
    Forneça channels (0-7) e/ou sensors (S1-S4). Canais finais = união.
    """
    ch = list(body.channels) if body.channels else []
    ch.extend(_channels_from_sensors(body.sensors or []))
    ch = sorted(set(c for c in ch if 0 <= c <= 7))
    if not ch:
        raise HTTPException(400, "Informe ao menos um canal ou sensor (S1-S4)")
    range_id = body.range_id or "UNI5VOLTS"
    if range_id not in VALID_RANGE_IDS:
        raise HTTPException(400, f"range_id inválido. Use um de: {sorted(VALID_RANGE_IDS)}")
    state = get_state()
    if state.status == AcquisitionStatus.RUNNING:
        raise HTTPException(409, "Aquisição já em andamento")
    run_id = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    run_acquisition(
        channels=ch,
        sample_rate_hz=body.sample_rate_hz,
        duration_s=body.duration_s,
        run_id=run_id,
        test_name=body.test_name,
        range_id=range_id,
    )
    return {"run_id": run_id, "status": "started", "channels": ch}


@router.post("/acquisition/stop")
async def acquisition_stop():
    """Solicita parada da aquisição (scan finito pode terminar naturalmente)."""
    stopped = stop_acquisition()
    return {"stopped": stopped}


@router.get("/acquisition/ranges")
async def acquisition_ranges():
    """Lista faixas de tensão ADC (USB-1808X) para popular o select no frontend."""
    return {"ranges": ADC_RANGES}


@router.get("/acquisition/status")
async def acquisition_status():
    """Status atual: idle | running | done | error; run_id; preview e métricas se done."""
    state = get_state()
    out = {
        "status": state.status.value,
        "run_id": state.run_id,
        "error_message": state.error_message,
    }
    if state.result and state.result.success and state.result.data is not None:
        data = state.result.data
        rate = state.result.rate_hz
        samples_per_channel = data.shape[1]
        duration_s = samples_per_channel / rate if rate else 0
        # Abaixo de 2 s: todos os pontos no gráfico; acima: downsample para 10k
        max_points = samples_per_channel if duration_s < 2.0 else 10_000
        down = downsample(data, max_points)
        n = down.shape[1]
        # Eixo de tempo pelos índices reais das amostras (0, step, 2*step, ...)
        step = max(1, samples_per_channel // max_points)
        indices = np.arange(0, samples_per_channel, step)[:n]
        t = (indices.astype(np.float64) / rate).tolist()
        out["preview"] = {
            "t": t,
            "channels": {
                str(ch): down[ch, :].tolist() for ch in range(down.shape[0])
            },
        }
        out["metrics"] = compute_channel_metrics(data)
    return out


@router.get("/files")
async def files_list():
    """Lista runs em /data/raw com metadados."""
    runs = list_runs()
    return {"runs": runs}


@router.get("/files/{run_id}/download/bin")
async def file_download_bin(run_id: str):
    """Download do arquivo .bin da run."""
    path = get_run_bin_path(run_id)
    if not path or not path.exists():
        raise HTTPException(404, "Run ou arquivo não encontrado")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@router.get("/files/{run_id}/download/json")
async def file_download_json(run_id: str):
    """Download do arquivo .json da run."""
    from config import RAW_DIR
    path = RAW_DIR / f"{run_id}.json"
    if not path.exists():
        raise HTTPException(404, "Run ou arquivo não encontrado")
    return FileResponse(path, filename=path.name, media_type="application/json")


@router.delete("/files/{run_id}")
async def file_delete(run_id: str):
    """Exclui a run (arquivos .bin e .json)."""
    removed = delete_run(run_id)
    if not removed:
        raise HTTPException(404, "Run não encontrada ou já excluída")
    return {"deleted": run_id}


@router.get("/files/{run_id}/metrics")
async def file_metrics(run_id: str):
    """Métricas (RMS, DC, peak, clipping) de uma run salva."""
    out = read_run_bin(run_id)
    if not out:
        raise HTTPException(404, "Run não encontrada")
    data, meta = out
    range_volts = range_id_to_volts(meta.get("range"))
    metrics = compute_channel_metrics(data, range_volts=range_volts)
    return {"run_id": run_id, "meta": meta, "metrics": metrics}


@router.get("/files/{run_id}/preview")
async def file_preview(run_id: str, max_points: int = MAX_PLOT_POINTS):
    """Dados downsampled para plot pós-aquisição (zoom/pan). Abaixo de 2 s: todos os pontos."""
    out = read_run_bin(run_id)
    if not out:
        raise HTTPException(404, "Run não encontrada")
    data, meta = out
    fs = meta["sample_rate_hz"]
    n_total = data.shape[1]
    duration_s = meta.get("duration_s") or (n_total / fs if fs else 0)
    pts = n_total if duration_s < 2.0 else max_points
    down = downsample_for_plot(data, pts)
    n = down.shape[1]
    step = max(1, n_total // pts)
    indices = np.arange(0, n_total, step)[:n]
    t = (indices.astype(np.float64) / fs).tolist()
    return {
        "run_id": run_id,
        "meta": meta,
        "t": t,
        "channels": {str(ch): down[ch, :].tolist() for ch in range(down.shape[0])},
    }


@router.get("/files/{run_id}/fft")
async def file_fft(run_id: str, channel: int = 0):
    """FFT de um canal; retorna freq (Hz) e magnitude (dB)."""
    out = read_run_bin(run_id)
    if not out:
        raise HTTPException(404, "Run não encontrada")
    data, meta = out
    fs = meta["sample_rate_hz"]
    if channel < 0 or channel >= data.shape[0]:
        raise HTTPException(400, "Canal inválido")
    freq, mag = fft_magnitude(data[channel, :], fs, window=True, db=True)
    return {
        "run_id": run_id,
        "channel": channel,
        "sample_rate_hz": fs,
        "freq_hz": freq.tolist(),
        "magnitude_db": mag.tolist(),
    }


@router.get("/files/{run_id}/stats")
async def file_stats(run_id: str, window_samples: int = 1000):
    """Estatísticas: RMS global, RMS janela deslizante (média), P95, P99 por canal."""
    out = read_run_bin(run_id)
    if not out:
        raise HTTPException(404, "Run não encontrada")
    data, meta = out
    range_volts = range_id_to_volts(meta.get("range"))
    metrics = compute_channel_metrics(data, range_volts=range_volts)
    percentiles = percentiles_per_channel(data, [95, 99])
    stats = []
    for ch in range(data.shape[0]):
        rms_win = rms_sliding_window(data[ch, :], window_samples)
        stats.append({
            "channel": ch,
            "rms": metrics[ch]["rms"],
            "rms_window_mean": float(np.mean(rms_win)),
            "p95": percentiles[ch]["p95"],
            "p99": percentiles[ch]["p99"],
        })
    return {"run_id": run_id, "meta": meta, "stats": stats}


@router.get("/files/{run_id}/export/csv")
async def file_export_csv(run_id: str, decimate: int = 1):
    """Export CSV decimado (timestamp + canais). decimate=1 sem decimação; 10 = 1 a cada 10 amostras."""
    out = read_run_bin(run_id)
    if not out:
        raise HTTPException(404, "Run não encontrada")
    data, meta = out
    if decimate < 1:
        decimate = 1
    fs = meta["sample_rate_hz"]
    n = data.shape[1]
    idx = np.arange(0, n, decimate)
    t = idx / fs
    rows = ["time_s," + ",".join(f"ch{c}" for c in range(data.shape[0]))]
    for i, j in enumerate(idx):
        row = f"{t[i]:.6f}," + ",".join(f"{data[c, j]:.6f}" for c in range(data.shape[0]))
        rows.append(row)
    csv_content = "\n".join(rows)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={run_id}.csv"},
    )


# --- Reset DAQ (parar monitor + espectro e aguardar liberação do dispositivo) ---

@router.post("/daq/reset")
async def daq_reset():
    """
    Para monitor e espectro e aguarda a liberação do dispositivo.
    Use após Parar ou antes de Iniciar de novo para evitar travar o DAQ.
    """
    import time
    stop_monitor()
    stop_spectrum()
    time.sleep(1.2)
    return {"ok": True, "message": "DAQ resetado. Pode iniciar Monitor ou Espectro."}


# --- Monitor em tempo real (streaming por sensor) ---

@router.get("/monitor/status")
async def monitor_status():
    """Status do monitor: se está ativo e para qual sensor."""
    return {
        "running": is_monitor_running(),
        "sensor": get_monitor_sensor(),
    }


@router.post("/monitor/stop")
async def monitor_stop():
    """Para o monitor em tempo real."""
    stop_monitor()
    return {"stopped": True}


@router.websocket("/monitor/stream")
async def monitor_stream(websocket: WebSocket):
    """
    WebSocket: inicia monitor para o sensor (query param sensor=S1|S2|S3|S4)
    e envia frames ~10 Hz com t, ch0, ch1, diff (tensão diferencial).
    """
    await websocket.accept()
    sensor = websocket.query_params.get("sensor", "S1").upper()
    if sensor not in ("S1", "S2", "S3", "S4"):
        await websocket.send_json({"error": "Sensor inválido. Use S1, S2, S3 ou S4."})
        await websocket.close()
        return
    ok, msg = start_monitor(sensor)
    if not ok:
        await websocket.send_json({"error": msg})
        await websocket.close()
        return
    conn_id = id(websocket)
    global _monitor_stream_owner
    _monitor_stream_owner = conn_id
    try:
        while True:
            frame = get_last_frame()
            if frame is None:
                await asyncio.sleep(0.1)
                continue
            if "error" in frame:
                await websocket.send_json(frame)
                break
            await websocket.send_json(frame)
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if _monitor_stream_owner == conn_id:
            _monitor_stream_owner = None
            stop_monitor()
        try:
            import time
            time.sleep(0.3)
        except Exception:
            pass


# --- Espectro em tempo real ---

@router.get("/spectrum/status")
async def spectrum_status():
    """Status do espectro: se está ativo, sensor e intervalo."""
    return {
        "running": is_spectrum_running(),
        "sensor": get_spectrum_sensor(),
        "interval_s": get_spectrum_interval_s(),
    }


@router.post("/spectrum/stop")
async def spectrum_stop():
    """Para o espectro em tempo real."""
    stop_spectrum()
    return {"stopped": True}


@router.websocket("/spectrum/stream")
async def spectrum_stream(websocket: WebSocket):
    """
    WebSocket: inicia espectro para o sensor (query sensor, interval_s, sample_rate).
    Envia frames com freq_hz e magnitude_db a cada novo cálculo.
    """
    await websocket.accept()
    sensor = websocket.query_params.get("sensor", "S1").upper()
    if sensor not in ("S1", "S2", "S3", "S4"):
        await websocket.send_json({"error": "Sensor inválido. Use S1, S2, S3 ou S4."})
        await websocket.close()
        return
    try:
        interval_s = float(websocket.query_params.get("interval_s", "0.5"))
    except ValueError:
        interval_s = 0.5
    try:
        sample_rate = int(websocket.query_params.get("sample_rate", "200000"))
    except ValueError:
        sample_rate = 200000
    ok, msg = start_spectrum(sensor, interval_s, sample_rate_hz=sample_rate)
    if not ok:
        await websocket.send_json({"error": msg})
        await websocket.close()
        return
    conn_id = id(websocket)
    global _spectrum_stream_owner
    _spectrum_stream_owner = conn_id
    try:
        last_sent = None
        while True:
            frame = get_last_spectrum_frame()
            if frame is None:
                await asyncio.sleep(0.05)
                continue
            if "error" in frame:
                await websocket.send_json(frame)
                break
            if frame != last_sent:
                last_sent = dict(frame)
                await websocket.send_json(frame)
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if _spectrum_stream_owner == conn_id:
            _spectrum_stream_owner = None
            stop_spectrum()
        try:
            from acquisition.calibration_loop import restart_calibration_if_desired
            restart_calibration_if_desired()
        except Exception:
            pass


# --- Calibração (Etapa 4) ---

@router.get("/calibration/status")
async def calibration_status():
    """Status do loop de calibração: running, params atuais, last_fit por sensor."""
    from acquisition.calibration_loop import get_calibration_status
    return get_calibration_status()


@router.post("/calibration/start")
async def calibration_start(body: CalibrationStartBody):
    """Inicia o loop de calibração contínua (para monitor/spectrum se ativos)."""
    from acquisition.calibration_loop import start_calibration_loop
    start_calibration_loop(
        rate_hz=body.rate_hz,
        chunk_duration_s=body.chunk_duration_s,
        interval_s=body.interval_s,
        fit_points=body.fit_points,
        sensors=body.sensors,
    )
    return {"started": True}


@router.post("/calibration/stop")
async def calibration_stop():
    """Para o loop de calibração (solicitação do usuário na página; não re-inicia ao terminar aquisição/monitor/espectro)."""
    from acquisition.calibration_loop import stop_calibration_loop
    stop_calibration_loop(user_requested=True)
    return {"stopped": True}


@router.post("/calibration/reset")
async def calibration_reset(body: Optional[CalibrationResetBody] = None):
    """
    Zera buffers e último fit.
    Se body.restart=True, para a calibração (se estiver rodando), reseta e reinicia com os parâmetros
    enviados, executando novamente a aquisição inicial de 10 s por sensor.
    """
    import time
    from acquisition.calibration_loop import (
        reset_calibration,
        stop_calibration_loop,
        start_calibration_loop,
        is_calibration_running,
    )
    was_running = is_calibration_running()
    if was_running:
        stop_calibration_loop()
        time.sleep(1.5)
    reset_calibration()
    if body and body.restart:
        start_calibration_loop(
            rate_hz=body.rate_hz,
            chunk_duration_s=body.chunk_duration_s,
            interval_s=body.interval_s,
            fit_points=body.fit_points,
            sensors=body.sensors or None,
        )
        return {"reset": True, "restarted": True}
    return {"reset": True, "restarted": False}


@router.get("/calibration/fit/{sensor}")
async def calibration_fit(sensor: str):
    """Último fit do sensor (params, R, G, ellipse_curve) para o gráfico X-Y."""
    from acquisition.calibration_loop import get_last_fit
    if sensor not in SENSOR_CHANNELS:
        raise HTTPException(400, "Sensor inválido. Use S1, S2, S3 ou S4.")
    fit = get_last_fit(sensor)
    if fit is None:
        return {"sensor": sensor, "params": None, "R": [], "G": [], "ellipse_curve": {"x": [], "y": []}, "updated_utc": None}
    return {"sensor": sensor, **fit}


@router.post("/calibration/fit-from-run")
async def calibration_fit_from_run(body: FitFromRunBody):
    """Aplica fit na run indicada para o sensor e grava no JSON do sensor. One-shot."""
    from calibration.ellipse import fit_ellipse, ellipse_curve_points
    from calibration.storage import save_ellipse_params
    from datetime import datetime
    if body.sensor not in SENSOR_CHANNELS:
        raise HTTPException(400, "Sensor inválido. Use S1, S2, S3 ou S4.")
    out = read_run_bin(body.run_id)
    if not out:
        raise HTTPException(404, "Run não encontrada")
    data, meta = out
    ch0, ch1 = SENSOR_CHANNELS[body.sensor]
    channels = meta.get("channels", [])
    if ch0 not in channels or ch1 not in channels:
        raise HTTPException(400, f"Run não contém canais do sensor {body.sensor}")
    idx0 = channels.index(ch0)
    idx1 = channels.index(ch1)
    R = data[idx0, :].flatten()
    G = data[idx1, :].flatten()
    max_pts = 100000
    if len(R) > max_pts:
        step = len(R) // max_pts
        R = R[::step]
        G = G[::step]
    if len(R) < 10:
        raise HTTPException(400, "Poucos pontos na run para o fit")
    p, q, r, s, alpha = fit_ellipse(R, G)
    param = (p, q, r, s, alpha)
    updated_utc = datetime.utcnow().isoformat() + "Z"
    save_ellipse_params(body.sensor, list(param), updated_utc)
    ex, ey = ellipse_curve_points(param, 200)
    # Downsample R,G para plot (máx 2000)
    n_plot = min(2000, len(R))
    step_r = max(1, len(R) // n_plot)
    R_plot = R[::step_r].tolist()
    G_plot = G[::step_r].tolist()
    return {
        "sensor": body.sensor,
        "params": [p, q, r, s, alpha],
        "R": R_plot,
        "G": G_plot,
        "ellipse_curve": {"x": ex.tolist(), "y": ey.tolist()},
        "updated_utc": updated_utc,
    }


@router.get("/calibration/params/{sensor}")
async def calibration_params(sensor: str):
    """Parâmetros da elipse carregados do arquivo do sensor (para UI ou demodulação)."""
    from calibration.storage import load_ellipse_params
    if sensor not in SENSOR_CHANNELS:
        raise HTTPException(400, "Sensor inválido. Use S1, S2, S3 ou S4.")
    params = load_ellipse_params(sensor)
    if params is None:
        return {"sensor": sensor, "params": None, "updated_utc": None}
    return {"sensor": sensor, **params}


@router.get("/files/{run_id}/demod")
async def file_demod(run_id: str):
    """
    Dados demodulados (fase por sensor). Se existir processed/{run_id}_demod.json retorna;
    senão, se meta tiver ellipse_params, calcula on-the-fly a partir do BIN.
    """
    demod = read_demod(run_id)
    if demod is not None:
        meta = get_run_metadata(run_id) or {}
        fs = meta.get("sample_rate_hz", 1)
        for sensor in list(demod.keys()):
            v = demod[sensor]
            if isinstance(v, dict) and "time_s" not in v and "phase" in v:
                n = len(v["phase"])
                demod[sensor] = {**v, "time_s": (np.arange(n, dtype=np.float64) / fs).tolist()}
        return {"run_id": run_id, "meta": meta, "demod": demod}
    meta = get_run_metadata(run_id)
    if not meta:
        raise HTTPException(404, "Run não encontrada")
    ellipse_params = meta.get("ellipse_params")
    if not ellipse_params:
        return {"run_id": run_id, "meta": meta, "demod": None}
    out = read_run_bin(run_id)
    if not out:
        raise HTTPException(404, "Run não encontrada")
    data, _ = out
    from calibration.ellipse import demodulate_phase
    channels = meta.get("channels", [])
    fs = meta.get("sample_rate_hz", 1)
    demod = {}
    for sensor, params in ellipse_params.items():
        if sensor not in SENSOR_CHANNELS:
            continue
        ch0, ch1 = SENSOR_CHANNELS[sensor]
        if ch0 not in channels or ch1 not in channels:
            continue
        idx0 = channels.index(ch0)
        idx1 = channels.index(ch1)
        phase = demodulate_phase(data[idx0], data[idx1], tuple(params))
        n = len(phase)
        t = (np.arange(n, dtype=np.float64) / fs).tolist()
        demod[sensor] = {"phase": phase.tolist(), "time_s": t, "ellipse_params": list(params)}
    return {"run_id": run_id, "meta": meta, "demod": demod}
