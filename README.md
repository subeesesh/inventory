# AI Business Control Tower for SMEs (Phase 2)

A sophisticated multi-agent decision support platform built around the **Adaptive Multi-Agent Decision Intelligence Engine (AMDIE)**. This Phase 2 system extends beyond classic inventory reorder optimization to support pricing, promotions, and procurement-aware decision workflows while maintaining backward compatibility with Phase 1.

## Overview

The Control Tower is a decision fusion platform designed for Small and Medium Enterprises (SMEs) that need to orchestrate complex business decisions across multiple organizational functions. It implements decision-type-aware AMDIE orchestration, where each decision cycle is scoped to a specific decision type and only relevant agents participate.

### Supported Decision Types

| Decision Type | Agents Involved | Purpose |
|---|---|---|
| **reorder_quantity** | Inventory, Sales, Finance, Procurement | Optimize inventory replenishment quantities |
| **price_adjustment** | Pricing, Sales, Risk | Dynamic pricing optimization |
| **promotion_trigger** | Marketing, Finance | Promotion and discount strategy |

### Key Characteristics

- **Modular architecture**: Each decision type has its own agent coalition
- **Multi-tenant**: Supports multiple tenant businesses with complete data isolation
- **Explainable**: Provides decision rationale and confidence scores
- **Conflict detection**: Identifies and resolves agent disagreements
- **Business-goal aligned**: Adjusts recommendations based on strategic objectives
- **Production-ready API**: FastAPI backend with comprehensive endpoints

---

## Core Architecture

### 1. Decision Type Registry

The **Decision Registry** ([backend/app/decision_registry.py](backend/app/decision_registry.py)) is the Phase 2 structural cornerstone. It:

- Maps decision types to participating agents
- Defines decision labels and axis descriptions
- Sets optional LP upper bounds per decision type
- Enables adding new decision types without modifying pipeline code

Example:
```python
DECISION_TYPES: Dict[str, List[str]] = {
    "reorder_quantity": ["inventory", "sales", "finance", "procurement"],
    "price_adjustment": ["pricing", "sales", "risk"],
    "promotion_trigger": ["marketing", "finance"],
}
```

### 2. Seven Specialized Agents

Each agent operates independently and provides a structured `DecisionObject` with:
- Numeric recommendation
- Confidence score (0-1)
- Priority rating
- Risk assessment
- Expected cost and benefit
- Historical similarity to past decisions

**Agent List:**
- **Sales Agent** ([backend/app/agents/sales.py](backend/app/agents/sales.py)) — Demand forecasting and sales impact
- **Inventory Agent** ([backend/app/agents/inventory.py](backend/app/agents/inventory.py)) — Stock levels and replenishment timing
- **Finance Agent** ([backend/app/agents/finance.py](backend/app/agents/finance.py)) — Budget constraints and ROI analysis
- **Procurement Agent** ([backend/app/agents/procurement.py](backend/app/agents/procurement.py)) — Supplier availability and lead times (Neo4j-enabled)
- **Pricing Agent** ([backend/app/agents/pricing.py](backend/app/agents/pricing.py)) — Price elasticity and margin optimization
- **Marketing Agent** ([backend/app/agents/marketing.py](backend/app/agents/marketing.py)) — Campaign feasibility and customer segment impact
- **Risk Agent** ([backend/app/agents/risk.py](backend/app/agents/risk.py)) — Risk quantification and hedging strategies

All agents inherit from `BaseAgent` and implement the `run()` method.

### 3. AMDIE Fusion Engine

The AMDIE module ([backend/app/amdie/](backend/app/amdie/)) orchestrates multi-agent fusion:

**Submodules:**

- **[conflict.py](backend/app/amdie/conflict.py)** — Detects recommendation disagreements using cosine similarity thresholds
- **[weights.py](backend/app/amdie/weights.py)** — Computes adaptive agent weights using softmax, confidence, and historical accuracy
- **[goals.py](backend/app/amdie/goals.py)** — Adjusts objective functions based on tenant goals (seasonality, volatility, supplier concentration)
- **[optimization.py](backend/app/amdie/optimization.py)** — Solves constrained LP fusion to produce final recommendation with explainability

