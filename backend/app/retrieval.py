from contextvars import ContextVar
from datetime import datetime, date, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from backend.app.db import SalesRecord, InventoryState, FinanceLedger, Product
from backend.app.vector_db import vector_db
import json

# Thread-safe ContextVar to log all retrievals during a decision cycle
# Each element will be: {"agent_id": str, "source": "postgres"|"vector"|"graph", "id": str, "details": str}
retrieval_log_var: ContextVar[list] = ContextVar("retrieval_log", default=[])

def get_postgres_context(tenant_id: str, agent_id: str, product_id: str, current_date: date, db: Session):
    """Retrieve recent sales, inventory state, and finance ledger. Logs audit IDs."""
    log = retrieval_log_var.get()

    # 1. Product details
    product = db.query(Product).filter(Product.tenant_id == tenant_id, Product.id == product_id).first()
    if product:
        log.append({
            "agent_id": agent_id,
            "source": "postgres",
            "table": "products",
            "id": product.id,
            "details": f"Price: {product.unit_price}, Cost: {product.unit_cost}"
        })

    # 2. Inventory state
    inv_state = db.query(InventoryState).filter(
        InventoryState.tenant_id == tenant_id,
        InventoryState.product_id == product_id
    ).first()
    if inv_state:
        log.append({
            "agent_id": agent_id,
            "source": "postgres",
            "table": "inventory_states",
            "id": f"{inv_state.tenant_id}:{inv_state.product_id}",
            "details": f"Stock: {inv_state.stock_level}, Reorder: {inv_state.reorder_point}, Lead Time: {inv_state.lead_time_days}"
        })

    # 3. Sales records (past 90 days)
    start_date = current_date - timedelta(days=90)
    sales = db.query(SalesRecord).filter(
        SalesRecord.tenant_id == tenant_id,
        SalesRecord.product_id == product_id,
        SalesRecord.date >= start_date,
        SalesRecord.date <= current_date
    ).all()

    for r in sales:
        log.append({
            "agent_id": agent_id,
            "source": "postgres",
            "table": "sales_records",
            "id": r.id,
            "details": f"Date: {r.date}, Qty: {r.qty_sold}, Price: {r.price}"
        })

    # 4. Finance ledger state for the current period/date
    ledger = db.query(FinanceLedger).filter(
        FinanceLedger.tenant_id == tenant_id,
        FinanceLedger.date == current_date
    ).first()

    # Fallback to the latest ledger if exact date not found
    if not ledger:
        ledger = db.query(FinanceLedger).filter(
            FinanceLedger.tenant_id == tenant_id,
            FinanceLedger.date <= current_date
        ).order_by(FinanceLedger.date.desc()).first()

    if ledger:
        log.append({
            "agent_id": agent_id,
            "source": "postgres",
            "table": "finance_ledgers",
            "id": ledger.id,
            "details": f"Cash Balance: {ledger.cash_balance}, Budget: {ledger.budget_per_period}"
        })

    return {
        "product": product,
        "inventory": inv_state,
        "sales": sales,
        "ledger": ledger
    }

def get_vector_context(tenant_id: str, agent_id: str, product_name: str, category: str, decision_type: str, current_date: date, limit: int = 5):
    """Retrieve semantically relevant chunks from Qdrant/vector db and log IDs."""
    log = retrieval_log_var.get()

    # Build query text based on template
    query_text = f"{decision_type} decision for product {product_name} (category: {category}) on {current_date} for tenant {tenant_id}"

    # Search Vector DB
    hits = vector_db.search_knowledge(tenant_id=tenant_id, query_text=query_text, limit=limit)

    results = []
    for hit in hits:
        payload = hit["payload"]
        log.append({
            "agent_id": agent_id,
            "source": "vector",
            "table": "sme_knowledge",
            "id": hit["id"],
            "details": f"Score: {hit['score']:.4f}, Type: {payload.get('type')}, Content: {payload.get('content')[:100]}"
        })
        results.append({
            "id": hit["id"],
            "score": hit["score"],
            "content": payload.get("content"),
            "type": payload.get("type"),
            "metadata": payload.get("metadata", {})
        })

    return results, query_text


def get_graph_context(
    tenant_id: str,
    agent_id: str,
    query: str,
    db: Session,
    run_date: Optional[date] = None,
) -> list:
    """
    Phase 2: Retrieve relationship-context from the Neo4j knowledge graph.
    Called only by Procurement Agent (Customer Agent deferred to Phase 2b).

    All Cypher queries must filter on tenant_id — this is enforced by the
    graph_db adapter's helper methods.  When raw Cypher is passed directly
    (as the Procurement Agent does for supplier lookups), the caller is
    responsible for embedding tenant_id in the query.

    Logs retrieval in retrieval_log_var identically to the Postgres/vector sources
    so the full audit trail captures all three data sources in one unified log.

    Returns:
        list of dicts (one per matched graph record), or [] when Neo4j is disabled.
    """
    from backend.app.graph_db import graph_db as neo4j

    log = retrieval_log_var.get()

    if not neo4j.enabled:
        # Neo4j disabled — caller falls back to Postgres
        log.append({
            "agent_id": agent_id,
            "source": "graph",
            "table": "neo4j",
            "id": "N/A",
            "details": "Neo4j disabled (NEO4J_ENABLED=false). Falling back to Postgres supplier query."
        })
        return []

    try:
        results = neo4j.run_raw_cypher(query)
        for i, row in enumerate(results):
            log.append({
                "agent_id": agent_id,
                "source": "graph",
                "table": "neo4j",
                "id": f"graph-result-{i}",
                "details": f"Query: {query[:80]}... → {str(row)[:120]}"
            })
        return results
    except Exception as exc:
        log.append({
            "agent_id": agent_id,
            "source": "graph",
            "table": "neo4j",
            "id": "error",
            "details": f"Graph query failed: {exc}"
        })
        return []
