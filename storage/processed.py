"""
Armazenamento de dados processados por run (ex.: fase demodulada).
Formato: data/processed/{run_id}_demod.json com { "S1": { "phase": [...], "ellipse_params": [...] }, ... }
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import PROCESSED_DIR


def get_demod_path(run_id: str) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    return PROCESSED_DIR / f"{run_id}_demod.json"


def write_demod(run_id: str, data: Dict[str, Any]) -> None:
    """
    data: { "S1": { "phase": list, "ellipse_params": [p,q,r,s,alpha] }, ... }
    """
    path = get_demod_path(run_id)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    # Serializar listas numpy como list
    out = {}
    for sensor, v in data.items():
        out[sensor] = {
            "phase": v["phase"] if isinstance(v["phase"], list) else v["phase"].tolist(),
            "ellipse_params": v.get("ellipse_params", []),
        }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.flush()


def read_demod(run_id: str) -> Optional[Dict[str, Any]]:
    """Retorna conteúdo do JSON demodulado ou None."""
    path = get_demod_path(run_id)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
