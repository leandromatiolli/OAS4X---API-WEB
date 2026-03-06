"""
Fit de elipse e demodulação (fase) – baseado em mkf.
Funções puras: fit_ellipse, rescale, demodulate_phase, ellipse_curve_points.
"""
from __future__ import annotations

from typing import Tuple, Union

import numpy as np


def fit_ellipse(R: np.ndarray, G: np.ndarray) -> Tuple[float, float, float, float, float]:
    """
    Ajuste de elipse em dados (R, G) dos dois canais.
    Retorna (p, q, r, s, alpha).
    """
    x2 = np.float32(R).flatten()
    y2 = np.float32(G).flatten()
    A2 = np.vstack([x2**2, y2**2, x2*y2, x2, y2]).T
    A, B, C, D, E = np.linalg.lstsq(A2, np.ones_like(x2), rcond=None)[0]
    alpha = -np.arcsin(C / np.sqrt(4 * A * B))
    r = np.sqrt(B / A)
    p = (2*B*D - E*C) / (C**2 - 4*A*B)
    q = (2*A*E - D*C) / (C**2 - 4*A*B)
    s = np.sqrt(p**2 + (1/A + (q**2)*(r**2) + 2*p*q*r*np.sin(alpha) + (p**2)*np.sin(alpha)**2) / np.cos(alpha)**2)
    return float(p), float(q), float(r), float(s), float(alpha)


def rescale(
    R: np.ndarray,
    G: np.ndarray,
    param: Tuple[float, float, float, float, float],
    invert: bool = False,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Converte (R, G) para coordenadas normalizadas da elipse (ou inverte).
    param = (p, q, r, s, alpha).
    """
    x2 = np.float32(R)
    y2 = np.float32(G)
    p, q, r, s, alpha = param
    if invert:
        x = s * x2 + p
        y = s * (y2 * np.cos(alpha) - x2 * np.sin(alpha)) / r + q
    else:
        x = (x2 - p) / s
        y = ((y2 - q) * r + (x2 - p) * np.sin(alpha)) / np.cos(alpha) / s
    return x, y


def demodulate_phase(
    ch0: np.ndarray,
    ch1: np.ndarray,
    param: Tuple[float, float, float, float, float],
) -> np.ndarray:
    """
    Fase demodulada: unwrap(arctan2(x, y)) após rescale(ch0, ch1, param).
    Entrada: dois arrays 1D (canal 0 e 1 do sensor).
    """
    x, y = rescale(ch0, ch1, param)
    phase = np.unwrap(np.arctan2(x, y))
    return phase


def ellipse_curve_points(
    param: Tuple[float, float, float, float, float],
    n_points: int = 200,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Pontos da elipse em coordenadas originais para plotar.
    Retorna (x, y) = rescale(sin(t), cos(t), param, invert=True).
    """
    t = np.linspace(0, 2 * np.pi, n_points)
    x_c = np.sin(t)
    y_c = np.cos(t)
    x, y = rescale(x_c, y_c, param, invert=True)
    return x, y
