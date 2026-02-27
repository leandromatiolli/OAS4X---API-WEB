"""
Métricas por canal: RMS, DC (média), peak (max abs), clipping (% ou count).
"""
from __future__ import annotations

from typing import List

import numpy as np


def clip_threshold_from_range(range_v: float = 5.0) -> float:
    """Threshold de clipping em volts (ex.: 95% do range ±5V)."""
    return 0.95 * range_v


def compute_channel_metrics(
    data: np.ndarray,
    range_volts: float = 5.0,
) -> List[dict]:
    """
    data: shape (num_channels, samples)
    range_volts: range usado (ex. 5.0 para ±5V)
    Retorna lista de dicts por canal: rms, dc, peak, clipping_pct, clipping_count.
    """
    threshold = clip_threshold_from_range(range_volts)
    out = []
    for ch in range(data.shape[0]):
        x = data[ch, :].astype(np.float64)
        n = x.size
        dc = float(np.mean(x))
        rms = float(np.sqrt(np.mean(x ** 2)))
        peak = float(np.max(np.abs(x)))
        clip_count = int(np.sum(np.abs(x) >= threshold))
        clip_pct = 100.0 * clip_count / n if n else 0.0
        out.append({
            "channel": ch,
            "rms": rms,
            "dc": dc,
            "peak": peak,
            "clipping_count": clip_count,
            "clipping_pct": round(clip_pct, 4),
        })
    return out


def downsample(data: np.ndarray, max_points: int) -> np.ndarray:
    """
    Downsample por canal: mantém no máximo max_points pontos por canal.
    data: (num_channels, samples)
    """
    _, n = data.shape
    if n <= max_points:
        return data
    step = n // max_points
    idx = np.arange(0, n, step)[:max_points]
    return data[:, idx]
