#!/bin/bash
# Deploy OAS4X como serviço systemd (Etapa 2).
# Uso: sudo ./scripts/deploy-systemd.sh [diretório_instalação]
# Ex.: sudo ./scripts/deploy-systemd.sh /home/pi/OAS4X-API-WEB

set -e
INSTALL_DIR="${1:-$(pwd)}"
INSTALL_DIR="$(realpath "$INSTALL_DIR")"
SERVICE_NAME="oas4x.service"
UNIT_DEST="/etc/systemd/system/$SERVICE_NAME"
SRC_UNIT="$(dirname "$0")/../system/oas4x.service"

if [ ! -d "$INSTALL_DIR" ]; then
    echo "Diretório não encontrado: $INSTALL_DIR"
    exit 1
fi
if [ ! -f "$INSTALL_DIR/.venv/bin/python" ]; then
    echo "Venv não encontrado em $INSTALL_DIR/.venv"
    exit 1
fi

echo "Instalando serviço OAS4X em $INSTALL_DIR"
sed "s|__INSTALL_DIR__|$INSTALL_DIR|g" "$SRC_UNIT" | sudo tee "$UNIT_DEST" > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
echo "Serviço instalado e iniciado. Status:"
sudo systemctl status --no-pager "$SERVICE_NAME"
