"""
Replenishment policies compared in the experiments.

Every agent-based policy calls the production agents / AMDIE pipeline
(backend.app) against the simulator's database, so the numbers describe the
deployed system, not a re-implementation.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import defaultdict
from dataclasses import replace
from datetime import timedelta
from typing import Dict, List, Optional

import numpy as np
from scipy.stats import norm

from backend.app.amdie.options import AmdieOptions
from backend.app.db import SalesRecord

REORDER_AGENTS = ["inventory", "sales", "finance", "procurement"]


class Policy:
    name = "policy"
    family = "other"

    def setup(self, sim) -> None:
        pass

    def decide(self, sim, product, day, run_date, *, lead_time: int, q_star: float):
        raise NotImplementedError

    def feedback(self, sim, record) -> None:
        pass

    def trace(self, decisions) -> dict:
        return {}


# ── Perfect-information reference ────────────────────────────────────────────

class OraclePolicy(Policy):
    """Knows future demand and the realised lead time: orders exactly q*."""
    name = "oracle"
    family = "reference"

    def decide(self, sim, product, day, run_date, *, lead_time, q_star):
        return q_star, {}


# ── Classical operations-research baselines ──────────────────────────────────

class _OrderUpToPolicy(Policy):
    """Periodic-review order-up-to S = mu(L+R) + z sigma sqrt(L+R) on observed sales."""
    family = "operations_research"
    history_days = 90

    def z_value(self, product, sim) -> float:
        raise NotImplementedError

    def decide(self, sim, product, day, run_date, *, lead_time, q_star):
        start = run_date - timedelta(days=self.history_days)
        rows = sim.db.query(SalesRecord.date, SalesRecord.qty_sold).filter(
            SalesRecord.product_id == product.id,
            SalesRecord.date >= start,
            SalesRecord.date < run_date,
        ).all()
        by_day = defaultdict(float)
        for d, q in rows:
            by_day[d] += q
        series = [by_day.get(start + timedelta(days=k), 0.0) for k in range(self.history_days)]
        mu, sigma = float(np.mean(series)), float(np.std(series))
        protection = product.lead_time_mean + sim.cfg.review_period
        target = mu * protection + self.z_value(product, sim) * sigma * math.sqrt(protection)
        return max(0.0, target - sim.position(product.id)), {"target": target}


class BaseStockPolicy(_OrderUpToPolicy):
    name = "base_stock"

    def __init__(self, service_level: float = 0.95):
        self.z = float(norm.ppf(service_level))

    def z_value(self, product, sim):
        return self.z


class NewsvendorPolicy(_OrderUpToPolicy):
    """Order-up-to with the newsvendor critical ratio: underage = lost margin,
    overage = holding cost for one review period."""
    name = "newsvendor"

    def z_value(self, product, sim):
        underage = product.price - product.cost
        overage = product.cost * sim.cfg.holding_rate_annual * sim.cfg.review_period / 365.0
        ratio = float(np.clip(underage / (underage + overage), 0.5, 0.99))
        return float(norm.ppf(ratio))


# ── Agent-based baselines ────────────────────────────────────────────────────

def _run_agents(sim, product_id, run_date, agent_ids=REORDER_AGENTS) -> Dict[str, float]:
    from backend.app.api import _build_agent
    from backend.app.retrieval import retrieval_log_var
    retrieval_log_var.set([])
    return {
        aid: _build_agent(aid).run(sim.tenant_id, product_id, run_date, sim.db,
                                   decision_type="reorder_quantity").recommendation
        for aid in agent_ids
    }


class SingleAgentPolicy(Policy):
    family = "single_agent"

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.name = f"agent_{agent_id}"

    def decide(self, sim, product, day, run_date, *, lead_time, q_star):
        recs = _run_agents(sim, product.id, run_date, [self.agent_id])
        return recs[self.agent_id], {}


class EnsemblePolicy(Policy):
    """Naive multi-agent aggregation without AMDIE (no weighting, no constraints)."""
    family = "naive_ensemble"

    def __init__(self, how: str):
        assert how in ("mean", "median")
        self.how = how
        self.name = f"ensemble_{how}"

    def decide(self, sim, product, day, run_date, *, lead_time, q_star):
        recs = _run_agents(sim, product.id, run_date)
        vals = list(recs.values())
        value = float(np.mean(vals) if self.how == "mean" else np.median(vals))
        return value, {"agents": recs}


# ── AMDIE (production pipeline) and its ablations ────────────────────────────

class AmdiePolicy(Policy):
    family = "amdie"

    def __init__(self, name: str, options: AmdieOptions = AmdieOptions(explain=False), learn: bool = True,
                 service_level: Optional[float] = None):
        self.name = name
        self.options = options
        self.learn = learn
        self.service_level = service_level   # None -> settings.AMDIE_REORDER_SERVICE_LEVEL
        self._decision_ids: Dict[tuple, str] = {}
        self._weights: List[dict] = []
        self._conflicts: List[bool] = []

    def decide(self, sim, product, day, run_date, *, lead_time, q_star):
        from backend.app.api import trigger_decision_internal
        res = trigger_decision_internal(
            tenant_id=sim.tenant_id, product_id=product.id, date_str=run_date.isoformat(),
            decision_type="reorder_quantity", db=sim.db, options=self.options,
        )
        self._decision_ids[(product.id, day)] = res["decision_id"]
        self._weights.append({"day": day, **res["weights"]})
        self._conflicts.append(bool(res["conflict_detected"]))
        return res["fused_recommendation"], {"agents": res["agent_recommendations"]}

    def feedback(self, sim, record):
        if not self.learn:
            return
        from backend.app.amdie import update_reliability_and_logs, check_and_trigger_retraining
        dec_id = self._decision_ids.get((record.product_id, record.day))
        if dec_id:
            update_reliability_and_logs(sim.tenant_id, dec_id, record.q_star, sim.db,
                                        decision_type="reorder_quantity", quantile_level=self.service_level)
            check_and_trigger_retraining(sim.tenant_id, sim.db, decision_type="reorder_quantity",
                                         quantile_level=self.service_level)

    def trace(self, decisions):
        # Mean agent weight per review week, and conflict rate
        by_day = defaultdict(list)
        for w in self._weights:
            by_day[w["day"]].append(w)
        weekly = []
        for d in sorted(by_day):
            rows = by_day[d]
            agents = [k for k in rows[0] if k != "day"]
            weekly.append({"day": d, **{a: float(np.mean([r[a] for r in rows])) for a in agents}})
        return {
            "weights_by_review": weekly,
            "conflict_rate": float(np.mean(self._conflicts)) if self._conflicts else 0.0,
        }


# ── LLM decision-maker baseline (optional; needs an API key) ─────────────────

class LLMPolicy(Policy):
    """
    A single LLM asked for the order quantity from the same information the
    agents see (recent sales, stock, on-order, lead time, price/cost, budget).
    Represents the 'LLM agent as decision maker' approach.

    Provider: EXPERIMENT_LLM_PROVIDER (gemini | anthropic | openai), otherwise the
    first key found among GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY
    (environment or the repo-root .env).  Model: EXPERIMENT_LLM_MODEL.
    Gemini is called through its OpenAI-compatible endpoint.
    """
    MAX_ATTEMPTS = 8
    name = "llm"
    family = "llm"

    def __init__(self, model: Optional[str] = None):
        self.model = model
        self._client = None
        self._provider = None

    def setup(self, sim):
        from backend.app.config import settings
        keys = {
            "gemini": os.getenv("GEMINI_API_KEY") or settings.GEMINI_API_KEY,
            "anthropic": os.getenv("ANTHROPIC_API_KEY") or settings.ANTHROPIC_API_KEY,
            "openai": os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY,
        }
        provider = os.getenv("EXPERIMENT_LLM_PROVIDER") or next((p for p, k in keys.items() if k), None)
        if not provider or not keys.get(provider):
            raise RuntimeError("LLM baseline needs GEMINI_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY")
        model_override = os.getenv("EXPERIMENT_LLM_MODEL")
        if provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=keys["anthropic"])
            self.model = self.model or model_override or "claude-sonnet-5-5"
        else:
            import openai
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/" if provider == "gemini" else None
            import httpx
            # Explicit http_client: openai<1.55 passes `proxies`, which httpx>=0.28 rejects
            self._client = openai.OpenAI(api_key=keys[provider], base_url=base_url, max_retries=0,
                                         http_client=httpx.Client(timeout=120))
            self.model = self.model or model_override or ("gemini-3.8-flash" if provider == "gemini" else "gpt-4o-mini")
        self._provider = provider
        self.calls = 0

    def decide(self, sim, product, day, run_date, *, lead_time, q_star):
        start = run_date - timedelta(days=28)
        rows = sim.db.query(SalesRecord.date, SalesRecord.qty_sold).filter(
            SalesRecord.product_id == product.id, SalesRecord.date >= start, SalesRecord.date < run_date,
        ).all()
        by_day = defaultdict(int)
        for d, q in rows:
            by_day[d] += q
        recent = [by_day.get(start + timedelta(days=k), 0) for k in range(28)]
        prompt = (
            "You manage replenishment for a small retailer. Decide how many units to order now.\n"
            f"Unit price: {product.price:.2f}; unit cost: {product.cost:.2f}; holding cost: "
            f"{sim.cfg.holding_rate_annual:.0%} of cost per year; fixed cost per order: {sim.cfg.order_fixed_cost:.2f}.\n"
            f"Units sold per day over the last 28 days (oldest first; 0 can mean a stock-out): {recent}\n"
            f"On hand: {sim.stock[product.id]}; already on order: {sim.on_order(product.id)}.\n"
            f"Supplier lead time: mean {product.lead_time_mean} days, std dev {product.lead_time_sd:.1f}; "
            f"minimum order quantity {product.moq}.\n"
            f"You review this product again in {sim.cfg.review_period} days. Unmet demand is lost.\n"
            f"Weekly purchase budget shared by {len(sim.inst.products)} products: {sim.inst.weekly_budget:.2f}.\n"
            'Reply with JSON only: {"order_qty": <non-negative integer>, "reason": "<one sentence>"}'
        )
        text = self._complete(prompt)
        match = re.search(r"\{.*\}", text, re.S)
        try:
            qty = float(json.loads(match.group(0))["order_qty"]) if match else 0.0
        except (ValueError, KeyError, TypeError):
            nums = re.findall(r"\d+(?:\.\d+)?", text)
            qty = float(nums[0]) if nums else 0.0
        return qty, {"raw": text[:200]}

    def _complete(self, prompt: str) -> str:
        """Call the model, backing off on rate limits / transient errors."""
        import random
        import time
        for attempt in range(self.MAX_ATTEMPTS):
            try:
                text = self._call(prompt)
                self.calls += 1
                if text.strip():
                    return text
                raise RuntimeError("empty completion")
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                # Bad model name, bad key, bad request: retrying cannot help
                if status is not None and status < 500 and status not in (408, 409, 429):
                    raise RuntimeError(f"LLM call rejected ({status}): {exc}") from exc
                if attempt == self.MAX_ATTEMPTS - 1:
                    raise RuntimeError(f"LLM call failed after {self.MAX_ATTEMPTS} attempts: {exc}") from exc
                time.sleep(min(60.0, 2 ** attempt) + random.random())
        return ""

    def _call(self, prompt: str) -> str:
        if self._provider == "anthropic":
            msg = self._client.messages.create(
                model=self.model, max_tokens=200, messages=[{"role": "user", "content": prompt}],
            )
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        # Generous token budget: Gemini 2.5 models spend output tokens on thinking
        resp = self._client.chat.completions.create(
            model=self.model, messages=[{"role": "user", "content": prompt}], max_tokens=2048,
        )
        return resp.choices[0].message.content or ""


# ── Registry ─────────────────────────────────────────────────────────────────

def _amdie(name, learn=True, **kw):
    return lambda: AmdiePolicy(name, AmdieOptions(explain=False, **kw), learn=learn)


POLICIES = {
    "oracle":                   OraclePolicy,
    "base_stock":               BaseStockPolicy,
    "newsvendor":               NewsvendorPolicy,
    **{f"agent_{a}": (lambda a=a: SingleAgentPolicy(a)) for a in REORDER_AGENTS},
    "ensemble_mean":            lambda: EnsemblePolicy("mean"),
    "ensemble_median":          lambda: EnsemblePolicy("median"),
    "amdie":                    _amdie("amdie"),
    "amdie_static_weights":     _amdie("amdie_static_weights", adaptive_weights=False),
    "amdie_no_lp":              _amdie("amdie_no_lp", lp_fusion=False),
    "amdie_no_divergence":      _amdie("amdie_no_divergence", disabled_weight_terms=frozenset({"divergence"})),
    "amdie_no_context":         _amdie("amdie_no_context", disabled_weight_terms=frozenset({"context_relevance"})),
    "amdie_no_caps":            _amdie("amdie_no_caps", agent_caps=False),
    "amdie_no_learning":        _amdie("amdie_no_learning", learn=False),
    # Pre-tuning AMDIE: flat softmax (T=1) and symmetric outcome scoring
    "amdie_untuned":            lambda: AmdiePolicy("amdie_untuned", AmdieOptions(explain=False, weight_temperature=1.0),
                                                    service_level=0.5),
    "llm":                      LLMPolicy,
}

DEFAULT_POLICIES = [p for p in POLICIES if p != "llm"]


def make_policy(name: str) -> Policy:
    """Registry name, or a parametrised AMDIE variant such as 'amdie[t=0.1,sl=0.9]'
    (t = softmax temperature, sl = reorder service level) used for tuning."""
    m = re.fullmatch(r"(amdie[a-z_]*)\[(.*)\]", name)
    if m:
        base = make_policy(m.group(1))
        params = dict(kv.split("=") for kv in m.group(2).split(",") if kv)
        unknown = set(params) - {"t", "sl"}
        if unknown:
            raise KeyError(f"Unknown AMDIE parameters {sorted(unknown)} in '{name}'")
        opts = base.options
        if "t" in params:
            opts = replace(opts, weight_temperature=float(params["t"]))
        return AmdiePolicy(name, opts, learn=base.learn,
                           service_level=float(params["sl"]) if "sl" in params else base.service_level)
    if name not in POLICIES:
        raise KeyError(f"Unknown policy '{name}'. Available: {sorted(POLICIES)}")
    return POLICIES[name]()
