# OAS4X API-WEB

Aplicação web para aquisição e análise de dados da placa **USB-1808X** (MCC) no **Raspberry Pi 5**, acessível por Ethernet ou Wi-Fi na LAN via browser.

- **4 sensores = 8 canais:** S1=CH0/1, S2=CH2/3, S3=CH4/5, S4=CH6/7.
- **Backend:** FastAPI (REST); aquisição em thread dedicada; gravação BIN+JSON em `/data`.

## Etapa 1

- Web app acessível por `http://<IP-do-Pi>:8000`.
- **Acquisition:** Seleção de canais (0–7) e/ou sensores (S1–S4), sample rate, duração, Start/Stop; preview (plot) e métricas (RMS, DC, peak, clipping).
- **Files:** Listar runs em `/data/raw`, baixar BIN e JSON.
- Formato: BIN intercalado (float32) + JSON com metadados.

## Etapa 2 (robustez e 24/7)

- **Serviço systemd:** `system/oas4x.service` + `scripts/deploy-systemd.sh` (auto-start no boot, restart on failure).
- **Logs:** Estruturados em stdout; opcionalmente arquivo em `/data/logs/oas4x.log` com rotação (5 MB, 3 backups). Variáveis: `LOG_LEVEL`, `OAS4X_LOG_FILE`, `OAS4X_JSON_LOG`.
- **Health:** Página **Health** e endpoint `GET /health` com uptime, temperatura CPU, RAM (psutil), disco (`/data`), status USB/DAQ.
- **Gravação robusta:** BIN gravado em chunks + `fsync`; aquisição e gravação no backend (independente do browser).

## Requisitos

- Raspberry Pi 5 (ou Linux com USB-1808X)
- Driver uldaq instalado (veja [docs/INSTALACAO_USB1808X.md](docs/INSTALACAO_USB1808X.md))
- Python 3.10+

## Instalação

```bash
# Clone ou copie o projeto; crie o venv e instale dependências
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Driver USB-1808X (se ainda não instalado)
bash scripts/install_usb1808x_driver.sh
```

## Execução

Na raiz do projeto:

```bash
./run.sh
# ou
OAS4X_DATA=./data OAS4X_CALIBRATION=./calibration .venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Acesse no browser (PC ou celular na mesma rede): `http://<IP-do-Pi>:8000`.

- **OAS4X_DATA:** diretório de dados (default: `./data` no dev, `/data` em produção).
- **OAS4X_CALIBRATION:** diretório de calibração (default: `./calibration` no dev).

### Rodar como serviço (Etapa 2)

```bash
# Instalar e ativar serviço systemd (ajuste o caminho se necessário)
sudo ./scripts/deploy-systemd.sh /home/pi/OAS4X-API-WEB
# Ver status
sudo systemctl status oas4x
# Logs
journalctl -u oas4x -f
```

O unit usa `User=pi` e `WorkingDirectory` no diretório do projeto; dados em `/data` e calibração em `/calibration`. Ajuste usuário e paths no `system/oas4x.service` se precisar.

## Estrutura

- `api/` – FastAPI, rotas REST, páginas (Acquisition, Files, Health).
- `acquisition/` – Runner uldaq (1–8 canais, scan em thread).
- `processing/` – Métricas (RMS, DC, peak, clipping), downsample; análise (FFT, RMS janela, P95/P99).
- `storage/` – Escrita/leitura de runs (BIN+JSON em chunks + fsync), listagem.
- `system/` – Health (uptime, CPU temp, RAM, disco, DAQ), logging, unit systemd.
- `frontend/` – Templates Jinja2 e estáticos (CSS, JS).
- `config.py` – Paths e mapeamento S1–S4 ↔ canais.

## Formato dos arquivos de run

- **BIN:** `data/raw/<run_id>.bin` – amostras float32 intercaladas: ch0_s0, ch1_s0, …, chN_s0, ch0_s1, …
- **JSON:** `data/raw/<run_id>.json` – metadados: `timestamp`, `sample_rate_hz`, `duration_s`, `channels`, `software_version`, `test_name`, `binary_file`, `format` ("interleaved_float32").

## Etapa 3 (visualização e análise)

- **Analysis:** Página **Analysis** (ou link "Analisar" em Files): plot pós-aquisição com **zoom/pan** (Plotly), downsample automático (até 10k pontos).
- **FFT:** Por canal, magnitude em dB; seleção de canal na própria página.
- **Estatísticas:** RMS global, RMS em janela deslizante (média), P95 e P99 por canal.
- **Export CSV:** Dados decimados (fator configurável); download direto do navegador.

API: `GET /api/files/{run_id}/preview`, `/fft?channel=`, `/stats`, `/export/csv?decimate=`.

## Próximas etapas (plano)

- **Etapa 4:** Calibração (fit elipse por sensor), Demod (fase, LPF, RMS).
- **Etapa 5:** Trigger por RMS/nível, monitoramento contínuo, rotação de armazenamento, autenticação admin.
- **Etapa 6:** Atualização remota (OTA-lite), rollback, README de deploy/update.
