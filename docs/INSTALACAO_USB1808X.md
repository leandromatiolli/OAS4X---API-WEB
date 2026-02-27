# Instalação do driver USB-1808X (Linux)

A placa **USB-1808X** da Measurement Computing usa o driver **Universal Library for Linux (uldaq)**. Siga um dos métodos abaixo.

## Requisitos

- Linux (testado em Raspberry Pi OS / Debian / Ubuntu)
- Compilador C/C++, make, **libusb-1.0-0-dev**
- Python 3.6+ (para o aplicativo de streaming)

## Método 1: Script automático

Na raiz do projeto:

```bash
chmod +x scripts/install_usb1808x_driver.sh
./scripts/install_usb1808x_driver.sh
```

O script instala dependências, baixa e compila a libuldaq, configura as regras udev e instala o pacote Python `uldaq`.

## Método 2: Passo a passo manual

### 1. Dependências (Debian/Ubuntu/Raspberry Pi OS)

```bash
sudo apt-get update
sudo apt-get install -y gcc g++ make libusb-1.0-0-dev
```

### 2. Baixar e instalar a biblioteca C (libuldaq)

Versão usada: **1.2.1** (verifique [releases](https://github.com/mccdaq/uldaq/releases) para mais recente).

```bash
cd /tmp
wget -N https://github.com/mccdaq/uldaq/releases/download/v1.2.1/libuldaq-1.2.1.tar.bz2
tar -xvjf libuldaq-1.2.1.tar.bz2
cd libuldaq-1.2.1
./configure && make
sudo make install
sudo ldconfig
```

### 3. Regras udev (acesso ao USB sem root)

```bash
sudo cp rules/50-uldaq.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Reconecte a placa USB após isso.

### 4. Pacote Python uldaq

```bash
pip install --user uldaq
# ou
pip3 install --user uldaq
```

Requer que a libuldaq (passo 2) já esteja instalada no sistema.

## Verificação

1. Conecte a USB-1808X.
2. Execute o script de streaming:

   ```bash
   python3 stream_ch.py
   ```

   Você deve ver valores do canal analógico sendo impressos. Interrompa com **Ctrl+C**.

## Referências

- [uldaq no GitHub](https://github.com/mccdaq/uldaq)
- [Documentação Python UL for Linux](https://files.digilent.com/manuals/UL-Linux/python/index.html)
- [MCC DAQ – Suporte Linux](https://www.mccdaq.com/Linux)
