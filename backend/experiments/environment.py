"""
Simulation environment for the replenishment experiments.

A seeded synthetic SME with known ground-truth demand and supplier lead times.
Every policy is run on its own fresh in-memory copy of the *same* instance
(common random numbers), so differences between policies are paired.

Timeline per simulated day d (periodic review every R days):
  1. Purchase orders whose lead time has elapsed arrive (stock += qty, PO "received").
  2. On review days, the policy decides an order quantity for each product.
     Orders are paid on placement and truncated to the remaining weekly
     purchase budget and to available cash (a hard real-world constraint the
     policy may or may not anticipate).  Orders are written as PurchaseOrders,
     so agents see them as on-order stock.
  3. True demand is realised; sales = min(stock, demand), the excess is lost.
     Only the censored sales are written to SalesRecord, as a real POS would.
  4. Holding cost accrues on end-of-day stock; a FinanceLedger row is written.

The decision-quality reference for an order placed on day d with realised lead
time L is the perfect-information order-up-to quantity
    q* = max(0, true demand over [d, d + L + R) - inventory position at d).
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import (
    Base, Tenant, Product, InventoryState, SalesRecord, FinanceLedger,
    Supplier, SupplierProfile, PurchaseOrder, PurchaseOrderItem,
)

TENANT_ID = "exp-tenant"
_SAFETY_Z = 1.65   # service level an owner would use to set the reorder point


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    budget_factor: float            # weekly purchase budget / expected weekly cost of goods
    demand_cv: tuple                # range of per-product demand noise coefficient of variation
    shock_prob: float               # probability a product experiences a demand shock in the test window
    lead_time_sd_scale: float       # multiplier on supplier lead-time standard deviation
    unreliable_frac: float          # fraction of suppliers with a late-delivery tail


SCENARIOS: Dict[str, Scenario] = {
    "baseline": Scenario(
        "baseline", "Adequate purchase budget, moderate demand noise, reliable suppliers",
        budget_factor=1.5, demand_cv=(0.2, 0.4), shock_prob=0.0, lead_time_sd_scale=1.0, unreliable_frac=0.0,
    ),
    "tight_budget": Scenario(
        "tight_budget", "Weekly purchase budget below expected cost of goods (cash-constrained SME)",
        budget_factor=0.8, demand_cv=(0.2, 0.4), shock_prob=0.0, lead_time_sd_scale=1.0, unreliable_frac=0.0,
    ),
    "volatile": Scenario(
        "volatile", "High demand noise, demand surges/drops and unreliable suppliers",
        budget_factor=1.5, demand_cv=(0.4, 0.7), shock_prob=0.5, lead_time_sd_scale=2.0, unreliable_frac=0.3,
    ),
}


@dataclass(frozen=True)
class ExperimentConfig:
    n_products: int = 8
    history_days: int = 120
    horizon_days: int = 140            # 20 weekly review cycles
    review_period: int = 7
    holding_rate_annual: float = 0.25  # holding cost as a fraction of unit cost per year
    order_fixed_cost: float = 15.0     # per purchase order line
    start_date: date = date(2025, 1, 6)


@dataclass
class ProductSpec:
    id: str
    price: float
    cost: float
    base_demand: float
    demand_cv: float
    lead_time_mean: int
    lead_time_sd: float
    reliability: float
    moq: int
    category: str


@dataclass
class ProblemInstance:
    seed: int
    scenario: Scenario
    config: ExperimentConfig
    products: List[ProductSpec]
    demand: np.ndarray            # [n_products, history + horizon + tail] true daily demand
    lead_times: np.ndarray        # [n_products, n_reviews] realised lead time of each review's order
    weekly_budget: float
    initial_cash: float

    @classmethod
    def generate(cls, seed: int, scenario: Scenario, config: ExperimentConfig) -> "ProblemInstance":
        rng = np.random.default_rng(seed)
        n = config.n_products
        tail = 60  # demand beyond the horizon, for the decision-quality reference
        total_days = config.history_days + config.horizon_days + tail
        n_reviews = math.ceil(config.horizon_days / config.review_period)

        products: List[ProductSpec] = []
        demand = np.zeros((n, total_days))
        lead_times = np.zeros((n, n_reviews), dtype=int)
        categories = ["Electronics", "Office Supply", "Industrial", "Consumer Goods"]

        for i in range(n):
            price = round(float(rng.uniform(15, 120)), 2)
            cost = round(price * float(rng.uniform(0.4, 0.6)), 2)
            base = float(rng.uniform(4, 20))
            cv = float(rng.uniform(*scenario.demand_cv))
            trend = float(rng.uniform(-0.1, 0.3))            # per year
            yearly_amp = float(rng.uniform(0.1, 0.35))
            phase = float(rng.uniform(0, 2 * math.pi))

            t = np.arange(total_days)
            mean = (
                base
                * (1 + trend * t / 365)
                * (1 + 0.25 * np.sin(2 * math.pi * t / 7))
                * (1 + yearly_amp * np.sin(2 * math.pi * t / 365 + phase))
            )
            if rng.random() < scenario.shock_prob:
                start = config.history_days + int(rng.integers(0, max(config.horizon_days - 21, 1)))
                factor = float(rng.uniform(1.6, 2.2)) if rng.random() < 0.6 else float(rng.uniform(0.4, 0.6))
                mean[start:start + 21] *= factor
            demand[i] = np.maximum(0, np.round(rng.normal(mean, cv * mean)))

            lt_mean = int(rng.choice([3, 5, 7, 10]))
            lt_sd = float(rng.uniform(0.5, 2.0)) * scenario.lead_time_sd_scale
            unreliable = rng.random() < scenario.unreliable_frac
            reliability = float(rng.uniform(0.6, 0.75)) if unreliable else float(rng.uniform(0.8, 0.98))
            lts = np.maximum(1, np.round(rng.normal(lt_mean, lt_sd, n_reviews))).astype(int)
            if unreliable:
                late = rng.random(n_reviews) < 0.25
                lts = lts + late * rng.integers(3, 8, n_reviews)
            lead_times[i] = lts

            products.append(ProductSpec(
                id=f"P{i + 1:02d}", price=price, cost=cost, base_demand=base, demand_cv=cv,
                lead_time_mean=lt_mean, lead_time_sd=lt_sd, reliability=reliability,
                moq=int(rng.choice([5, 10, 20])), category=categories[i % len(categories)],
            ))

        expected_weekly_cogs = sum(p.base_demand * p.cost * 7 for p in products)
        weekly_budget = round(scenario.budget_factor * expected_weekly_cogs, 2)
        return cls(
            seed=seed, scenario=scenario, config=config, products=products,
            demand=demand, lead_times=lead_times,
            weekly_budget=weekly_budget, initial_cash=round(4 * weekly_budget, 2),
        )


@dataclass
class DecisionRecord:
    product_id: str
    day: int
    requested: float
    placed: int
    position: int
    lead_time: int
    q_star: float
    truncated: bool
    meta: dict = field(default_factory=dict)


class Simulator:
    def __init__(self, instance: ProblemInstance):
        self.inst = instance
        self.cfg = instance.config
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False)()
        self.tenant_id = TENANT_ID
        self.stock: Dict[str, int] = {}
        self.pipeline: List[dict] = []   # {product_id, qty, arrive_day, po_id}
        self.cash = instance.initial_cash
        self._seed_database()

    # ── Setup ───────────────────────────────────────────────────────────────
    def date_of(self, day: int) -> date:
        """Calendar date of simulation day `day` (day 0 = first test day)."""
        return self.cfg.start_date + timedelta(days=self.cfg.history_days + day)

    def _seed_database(self) -> None:
        inst, cfg, db = self.inst, self.cfg, self.db
        db.add(Tenant(id=self.tenant_id, name="Experiment SME", api_key_hash=f"exp-{uuid.uuid4()}",
                      business_goal="maximize_profit"))
        for i, p in enumerate(inst.products):
            prod = Product(id=p.id, tenant_id=self.tenant_id, name=f"Item {p.id}", category=p.category,
                           unit_price=p.price, warehouse_capacity_limit=None, min_stock=0)
            prod.unit_cost = p.cost
            db.add(prod)
            protection = p.lead_time_mean
            mu = p.base_demand
            reorder_point = int(round(mu * protection + _SAFETY_Z * p.demand_cv * mu * math.sqrt(protection)))
            initial = int(round(mu * (p.lead_time_mean + cfg.review_period)))
            self.stock[p.id] = initial
            db.add(InventoryState(product_id=p.id, tenant_id=self.tenant_id, stock_level=initial,
                                  lead_time_days=p.lead_time_mean, reorder_point=reorder_point))
            db.add(Supplier(tenant_id=self.tenant_id, product_id=p.id, name=f"Supplier {p.id}",
                            avg_lead_time_days=float(p.lead_time_mean), lead_time_std_dev=p.lead_time_sd,
                            reliability_score=p.reliability, min_order_qty=p.moq,
                            supplier_profile_id=f"SP-{p.id}"))
            db.add(SupplierProfile(id=f"SP-{p.id}", tenant_id=self.tenant_id, name=f"Supplier {p.id}"))

            # Uncensored sales history (the business was adequately stocked before the test window)
            for d in range(cfg.history_days):
                qty = int(inst.demand[i, d])
                if qty > 0:
                    db.add(SalesRecord(tenant_id=self.tenant_id, product_id=p.id, qty_sold=qty,
                                       price=p.price, date=cfg.start_date + timedelta(days=d)))
        for d in range(cfg.history_days):
            ledger = FinanceLedger(tenant_id=self.tenant_id, date=cfg.start_date + timedelta(days=d))
            ledger.cash_balance = self.cash
            ledger.budget_per_period = inst.weekly_budget
            db.add(ledger)
        db.commit()

    # ── State helpers ───────────────────────────────────────────────────────
    def on_order(self, product_id: str) -> int:
        return sum(o["qty"] for o in self.pipeline if o["product_id"] == product_id)

    def position(self, product_id: str) -> int:
        return self.stock[product_id] + self.on_order(product_id)

    def product_index(self, product_id: str) -> int:
        return next(i for i, p in enumerate(self.inst.products) if p.id == product_id)

    def true_demand(self, product_id: str, day: int, days: int) -> float:
        i = self.product_index(product_id)
        start = self.cfg.history_days + day
        return float(self.inst.demand[i, start:start + days].sum())

    def _place_order(self, p: ProductSpec, qty: int, day: int, lead_time: int) -> None:
        po = PurchaseOrder(id=str(uuid.uuid4()), tenant_id=self.tenant_id,
                           supplier_profile_id=f"SP-{p.id}", status="ordered")
        self.db.add(po)
        self.db.add(PurchaseOrderItem(po_id=po.id, product_id=p.id, qty=qty, unit_cost=p.cost))
        self.pipeline.append({"product_id": p.id, "qty": qty, "arrive_day": day + lead_time, "po_id": po.id})

    # ── Main loop ───────────────────────────────────────────────────────────
    def run(self, policy) -> dict:
        inst, cfg, db = self.inst, self.cfg, self.db
        R = cfg.review_period
        daily_holding = cfg.holding_rate_annual / 365.0
        policy.setup(self)

        initial_value = sum(self.stock[p.id] * p.cost for p in inst.products)
        per_product = {p.id: {"revenue": 0.0, "purchases": 0.0, "holding": 0.0, "order_costs": 0.0,
                              "demand": 0.0, "sold": 0.0, "stockout_days": 0} for p in inst.products}
        decisions: List[DecisionRecord] = []
        pending_feedback: List[DecisionRecord] = []
        inventory_value_sum = 0.0
        t0 = time.perf_counter()

        for day in range(cfg.horizon_days):
            run_date = self.date_of(day)

            # 1. Arrivals
            arrived = [o for o in self.pipeline if o["arrive_day"] <= day]
            for o in arrived:
                self.stock[o["product_id"]] += o["qty"]
                db.query(PurchaseOrder).filter_by(id=o["po_id"]).update({"status": "received"})
            self.pipeline = [o for o in self.pipeline if o["arrive_day"] > day]
            if arrived:
                self._sync_stock()

            # 2. Periodic review
            if day % R == 0:
                review_idx = day // R
                budget_left = inst.weekly_budget
                for i, p in enumerate(inst.products):
                    position = self.position(p.id)
                    lead_time = int(inst.lead_times[i, review_idx])
                    q_star = max(0.0, self.true_demand(p.id, day, lead_time + R) - position)
                    requested, meta = policy.decide(self, p, day, run_date, lead_time=lead_time, q_star=q_star)
                    requested = max(0.0, float(requested))
                    want = int(round(requested))
                    affordable = int(max(0.0, min(budget_left, self.cash - cfg.order_fixed_cost)) // p.cost)
                    placed = min(want, affordable)
                    if placed > 0:
                        self._place_order(p, placed, day, lead_time)
                        spend = placed * p.cost
                        budget_left -= spend
                        self.cash -= spend + cfg.order_fixed_cost
                        per_product[p.id]["purchases"] += spend
                        per_product[p.id]["order_costs"] += cfg.order_fixed_cost
                    rec = DecisionRecord(p.id, day, requested, placed, position, lead_time, q_star,
                                         truncated=placed < want, meta=meta)
                    decisions.append(rec)
                    pending_feedback.append(rec)
                db.commit()

            # Delayed outcome feedback once a decision's protection interval has elapsed
            ready = [r for r in pending_feedback if r.day + r.lead_time + R <= day]
            for r in ready:
                policy.feedback(self, r)
            pending_feedback = [r for r in pending_feedback if r.day + r.lead_time + R > day]

            # 3. Demand realisation
            for i, p in enumerate(inst.products):
                dem = int(inst.demand[i, cfg.history_days + day])
                sold = min(self.stock[p.id], dem)
                self.stock[p.id] -= sold
                pp = per_product[p.id]
                pp["demand"] += dem
                pp["sold"] += sold
                pp["revenue"] += sold * p.price
                pp["stockout_days"] += int(dem > sold)
                self.cash += sold * p.price
                if sold > 0:
                    db.add(SalesRecord(tenant_id=self.tenant_id, product_id=p.id, qty_sold=sold,
                                       price=p.price, date=run_date))

            # 4. Holding cost + ledger
            for p in inst.products:
                h = self.stock[p.id] * p.cost * daily_holding
                per_product[p.id]["holding"] += h
                self.cash -= h
            inventory_value_sum += sum(self.stock[p.id] * p.cost for p in inst.products)
            self._sync_stock()
            ledger = FinanceLedger(tenant_id=self.tenant_id, date=run_date)
            ledger.cash_balance = self.cash
            ledger.budget_per_period = inst.weekly_budget
            db.add(ledger)
            db.commit()

        runtime = time.perf_counter() - t0
        return self._summarise(policy, per_product, decisions, initial_value, inventory_value_sum, runtime)

    def _sync_stock(self) -> None:
        for pid, qty in self.stock.items():
            self.db.query(InventoryState).filter_by(product_id=pid).update({"stock_level": int(qty)})

    def _summarise(self, policy, per_product, decisions, initial_value, inventory_value_sum, runtime) -> dict:
        inst, cfg = self.inst, self.cfg
        for p in inst.products:
            pp = per_product[p.id]
            ending_value = (self.stock[p.id] + self.on_order(p.id)) * p.cost
            start_value = round(p.base_demand * (p.lead_time_mean + cfg.review_period)) * p.cost
            pp["profit"] = (pp["revenue"] - pp["purchases"] - pp["holding"] - pp["order_costs"]
                            + ending_value - start_value)
            pp["fill_rate"] = pp["sold"] / pp["demand"] if pp["demand"] else 1.0

        tot = lambda k: sum(pp[k] for pp in per_product.values())  # noqa: E731
        ordering = [d for d in decisions if d.requested >= 0.5]
        q_star_total = sum(d.q_star for d in decisions)
        metrics = {
            "profit": tot("profit"),
            "revenue": tot("revenue"),
            "purchases": tot("purchases"),
            "holding_cost": tot("holding"),
            "order_costs": tot("order_costs"),
            "fill_rate": tot("sold") / max(tot("demand"), 1.0),
            "stockout_rate": tot("stockout_days") / (len(inst.products) * cfg.horizon_days),
            "avg_inventory_value": inventory_value_sum / cfg.horizon_days,
            "n_orders": sum(1 for d in decisions if d.placed > 0),
            "truncation_rate": sum(1 for d in ordering if d.truncated) / max(len(ordering), 1),
            "decision_mae": float(np.mean([abs(d.placed - d.q_star) for d in decisions])),
            "decision_wape": sum(abs(d.placed - d.q_star) for d in decisions) / max(q_star_total, 1.0),
            "runtime_s": runtime,
            "n_decisions": len(decisions),
        }
        return {
            "scenario": inst.scenario.name,
            "seed": inst.seed,
            "policy": policy.name,
            "metrics": metrics,
            "per_product": {pid: {k: pp[k] for k in ("profit", "fill_rate", "revenue")}
                            for pid, pp in per_product.items()},
            "trace": policy.trace(decisions),
            "weekly_budget": inst.weekly_budget,
            "config": asdict(cfg) | {"start_date": str(cfg.start_date)},
        }
