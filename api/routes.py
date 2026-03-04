"""
Rotas REST: acquisition (start/stop/status/preview/metrics) e files (list/download).
"""
import uuid
from datetime import datetime
from typing import Optional

import numpy as np

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from acquisition.daq_runner import (
    get_state,
    run_acquisition,
    stop_acquisition,
    AcquisitionStatus,
)
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

router = APIRouter(prefix="/api", tags=["api"])


class AcquisitionStartBody(BaseModel):
    channels: Optional[list[int]] = None
    sensors: Optional[list[str]] = None
    sample_rate_hz: float = 5000
    duration_s: float = 5
    test_name: str = ""
    range_id: Optional[str] = "BIP5VOLTS"


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
        range_id=body.range_id or "BIP5VOLTS",
    )
    return {"run_id": run_id, "status": "started", "channels": ch}


@router.post("/acquisition/stop")
async def acquisition_stop():
    """Solicita parada da aquisição (scan finito pode terminar naturalmente)."""
    stopped = stop_acquisition()
    return {"stopped": stopped}


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
        # Preview: downsample para ~1000 pontos
        data = state.result.data
        down = downsample(data, 1000)
        # Enviar por canal: { channel: [t, values] }
        rate = state.result.rate_hz
        n = down.shape[1]
        t = [i / rate for i in range(n)]
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
    metrics = compute_channel_metrics(data)
    return {"run_id": run_id, "meta": meta, "metrics": metrics}


@router.get("/files/{run_id}/preview")
async def file_preview(run_id: str, max_points: int = MAX_PLOT_POINTS):
    """Dados downsampled para plot pós-aquisição (zoom/pan)."""
    out = read_run_bin(run_id)
    if not out:
        raise HTTPException(404, "Run não encontrada")
    data, meta = out
    fs = meta["sample_rate_hz"]
    down = downsample_for_plot(data, max_points)
    n = down.shape[1]
    t = [i / fs for i in range(n)]
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
    metrics = compute_channel_metrics(data)
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
