"""
Runner de aquisição USB-1808X em thread.
Suporta 1-8 canais, scan finito; execução em background para não travar a API.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import numpy as np

# uldaq importado sob demanda para não quebrar se driver não estiver instalado
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


@dataclass
class RunResult:
    """Resultado de uma aquisição."""
    success: bool
    data: Optional[np.ndarray] = None  # shape (num_channels, samples_per_channel)
    rate_hz: float = 0.0
    error: Optional[str] = None


class AcquisitionStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class AcquisitionState:
    status: AcquisitionStatus = AcquisitionStatus.IDLE
    run_id: Optional[str] = None
    result: Optional[RunResult] = None
    error_message: Optional[str] = None


# Estado global da aquisição (uma run por vez)
_state = AcquisitionState()
_lock = threading.Lock()


def get_state() -> AcquisitionState:
    with _lock:
        return AcquisitionState(
            status=_state.status,
            run_id=_state.run_id,
            result=_state.result,
            error_message=_state.error_message,
        )


def _set_state(status: AcquisitionStatus, run_id: Optional[str] = None,
               result: Optional[RunResult] = None, error_message: Optional[str] = None) -> None:
    with _lock:
        _state.status = status
        _state.run_id = run_id
        if result is not None:
            _state.result = result
        if error_message is not None:
            _state.error_message = error_message


# Identificadores de faixa de tensão (uldaq Range) para uso na API e frontend
RANGE_IDS = ["BIP10VOLTS", "BIP5VOLTS", "BIP2PT5VOLTS", "BIP1PT25VOLTS", "BIP1VOLTS", "BIPPT5VOLTS"]


def discover_device():
    """Retorna (True, descriptor) se encontrar USB-1808X, senão (False, msg)."""
    ok, ul = _get_uldaq()
    if not ok or ul is None:
        return False, "uldaq não instalado"
    get_inv, _, InterfaceType, *_ = ul
    devices = get_inv(InterfaceType.ANY)
    if not devices:
        return False, "Nenhum dispositivo MCC encontrado"
    return True, devices[0]


def run_acquisition(
    channels: List[int],
    sample_rate_hz: float,
    duration_s: float,
    run_id: str,
    test_name: str = "",
    range_id: str = "BIP5VOLTS",
) -> None:
    """
    Executa uma aquisição finita em thread.
    channels: lista de canais 0-7 (ex.: [0,1] ou [0,1,2,3,4,5,6,7])
    Escreve resultado em _state.result; dados em shape (num_channels, samples_per_channel).
    """
    def _run() -> None:
        ok, ul = _get_uldaq()
        if not ok or ul is None:
            _set_state(AcquisitionStatus.ERROR, error_message="uldaq não disponível")
            return
        (get_daq_device_inventory, DaqDevice, InterfaceType, AiInputMode, Range,
         create_float_buffer, ScanOption, AInScanFlag, WaitType) = ul

        range_map = {
            "BIP10VOLTS": Range.BIP10VOLTS,
            "BIP5VOLTS": Range.BIP5VOLTS,
            "BIP2PT5VOLTS": Range.BIP2PT5VOLTS,
            "BIP1PT25VOLTS": Range.BIP1PT25VOLTS,
            "BIP1VOLTS": Range.BIP1VOLTS,
            "BIPPT5VOLTS": Range.BIPPT5VOLTS,
        }
        range_uldaq = range_map.get(range_id, Range.BIP5VOLTS)

        if not channels:
            _set_state(AcquisitionStatus.ERROR, error_message="Nenhum canal selecionado")
            return

        devices = get_daq_device_inventory(InterfaceType.ANY)
        if not devices:
            _set_state(AcquisitionStatus.ERROR, error_message="Dispositivo não encontrado")
            return

        descriptor = devices[0]
        daq = DaqDevice(descriptor)
        ai = daq.get_ai_device()
        if not ai:
            daq.release()
            _set_state(AcquisitionStatus.ERROR, error_message="Dispositivo sem entrada analógica")
            return

        num_channels = len(channels)
        low_channel = min(channels)
        high_channel = max(channels)
        samples_per_channel = int(sample_rate_hz * duration_s)
        total_samples = samples_per_channel * num_channels

        _set_state(AcquisitionStatus.RUNNING, run_id=run_id)

        try:
            daq.connect()
            buf = create_float_buffer(num_channels, samples_per_channel)
            rate = ai.a_in_scan(
                low_channel,
                high_channel,
                AiInputMode.SINGLE_ENDED,
                range_uldaq,
                samples_per_channel,
                sample_rate_hz,
                ScanOption.DEFAULTIO,
                AInScanFlag.DEFAULT,
                buf,
            )
            ai.scan_wait(WaitType.WAIT_UNTIL_DONE, duration_s + 10.0)
        except Exception as e:
            _set_state(AcquisitionStatus.ERROR, error_message=str(e))
            if daq.is_connected():
                daq.disconnect()
            daq.release()
            return
        finally:
            pass

        # Buffer uldaq é intercalado: ch0_s0, ch1_s0, ..., chN_s0, ch0_s1, ...
        # Extrair por canal para shape (num_channels, samples_per_channel)
        arr = np.array(buf[:total_samples], dtype=np.float32)
        # Se scan foi 1 canal, arr já é (samples,); se vários, intercalado
        if num_channels == 1:
            data = arr.reshape(1, -1)
        else:
            data = arr.reshape(-1, num_channels).T  # (num_channels, samples_per_channel)

        result = RunResult(success=True, data=data, rate_hz=rate)
        _set_state(AcquisitionStatus.DONE, run_id=run_id, result=result)

        # Persistir run em /data/raw (canais efetivamente escaneados: low..high)
        channels_scanned = list(range(low_channel, high_channel + 1))
        try:
            from storage.runs import write_run
            write_run(
                data=data,
                sample_rate_hz=rate,
                duration_s=duration_s,
                channels=channels_scanned,
                test_name=test_name,
                run_id=run_id,
                range_id=range_id,
            )
        except Exception:
            pass

        if daq.is_connected():
            daq.disconnect()
        daq.release()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def stop_acquisition() -> bool:
    """Para aquisição em andamento (no futuro: scan_stop). Por ora só retorna se estava rodando."""
    with _lock:
        if _state.status == AcquisitionStatus.RUNNING:
            # uldaq scan finito não tem stop fácil; deixamos terminar
            return True
        return False
