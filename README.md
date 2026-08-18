# AI Business Control Tower for SMEs (Phase 1 MVP)

A multi-agent decision support system utilizing the **Adaptive Multi-Agent Decision Intelligence Engine (AMDIE)** to negotiate and fuse business reorder decisions across Inventory, Sales, and Finance agents.

---

## Technical Architecture & Core Contributions

1. **Multi-Agent Negotiation Layer**:
   - **Sales Agent**: Computes daily forecasts using statsmodels `ExponentialSmoothing` / `ARIMA`. Sets confidence and risk based on 95% forecast prediction intervals.
   - **Inventory Agent**: Evaluates stockout risks, safety stock levels, and reorder points.
   - **Finance Agent**: Reconstitutes liquidity limits using cash balances and allocated period budgets.
2. **AMDIE Fusion (Constrained Optimization Solver)**:
   - **Softmax Weights**: Score weights based on: `score = w1*reliability + w2*confidence + w3*hist_accuracy + w4*context_relevance - w5*risk`.
   - **Linear Programming Formulation**: Casts triangular/piecewise-linear utility curves peaking at agent recommendations into a system of linear inequality constraints, maximizing global business utility under budget ceilings.
   - **Business Goal Overrides**: Shifts objectives dynamically to align with tenant goals: `maximize_profit`, `minimize_cost`, `minimize_risk`, `maximize_turnover`.
   - **Explainability**: Logged retrieval audits tracking all database row IDs and supplier notes context.

---

## Directory Structure

```
/
├── backend/
│   ├── app/
│   │   ├── config.py          # App settings & fallback configurations
│   │   ├── db.py              # PostgreSQL/SQLite schemas with transparent AES-GCM encryption
│   │   ├── security.py        # Application-layer AES-GCM and PII redaction
│   │   ├── retrieval.py       # Retrieval Manager with ContextVar audit logs
│   │   ├── agents/            # Sales, Inventory, and Finance Agent scripts
│   │   ├── amdie/             # Conflict detection, Softmax weighting, Goal adjustments, LP solver
│   │   ├── api.py             # FastAPI REST endpoints
│   │   └── main.py            # App bootloader & synthetic database seeder
│   ├── tests/                 # Unit tests (Pytest)
│   └── evaluate.py            # Evaluation scenario simulation & baseline comparisons
├── frontend/                  # React + Vite frontend dashboard
└── README.md
```

---

## Setup & Running Instructions

### Prerequisites
- Python 3.12+
- Node.js v24+ & npm

### 1. Run Backend Server
From the project root:
```bash
# Install dependencies
pip install -r backend/requirements.txt

# Start FastAPI server (runs on http://127.0.0.1:8000)
# Automatically seeds 12 months of synthetic transaction data on startup
python -m backend.app.main
```

### 2. Run React Frontend
Open another terminal:
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

### 3. Run Unit Tests
To verify all schemas, weights, and LP optimization solver constraints:
```bash
python -m pytest backend/tests
```

### 4. Run Scenarios Evaluation
To run the evaluation script and compare AMDIE against the 3 baselines:
```bash
python -m backend.evaluate
```
The comparison report is written to: `C:/Users/subee/.gemini/antigravity/brain/6d05e865-a45e-428f-b41d-72326a118f82/evaluation_report.md`
