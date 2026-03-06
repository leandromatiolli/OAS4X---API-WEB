"""
FastAPI application - OAS4X API-WEB.
Acessível por IP/hostname na LAN (Ethernet/Wi-Fi).
"""
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import ensure_dirs
from api.routes import router as api_router
from system.logging_config import setup_logging

# Diretório base do projeto (parent de api/)
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "frontend" / "templates"
STATIC_DIR = BASE_DIR / "frontend" / "static"

ensure_dirs()
setup_logging(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    log_to_file=os.environ.get("OAS4X_LOG_FILE", "1") == "1",
    json_stdout=os.environ.get("OAS4X_JSON_LOG", "0") == "1",
)

app = FastAPI(
    title="OAS4X API-WEB",
    description="Aquisição e análise de dados USB-1808X (4 sensores, 8 canais)",
    version="0.1.0",
)

# CORS para acesso pela LAN (browser em outro PC/celular)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if TEMPLATES_DIR.exists():
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
else:
    templates = None

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(api_router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Página inicial com links para Acquisition e Files."""
    if templates is None:
        return HTMLResponse(
            "<h1>OAS4X API-WEB</h1><p>Frontend templates not found. Add frontend/templates.</p>"
        )
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/acquisition", response_class=HTMLResponse)
async def acquisition_page(request: Request):
    """Página Acquisition - canais, sample rate, Start/Stop."""
    if templates is None:
        return HTMLResponse("<h1>Acquisition</h1><p>Templates not found.</p>")
    return templates.TemplateResponse("acquisition.html", {"request": request})


@app.get("/files", response_class=HTMLResponse)
async def files_page(request: Request):
    """Página Files - listar e baixar runs."""
    if templates is None:
        return HTMLResponse("<h1>Files</h1><p>Templates not found.</p>")
    return templates.TemplateResponse("files.html", {"request": request})


@app.get("/analysis", response_class=HTMLResponse)
async def analysis_page(request: Request):
    """Página Analysis - plot zoom/pan, FFT, estatísticas, export CSV (Etapa 3)."""
    if templates is None:
        return HTMLResponse("<h1>Analysis</h1><p>Templates not found.</p>")
    return templates.TemplateResponse("analysis.html", {"request": request})


@app.get("/health-page", response_class=HTMLResponse)
async def health_page(request: Request):
    """Página Health - uptime, CPU temp, RAM, disco, status DAQ."""
    if templates is None:
        return HTMLResponse("<h1>Health</h1><p>Templates not found.</p>")
    return templates.TemplateResponse("health.html", {"request": request})


@app.get("/monitor", response_class=HTMLResponse)
async def monitor_page(request: Request):
    """Página Monitor - tensão em tempo real por sensor (CH0, CH1 e diferencial)."""
    if templates is None:
        return HTMLResponse("<h1>Monitor</h1><p>Templates not found.</p>")
    return templates.TemplateResponse("monitor.html", {"request": request})


@app.get("/espectro", response_class=HTMLResponse)
async def espectro_page(request: Request):
    """Página Espectro - espectro (FFT) em tempo real por sensor."""
    if templates is None:
        return HTMLResponse("<h1>Espectro</h1><p>Templates not found.</p>")
    return templates.TemplateResponse("espectro.html", {"request": request})


@app.get("/calibration", response_class=HTMLResponse)
async def calibration_page(request: Request):
    """Página Calibration - calibração contínua e fit a partir de run (Etapa 4)."""
    if templates is None:
        return HTMLResponse("<h1>Calibration</h1><p>Templates not found.</p>")
    return templates.TemplateResponse("calibration.html", {"request": request})


@app.get("/health")
async def health():
    """Health check (Etapa 2): uptime, CPU temp, RAM, disco, status USB/DAQ."""
    from system.health import get_health_data
    return get_health_data()
