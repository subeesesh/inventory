# AI Business Control Tower for SMEs (Phase 2)

A multi-agent decision support platform built around the Adaptive Multi-Agent Decision Intelligence Engine (AMDIE). The project is now structured as a Phase 2 decision-scoping system, where each decision cycle is tied to a specific decision type and only the relevant agents participate.

This version expands beyond classic reorder optimization to support pricing, promotions, and procurement-aware decision workflows while preserving the original reorder use case.

---

## What is Phase 2 in this project?

The key Phase 2 change is the introduction of a decision registry and decision-type-aware AMDIE orchestration.

Supported decision types include:
- reorder_quantity
- price_adjustment
- promotion_trigger

Each decision type is mapped to a specific list of agents, and the system now scopes conflict detection, weight calculation, goal adjustment, and optimization to that decision context.

This makes the engine more modular and more realistic for a business system where different parts of the organization evaluate different decisions under different constraints.

---

## Core architecture

### 1. Decision type registry
The project now defines a central registry in [backend/app/decision_registry.py](backend/app/decision_registry.py) that maps:
- decision type → participating agents
- decision label → display name
- decision axis description → recommendation units
- LP upper bound → optional bounded decision variable

This is the Phase 2 structural prerequisite for the system.

### 2. Multi-agent decision layer
The agent set now includes:
- Sales Agent
- Inventory Agent
- Finance Agent
- Procurement Agent
- Pricing Agent
- Marketing Agent
- Risk Agent

Each agent contributes a decision recommendation, confidence, historical signal, and risk/cost profile.

### 3. AMDIE fusion engine
The fusion layer handles:
- conflict detection across agents
- softmax-based adaptive weighting
- business-goal-aware objective adjustments
- constrained optimization for final fusion
- explainability and decision logging

The optimization flow is implemented in the AMDIE modules under [backend/app/amdie](backend/app/amdie).

### 4. API and backend services
The backend uses FastAPI and exposes endpoints for:
- tenant info and product data
- goal updates
- decision trigger execution
- decision history querying
- supplier creation and metadata
- chat and decision explainability workflows

The primary API module is [backend/app/api.py](backend/app/api.py), with app startup and routing in [backend/app/main.py](backend/app/main.py).

### 5. Frontend dashboard
The frontend is a React + Vite application that presents tenant-level business data, dashboard views, and decision orchestration UI.

Relevant frontend files are under:
- [frontend/src](frontend/src)
- [frontend/package.json](frontend/package.json)

---

## Current project structure

```text
/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── base.py
│   │   │   ├── finance.py
│   │   │   ├── inventory.py
│   │   │   ├── marketing.py
│   │   │   ├── pricing.py
│   │   │   ├── procurement.py
│   │   │   ├── risk.py
│   │   │   └── sales.py
│   │   ├── amdie/
│   │   │   ├── conflict.py
│   │   │   ├── goals.py
│   │   │   ├── optimization.py
│   │   │   └── weights.py
│   │   ├── auth.py
│   │   ├── auth_routes.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── decision_registry.py
│   │   ├── generator.py
│   │   ├── graph_db.py
│   │   ├── llm.py
│   │   ├── main.py
│   │   ├── retrieval.py
│   │   ├── security.py
│   │   ├── vector_db.py
│   │   └── api.py
│   ├── tests/
│   │   └── test_all.py
│   ├── evaluate.py
│   ├── evaluate_fresh.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── package.json
│   ├── vite.config.js
│   └── index.html
├── docker-compose.yml
├── README.md
└── .gitignore
```

---

## Setup and run

### Prerequisites
- Python 3.12+
- Node.js 20+ and npm

### 1. Install backend dependencies
From the project root:

```bash
pip install -r backend/requirements.txt
```

### 2. Start the backend

```bash
python -m backend.app.main
```

The app runs on:
- http://127.0.0.1:8000

It initializes the database schema and seeds synthetic tenant/product/decision data on startup.

### 3. Start the frontend
Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open:
- http://localhost:5173

### 4. Run the test suite

```bash
python -m pytest backend/tests -q
```

The project currently passes its backend test suite.

---

## Current status

The codebase is a working Phase 2 MVP with:
- decision-type-aware orchestration
- multi-agent recommendation flow
- conflict detection and fusion logic
- business-goal alignment
- a working FastAPI backend
- a functioning React frontend build

It is suitable for local development and demo scenarios, but should still be treated as a prototype rather than a hardened production system.

---

## Useful references

- [backend/app/decision_registry.py](backend/app/decision_registry.py)
- [backend/app/api.py](backend/app/api.py)
- [backend/app/main.py](backend/app/main.py)
- [backend/tests/test_all.py](backend/tests/test_all.py)
- [frontend/package.json](frontend/package.json)

---

## Notes

This repo is intentionally structured as a business-control-tower prototype for SME decision support. The Phase 2 architecture introduces more realistic business workflow scoping, moving from a single reorder-oriented pipeline to a broader set of business decision classes while retaining compatibility with the original decision flow.
