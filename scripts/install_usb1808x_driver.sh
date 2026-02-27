#!/bin/bash
# Instalação do driver Universal Library (uldaq) para placas MCC no Linux
# Suporta USB-1808X e outras placas da Measurement Computing
# Uso: execute com sudo ou como usuário (sudo será pedido quando necessário)

set -e

ULDAQ_VERSION="1.2.1"
INSTALL_DIR="/tmp/libuldaq-${ULDAQ_VERSION}"
RULES_SRC="${INSTALL_DIR}/rules/50-uldaq.rules"
RULES_DEST="/etc/udev/rules.d/50-uldaq.rules"

echo "=== Instalação do driver USB-1808X (MCC uldaq) ==="

# 1. Dependências (Debian/Ubuntu/Raspberry Pi OS)
echo "[1/5] Instalando dependências..."
if command -v apt-get &>/dev/null; then
    sudo apt-get update
    sudo apt-get install -y gcc g++ make libusb-1.0-0-dev
elif command -v pacman &>/dev/null; then
    sudo pacman -S --noconfirm gcc make libusb
else
    echo "Instale manualmente: gcc, g++, make, libusb-1.0-0-dev (ou equivalente)"
    exit 1
fi

# 2. Download e build da biblioteca C
echo "[2/5] Baixando libuldaq ${ULDAQ_VERSION}..."
cd /tmp
wget -q -O "libuldaq-${ULDAQ_VERSION}.tar.bz2" \
    "https://github.com/mccdaq/uldaq/releases/download/v${ULDAQ_VERSION}/libuldaq-${ULDAQ_VERSION}.tar.bz2" || {
    echo "Falha no download. Verifique a versão em: https://github.com/mccdaq/uldaq/releases"
    exit 1
}

echo "[3/5] Compilando e instalando a biblioteca..."
tar -xjf "libuldaq-${ULDAQ_VERSION}.tar.bz2"
cd "libuldaq-${ULDAQ_VERSION}"
./configure && make
sudo make install
sudo ldconfig

# 3. Regras udev para acesso ao USB sem root
echo "[4/5] Configurando regras udev..."
if [ -f "$RULES_SRC" ]; then
    sudo cp "$RULES_SRC" "$RULES_DEST"
else
    echo "Baixando regras udev do repositório..."
    sudo mkdir -p "$(dirname "$RULES_DEST")"
    sudo wget -q -O "$RULES_DEST" \
        "https://raw.githubusercontent.com/mccdaq/uldaq/master/rules/50-uldaq.rules" || true
fi
if [ -f "$RULES_DEST" ]; then
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    echo "Regras udev instaladas. Reconecte a placa USB se já estiver conectada."
fi

# 4. Pacote Python uldaq
echo "[5/5] Instalando pacote Python uldaq..."
pip install --user uldaq 2>/dev/null || pip3 install --user uldaq 2>/dev/null || {
    echo "Tentando com sudo..."
    sudo pip install uldaq 2>/dev/null || sudo pip3 install uldaq
}

echo ""
echo "=== Instalação concluída ==="
echo "Reconecte a placa USB-1808X e execute o script de streaming para testar:"
echo "  python3 stream_ch.py"
echo ""
