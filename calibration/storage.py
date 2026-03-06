"""
Persistência dos parâmetros da elipse por sensor em CALIBRATION_ROOT.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import CALIBRATION_ROOT


def get_calibration_path(sensor: str) -> Path:
    """Caminho do JSON de calibração do sensor (ex.: sensor_S1.json)."""
    CALIBRATION_ROOT.mkdir(parents=True, exist_ok=True)
    return CALIBRATION_ROOT / f"sensor_{sensor}.json"


def load_ellipse_params(sensor: str) -> Optional[Dict[str, Any]]:
    """
    Carrega parâmetros da elipse do sensor.
    Retorna dict com "p", "q", "r", "s", "alpha", "updated_utc" e "params" (lista [p,q,r,s,alpha])
    ou None se não existir.
    """
    path = get_calibration_path(sensor)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if "params" in data and len(data["params"]) == 5:
        p, q, r, s, alpha = data["params"]
        data["p"] = p
        data["q"] = q
        data["r"] = r
        data["s"] = s
        data["alpha"] = alpha
    return data


def save_ellipse_params(
    sensor: str,
    params: List[float],
    updated_utc: Optional[str] = None,
) -> None:
    """
    Grava parâmetros da elipse (lista [p, q, r, s, alpha]) no JSON do sensor.
    """
    if len(params) != 5:
        raise ValueError("params deve ter 5 elementos: p, q, r, s, alpha")
    path = get_calibration_path(sensor)
    CALIBRATION_ROOT.mkdir(parents=True, exist_ok=True)
    updated_utc = updated_utc or datetime.utcnow().isoformat() + "Z"
    data = {
        "params": [float(x) for x in params],
        "updated_utc": updated_utc,
        "sensor": sensor,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
