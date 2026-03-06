"""
Espectro em tempo real: scan contínuo em buffer circular, FFT nos últimos N pontos.
Um único "dono" do DAQ por vez (Acquisition, Monitor ou Espectro).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional, Tuple

import numpy as np

from config import SENSOR_CHANNELS

SPECTRUM_MAX_POINTS_DISPLAY = 8000
SPECTRUM_FFT_POINTS_MIN = 8192
SPECTRUM_FFT_POINTS_MAX = 1048576
SPECTRUM_UPDATE_INTERVAL_MIN = 0.05
SPECTRUM_UPDATE_INTERVAL_MAX = 2.0

# Parâmetros FFT padrão (Regulagens FFT)
DEFAULT_FFT_PARAMS: Dict[str, Any] = {
    "window_type": "hamming",
    "db": True,
    "channel": 0,
    "zero_pad": None,
}

_spectrum_lock = threading.Lock()
_spectrum_thread: Optional[threading.Thread] = None
_spectrum_stop = threading.Event()
_spectrum_frame: Optional[Dict[str, Any]] = None
_spectrum_sensor: Optional[str] = None
_spectrum_fft_points: int = 262144
_spectrum_update_interval_s: float = 0.1
_spectrum_fft_params: Dict[str, Any] = {}


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
            ScanStatus,
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
            ScanStatus,
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
    fft_points: int,
    update_interval_s: float,
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
        ScanStatus,
    ) = ul

    if sensor not in SENSOR_CHANNELS:
        with _spectrum_lock:
            _spectrum_frame = {"error": f"Sensor {sensor} inválido"}
        return
    ch0, ch1 = SENSOR_CHANNELS[sensor]
    from acquisition.ranges import get_range_enum
    range_enum = get_range_enum(range_id)

    from processing.analysis import fft_magnitude_advanced, FFT_WINDOW_TYPES

    params = _spectrum_fft_params or DEFAULT_FFT_PARAMS
    window_type = str(params.get("window_type", "hamming")).lower()
    if window_type not in FFT_WINDOW_TYPES:
        window_type = "hamming"
    use_db = bool(params.get("db", True))
    channel = int(params.get("channel", 0))
    if channel not in (0, 1):
        channel = 0
    zero_pad = params.get("zero_pad")
    if zero_pad is not None:
        zero_pad = int(zero_pad)
    if zero_pad is not None and zero_pad <= 0:
        zero_pad = None

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
    samples_per_channel = fft_points
    total_buffer = num_channels * samples_per_channel
    num_per_fft = num_channels * fft_points
    df_hz = sample_rate_hz / fft_points if fft_points else 0

    try:
        daq.connect()
    except Exception as e:
        daq.release()
        with _spectrum_lock:
            _spectrum_frame = {"error": str(e)}
        return

    buf = create_float_buffer(num_channels, samples_per_channel)

    try:
        ai.a_in_scan(
            ch0,
            ch1,
            AiInputMode.SINGLE_ENDED,
            range_enum,
            samples_per_channel,
            sample_rate_hz,
            ScanOption.CONTINUOUS,
            AInScanFlag.DEFAULT,
            buf,
        )
    except Exception as e:
        if daq.is_connected():
            try:
                daq.disconnect()
            except Exception:
                pass
        daq.release()
        with _spectrum_lock:
            _spectrum_frame = {"error": str(e)}
        return

    while not _spectrum_stop.is_set():
        try:
            status, transfer = ai.get_scan_status()
            if status != ScanStatus.RUNNING:
                break
            cur = transfer.current_index
            total_count = getattr(transfer, "current_total_count", None)
            if total_count is not None:
                try:
                    total_count = int(total_count)
                except (TypeError, ValueError):
                    total_count = None
            if cur is None:
                time.sleep(0.01)
                continue
            cur = int(cur)
            # current_index is circular (0..buf_len-1); use current_total_count to know when we have enough samples
            total_count_val = total_count if total_count is not None else cur
            if total_count_val < num_per_fft:
                time.sleep(0.01)
                continue
            buf_len = total_buffer
            indices = [(cur - num_per_fft + i) % buf_len for i in range(num_per_fft)]
            raw = np.array([buf[i] for i in indices], dtype=np.float32)
            data = raw.reshape(-1, num_channels).T
            ch_idx = min(channel, data.shape[0] - 1)
            signal = data[ch_idx, :]
            freq, mag = fft_magnitude_advanced(
                signal, float(sample_rate_hz),
                window_type=window_type,
                db=use_db,
                zero_pad=zero_pad,
            )
            freq_d, mag_d = _downsample_spectrum(
                freq, mag, SPECTRUM_MAX_POINTS_DISPLAY
            )
            frame_data: Dict[str, Any] = {
                "freq_hz": freq_d.tolist(),
                "sensor": sensor,
                "fft_points": fft_points,
                "update_interval_s": update_interval_s,
                "fs_hz": float(sample_rate_hz),
                "df_hz": df_hz,
                "n_points": len(freq_d),
                "channel": ch_idx,
                "window_type": window_type,
                "db": use_db,
            }
            if use_db:
                frame_data["magnitude_db"] = mag_d.tolist()
            else:
                frame_data["magnitude_linear"] = mag_d.tolist()
            with _spectrum_lock:
                _spectrum_frame = frame_data
        except Exception as e:
            with _spectrum_lock:
                _spectrum_frame = {"error": str(e)}
            break
        time.sleep(update_interval_s)

    try:
        ai.scan_stop()
    except Exception:
        pass
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


def get_spectrum_fft_points() -> int:
    return _spectrum_fft_points


def get_spectrum_update_interval_s() -> float:
    return _spectrum_update_interval_s


def get_spectrum_fft_params() -> Dict[str, Any]:
    """Parâmetros FFT atuais (window_type, db, channel, zero_pad)."""
    return dict(_spectrum_fft_params or DEFAULT_FFT_PARAMS)


def get_last_spectrum_frame() -> Optional[Dict[str, Any]]:
    with _spectrum_lock:
        if _spectrum_frame is None:
            return None
        return dict(_spectrum_frame)


def start_spectrum(
    sensor: str,
    fft_points: int = 262144,
    update_interval_s: float = 0.1,
    sample_rate_hz: float = 200000,
    range_id: str = "UNI5VOLTS",
    fft_params: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Inicia o espectro em tempo real (buffer circular + FFT nos últimos N pontos). Retorna (ok, mensagem)."""
    from acquisition.monitor import stop_monitor
    from processing.analysis import FFT_WINDOW_TYPES

    if sensor not in SENSOR_CHANNELS:
        return False, f"Sensor {sensor} inválido. Use S1, S2, S3 ou S4."
    n = max(SPECTRUM_FFT_POINTS_MIN, min(fft_points, SPECTRUM_FFT_POINTS_MAX))
    if not (SPECTRUM_UPDATE_INTERVAL_MIN <= update_interval_s <= SPECTRUM_UPDATE_INTERVAL_MAX):
        update_interval_s = max(SPECTRUM_UPDATE_INTERVAL_MIN, min(update_interval_s, SPECTRUM_UPDATE_INTERVAL_MAX))
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
    global _spectrum_thread, _spectrum_sensor, _spectrum_fft_points, _spectrum_update_interval_s, _spectrum_frame
    with _spectrum_lock:
        thread_alive = _spectrum_thread is not None and _spectrum_thread.is_alive()
    if thread_alive:
        return False, "Aguarde: espectro ainda encerrando."
    global _spectrum_fft_params
    _spectrum_fft_params = dict(fft_params) if fft_params else dict(DEFAULT_FFT_PARAMS)
    wt = _spectrum_fft_params.get("window_type", "hamming")
    if isinstance(wt, str) and wt.lower() not in FFT_WINDOW_TYPES:
        _spectrum_fft_params["window_type"] = "hamming"
    ch = _spectrum_fft_params.get("channel", 0)
    if ch not in (0, 1):
        _spectrum_fft_params["channel"] = 0
    zp = _spectrum_fft_params.get("zero_pad")
    if zp is not None and (not isinstance(zp, int) or zp < 0):
        _spectrum_fft_params["zero_pad"] = None
    with _spectrum_lock:
        _spectrum_frame = None
    _spectrum_stop.clear()
    _spectrum_sensor = sensor
    _spectrum_fft_points = n
    _spectrum_update_interval_s = update_interval_s
    _spectrum_thread = threading.Thread(
        target=_run_spectrum_thread,
        args=(sensor, n, update_interval_s, sample_rate_hz, range_id),
        daemon=True,
    )
    _spectrum_thread.start()
    time.sleep(0.5)
    if not _spectrum_thread.is_alive():
        err = (get_last_spectrum_frame() or {}).get("error", "Falha ao iniciar espectro")
        return False, err
    return True, "Espectro iniciado."


def stop_spectrum() -> None:
    global _spectrum_thread, _spectrum_sensor, _spectrum_fft_points, _spectrum_update_interval_s, _spectrum_frame, _spectrum_fft_params
    _spectrum_stop.set()
    with _spectrum_lock:
        th = _spectrum_thread
        _spectrum_thread = None
        _spectrum_sensor = None
        _spectrum_frame = None
    _spectrum_fft_params = {}
    if th is not None:
        th.join(timeout=15.0)
    time.sleep(0.6)
