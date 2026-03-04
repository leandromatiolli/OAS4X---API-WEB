#!/usr/bin/env python3
"""
Streaming simples do canal analógico da placa USB-1808X (MCC).
Mostra dados do(s) canal(is) em tempo real para verificar se o hardware está OK.
Interrompa com Ctrl+C.

Requer: driver uldaq instalado (veja docs/INSTALACAO_USB1808X.md) e pacote: pip install uldaq
"""

import sys
import time
import signal

try:
    from uldaq import (
        get_daq_device_inventory,
        DaqDevice,
        InterfaceType,
        AiInputMode,
        Range,
        ScanOption,
        AInScanFlag,
        ScanStatus,
        create_float_buffer,
    )
except ImportError:
    print("Pacote 'uldaq' não encontrado. Instale com: pip install uldaq")
    print("E instale o driver libuldaq (veja docs/INSTALACAO_USB1808X.md)")
    sys.exit(1)

# Configuração do streaming (ajuste se quiser)
CANAL_INICIAL = 0
CANAL_FINAL = 0
TAXA_HZ = 1000
SEGUNDOS_BUFFER = 5
MOSTRAR_A_CADA_AMOSTRAS = 100
INPUT_MODE = AiInputMode.SINGLE_ENDED
RANGE = Range.BIP5VOLTS


def main():
    descriptor = None
    daq_device = None
    ai_device = None
    buffer = None
    num_canais = CANAL_FINAL - CANAL_INICIAL + 1
    samples_per_channel = int(TAXA_HZ * SEGUNDOS_BUFFER)

    def cleanup(signum=None, frame=None):
        nonlocal daq_device, ai_device
        print("\nParando aquisição...")
        if ai_device:
            try:
                ai_device.scan_stop()
            except Exception:
                pass
        if daq_device and daq_device.is_connected():
            try:
                daq_device.disconnect()
                daq_device.release()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)

    print("USB-1808X – Streaming de canal analógico")
    print("Canal(s): {} a {} | Taxa: {} Hz | Buffer: {} s".format(
        CANAL_INICIAL, CANAL_FINAL, TAXA_HZ, SEGUNDOS_BUFFER))
    print("Interrompa com Ctrl+C.\n")

    # Descobrir dispositivos
    devices = get_daq_device_inventory(InterfaceType.ANY)
    if not devices:
        print("Nenhum dispositivo MCC encontrado. Conecte a USB-1808X e verifique o driver/udev.")
        sys.exit(1)

    descriptor = devices[0]
    print("Dispositivo: {} ({})".format(descriptor.product_name, descriptor.unique_id))

    daq_device = DaqDevice(descriptor)
    ai_device = daq_device.get_ai_device()

    if not ai_device:
        print("Este dispositivo não possui subsistema de entrada analógica.")
        daq_device.release()
        sys.exit(1)

    daq_device.connect()
    print("Conectado.\n")

    # Buffer para modo contínuo (dados intercalados: ch0, ch1, ...)
    buffer = create_float_buffer(num_canais, samples_per_channel)

    try:
        rate = ai_device.a_in_scan(
            CANAL_INICIAL,
            CANAL_FINAL,
            INPUT_MODE,
            RANGE,
            samples_per_channel,
            TAXA_HZ,
            ScanOption.CONTINUOUS,
            AInScanFlag.DEFAULT,
            buffer,
        )
    except Exception as e:
        print("Erro ao iniciar scan:", e)
        daq_device.disconnect()
        daq_device.release()
        sys.exit(1)

    print("Taxa efetiva: {:.1f} Hz. Exibindo última amostra a cada ~{} amostras...\n".format(
        rate, MOSTRAR_A_CADA_AMOSTRAS))

    total_samples = 0
    last_printed = 0

    while True:
        status, transfer = ai_device.get_scan_status()
        if status != ScanStatus.RUNNING:
            break
        cur = transfer.current_index
        if cur is None:
            time.sleep(0.01)
            continue

        total_samples = transfer.current_total_count or 0
        # Exibir só a cada MOSTRAR_A_CADA_AMOSTRAS amostras (por canal)
        if total_samples - last_printed >= MOSTRAR_A_CADA_AMOSTRAS:
            last_printed = total_samples
            buf_len = samples_per_channel * num_canais
            # Última amostra está em current_index - 1 (buffer circular)
            idx = (cur - 1) % buf_len if buf_len else 0
            if num_canais == 1:
                v = buffer[idx] if 0 <= idx < len(buffer) else 0
                print("CH{}: {:+.4f} V  (amostra #{})".format(CANAL_INICIAL, v, total_samples))
            else:
                line = []
                for c in range(num_canais):
                    i = (cur - num_canais + c) % buf_len
                    v = buffer[i] if 0 <= i < len(buffer) else 0
                    line.append("CH{}: {:+.4f}".format(CANAL_INICIAL + c, v))
                print("  ".join(line))

        time.sleep(0.05)


if __name__ == "__main__":
    main()
