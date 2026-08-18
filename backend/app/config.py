import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "AI Business Control Tower"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "127.0.0.1"

    # Database: PostgreSQL with SQLite fallback
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./control_tower.db")

    # Vector DB: Qdrant with ChromaDB (in-memory/local) fallback
    # Supported values: "qdrant", "chroma"
    VECTOR_DB_TYPE: str = os.getenv("VECTOR_DB_TYPE", "chroma")
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")

    # Security
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "31gG6qg_Lh_N6uB3D7V3E5C7O8N9T0R1o2w3e4r5t6y=")  # 32-byte url-safe base64 key
    JWT_SECRET: str = os.getenv("JWT_SECRET", "supersecretjwtkeyforcontroltower")

    # LLM Settings (configurable adapter)
    # Supported providers: "mock", "openai", "anthropic"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "mock")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Embedding Model Settings
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ── Phase 2: Neo4j Knowledge Graph ───────────────────────────────────────
    # Set NEO4J_ENABLED=true only when a Neo4j instance is available.
    # When False (default), Procurement Agent falls back to flat Postgres queries.
    NEO4J_ENABLED: bool = os.getenv("NEO4J_ENABLED", "false").lower() == "true"
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "password")

    class Config:
        env_file = ".env"

settings = Settings()
