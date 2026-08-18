from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.db import init_db
from backend.app.generator import seed_db_script
from backend.app.api import router
from backend.app.auth_routes import router as auth_router

app = FastAPI(
    title=settings.APP_NAME,
    description="Multi-agent decision fusion tower for SMEs using AMDIE",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(auth_router, prefix="/api")
app.include_router(router, prefix="/api")

@app.on_event("startup")
def startup_event():
    print("Starting Control Tower backend...")
    # Initialize SQLAlchemy database schema
    init_db()
    # Seed database with initial tenant, products, sales ledger, and vector knowledge base
    seed_db_script()

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
