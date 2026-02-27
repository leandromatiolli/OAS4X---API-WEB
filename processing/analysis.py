"""
Análise para Etapa 3: RMS em janela deslizante, P95/P99, FFT.
"""
from __future__ import annotations

from typing import List

import numpy as np

# Máximo de pontos para preview/plot (downsample no backend)
MAX_PLOT_POINTS = 10_000


def rms_sliding_window(signal: np.ndarray, window_samples: int) -> np.ndarray:
    """
    RMS em janela deslizante.
    signal: 1D array
    window_samples: tamanho da janela em amostras
    Retorna array de mesmo tamanho (modo 'same': janela centralizada).
    """
    n = signal.size
    if window_samples <= 0 or n == 0:
        return np.zeros_like(signal, dtype=np.float64)
    window_samples = min(window_samples, n)
    sq = signal.astype(np.float64) ** 2
    kernel = np.ones(window_samples, dtype=np.float64) / window_samples
    mean_sq = np.convolve(sq, kernel, mode="same")
    return np.sqrt(np.maximum(mean_sq, 0))


def percentiles_per_channel(
    data: np.ndarray,
    percentiles: List[float],
) -> List[dict]:
    """
    data: shape (num_channels, samples)
    percentiles: ex. [95, 99]
    Retorna lista de dicts por canal: channel, p95, p99, etc.
    """
    out = []
    for ch in range(data.shape[0]):
        x = data[ch, :].astype(np.float64)
        row = {"channel": ch}
        for p in percentiles:
            row[f"p{p}"] = float(np.percentile(np.abs(x), p))
        out.append(row)
    return out


def fft_magnitude(
    signal: np.ndarray,
    fs_hz: float,
    window: bool = True,
    db: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """
    FFT unilateral: retorna (freq_axis_hz, magnitude).
    signal: 1D array
    fs_hz: taxa de amostragem
    window: aplicar janela de Hamming
    db: magnitude em dB (True) ou linear (False)
    """
    n = signal.size
    if n == 0:
        return np.array([]), np.array([])
    x = signal.astype(np.float64)
    if window:
        x = x * np.hamming(n)
    ft = np.fft.rfft(x)
    mag = np.abs(ft) * (2.0 / n)
    mag[0] *= 0.5
    if len(ft) > 1 and n % 2 == 0:
        mag[-1] *= 0.5
    if db:
        mag = 20 * np.log10(np.maximum(mag, 1e-12))
    freq = np.fft.rfftfreq(n, 1.0 / fs_hz)
    return freq, mag


def downsample_for_plot(
    data: np.ndarray,
    max_points: int = MAX_PLOT_POINTS,
) -> np.ndarray:
    """Downsample para plot (zoom/pan suave). data: (num_channels, samples)."""
    _, n = data.shape
    if n <= max_points:
        return data
    step = n // max_points
    idx = np.arange(0, n, step)[:max_points]
    return data[:, idx]
