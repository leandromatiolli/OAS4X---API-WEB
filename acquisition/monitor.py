"""
Monitor em tempo real: scan contínuo de 2 canais (um sensor) para streaming via WebSocket.
Usado para regular potência do laser (tensão diferencial dos dois canais do sensor).
Taxa de atualização ao cliente: 10 Hz (a cada 100 ms) com 500 pontos por frame.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from config import SENSOR_CHANNELS

# Parâmetros do monitor (estáveis para não sobrecarregar)
MONITOR_SAMPLE_RATE_HZ = 2000
MONITOR_BUFFER_S = 2
MONITOR_UPDATE_INTERVAL_S = 0.1  # 10 Hz
MONITOR_POINTS_PER_FRAME = 500

_monitor_lock = threading.Lock()
_monitor_thread: Optional[threading.Thread] = None
_monitor_stop = threading.Event()
_monitor_frame: Optional[Dict[str, Any]] = None
_monitor_sensor: Optional[str] = None


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


def _downsample_1d(arr: np.ndarray, max_points: int) -> np.ndarray:
    n = arr.size
    if n <= max_points:
        return arr.astype(np.float64)
    step = n / max_points
    idx = (np.arange(max_points) * step).astype(int)
    return arr[idx].astype(np.float64)


def _run_monitor_thread(sensor: str, range_id: str) -> None:
    global _monitor_frame
    ok, ul = _get_uldaq()
    if not ok or ul is None:
        with _monitor_lock:
            _monitor_frame = {"error": "uldaq não disponível"}
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
        with _monitor_lock:
            _monitor_frame = {"error": f"Sensor {sensor} inválido"}
        return
    ch0, ch1 = SENSOR_CHANNELS[sensor]
    try:
        range_enum = getattr(Range, range_id) if hasattr(Range, range_id) else Range.BIP5VOLTS
    except Exception:
        range_enum = Range.BIP5VOLTS

    devices = get_daq_device_inventory(InterfaceType.ANY)
    if not devices:
        with _monitor_lock:
            _monitor_frame = {"error": "Dispositivo não encontrado"}
        return

    daq = DaqDevice(devices[0])
    ai = daq.get_ai_device()
    if not ai:
        daq.release()
        with _monitor_lock:
            _monitor_frame = {"error": "Dispositivo sem entrada analógica"}
        return

    num_channels = 2
    samples_per_channel = int(MONITOR_SAMPLE_RATE_HZ * MONITOR_BUFFER_S)
    total_buffer = num_channels * samples_per_channel
    buf = create_float_buffer(num_channels, samples_per_channel)

    try:
        daq.connect()
        ai.a_in_scan(
            ch0,
            ch1,
            AiInputMode.SINGLE_ENDED,
            range_enum,
            samples_per_channel,
            MONITOR_SAMPLE_RATE_HZ,
            ScanOption.CONTINUOUS,
            AInScanFlag.DEFAULT,
            buf,
        )
    except Exception as e:
        if daq.is_connected():
            daq.disconnect()
        daq.release()
        with _monitor_lock:
            _monitor_frame = {"error": str(e)}
        return

    samples_per_frame = MONITOR_POINTS_PER_FRAME
    num_per_frame = samples_per_frame * num_channels

    while not _monitor_stop.is_set():
        try:
            status, transfer = ai.get_scan_status()
            if status != ScanStatus.RUNNING:
                break
            cur = transfer.current_index
            if cur is None:
                time.sleep(0.01)
                continue
            cur = int(cur)
            buf_len = total_buffer
            indices = [(cur - num_per_frame + i) % buf_len for i in range(num_per_frame)]
            raw = np.array([buf[i] for i in indices], dtype=np.float32)
            data = raw.reshape(-1, num_channels).T
            n = data.shape[1]
            t = np.arange(n, dtype=np.float64) / MONITOR_SAMPLE_RATE_HZ
            ch0_vals = _downsample_1d(data[0, :], MONITOR_POINTS_PER_FRAME)
            ch1_vals = _downsample_1d(data[1, :], MONITOR_POINTS_PER_FRAME)
            t_down = _downsample_1d(t, MONITOR_POINTS_PER_FRAME)
            diff_vals = ch1_vals - ch0_vals
            with _monitor_lock:
                _monitor_frame = {
                    "t": t_down.tolist(),
                    "ch0": ch0_vals.tolist(),
                    "ch1": ch1_vals.tolist(),
                    "diff": diff_vals.tolist(),
                    "sensor": sensor,
                    "rate_hz": MONITOR_SAMPLE_RATE_HZ,
                }
        except Exception as e:
            with _monitor_lock:
                _monitor_frame = {"error": str(e)}
        time.sleep(MONITOR_UPDATE_INTERVAL_S)

    try:
        ai.scan_stop()
    except Exception:
        pass
    if daq.is_connected():
        daq.disconnect()
    daq.release()
    with _monitor_lock:
        _monitor_frame = None


def is_monitor_running() -> bool:
    with _monitor_lock:
        return _monitor_thread is not None and _monitor_thread.is_alive()


def get_monitor_sensor() -> Optional[str]:
    return _monitor_sensor


def get_last_frame() -> Optional[Dict[str, Any]]:
    with _monitor_lock:
        if _monitor_frame is None:
            return None
        return dict(_monitor_frame)


def start_monitor(sensor: str, range_id: str = "BIP5VOLTS") -> Tuple[bool, str]:
    """Inicia o monitor para o sensor (S1-S4). Retorna (ok, mensagem)."""
    from acquisition.daq_runner import get_state, AcquisitionStatus

    if sensor not in SENSOR_CHANNELS:
        return False, f"Sensor {sensor} inválido. Use S1, S2, S3 ou S4."
    state = get_state()
    if state.status == AcquisitionStatus.RUNNING:
        return False, "Pare a aquisição antes de iniciar o monitor."
    global _monitor_thread, _monitor_stop, _monitor_sensor
    with _monitor_lock:
        if _monitor_thread is not None and _monitor_thread.is_alive():
            if _monitor_sensor == sensor:
                return True, "Monitor já ativo para este sensor."
    stop_monitor()
    _monitor_stop.clear()
    _monitor_sensor = sensor
    _monitor_thread = threading.Thread(
        target=_run_monitor_thread,
        args=(sensor, range_id),
        daemon=True,
    )
    _monitor_thread.start()
    time.sleep(0.3)
    if not _monitor_thread.is_alive():
        err = (get_last_frame() or {}).get("error", "Falha ao iniciar monitor")
        return False, err
    return True, "Monitor iniciado."


def stop_monitor() -> None:
    global _monitor_thread, _monitor_sensor
    _monitor_stop.set()
    with _monitor_lock:
        th = _monitor_thread
        _monitor_thread = None
        _monitor_sensor = None
    if th is not None:
        th.join(timeout=2.0)
