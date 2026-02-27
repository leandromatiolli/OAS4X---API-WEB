"""
Logging estruturado para OAS4X (Etapa 2).
Saída em stdout (JSON ou formato legível); opcionalmente arquivo em /data/logs/.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from config import LOGS_DIR


class StructuredFormatter(logging.Formatter):
    """Formata registros como JSON com timestamp e nível."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging(
    level: str = "INFO",
    log_to_file: bool = True,
    json_stdout: bool = False,
) -> None:
    """
    Configura logging global.
    json_stdout: se True, stdout em JSON; senão formato legível.
    log_to_file: se True, grava também em /data/logs/oas4x.log (rotação por tamanho).
    """
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)

    if json_stdout:
        fmt = StructuredFormatter()
    else:
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    if log_to_file and LOGS_DIR:
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            from logging.handlers import RotatingFileHandler
            fh = RotatingFileHandler(
                LOGS_DIR / "oas4x.log",
                maxBytes=5 * 1024 * 1024,  # 5 MB
                backupCount=3,
                encoding="utf-8",
            )
            fh.setFormatter(StructuredFormatter())
            root.addHandler(fh)
        except Exception:
            pass
