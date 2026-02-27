"""
Configuração central do OAS4X API-WEB.
Paths /data e /calibration configuráveis via env.
Em desenvolvimento, use OAS4X_DATA=./data e OAS4X_CALIBRATION=./calibration.
"""
import os
from pathlib import Path

# Base do projeto (diretório que contém api/)
_PROJECT_ROOT = Path(__file__).resolve().parent

# Base paths: env ou default local (./data, ./calibration) para dev
DATA_ROOT = Path(os.environ.get("OAS4X_DATA", str(_PROJECT_ROOT / "data")))
CALIBRATION_ROOT = Path(os.environ.get("OAS4X_CALIBRATION", str(_PROJECT_ROOT / "calibration")))

# Subpastas sob /data
RAW_DIR = DATA_ROOT / "raw"
PROCESSED_DIR = DATA_ROOT / "processed"
LOGS_DIR = DATA_ROOT / "logs"

# Versão do software (para metadados)
SOFTWARE_VERSION = os.environ.get("OAS4X_VERSION", "0.1.0")

# Sensores -> canais (fixo)
SENSOR_CHANNELS = {
    "S1": (0, 1),
    "S2": (2, 3),
    "S3": (4, 5),
    "S4": (6, 7),
}


def ensure_dirs() -> None:
    """Cria diretórios de dados e calibração se não existirem."""
    for d in (RAW_DIR, PROCESSED_DIR, LOGS_DIR, CALIBRATION_ROOT):
        d.mkdir(parents=True, exist_ok=True)