**Fusion Flow:**
1. Collect agent recommendations (decision_type-scoped)
2. Detect conflicts between agents
3. Calculate adaptive weights per agent
4. Adjust objectives for business goals
5. Solve LP optimization with budget/capacity constraints
6. Return fused recommendation with decision log

### 4. FastAPI Backend Services

The backend exposes RESTful endpoints through [backend/app/main.py](backend/app/main.py) and route modules:

**Core Modules:**

- **[api.py](backend/app/api.py)** — Decision triggers, history, explainability, chat endpoints
- **[auth_routes.py](backend/app/auth_routes.py)** — JWT-based authentication, user management
- **[retail_routes.py](backend/app/retail_routes.py)** — Retail-specific endpoints (POS, inventory, sales)
- **[db.py](backend/app/db.py)** — SQLAlchemy ORM models (SQLite/PostgreSQL)
- **[security.py](backend/app/security.py)** — Role-based access control (RBAC), encryption
- **[config.py](backend/app/config.py)** — Environment-based configuration with sensible defaults

**Database Support:**
- PostgreSQL (production)
- SQLite (development)

**Vector Databases:**
- Chroma (default, in-memory/persistent)
- Qdrant (distributed vector store)

**Optional Neo4j Graph DB:**
- Supply chain graph modeling
- Supplier relationship mapping
- Controlled via `NEO4J_ENABLED` environment variable

**LLM Provider Support:**
- Mock adapter (testing)
- OpenAI (GPT-4, GPT-3.5-turbo)
- Anthropic (Claude)

### 5. Frontend Dashboard

React + Vite SPA for tenant business data visualization and decision orchestration.

**Key Pages:**
- **Dashboard** — Overview of KPIs and decision history
- **Inventory** — Stock levels, reorder recommendations, purchase orders
- **Purchases** — Supplier management and procurement
- **POS** — Point-of-sale transaction entry
- **Customers** — Customer data and segmentation
- **AI Assistant** — Chat interface for explainability and ad-hoc queries

**Frontend Stack:**
- React 19.2.7
- React Router 7.18.2
- Recharts 3.10.1 (data visualization)
- Vite 8.1.1 (build tool)
- Oxlint (linting)

---

## Project Structure

```
inventory/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                  # BaseAgent abstract class
│   │   │   ├── sales.py                 # Sales demand forecasting agent
│   │   │   ├── inventory.py             # Inventory optimization agent
│   │   │   ├── finance.py               # Financial constraint agent
│   │   │   ├── procurement.py           # Procurement and supplier agent
│   │   │   ├── pricing.py               # Price optimization agent
│   │   │   ├── marketing.py             # Marketing campaign agent
│   │   │   └── risk.py                  # Risk assessment agent
│   │   │
│   │   ├── amdie/
│   │   │   ├── __init__.py
│   │   │   ├── conflict.py              # Conflict detection module
│   │   │   ├── weights.py               # Adaptive weighting via softmax
│   │   │   ├── goals.py                 # Goal alignment and adjustments
│   │   │   └── optimization.py          # LP fusion solver
│   │   │
│   │   ├── __init__.py
│   │   ├── main.py                      # FastAPI app and startup
│   │   ├── api.py                       # Decision endpoints and logic
│   │   ├── auth_routes.py               # Authentication endpoints
│   │   ├── retail_routes.py             # Retail-specific endpoints
│   │   ├── auth.py                      # JWT and role management
│   │   ├── config.py                    # Settings and environment
│   │   ├── db.py                        # SQLAlchemy models
│   │   ├── security.py                  # RBAC and encryption
│   │   ├── decision_registry.py         # Decision type registry (Phase 2)
│   │   ├── generator.py                 # Database seeding utility
│   │   ├── llm.py                       # LLM adapter (OpenAI, Anthropic, Mock)
│   │   ├── retrieval.py                 # Vector DB retrieval
│   │   ├── vector_db.py                 # Chroma/Qdrant integration
│   │   └── graph_db.py                  # Neo4j integration (optional)
│   │
│   ├── tests/
│   │   ├── __init__.py
│   │   └── test_all.py                  # Comprehensive test suite
│   │
│   ├── evaluate.py                      # Newsvendor baseline evaluation
│   ├── evaluate_fresh.py                # Fresh evaluation runner
│   └── requirements.txt                 # Python dependencies
│
├── frontend/
│   ├── src/
│   │   ├── api.js                       # API client wrapper
│   │   ├── App.jsx                      # Main app component
│   │   ├── App.css
│   │   ├── index.css
│   │   ├── Login.jsx                    # Login page
│   │   ├── main.jsx                     # React entry point
│   │   ├── MaintenanceDashboard.jsx     # Admin dashboard
│   │   ├── OwnerDashboard.jsx           # Owner dashboard
│   │   ├── components/
│   │   │   ├── Layout.jsx               # Page layout wrapper
│   │   │   ├── ToastProvider.jsx        # Toast notification provider
│   │   │   └── ui.jsx                   # Shared UI components
│   │   ├── pages/
│   │   │   ├── AiAssistant.jsx          # Chat/explainability page
│   │   │   ├── Customers.jsx            # Customer management
│   │   │   ├── Dashboard.jsx            # Main dashboard
│   │   │   ├── Inventory.jsx            # Inventory management
│   │   │   ├── POS.jsx                  # Point-of-sale
│   │   │   ├── Purchases.jsx            # Purchase orders
│   │   │   └── index.jsx                # Page routing
│   │   └── assets/                      # Images and static assets
│   │
│   ├── public/                          # Static assets
│   ├── package.json                     # npm dependencies
│   ├── vite.config.js                   # Vite configuration
│   ├── index.html                       # HTML entry point
│   └── README.md                        # Frontend-specific docs
│
├── docker-compose.yml                   # PostgreSQL + Qdrant services
└── README.md                            # This file
```

