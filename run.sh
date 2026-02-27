#!/bin/bash
# Executar OAS4X API-WEB (raiz do projeto)
cd "$(dirname "$0")"
export OAS4X_DATA="${OAS4X_DATA:-./data}"
export OAS4X_CALIBRATION="${OAS4X_CALIBRATION:-./calibration}"
mkdir -p "$OAS4X_DATA/raw" "$OAS4X_DATA/processed" "$OAS4X_DATA/logs" "$OAS4X_CALIBRATION"
exec .venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
