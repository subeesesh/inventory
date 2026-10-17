# Replenishment experiments

Evaluates AMDIE on the one decision type with an objective ground truth,
`reorder_quantity`, by simulating a small retailer over time and measuring
realised profit.

## Run

```bash
# from the repo root
python -m backend.experiments.run --quick                                   # smoke test, ~2 min
python -m backend.experiments.run --seeds 10 --out backend/experiments/results/main
python -m backend.experiments.run --seeds 10 --llm --workers 2 --out backend/experiments/results/main   # adds the LLM baseline to an existing run
# LLM key: GEMINI_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY in the environment or the repo-root .env
# (EXPERIMENT_LLM_PROVIDER / EXPERIMENT_LLM_MODEL to choose; Gemini defaults to gemini-3.8-flash)
python -m backend.experiments.analyze backend/experiments/results/main     # re-run analysis only
```

Runs resume: finished jobs are kept in `runs.jsonl` and skipped. Each worker
loads its own embedding model (~0.5–1 GB RAM), so size `--workers` to memory
(default ≤ 6).

## Protocol

- **Environment** (`environment.py`): N products with ground-truth daily demand
  (trend, weekly and yearly seasonality, Gaussian noise, optional surges/drops),
  stochastic supplier lead times, periodic weekly review, lost sales, holding cost
  (25%/yr), a fixed cost per order line, and a shared weekly purchase budget plus
  cash that truncate orders.  Only censored sales are written to the database,
  as a real POS would record them.
- **Same code path as production.** Agent policies call the real agents, and
  AMDIE policies call `trigger_decision_internal` (the API's decision function)
  against the simulator's database.  Orders are written as purchase orders, so
  agents see on-order stock.  Ablations switch components off through
  `AmdieOptions`, not a re-implementation.
- **Outcome feedback.** Once an order's protection interval has elapsed, AMDIE
  receives the perfect-foresight order quantity q* as the decision's outcome,
  which updates agent reliability and triggers weight retraining after 30
  outcomes, as `POST /decisions/{id}/outcome` does in the app.
- **Paired design.** Every policy runs on a fresh copy of the same seeded instance
  (common random numbers), so differences are paired by seed.
- **Tuning vs test.** AMDIE's two hyper-parameters (softmax temperature, reorder
  service level) were chosen on development seeds 1000+ (`results/dev_tuning`);
  reported results use held-out seeds 0–9.

## Scenarios

| Scenario | What changes |
|---|---|
| `baseline` | Budget 1.5× expected cost of goods, demand CV 0.2–0.4, reliable suppliers |
| `tight_budget` | Budget 0.8× expected cost of goods (cash-constrained SME) |
| `volatile` | Demand CV 0.4–0.7, 50% of products hit by a 3-week surge/drop, 2× lead-time variance, 30% unreliable suppliers |

## Policies

| Name | Family | Description |
|---|---|---|
| `newsvendor` | OR baseline | Order-up-to with the newsvendor critical-ratio safety factor |
| `base_stock` | OR baseline | Order-up-to at 95% cycle service; **reference for relative profit** |
| `agent_*` | single agent | One AMDIE agent's recommendation alone |
| `ensemble_mean` / `ensemble_median` | naive ensemble | Unweighted aggregate of the four agents |
| `amdie` | proposed | Full AMDIE pipeline |
| `amdie_*` | ablation | One component removed (see `policies.POLICIES`) |
| `oracle` | reference | Orders exactly q* with perfect foresight of demand and lead time; **not** an upper bound (it carries no buffer for the next order's lead time) |
| `llm` | LLM baseline | One LLM asked for the order quantity from the same information |

Parametrised variants such as `amdie[t=0.05,sl=0.9]` set the softmax
temperature and service level (used for the tuning sweep).

## Metrics

- **Δ profit vs base-stock (%)**: primary metric. Profit = revenue − purchases −
  holding − order costs + change in inventory value.
- Fill rate, stock-out days (fraction of product-days with lost sales), average
  inventory value, share of orders truncated by budget/cash.
- **WAPE vs perfect foresight**: Σ|placed − q*| / Σq*.  A diagnostic, not an
  objective: good policies hold safety stock and so deviate from q*.
- Conflict rate (AMDIE): share of decisions with conflict score > τ = 0.3.

## Outputs

`summary.csv`, `tables.md`, `tables.tex` (booktabs), `stats.md` (paired t-test
and Wilcoxon at seed level, Wilcoxon at product level, Holm-corrected), and
`figures/` (PNG + PDF).
