"""
Neo4j Knowledge Graph Adapter  (Phase 2 — feature-flagged)
===========================================================
Provides graph-based retrieval for Procurement Agent relationship queries:

    (:Tenant)-[:OWNS]->(:Product)
    (:Supplier)-[:SUPPLIES {lead_time_days, reliability}]->(:Product)
    (:Product)-[:BELONGS_TO]->(:Category)

TENANT ISOLATION: every node carries a `tenant_id` property; every Cypher
query filters on it — same isolation discipline as the Postgres/Qdrant layers.

FEATURE FLAG: when NEO4J_ENABLED=False (default), all graph functions return
empty lists immediately.  The Procurement Agent's `_get_best_supplier()` method
gracefully falls back to the Postgres Supplier table in that case.

SYNC MODEL: the graph is populated/synced via `sync_suppliers_to_graph()` and
`sync_products_to_graph()`, called from the data generator and from the supplier
creation API endpoint.  The graph is a read-through cache / relationship index
— the Postgres tables remain the system of record.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional

from backend.app.config import settings


class Neo4jAdapter:
    """
    Wraps the neo4j Python driver with tenant-scoped helper methods.
    Instantiated lazily so the import succeeds even when neo4j package is not
    installed (falls back gracefully).
    """

    def __init__(self):
        self._driver = None
        self._enabled = settings.NEO4J_ENABLED

        if self._enabled:
            self._connect()

    def _connect(self):
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            )
            print(f"[Neo4j] Connected to {settings.NEO4J_URI}")
        except ImportError:
            print("[Neo4j] neo4j package not installed. Disabling graph context.")
            self._enabled = False
        except Exception as exc:
            print(f"[Neo4j] Connection failed: {exc}. Disabling graph context.")
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled and self._driver is not None

    def close(self):
        if self._driver:
            self._driver.close()

    # ── Schema initialisation ─────────────────────────────────────────────

    def init_schema(self):
        """Create uniqueness constraints and indexes.  Idempotent."""
        if not self.enabled:
            return
        with self._driver.session() as session:
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Tenant) REQUIRE t.id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Product) REQUIRE (p.id, p.tenant_id) IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Supplier) REQUIRE (s.id, s.tenant_id) IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE"
            )

    # ── Sync helpers (called from generator + API) ────────────────────────

    def sync_products_to_graph(self, tenant_id: str, products: list):
        """Upsert Product and Category nodes and Tenant->Product edges."""
        if not self.enabled:
            return
        with self._driver.session() as session:
            for p in products:
                session.run(
                    """
                    MERGE (t:Tenant {id: $tenant_id})
                    MERGE (c:Category {name: $category})
                    MERGE (p:Product {id: $product_id, tenant_id: $tenant_id})
                      ON CREATE SET p.name = $name, p.unit_price = $unit_price
                      ON MATCH  SET p.name = $name, p.unit_price = $unit_price
                    MERGE (t)-[:OWNS]->(p)
                    MERGE (p)-[:BELONGS_TO]->(c)
                    """,
                    tenant_id=tenant_id,
                    product_id=p.id,
                    name=p.name,
                    category=p.category,
                    unit_price=p.unit_price,
                )

    def sync_supplier_to_graph(self, tenant_id: str, supplier) -> None:
        """Upsert a Supplier node and Supplier->Product SUPPLIES edge."""
        if not self.enabled:
            return
        with self._driver.session() as session:
            session.run(
                """
                MERGE (s:Supplier {id: $supplier_id, tenant_id: $tenant_id})
                  ON CREATE SET
                    s.name               = $name,
                    s.avg_lead_time_days = $avg_lead_time_days,
                    s.lead_time_std_dev  = $lead_time_std_dev,
                    s.reliability_score  = $reliability_score,
                    s.min_order_qty      = $min_order_qty
                  ON MATCH SET
                    s.name               = $name,
                    s.avg_lead_time_days = $avg_lead_time_days,
                    s.lead_time_std_dev  = $lead_time_std_dev,
                    s.reliability_score  = $reliability_score,
                    s.min_order_qty      = $min_order_qty
                WITH s
                MATCH (p:Product {id: $product_id, tenant_id: $tenant_id})
                MERGE (s)-[r:SUPPLIES]->(p)
                  ON CREATE SET r.lead_time_days = $avg_lead_time_days,
                                r.reliability    = $reliability_score
                  ON MATCH  SET r.lead_time_days = $avg_lead_time_days,
                                r.reliability    = $reliability_score
                """,
                supplier_id=supplier.id,
                tenant_id=tenant_id,
                product_id=supplier.product_id,
                name=supplier.name,
                avg_lead_time_days=supplier.avg_lead_time_days,
                lead_time_std_dev=supplier.lead_time_std_dev,
                reliability_score=supplier.reliability_score,
                min_order_qty=supplier.min_order_qty,
            )

    # ── Query helpers (called by Procurement Agent via retrieval.py) ──────

    def get_suppliers_for_product(
        self, tenant_id: str, product_id: str
    ) -> List[Dict[str, Any]]:
        """
        Return all suppliers for a product as plain dicts, tenant-scoped.
        Cypher filters on tenant_id on BOTH Supplier and Product nodes.
        """
        if not self.enabled:
            return []
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (s:Supplier {tenant_id: $tenant_id})
                      -[:SUPPLIES]->
                      (p:Product {id: $product_id, tenant_id: $tenant_id})
                RETURN s.id               AS id,
                       s.name             AS name,
                       s.avg_lead_time_days AS avg_lead_time_days,
                       s.lead_time_std_dev  AS lead_time_std_dev,
                       s.reliability_score  AS reliability_score,
                       s.min_order_qty      AS min_order_qty
                ORDER BY s.reliability_score DESC
                """,
                tenant_id=tenant_id,
                product_id=product_id,
            )
            return [dict(record) for record in result]

    def get_category_peers(
        self, tenant_id: str, product_id: str
    ) -> List[Dict[str, Any]]:
        """
        Return other products in the same category (peer comparison context).
        """
        if not self.enabled:
            return []
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (p:Product {id: $product_id, tenant_id: $tenant_id})
                      -[:BELONGS_TO]->(c:Category)
                      <-[:BELONGS_TO]-(peer:Product {tenant_id: $tenant_id})
                WHERE peer.id <> $product_id
                RETURN peer.id AS product_id, peer.name AS name,
                       peer.unit_price AS unit_price, c.name AS category
                LIMIT 10
                """,
                tenant_id=tenant_id,
                product_id=product_id,
            )
            return [dict(record) for record in result]

    def run_raw_cypher(
        self, cypher: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute an arbitrary read-only Cypher query.  Used by get_graph_context()
        in retrieval.py when the Procurement Agent passes a custom query string.
        """
        if not self.enabled:
            return []
        with self._driver.session() as session:
            result = session.run(cypher, **(params or {}))
            return [dict(record) for record in result]


# Singleton instance — created once at import time
graph_db = Neo4jAdapter()
