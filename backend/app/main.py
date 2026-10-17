import sys
import os
import logging
import threading
from contextlib import asynccontextmanager

# Ensure backend root is always in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings, INSECURE_DEFAULTS
from backend.app.db import init_db, SessionLocal
from backend.app.generator import seed_db_script
from backend.app.api import router
from backend.app.auth_routes import router as auth_router
from backend.app.retail_routes import router as retail_router
from backend.app.monitoring import run_monitoring_cycle

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("control_tower")


def _monitoring_loop(stop: threading.Event, interval: int) -> None:
    """Continuous monitoring (§III-C): scan every tenant every `interval` seconds."""
    while not stop.wait(interval):
        try:
            opened = run_monitoring_cycle(SessionLocal)
            if opened:
                logger.info("Monitoring cycle opened %d new event(s)", opened)
        except Exception:
            logger.exception("Monitoring cycle failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Control Tower backend...")
    for name, default in INSECURE_DEFAULTS.items():
        if getattr(settings, name) == default:
            logger.warning("%s is using the insecure default from source control; set it in the environment.", name)

    # Initialize SQLAlchemy database schema
    init_db()
    # Seed database with initial tenant, products, sales ledger, and vector knowledge base
    seed_db_script()

    stop = threading.Event()
    if settings.MONITORING_INTERVAL_SECONDS > 0:
        threading.Thread(
            target=_monitoring_loop,
            args=(stop, settings.MONITORING_INTERVAL_SECONDS),
            name="monitoring-scheduler",
            daemon=True,
        ).start()
        logger.info("Monitoring scheduler running every %ds", settings.MONITORING_INTERVAL_SECONDS)
    yield
    stop.set()


app = FastAPI(
    title=settings.APP_NAME,
    description="Multi-agent decision fusion tower for SMEs using AMDIE",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(auth_router, prefix="/api")
app.include_router(retail_router, prefix="/api")
app.include_router(router, prefix="/api")

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": settings.APP_NAME,
        "message": "AI Business Control Tower API is running. Access docs at /docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
