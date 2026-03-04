"""
Gravação e listagem de runs: BIN (bruto intercalado) + JSON (metadados).
Path /data configurável via config.RAW_DIR.
Etapa 2: gravação robusta em chunks + fsync (não depende do browser; tolera rede lenta).
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import numpy as np

from config import RAW_DIR, SOFTWARE_VERSION

# Tamanho do chunk para gravar BIN (em amostras float32) - evita pico de I/O
_CHUNK_FLOATS = 256 * 1024


def _run_base(run_id: str) -> Path:
    return RAW_DIR / run_id


def write_run(
    data: np.ndarray,
    sample_rate_hz: float,
    duration_s: float,
    channels: List[int],
    test_name: str = "",
    run_id: Optional[str] = None,
    analog_range_id: Optional[str] = None,
) -> str:
    """
    Escreve uma run em /data/raw/<run_id>.<bin|json>.
    data: shape (num_channels, samples_per_channel), float32.
    Grava BIN em chunks e faz fsync para garantir persistência em disco.
    Retorna run_id usado.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if run_id is None:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        run_id = f"{ts}_{uuid.uuid4().hex[:8]}"
    base = _run_base(run_id)
    bin_path = base.with_suffix(".bin")
    json_path = base.with_suffix(".json")

    num_channels, samples_per_channel = data.shape
    interleaved = data.T.reshape(-1).astype(np.float32)
    n_total = interleaved.size
    with open(bin_path, "wb") as f:
        offset = 0
        while offset < n_total:
            end = min(offset + _CHUNK_FLOATS, n_total)
            chunk = interleaved[offset:end]
            f.write(chunk.tobytes())
            offset = end
        f.flush()
        os.fsync(f.fileno())

    meta = {
        "run_id": run_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "sample_rate_hz": sample_rate_hz,
        "duration_s": duration_s,
        "channels": channels,
        "num_channels": num_channels,
        "samples_per_channel": int(samples_per_channel),
        "software_version": SOFTWARE_VERSION,
        "test_name": test_name or run_id,
        "binary_file": bin_path.name,
        "format": "interleaved_float32",
    }
    if analog_range_id is not None:
        meta["range"] = analog_range_id
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    return run_id


def list_runs() -> List[dict]:
    """Lista runs em RAW_DIR; cada item tem metadados do JSON + run_id (stem)."""
    if not RAW_DIR.exists():
        return []
    out = []
    for jpath in sorted(RAW_DIR.glob("*.json"), reverse=True):
        run_id = jpath.stem
        try:
            with open(jpath, encoding="utf-8") as f:
                meta = json.load(f)
            meta["run_id"] = run_id
            out.append(meta)
        except Exception:
            continue
    return out


def get_run_metadata(run_id: str) -> dict | None:
    """Retorna metadados de uma run ou None."""
    jpath = RAW_DIR / f"{run_id}.json"
    if not jpath.exists():
        return None
    with open(jpath, encoding="utf-8") as f:
        return json.load(f)


def get_run_bin_path(run_id: str) -> Path | None:
    """Retorna Path do arquivo .bin da run ou None."""
    p = RAW_DIR / f"{run_id}.bin"
    return p if p.exists() else None


def delete_run(run_id: str) -> bool:
    """
    Exclui os arquivos .bin e .json da run.
    Retorna True se pelo menos um arquivo foi removido; False se run não existir.
    """
    if not run_id or ".." in run_id or "/" in run_id:
        return False
    bin_path = RAW_DIR / f"{run_id}.bin"
    json_path = RAW_DIR / f"{run_id}.json"
    removed = False
    if bin_path.exists():
        try:
            bin_path.unlink()
            removed = True
        except Exception:
            pass
    if json_path.exists():
        try:
            json_path.unlink()
            removed = True
        except Exception:
            pass
    return removed


def read_run_bin(run_id: str) -> tuple[np.ndarray, dict] | None:
    """
    Lê BIN da run; retorna (data, meta) com data shape (num_channels, samples_per_channel)
    ou None se run não existir.
    """
    meta = get_run_metadata(run_id)
    if not meta:
        return None
    bin_path = get_run_bin_path(run_id)
    if not bin_path or not bin_path.exists():
        return None
    num_ch = meta["num_channels"]
    samples = meta["samples_per_channel"]
    interleaved = np.fromfile(bin_path, dtype=np.float32)
    total = num_ch * samples
    if interleaved.size != total:
        return None
    data = interleaved.reshape(samples, num_ch).T
    return data, meta