### Directory Descriptions

- **backend/app/agents/** — Independent agent implementations; each provides a `DecisionObject`
- **backend/app/amdie/** — Conflict detection, weight calculation, goal adjustment, and LP fusion
- **backend/app/** — Core API routes, database models, authentication, configuration
- **frontend/src/** — React components organized by domain (pages, components)
- **backend/tests/** — pytest-based integration tests

---

## Setup and Installation

### Prerequisites

- **Python**: 3.12 or higher
- **Node.js**: 20+ and npm
- **Docker** & **Docker Compose** (optional, for PostgreSQL + Qdrant)
- **Git**

### Option 1: Quick Start (SQLite + Chroma, No Docker)

#### 1.1 Clone and Install Backend

```bash
# Clone the repository
git clone <repo-url>
cd inventory

# Install Python dependencies
pip install -r backend/requirements.txt
```

#### 1.2 Configure Environment (Optional)

Create `.env` file in project root if you want custom settings:

```env
# App
DEBUG=True
PORT=8000
HOST=127.0.0.1

# Database (default: SQLite)
DATABASE_URL=sqlite:///./control_tower.db

# Vector DB (default: Chroma)
VECTOR_DB_TYPE=chroma
CHROMA_PERSIST_DIR=./chroma_db

# LLM Provider (default: mock for testing)
LLM_PROVIDER=mock
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-...
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=sk-ant-...      (model: ANTHROPIC_MODEL_NAME, default claude-sonnet-5-5)

# Security: the defaults are public; always override outside local dev
# JWT_SECRET=...
# ENCRYPTION_KEY=...                (Fernet key; changing it makes existing encrypted costs unreadable)
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Continuous monitoring: scan all tenants every N seconds (0 disables)
MONITORING_INTERVAL_SECONDS=300
# Autonomous reorders above this cost wait for owner review
AUTOMATION_AUTO_APPROVAL_COST_LIMIT=500

# Neo4j (optional)
NEO4J_ENABLED=false
# NEO4J_URI=bolt://localhost:7687
# NEO4J_USER=neo4j
# NEO4J_PASSWORD=password
```

#### 1.3 Start Backend

```bash
# From project root
python -m backend.app.main
```

Backend runs on: `http://127.0.0.1:8000`

API docs available at: `http://127.0.0.1:8000/docs` (Swagger UI)

#### 1.4 Start Frontend (in a new terminal)

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on: `http://localhost:5173`

### Option 2: Production Setup (PostgreSQL + Qdrant + Docker)

#### 2.1 Start Services

```bash
docker-compose up -d
```

This starts:
- PostgreSQL database on `localhost:5432`
- Qdrant vector DB on `localhost:6333`

#### 2.2 Configure Backend for PostgreSQL

Set environment variables:

```bash
# Linux/macOS
export DATABASE_URL="postgresql://postgres:postgrespassword@localhost/control_tower"
export VECTOR_DB_TYPE="qdrant"
export QDRANT_HOST="localhost"
export QDRANT_PORT="6333"

# Windows PowerShell
$env:DATABASE_URL = "postgresql://postgres:postgrespassword@localhost/control_tower"
$env:VECTOR_DB_TYPE = "qdrant"
$env:QDRANT_HOST = "localhost"
$env:QDRANT_PORT = "6333"
```

Or add to `.env` file and install `psycopg2-binary`:

```bash
pip install psycopg2-binary
```

#### 2.3 Start Backend

```bash
python -m backend.app.main
```

#### 2.4 Start Frontend

```bash
cd frontend
npm run dev
```

### Option 3: Neo4j Graph Database (Optional, Advanced)

If you need supplier relationship graphs:

```bash
# 1. Install Neo4j (Docker)
docker run -d \
  --name control_tower_neo4j \
  -p 7687:7687 \
  -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:latest

# 2. Set environment variables
export NEO4J_ENABLED=true
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password

# 3. Start backend
python -m backend.app.main
```

Access Neo4j Browser at: `http://localhost:7474`

---

## Usage

### 1. Authentication

All API endpoints require JWT authentication (except `/api/auth/login` and `/api/auth/register`).

**Login:**
```bash
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"password"}'
```

Response includes JWT token:
```json
{"access_token": "eyJ0eXAi...", "token_type": "bearer"}
```

Use token for subsequent requests:
```bash
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/api/tenants
```

### 2. Triggering Decisions

**Via API:**
```bash
curl -X POST http://127.0.0.1:8000/api/decisions/trigger \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "prod_001",
    "date_str": "2026-08-28",
    "decision_type": "reorder_quantity"
  }'
```

Response includes:
- Fused recommendation
- Individual agent recommendations
- Conflict flags
- Explainability rationale
- Decision history log

**Via Frontend:**
1. Navigate to **Inventory** page
2. Select a product
3. Click "Get Recommendation"
4. View fusion results and agent details

### 3. Viewing Decision History

**API:**
```bash
curl -H "Authorization: Bearer <token>" \
  "http://127.0.0.1:8000/api/decisions/history?product_id=prod_001&limit=10"
```

**Frontend:**
- Open **Dashboard** → View decision history chart
- Open **AI Assistant** → Ask about past decisions

### 4. Explainability and Chat

**Chat with system:**
```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Why did the system recommend 500 units?"}
    ]
  }'
```

**Frontend:**
- Open **AI Assistant** page
- Chat naturally with the decision system

### 5. Managing Business Goals

Goals drive objective adjustments in the AMDIE fusion layer.

**API:**
```bash
curl -X PUT http://127.0.0.1:8000/api/goals \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "maximize_margin": true,
    "minimize_stockout": true,
    "target_inventory_turnover": 6.0
  }'
```

**Frontend:**
- Go to **Dashboard** → **Settings** → Update goals

### 6. Inventory and Purchase Management

**View inventory:**
```bash
curl -H "Authorization: Bearer <token>" \
  http://127.0.0.1:8000/api/inventory/state
```

**Create purchase order:**
```bash
curl -X POST http://127.0.0.1:8000/api/purchases/create \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "prod_001",
    "supplier_id": "supp_001",
    "quantity": 500,
    "target_date": "2026-09-15"
  }'
```

---

## Testing

### Run Full Test Suite

```bash
cd backend
python -m pytest tests/test_all.py -v
```

### Run Specific Test Class

```bash
python -m pytest tests/test_all.py::TestDecisionSchema -v
```

### Run with Coverage

```bash
python -m pytest tests/test_all.py --cov=backend.app --cov-report=html
# Open htmlcov/index.html in browser
```

### Test Categories

**test_all.py** includes:

1. **Schema Validation Tests** — Decision object validation
2. **Agent Tests** — Individual agent output verification
3. **Conflict Detection Tests** — Multi-agent disagreement detection
4. **Weight Calculation Tests** — Softmax weighting verification
5. **Goal Adjustment Tests** — Objective modification tests
6. **Optimization Tests** — LP fusion solver validation
7. **Phase 2 Decision Registry Tests** — Decision type scoping
8. **Integration Tests** — End-to-end decision flow

### Mock LLM for Testing

The default LLM provider is `mock`, which returns deterministic responses. No API keys needed for testing.

To use real LLM providers:
```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
```

---

## API Endpoints

### Authentication
- `POST /api/auth/login` — Login and get JWT token
- `POST /api/auth/register` — Register new user
- `POST /api/auth/logout` — Logout

### Tenants & Products
- `GET /api/tenants` — List tenants (admin)
- `GET /api/tenants/{tenant_id}` — Get tenant details
- `GET /api/products` — List tenant products
- `GET /api/products/{product_id}` — Get product details

### Decisions
- `POST /api/decisions/trigger` — Trigger a decision
- `GET /api/decisions/history` — Get decision history (paginated)
- `GET /api/decisions/{decision_id}` — Get decision details
- `POST /api/decisions/{decision_id}/outcome` — Record actual outcome

### Inventory
- `GET /api/inventory/state` — Current inventory state
- `GET /api/inventory/forecast` — Demand forecast
- `POST /api/inventory/adjust` — Manual inventory adjustment

### Purchases
- `GET /api/purchases` — List purchase orders
- `POST /api/purchases/create` — Create purchase order
- `PUT /api/purchases/{po_id}` — Update PO status

### Suppliers
- `GET /api/suppliers` — List suppliers
- `POST /api/suppliers/create` — Add new supplier
- `PUT /api/suppliers/{supplier_id}` — Update supplier

### Chat & Explainability
- `POST /api/chat` — Chat with system for decision explainability
- `GET /api/explain/{decision_id}` — Get decision explanation

### Goals
- `GET /api/goals` — Get current business goals
- `PUT /api/goals` — Update business goals

Full API documentation available at: `http://127.0.0.1:8000/docs` (Swagger UI)

---

## Development

### Code Organization Principles

1. **Agents are independent** — Each agent in `backend/app/agents/` operates without knowledge of others
2. **AMDIE orchestrates fusion** — `backend/app/amdie/` combines agent outputs
3. **Decision registry drives scoping** — `backend/app/decision_registry.py` defines who participates
4. **API is the contract** — `backend/app/api.py` defines all external interfaces
5. **Tests validate behavior** — `backend/tests/test_all.py` ensures correctness

### Adding a New Decision Type

1. Add entry to `DECISION_TYPES` in [backend/app/decision_registry.py](backend/app/decision_registry.py):
   ```python
   DECISION_TYPES["new_decision"] = ["agent1", "agent2", "agent3"]
   ```

2. Add label and axis description:
   ```python
   DECISION_TYPE_LABELS["new_decision"] = "New Decision"
   DECISION_TYPE_AXIS["new_decision"] = "units (new metric)"
   ```

3. Add optional upper bound:
   ```python
   DECISION_TYPE_UPPER_BOUND["new_decision"] = 1000.0  # or None for unconstrained
   ```

4. That's it! The pipeline automatically scopes to the new agent set.

### Adding a New Agent

1. Create `backend/app/agents/new_agent.py`:
   ```python
   from backend.app.agents.base import BaseAgent, DecisionObject
   from datetime import date
   from sqlalchemy.orm import Session

   class NewAgent(BaseAgent):
       def __init__(self):
           super().__init__(agent_id="new_agent")

       def run(self, tenant_id: str, product_id: str, run_date: date, db: Session) -> DecisionObject:
           # Implement agent logic
           recommendation = 100.0
           return DecisionObject(
               agent_id="new_agent",
               recommendation=recommendation,
               reason="Why this recommendation",
               confidence=0.8,
               priority=0.5,
               risk_score=0.2,
               expected_cost=500.0,
               expected_benefit=1000.0,
               required_resources={"cash": 500.0},
               historical_similarity=0.7
           )
   ```

2. Register in decision types:
   ```python
   DECISION_TYPES["some_decision"] = ["new_agent", "other_agents", ...]
   ```

3. Instantiate in [backend/app/api.py](backend/app/api.py) decision trigger endpoint.

### Extending AMDIE Fusion

Modify [backend/app/amdie/](backend/app/amdie/) modules:

- **conflict.py** — Change conflict detection thresholds
- **weights.py** — Adjust softmax weighting formulas
- **goals.py** — Add new goal dimensions
- **optimization.py** — Change LP objective or constraints

### Running Backend in Debug Mode

```bash
# With auto-reload on file changes
python -m backend.app.main
# or
export DEBUG=True
python -m uvicorn backend.app.main:app --reload
```

### Frontend Development

```bash
cd frontend

# Start dev server with HMR
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Lint code
npm run lint
```

---

## Troubleshooting

### Issue: Database Connection Error

**Error:** `OperationalError: unable to connect to postgres://...`

**Solution:**
- Check PostgreSQL is running: `docker ps`
- Verify DATABASE_URL in `.env`: `postgresql://postgres:postgrespassword@localhost/control_tower`
- For SQLite (default), ignore — ensure `backend/` directory is writable

### Issue: Vector DB Connection Error

**Error:** `Failed to connect to Qdrant at localhost:6333`

**Solution:**
- Check Qdrant is running: `docker ps` or `docker-compose ps`
- Switch to Chroma (default): `export VECTOR_DB_TYPE=chroma`
- Restart service: `docker-compose restart qdrant`

### Issue: JWT Token Invalid

**Error:** `HTTPException: 403 Invalid token`

**Solution:**
- Token may have expired. Re-login:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"password"}'
  ```
- Copy new token to Authorization header

### Issue: Frontend Cannot Connect to Backend

**Error:** `Failed to fetch from http://127.0.0.1:8000/api/...` (CORS error)

**Solution:**
- Backend should have CORS enabled (default)
- Check backend is running: `curl http://127.0.0.1:8000/docs`
- If frontend on different port, ensure backend CORS allows it (configured in [backend/app/main.py](backend/app/main.py))

### Issue: Mock LLM Always Returns Same Response

**Expected behavior** — Mock LLM is deterministic for testing.

**To use real LLM:**
```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
```

### Issue: Tests Fail with Import Error

**Error:** `ModuleNotFoundError: No module named 'backend'`

**Solution:**
```bash
# Run from project root
cd /path/to/inventory
python -m pytest backend/tests/test_all.py -v

# Or
cd backend
python -m pytest tests/test_all.py -v
```

### Issue: Port Already in Use

**Error:** `Address already in use: ('127.0.0.1', 8000)`

**Solution:**
```bash
# Kill process on port 8000 (Linux/macOS)
lsof -ti:8000 | xargs kill -9

# PowerShell (Windows)
Get-Process -Id (Get-NetTCPConnection -LocalPort 8000 -ErrorAction Ignore).OwningProcess | Stop-Process -Force

# Or use different port
export PORT=8001
python -m backend.app.main
```

### Issue: Neo4j Not Found

**Error:** `Could not resolve address for neo4j (name or service not known)`

**Solution:**
- Disable Neo4j: `export NEO4J_ENABLED=false`
- Or start Neo4j: `docker run -d --name neo4j -p 7687:7687 neo4j:latest`

---

## Architecture Deep Dive

### Decision Fusion Flow

```
1. Trigger Decision
   ├─ Select decision_type (e.g., "reorder_quantity")
   ├─ Look up agents for type in registry
   └─ Scope all downstream steps

2. Agent Execution (parallel)
   ├─ Sales Agent → demand forecast
   ├─ Inventory Agent → stock level analysis
   ├─ Finance Agent → budget constraints
   └─ Procurement Agent → supplier data

3. Conflict Detection
   ├─ Compute cosine similarity between recommendations
   └─ Flag disagreement if > threshold

4. Adaptive Weighting
   ├─ Get historical accuracy per agent
   ├─ Apply softmax to compute weights
   └─ Confidence scores adjust weight magnitudes

5. Goal Adjustment
   ├─ Fetch tenant business goals
   ├─ Compute seasonality and volatility
   ├─ Modify LP objective based on goal weights
   └─ Account for supplier concentration risk

6. LP Fusion (solve_decision_fusion)
   ├─ Weighted agent recommendations → objective
   ├─ Budget and capacity constraints
   ├─ Decision type upper bound constraint (if set)
   └─ Solve constrained optimization

7. Return Fused Recommendation
   ├─ Fused quantity/price/discount
   ├─ Confidence bounds
   ├─ Explainability rationale
   └─ Decision log entry
```

### Data Models

**Tenant** — Organization boundary
- Tenant ID, name, industry
- Isolated product, decision, and financial data

**Product** — SKU under management
- Product ID, tenant, category
- Cost, price, reorder point

**InventoryState** — Snapshot of stock
- Product, date, on-hand quantity, open orders

**DecisionLog** — Fusion result record
- Decision ID, type, date, product
- Fused recommendation, confidence, conflict flag
- Individual agent recommendations
- Business goals snapshot

**AgentAccuracy** — Historical performance
- Agent ID, decision type
- Correct count, total count, accuracy metric

**Sale** — Transaction record
- Product, tenant, date, quantity, revenue

**Supplier** — Vendor information
- Supplier ID, name, lead time, reliability
- (Optional: Neo4j relationships)

### Multi-Tenancy

- All queries filtered by `tenant_id`
- JWT token includes tenant context
- No cross-tenant data leakage
- Each tenant has isolated goals and decision history

### Security

- JWT authentication on all endpoints (except login/register)
- Role-based access control (admin, manager, viewer)
- Encryption for sensitive fields (supplier contracts, pricing)
- CORS configured for frontend domain

---

## Performance Tuning

### Database Optimization

- Index on `(product_id, date)` for decision history queries
- Index on `(tenant_id, decision_type)` for scoped aggregations
- Batch seed operations for large datasets

### Vector DB Optimization

- Use Qdrant in production (distributed, scalable)
- Use Chroma for development/testing
- Configure embedding model batch size for throughput

### Agent Execution

- Agents run in parallel where possible
- Cache recent agent outputs within decision cycle
- Implement timeout for slow agents (default: 5s)

### LP Solver Optimization

- Pre-scale decision variables for numerical stability
- Warm-start solver with initial guess from agent weights
- Implement solver timeout to avoid hanging

---

## Current Status

**Phase 2 MVP Features:**
- ✅ Decision type registry and scoping
- ✅ Seven specialized agents
- ✅ Conflict detection and adaptive weighting
- ✅ Business goal alignment
- ✅ Constrained LP fusion
- ✅ FastAPI backend with full authentication
- ✅ React frontend with dashboard
- ✅ Comprehensive test suite
- ✅ Docker Compose setup (PostgreSQL + Qdrant)
- ✅ Chat/explainability interface

**Known Limitations:**
- Neo4j support is optional (default: Postgres queries only)
- LLM providers (OpenAI, Anthropic) require API keys
- Vector DB requires external service (Docker or managed)
- Real-time agent updates require WebSocket extension

**Future Enhancements:**
- Real-time decision notifications (WebSocket)
- Advanced visualization (decision trees, agent influence)
- Causal inference for goal adjustments
- Multi-period optimization
- Supplier quality scoring
- Customer segmentation refinement

---

## Contributing

1. Create a feature branch: `git checkout -b feature/new-agent`
2. Make changes and test: `pytest backend/tests/test_all.py -v`
3. Commit with clear messages: `git commit -m "Add X Agent for Y decisions"`
4. Push and create a pull request

---

## License

This project is provided as-is for educational and commercial use.

---

## Support

For issues, questions, or feature requests, open an issue in the repository.
