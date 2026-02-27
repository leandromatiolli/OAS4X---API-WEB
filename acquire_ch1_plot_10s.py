#!/usr/bin/env python3
"""
Adquire dados do canal 1 da USB-1808X por 10 s e plota na tela.

Uso sugerido (no diretório do projeto):
    .venv/bin/python3 acquire_ch1_plot_10s.py
"""

import sys

import numpy as np
import matplotlib.pyplot as plt

from uldaq import (
    get_daq_device_inventory,
    DaqDevice,
    InterfaceType,
    AiInputMode,
    Range,
)


# Configurações de aquisição
CANAL = 1              # canal analógico a medir (0 = CH0, 1 = CH1, ...)
TAXA_HZ = 5000         # taxa de amostragem em Hz
DURACAO_S = 10         # tempo total de aquisição em segundos
INPUT_MODE = AiInputMode.SINGLE_ENDED
RANGE = Range.BIP5VOLTS


def main() -> None:
    print("USB-1808X – Aquisição do canal {} por {} s".format(CANAL, DURACAO_S))
    num_canais = 1
    samples_per_channel = int(TAXA_HZ * DURACAO_S)

    # Descobrir dispositivos MCC
    devices = get_daq_device_inventory(InterfaceType.ANY)
    if not devices:
        print("Nenhum dispositivo MCC encontrado. Conecte a USB-1808X e tente novamente.")
        sys.exit(1)

    descriptor = devices[0]
    print("Usando dispositivo: {} ({})".format(descriptor.product_name, descriptor.unique_id))

    daq = DaqDevice(descriptor)
    ai = daq.get_ai_device()

    if not ai:
        print("Este dispositivo não possui entrada analógica.")
        daq.release()
        sys.exit(1)

    try:
        daq.connect()
        print("Conectado. Coletando {} amostras a {} Hz...".format(samples_per_channel, TAXA_HZ))

        # Buffer para uma chamada de a_in_scan (varre só o canal 1)
        from uldaq import create_float_buffer, ScanOption, AInScanFlag

        buf = create_float_buffer(num_canais, samples_per_channel)

        # low_channel = high_channel = CANAL (só canal 1)
        low_channel = CANAL
        high_channel = CANAL

        rate_real = ai.a_in_scan(
            low_channel,
            high_channel,
            INPUT_MODE,
            RANGE,
            samples_per_channel,
            TAXA_HZ,
            ScanOption.DEFAULTIO,
            AInScanFlag.DEFAULT,
            buf,
        )
        print("Taxa efetiva reportada: {:.1f} Hz".format(rate_real))

        # Espera terminar a aquisição (bloqueante para varredura finita)
        from uldaq import WaitType, ScanStatus

        ai.scan_wait(WaitType.WAIT_UNTIL_DONE, DURACAO_S + 5)
        status, transfer = ai.get_scan_status()
        if status != ScanStatus.IDLE:
            print("Aviso: status de scan diferente de IDLE:", status)

        # Copia dados do buffer para numpy
        dados = np.array(buf[:samples_per_channel], dtype=float)

    finally:
        if daq.is_connected():
            daq.disconnect()
        daq.release()

    # Eixo de tempo
    t = np.arange(samples_per_channel) / float(rate_real)

    # Plot
    plt.figure(figsize=(10, 5))
    plt.plot(t, dados, linewidth=0.8)
    plt.title(f"Canal {CANAL} – {DURACAO_S} s @ {rate_real:.0f} Hz")
    plt.xlabel("Tempo (s)")
    plt.ylabel("Tensão (V)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
