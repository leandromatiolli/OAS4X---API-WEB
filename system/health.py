"""
Health do sistema (Etapa 2): uptime, CPU temp, RAM, disco, status USB/DAQ.
"""
import time
from pathlib import Path

from config import DATA_ROOT

# Uptime do processo (segundos desde import)
_process_start = time.time()


def _cpu_temp_c() -> float | None:
    """Temperatura da CPU em °C (Raspberry Pi: /sys/class/thermal/...)."""
    for path in (
        Path("/sys/class/thermal/thermal_zone0/temp"),
        Path("/sys/devices/platform/soc/soc:firmware/get_throttled"),
    ):
        if path.exists() and path.name == "temp":
            try:
                raw = path.read_text().strip()
                return int(raw) / 1000.0
            except Exception:
                pass
    return None


def _memory_mb() -> dict | None:
    """Uso de memória (total, available, percent) em MB."""
    try:
        import psutil
        v = psutil.virtual_memory()
        return {
            "total_mb": round(v.total / (1024 * 1024), 1),
            "available_mb": round(v.available / (1024 * 1024), 1),
            "percent": v.percent,
        }
    except ImportError:
        return None


def _disk_usage() -> dict | None:
    """Uso do disco onde está /data."""
    try:
        import psutil
        usage = psutil.disk_usage(str(DATA_ROOT))
        return {
            "path": str(DATA_ROOT),
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "used_gb": round(usage.used / (1024 ** 3), 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
            "percent": usage.percent,
        }
    except Exception:
        return None


def _daq_status() -> dict:
    """Status do dispositivo USB/DAQ (uldaq)."""
    try:
        from acquisition.daq_runner import discover_device
        ok, dev = discover_device()
        if ok and dev is not None:
            return {
                "connected": True,
                "product": getattr(dev, "product_name", "?"),
                "unique_id": getattr(dev, "unique_id", "?"),
            }
        return {"connected": False, "error": str(dev)}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def get_health_data() -> dict:
    """Agrega todos os dados de health para o endpoint /health."""
    uptime_sec = time.time() - _process_start
    return {
        "status": "ok",
        "service": "oas4x-api",
        "uptime_seconds": round(uptime_sec, 1),
        "uptime_human": _format_uptime(uptime_sec),
        "cpu_temp_c": _cpu_temp_c(),
        "memory": _memory_mb(),
        "disk": _disk_usage(),
        "daq": _daq_status(),
    }


def _format_uptime(sec: float) -> str:
    s = int(sec)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"
