"""
Loop de calibração contínua em baixa taxa: buffer circular por sensor,
aquisição periódica (um sensor por vez, 2 canais), fit de elipse e gravação.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from config import SENSOR_CHANNELS
from calibration.ellipse import fit_ellipse, ellipse_curve_points
from calibration.storage import save_ellipse_params

# Estado e controle
_calibration_running = False
_calibration_stop = False
_lock = threading.Lock()
_thread: Optional[threading.Thread] = None

# Parâmetros atuais do loop
_params: Dict[str, Any] = {
    "rate_hz": 1000,
    "chunk_duration_s": 1,
    "interval_s": 5,
    "fit_points": 50000,
    "sensors": ["S1", "S2", "S3", "S4"],
}

# Buffer circular por sensor: (R, G) cada um com max 50000 amostras (50 s a 1000 Hz)
_MAX_BUFFER_SAMPLES = 50000
_INITIAL_ACQUISITION_S = 10.0  # aquisição inicial ao ligar calibração (s)
_INITIAL_RATE_HZ = 1000  # taxa da aquisição inicial (Hz)
_buffers: Dict[str, tuple] = {}  # sensor -> (np.ndarray R, np.ndarray G, write_index)
_last_fit: Dict[str, Dict[str, Any]] = {}  # sensor -> {params, R, G, ellipse_curve, updated_utc}
_sensor_index = 0  # rotação: próximo sensor a calibrar
_phase: str = "idle"  # "idle" | "initial" | "continuous"
_user_wants_calibration_on: bool = False  # True = usuário ligou; mantém até desligar na página
_skip_initial_phase: bool = False  # True ao reiniciar após aquisição/monitor/espectro (mantém buffer)


def _get_uldaq():
    try:
        from uldaq import (
            get_daq_device_inventory,
            DaqDevice,
            InterfaceType,
            AiInputMode,
            create_float_buffer,
            ScanOption,
            AInScanFlag,
            WaitType,
        )
        from acquisition.ranges import get_range_enum
        return True, (
            get_daq_device_inventory,
            DaqDevice,
            InterfaceType,
            AiInputMode,
            create_float_buffer,
            ScanOption,
            AInScanFlag,
            WaitType,
            get_range_enum,
        )
    except ImportError:
        return False, None


def _acquire_two_channels(low_ch: int, high_ch: int, rate_hz: float, duration_s: float) -> Optional[np.ndarray]:
    """
    Aquisição finita 2 canais; retorna data (2, samples) ou None em erro.
    """
    ok, ul = _get_uldaq()
    if not ok or ul is None:
        return None
    (get_daq_device_inventory, DaqDevice, InterfaceType, AiInputMode,
     create_float_buffer, ScanOption, AInScanFlag, WaitType, get_range_enum) = ul
    range_enum = get_range_enum("BIP5VOLTS")
    devices = get_daq_device_inventory(InterfaceType.ANY)
    if not devices:
        return None
    daq = DaqDevice(devices[0])
    ai = daq.get_ai_device()
    if not ai:
        daq.release()
        return None
    num_channels = 2
    samples_per_channel = int(rate_hz * duration_s)
    total_samples = samples_per_channel * num_channels
    try:
        daq.connect()
        buf = create_float_buffer(num_channels, samples_per_channel)
        ai.a_in_scan(
            low_ch,
            high_ch,
            AiInputMode.SINGLE_ENDED,
            range_enum,
            samples_per_channel,
            rate_hz,
            ScanOption.DEFAULTIO,
            AInScanFlag.DEFAULT,
            buf,
        )
        ai.scan_wait(WaitType.WAIT_UNTIL_DONE, duration_s + 5.0)
        arr = np.array(buf[:total_samples], dtype=np.float32)
        data = arr.reshape(-1, num_channels).T
    except Exception:
        data = None
    finally:
        if daq.is_connected():
            daq.disconnect()
        daq.release()
    return data


def _ensure_buffer(sensor: str) -> None:
    if sensor not in _buffers:
        _buffers[sensor] = (
            np.zeros(_MAX_BUFFER_SAMPLES, dtype=np.float32),
            np.zeros(_MAX_BUFFER_SAMPLES, dtype=np.float32),
            0,
        )


def _append_to_buffer(sensor: str, R: np.ndarray, G: np.ndarray) -> None:
    _ensure_buffer(sensor)
    rb, gb, wi = _buffers[sensor]
    n = len(R)
    if n >= _MAX_BUFFER_SAMPLES:
        rb[:] = R[-_MAX_BUFFER_SAMPLES:]
        gb[:] = G[-_MAX_BUFFER_SAMPLES:]
        _buffers[sensor] = (rb, gb, _MAX_BUFFER_SAMPLES)
        return
    for i in range(n):
        rb[wi % _MAX_BUFFER_SAMPLES] = R[i]
        gb[wi % _MAX_BUFFER_SAMPLES] = G[i]
        wi += 1
    _buffers[sensor] = (rb, gb, wi)


def _get_buffer_slice(sensor: str, n_points: Optional[int]) -> Optional[tuple]:
    """Retorna (R, G) dos últimos n_points (ou todos se n_points is None/0)."""
    if sensor not in _buffers:
        return None
    rb, gb, wi = _buffers[sensor]
    total = min(wi, _MAX_BUFFER_SAMPLES)
    if total == 0:
        return None
    take = n_points if n_points and n_points > 0 else total
    take = min(take, total)
    start = (wi - take) % _MAX_BUFFER_SAMPLES
    if start + take <= _MAX_BUFFER_SAMPLES:
        R = rb[start : start + take].copy()
        G = gb[start : start + take].copy()
    else:
        R = np.concatenate([rb[start:], rb[: take - (_MAX_BUFFER_SAMPLES - start)]])
        G = np.concatenate([gb[start:], gb[: take - (_MAX_BUFFER_SAMPLES - start)]])
    return R, G


def _do_fit_for_sensor(sensor: str, fit_points: int, params: Dict[str, Any]) -> None:
    """Aplica fit no buffer do sensor e atualiza _last_fit e arquivo."""
    R, G = _get_buffer_slice(sensor, fit_points if fit_points else None)
    if R is None or len(R) < 10:
        return
    try:
        p, q, r, s, alpha = fit_ellipse(R, G)
        param = (p, q, r, s, alpha)
        updated_utc = datetime.utcnow().isoformat() + "Z"
        save_ellipse_params(sensor, list(param), updated_utc)
        ex, ey = ellipse_curve_points(param, 200)
        with _lock:
            _last_fit[sensor] = {
                "params": [p, q, r, s, alpha],
                "R": R.tolist() if len(R) <= 2000 else (R[:: max(1, len(R) // 2000)].tolist()),
                "G": G.tolist() if len(G) <= 2000 else (G[:: max(1, len(G) // 2000)].tolist()),
                "ellipse_curve": {"x": ex.tolist(), "y": ey.tolist()},
                "updated_utc": updated_utc,
            }
    except Exception:
        pass


def _run_loop() -> None:
    global _calibration_running, _sensor_index, _phase
    params = _params.copy()
    rate_hz = params["rate_hz"]
    chunk_duration_s = params["chunk_duration_s"]
    interval_s = params["interval_s"]
    fit_points = params["fit_points"] or 0
    sensors = [s for s in params["sensors"] if s in SENSOR_CHANNELS]
    if not sensors:
        with _lock:
            _calibration_running = False
            _phase = "idle"
        return
    for s in sensors:
        _ensure_buffer(s)
    skip_initial = _skip_initial_phase
    if not skip_initial:
        # Fase inicial: uma aquisição de 10 s a 1000 Hz por sensor
        with _lock:
            _phase = "initial"
        for sensor in sensors:
            if not _calibration_running or _calibration_stop:
                break
            ch0, ch1 = SENSOR_CHANNELS[sensor]
            data = _acquire_two_channels(ch0, ch1, _INITIAL_RATE_HZ, _INITIAL_ACQUISITION_S)
            if data is not None and data.shape[0] >= 2:
                _append_to_buffer(sensor, data[0], data[1])
                _do_fit_for_sensor(sensor, fit_points, params)
    with _lock:
        _phase = "continuous"
    # Loop periódico normal
    while _calibration_running and not _calibration_stop:
        sensor = sensors[_sensor_index % len(sensors)]
        _sensor_index += 1
        ch0, ch1 = SENSOR_CHANNELS[sensor]
        data = _acquire_two_channels(ch0, ch1, rate_hz, chunk_duration_s)
        if data is not None and data.shape[0] >= 2:
            _append_to_buffer(sensor, data[0], data[1])
            _do_fit_for_sensor(sensor, fit_points, params)
        time.sleep(interval_s)
    with _lock:
        _calibration_running = False
        _phase = "idle"


def start_calibration_loop(
    rate_hz: float = 1000,
    chunk_duration_s: float = 1,
    interval_s: float = 5,
    fit_points: int = 50000,
    sensors: Optional[List[str]] = None,
    skip_initial_phase: bool = False,
) -> None:
    """Inicia o loop de calibração em thread (para monitor/spectrum se estiverem ativos). skip_initial_phase=True: não faz 10 s iniciais (reinicío após aquisição/monitor/espectro)."""
    global _calibration_running, _calibration_stop, _thread, _params, _user_wants_calibration_on, _skip_initial_phase
    try:
        from acquisition.monitor import stop_monitor
        stop_monitor()
    except Exception:
        pass
    try:
        from acquisition.spectrum import stop_spectrum
        stop_spectrum()
    except Exception:
        pass
    with _lock:
        if _calibration_running:
            return
        _calibration_stop = False
        _user_wants_calibration_on = True
        _params = {
            "rate_hz": rate_hz,
            "chunk_duration_s": chunk_duration_s,
            "interval_s": interval_s,
            "fit_points": fit_points,
            "sensors": sensors or ["S1", "S2", "S3", "S4"],
        }
        _calibration_running = True
        _skip_initial_phase = skip_initial_phase
    _thread = threading.Thread(target=_run_loop, daemon=True)
    _thread.start()


def stop_calibration_loop(user_requested: bool = False) -> None:
    """
    Sinaliza parada do loop (o thread termina na próxima iteração).
    user_requested=True: usuário desligou na página Calibration (não re-inicia ao terminar aquisição/monitor/espectro).
    user_requested=False: parada temporária (ex.: aquisição/monitor/espectro); reinício automático se user_wants_on.
    """
    global _calibration_stop, _user_wants_calibration_on
    if user_requested:
        _user_wants_calibration_on = False
    _calibration_stop = True


def restart_calibration_if_desired() -> None:
    """
    Se o usuário tinha calibração ligada (user_wants_on) e o loop não está rodando,
    reinicia o loop com os últimos parâmetros. Chamar ao terminar aquisição, monitor ou espectro.
    """
    with _lock:
        want = _user_wants_calibration_on
        running = _calibration_running
        params = _params.copy()
    if want and not running:
        time.sleep(0.5)
        start_calibration_loop(
            rate_hz=params.get("rate_hz", 1000),
            chunk_duration_s=params.get("chunk_duration_s", 1),
            interval_s=params.get("interval_s", 5),
            fit_points=params.get("fit_points", 50000),
            sensors=params.get("sensors"),
            skip_initial_phase=True,
        )


def reset_calibration() -> None:
    """
    Zera buffers e último fit de todos os sensores.
    Use para recomeçar a coleta do zero (ex.: quando algo saiu errado).
    Pode ser chamado com calibração ligada ou desligada.
    """
    global _buffers, _last_fit
    with _lock:
        for sensor in list(_buffers.keys()):
            _buffers[sensor] = (
                np.zeros(_MAX_BUFFER_SAMPLES, dtype=np.float32),
                np.zeros(_MAX_BUFFER_SAMPLES, dtype=np.float32),
                0,
            )
        _last_fit.clear()


def is_calibration_running() -> bool:
    with _lock:
        return _calibration_running


def get_calibration_status() -> Dict[str, Any]:
    """Retorna status e parâmetros atuais do loop e last_fit por sensor."""
    with _lock:
        return {
            "running": _calibration_running,
            "user_wants_on": _user_wants_calibration_on,
            "phase": _phase,
            "params": _params.copy(),
            "last_fit": {k: v.copy() for k, v in _last_fit.items()},
        }


def get_last_fit(sensor: str) -> Optional[Dict[str, Any]]:
    """Retorna último fit do sensor para o frontend (params, R, G, ellipse_curve, updated_utc)."""
    with _lock:
        return _last_fit.get(sensor)
