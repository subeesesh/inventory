"""
Run the replenishment experiments.

    python -m backend.experiments.run --seeds 10 --out backend/experiments/results/main
    python -m backend.experiments.run --quick                      # smoke run
    python -m backend.experiments.run --policies amdie base_stock --scenarios baseline

Each (scenario, seed, policy) job runs in its own process on a fresh in-memory
database.  Results are appended to <out>/runs.jsonl as jobs finish, so an
interrupted run can be resumed with the same command (finished jobs are skipped).
Analysis (tables, statistics, figures) runs automatically at the end; see analyze.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import replace
from pathlib import Path

# Experiments must never call a paid LLM for explanations or touch the app database
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
# sentence-transformers only needs torch; stop transformers importing TensorFlow
# (roughly halves per-worker memory and start-up time)
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
# One BLAS/torch thread per worker process; parallelism comes from the process pool
for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_var, "1")


def _quiet_worker() -> None:
    import logging
    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)
    # Vector retrieval only feeds DecisionObject.historical_similarity, which AMDIE's
    # fusion does not use; stubbing it keeps runs fast and deterministic.
    import importlib
    for mod in ("sales", "inventory", "finance", "procurement", "pricing", "marketing", "hr", "customer_management"):
        m = importlib.import_module(f"backend.app.agents.{mod}")
        m.get_vector_context = lambda *a, **k: ([], "")


def run_job(scenario_name: str, seed: int, policy_name: str, config_kw: dict) -> dict:
    _quiet_worker()
    import contextlib
    import io
    from backend.experiments.environment import SCENARIOS, ExperimentConfig, ProblemInstance, Simulator
    from backend.experiments.policies import make_policy

    cfg = ExperimentConfig(**config_kw)
    instance = ProblemInstance.generate(seed, SCENARIOS[scenario_name], cfg)
    sim = Simulator(instance)
    policy = make_policy(policy_name)
    with contextlib.redirect_stdout(io.StringIO()):   # AMDIE retraining prints
        return sim.run(policy)


def _job_key(scenario, seed, policy):
    return f"{scenario}|{seed}|{policy}"


def main(argv=None) -> int:
    from backend.experiments.environment import SCENARIOS, ExperimentConfig
    from backend.experiments.policies import DEFAULT_POLICIES, POLICIES

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=10, help="number of random instances per scenario")
    ap.add_argument("--seed-offset", type=int, default=0)
    ap.add_argument("--scenarios", nargs="+", default=list(SCENARIOS), choices=list(SCENARIOS))
    ap.add_argument("--policies", nargs="+", default=DEFAULT_POLICIES,
                    help=f"registry names {sorted(POLICIES)} or tuned variants like 'amdie[t=0.1,sl=0.9]'")
    ap.add_argument("--llm", action="store_true", help="also run the LLM baseline (needs an API key)")
    ap.add_argument("--products", type=int, default=ExperimentConfig.n_products)
    ap.add_argument("--weeks", type=int, default=ExperimentConfig.horizon_days // 7)
    # Each worker holds its own embedding model (~0.5-1 GB); size the pool to RAM, not cores
    ap.add_argument("--workers", type=int, default=max(1, min((os.cpu_count() or 2) - 2, 6)))
    ap.add_argument("--out", type=Path, default=Path("backend/experiments/results/main"))
    ap.add_argument("--quick", action="store_true", help="2 seeds, 4 products, 6 weeks, baseline only")
    ap.add_argument("--no-analysis", action="store_true")
    args = ap.parse_args(argv)

    policies = list(args.policies)
    if args.llm and "llm" not in policies:
        policies.append("llm")
    cfg = replace(ExperimentConfig(), n_products=args.products, horizon_days=args.weeks * 7)
    seeds = list(range(args.seed_offset, args.seed_offset + args.seeds))
    scenarios = args.scenarios
    if args.quick:
        cfg = replace(cfg, n_products=4, horizon_days=42)
        seeds, scenarios = seeds[:2] or [0, 1], ["baseline"]

    config_kw = {k: getattr(cfg, k) for k in ("n_products", "history_days", "horizon_days", "review_period",
                                              "holding_rate_annual", "order_fixed_cost")}
    args.out.mkdir(parents=True, exist_ok=True)
    runs_path = args.out / "runs.jsonl"
    done = set()
    if runs_path.exists():
        for line in runs_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("config", {}).get("n_products") == cfg.n_products and \
               r.get("config", {}).get("horizon_days") == cfg.horizon_days:
                done.add(_job_key(r["scenario"], r["seed"], r["policy"]))

    jobs = [(sc, s, p) for sc in scenarios for s in seeds for p in policies if _job_key(sc, s, p) not in done]
    (args.out / "experiment.json").write_text(json.dumps({
        "scenarios": {s: SCENARIOS[s].__dict__ for s in scenarios},
        "seeds": seeds, "policies": policies, "config": config_kw,
    }, indent=2, default=str), encoding="utf-8")

    print(f"{len(jobs)} job(s) to run ({len(done)} already done) with {args.workers} worker(s) -> {args.out}")
    t0, failures = time.time(), 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool, runs_path.open("a", encoding="utf-8") as fh:
        futures = {pool.submit(run_job, sc, s, p, config_kw): (sc, s, p) for sc, s, p in jobs}
        for n, fut in enumerate(as_completed(futures), 1):
            sc, s, p = futures[fut]
            try:
                result = fut.result()
                fh.write(json.dumps(result, default=float) + "\n")
                fh.flush()
                m = result["metrics"]
                print(f"[{n}/{len(jobs)} {time.time() - t0:6.0f}s] {sc:12s} seed={s:<3d} {p:22s} "
                      f"profit={m['profit']:10.0f} fill={m['fill_rate']:.3f} ({m['runtime_s']:.0f}s)", flush=True)
            except BrokenProcessPool:
                print("A worker process died (usually out of memory). Finished jobs are saved in "
                      f"{runs_path}; rerun the same command with fewer --workers to resume.",
                      file=sys.stderr, flush=True)
                return 1
            except Exception:
                failures += 1
                print(f"[{n}/{len(jobs)}] FAILED {sc} seed={s} {p}\n{traceback.format_exc()}", file=sys.stderr, flush=True)

    if not args.no_analysis:
        from backend.experiments.analyze import analyze
        analyze(args.out)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
