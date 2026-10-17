import os
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # LLM Settings (configurable adapter)
    # Supported providers: "mock", "openai", "anthropic"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "mock")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL_NAME: str = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL_NAME: str = os.getenv("ANTHROPIC_MODEL_NAME", "claude-sonnet-5-5")
    # Used by the experiment harness's LLM baseline (backend/experiments)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1000"))

    # Embedding Model & Vector DB Settings
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
    EMBEDDING_VECTOR_SIZE: int = int(os.getenv("EMBEDDING_VECTOR_SIZE", "384"))
    VECTOR_COLLECTION_NAME: str = os.getenv("VECTOR_COLLECTION_NAME", "sme_knowledge")

    # Domain & Operational Defaults
    DEMO_TENANT_ID: str = os.getenv("DEMO_TENANT_ID", "t1-uuid-demo-sme-tenant-12345")
    SEED_DEFAULT_PASSWORD: str = os.getenv("SEED_DEFAULT_PASSWORD", "password")
    AUTOMATION_AUTO_APPROVAL_COST_LIMIT: float = float(os.getenv("AUTOMATION_AUTO_APPROVAL_COST_LIMIT", "500.0"))
    # Periodic-review interval assumed by replenishment agents: an order must
    # cover demand over lead time + review period (the L + R protection interval)
    REORDER_REVIEW_PERIOD_DAYS: int = int(os.getenv("REORDER_REVIEW_PERIOD_DAYS", "7"))
    # AMDIE adaptive weighting (defaults chosen on development seeds, see
    # backend/experiments/README.md).  Agent scores span roughly [0, 1], so a softmax at
    # temperature 1 is nearly uniform; lower temperatures let reliability matter.
    AMDIE_WEIGHT_TEMPERATURE: float = float(os.getenv("AMDIE_WEIGHT_TEMPERATURE", "0.05"))
    # Target service level for scoring reorder recommendations: agent accuracy is
    # the pinball (quantile) loss at this level, so under-ordering (lost sales)
    # costs more than over-ordering when > 0.5.  0.5 = symmetric error.
    AMDIE_REORDER_SERVICE_LEVEL: float = float(os.getenv("AMDIE_REORDER_SERVICE_LEVEL", "0.9"))
    MONITORING_DEFAULT_MIN_STOCK: int = int(os.getenv("MONITORING_DEFAULT_MIN_STOCK", "5"))
    # Background monitoring scan interval for all tenants; 0 disables the scheduler
    MONITORING_INTERVAL_SECONDS: int = int(os.getenv("MONITORING_INTERVAL_SECONDS", "300"))

    # Comma-separated browser origins allowed to call the API directly.
    # The Vite dev server proxies /api, so same-origin requests need no entry.
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")

    # ── Phase 2: Neo4j Knowledge Graph ───────────────────────────────────────
    # Set NEO4J_ENABLED=true only when a Neo4j instance is available.
    # When False (default), Procurement Agent falls back to flat Postgres queries.
    NEO4J_ENABLED: bool = os.getenv("NEO4J_ENABLED", "false").lower() == "true"
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "password")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

# Defaults shipped in source control; anything deployed must override them.
INSECURE_DEFAULTS = {
    "JWT_SECRET": "supersecretjwtkeyforcontroltower",
    "ENCRYPTION_KEY": "31gG6qg_Lh_N6uB3D7V3E5C7O8N9T0R1o2w3e4r5t6y=",
}
