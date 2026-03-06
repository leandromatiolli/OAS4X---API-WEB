"""
Espectro em tempo real: loop de aquisições finitas + FFT, streaming via WebSocket.
Um único "dono" do DAQ por vez (Acquisition, Monitor ou Espectro).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional, Tuple

import numpy as np

from config import SENSOR_CHANNELS

SPECTRUM_MAX_POINTS_DISPLAY = 8000
SPECTRUM_INTERVAL_MIN = 0.1
SPECTRUM_INTERVAL_MAX = 5.0

_spectrum_lock = threading.Lock()
_spectrum_thread: Optional[threading.Thread] = None
_spectrum_stop = threading.Event()
_spectrum_frame: Optional[Dict[str, Any]] = None
_spectrum_sensor: Optional[str] = None
_spectrum_interval_s: Optional[float] = None


def _get_uldaq():
    try:
        from uldaq import (
            get_daq_device_inventory,
            DaqDevice,
            InterfaceType,
            AiInputMode,
            Range,
            create_float_buffer,
            ScanOption,
            AInScanFlag,
            WaitType,
        )
        return True, (
            get_daq_device_inventory,
            DaqDevice,
            InterfaceType,
            AiInputMode,
            Range,
            create_float_buffer,
            ScanOption,
            AInScanFlag,
            WaitType,
        )
    except ImportError:
        return False, None


def _downsample_spectrum(freq: np.ndarray, mag: np.ndarray, max_pts: int) -> Tuple[np.ndarray, np.ndarray]:
    n = len(freq)
    if n <= max_pts:
        return freq, mag
    step = n / max_pts
    idx = (np.arange(max_pts) * step).astype(int)
    return freq[idx], mag[idx]


def _run_spectrum_thread(
    sensor: str,
    interval_s: float,
    sample_rate_hz: float,
    range_id: str,
) -> None:
    global _spectrum_frame
    ok, ul = _get_uldaq()
    if not ok or ul is None:
        with _spectrum_lock:
            _spectrum_frame = {"error": "uldaq não disponível"}
        return
    (
        get_daq_device_inventory,
        DaqDevice,
        InterfaceType,
        AiInputMode,
        Range,
        create_float_buffer,
        ScanOption,
        AInScanFlag,
        WaitType,
    ) = ul

    if sensor not in SENSOR_CHANNELS:
        with _spectrum_lock:
            _spectrum_frame = {"error": f"Sensor {sensor} inválido"}
        return
    ch0, ch1 = SENSOR_CHANNELS[sensor]
    from acquisition.ranges import get_range_enum
    range_enum = get_range_enum(range_id)

    from processing.analysis import fft_magnitude

    devices = get_daq_device_inventory(InterfaceType.ANY)
    if not devices:
        with _spectrum_lock:
            _spectrum_frame = {"error": "Dispositivo não encontrado"}
        return

    descriptor = devices[0]
    daq = DaqDevice(descriptor)
    ai = daq.get_ai_device()
    if not ai:
        daq.release()
        with _spectrum_lock:
            _spectrum_frame = {"error": "Dispositivo sem entrada analógica"}
        return

    num_channels = 2
    samples_per_channel = int(sample_rate_hz * interval_s)
    total_samples = samples_per_channel * num_channels
    df_hz = sample_rate_hz / samples_per_channel if samples_per_channel else 0

    try:
        daq.connect()
    except Exception as e:
        daq.release()
        with _spectrum_lock:
            _spectrum_frame = {"error": str(e)}
        return

    buf = create_float_buffer(num_channels, samples_per_channel)

    try:
        while not _spectrum_stop.is_set():
            try:
                rate = ai.a_in_scan(
                    ch0,
                    ch1,
                    AiInputMode.SINGLE_ENDED,
                    range_enum,
                    samples_per_channel,
                    sample_rate_hz,
                    ScanOption.DEFAULTIO,
                    AInScanFlag.DEFAULT,
                    buf,
                )
                ai.scan_wait(WaitType.WAIT_UNTIL_DONE, interval_s + 10.0)
            except Exception as e:
                with _spectrum_lock:
                    _spectrum_frame = {"error": str(e)}
                break
            arr = np.array(buf[:total_samples], dtype=np.float32)
            data = arr.reshape(-1, num_channels).T
            signal = data[0, :]
            freq, mag = fft_magnitude(signal, rate, window=True, db=True)
            freq_d, mag_d = _downsample_spectrum(
                freq, mag, SPECTRUM_MAX_POINTS_DISPLAY
            )
            with _spectrum_lock:
                _spectrum_frame = {
                    "freq_hz": freq_d.tolist(),
                    "magnitude_db": mag_d.tolist(),
                    "sensor": sensor,
                    "interval_s": interval_s,
                    "fs_hz": float(rate),
                    "df_hz": df_hz,
                    "n_points": len(freq_d),
                }
    finally:
        if daq.is_connected():
            try:
                daq.disconnect()
            except Exception:
                pass
        try:
            daq.release()
        except Exception:
            pass
        with _spectrum_lock:
            _spectrum_frame = None


def is_spectrum_running() -> bool:
    with _spectrum_lock:
        return _spectrum_thread is not None and _spectrum_thread.is_alive()


def get_spectrum_sensor() -> Optional[str]:
    return _spectrum_sensor


def get_spectrum_interval_s() -> Optional[float]:
    return _spectrum_interval_s


def get_last_spectrum_frame() -> Optional[Dict[str, Any]]:
    with _spectrum_lock:
        if _spectrum_frame is None:
            return None
        return dict(_spectrum_frame)


def start_spectrum(
    sensor: str,
    interval_s: float,
    sample_rate_hz: float = 200000,
    range_id: str = "UNI5VOLTS",
) -> Tuple[bool, str]:
    """Inicia o espectro em tempo real. Retorna (ok, mensagem)."""
    from acquisition.monitor import stop_monitor

    if sensor not in SENSOR_CHANNELS:
        return False, f"Sensor {sensor} inválido. Use S1, S2, S3 ou S4."
    if not (SPECTRUM_INTERVAL_MIN <= interval_s <= SPECTRUM_INTERVAL_MAX):
        return False, f"Intervalo deve estar entre {SPECTRUM_INTERVAL_MIN} e {SPECTRUM_INTERVAL_MAX} s."
    try:
        stop_monitor()
    except Exception:
        pass
    try:
        from acquisition.calibration_loop import stop_calibration_loop
        stop_calibration_loop()
    except Exception:
        pass
    stop_spectrum()
    time.sleep(1.0)
    global _spectrum_thread, _spectrum_sensor, _spectrum_interval_s, _spectrum_frame
    with _spectrum_lock:
        thread_alive = _spectrum_thread is not None and _spectrum_thread.is_alive()
    if thread_alive:
        return False, "Aguarde: espectro ainda encerrando."
    with _spectrum_lock:
        _spectrum_frame = None
    _spectrum_stop.clear()
    _spectrum_sensor = sensor
    _spectrum_interval_s = interval_s
    _spectrum_thread = threading.Thread(
        target=_run_spectrum_thread,
        args=(sensor, interval_s, sample_rate_hz, range_id),
        daemon=True,
    )
    _spectrum_thread.start()
    time.sleep(0.5)
    if not _spectrum_thread.is_alive():
        err = (get_last_spectrum_frame() or {}).get("error", "Falha ao iniciar espectro")
        return False, err
    return True, "Espectro iniciado."


def stop_spectrum() -> None:
    global _spectrum_thread, _spectrum_sensor, _spectrum_interval_s, _spectrum_frame
    _spectrum_stop.set()
    with _spectrum_lock:
        th = _spectrum_thread
        _spectrum_thread = None
        _spectrum_sensor = None
        _spectrum_interval_s = None
        _spectrum_frame = None
    if th is not None:
        th.join(timeout=15.0)
    time.sleep(0.6)
