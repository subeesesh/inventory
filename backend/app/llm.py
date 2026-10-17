import json
import importlib
from backend.app.config import settings
from backend.app.security import redact_pii

class LLMAdapter:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()
        self.openai_client = None
        self.anthropic_client = None
        
        if self.provider == "openai" and settings.OPENAI_API_KEY:
            try:
                openai_mod = importlib.import_module("openai")
                OpenAI = getattr(openai_mod, "OpenAI")
                self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
            except Exception:
                print("OpenAI SDK not installed. Falling back to Mock LLM.")
                self.provider = "mock"
                
        elif self.provider == "anthropic" and settings.ANTHROPIC_API_KEY:
            try:
                anthropic_mod = importlib.import_module("anthropic")
                Anthropic = getattr(anthropic_mod, "Anthropic")
                self.anthropic_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            except Exception:
                print("Anthropic SDK not installed. Falling back to Mock LLM.")
                self.provider = "mock"


    def generate_explanation(self, decision_summary_dict: dict) -> str:
        """
        Generates a natural language explanation of the multi-agent decision trace.
        Redacts PII prior to calling remote APIs.
        """
        # Formulate prompt using the decision summary
        raw_prompt = (
            f"Generate a clear, detailed, executive-level explanation for a business decision based on this trace:\n"
            f"{json.dumps(decision_summary_dict, indent=2)}"
        )
        
        # Redact PII (e.g. raw cash balances, cost values, etc.)
        prompt = redact_pii(raw_prompt)

        if self.provider == "openai" and self.openai_client:
            try:
                response = self.openai_client.chat.completions.create(
                    model=settings.OPENAI_MODEL_NAME,
                    messages=[
                        {"role": "system", "content": "You are a professional business advisor. Explain the decision based strictly on the provided multi-agent audit trace."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"OpenAI completion failed: {e}. Falling back to Mock NLG.")

        elif self.provider == "anthropic" and self.anthropic_client:
            try:
                response = self.anthropic_client.messages.create(
                    model=settings.ANTHROPIC_MODEL_NAME,
                    max_tokens=settings.LLM_MAX_TOKENS,
                    system="You are a professional business advisor. Explain the decision based strictly on the provided multi-agent audit trace.",
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.content[0].text.strip()
            except Exception as e:
                print(f"Anthropic completion failed: {e}. Falling back to Mock NLG.")

        # Default High-Quality Deterministic NLG
        return self._generate_mock_explanation(decision_summary_dict)

    def _generate_mock_explanation(self, summary: dict) -> str:
        date = summary.get("date")
        prod = summary.get("product_id")
        goal = summary.get("business_goal")
        dt = summary.get("decision_type", "reorder_quantity")
        conflict_detected = summary.get("conflict_detected", False)
        conflict_score = summary.get("conflict_score", 0.0)
        fused_rec = summary.get("fused_recommendation", 0.0)
        weights = summary.get("weights", {})
        decisions = summary.get("agent_decisions", {})

        if dt == "price_adjustment":
            rec_text = f"price adjustment of **{fused_rec:+.2f}**"
        elif dt == "promotion_trigger":
            rec_text = f"promotional discount depth of **{fused_rec:.1%}**"
        elif dt == "staffing_adjustment":
            rec_text = f"staffing change of **{fused_rec:+.1f} hours**"
        elif dt == "customer_retention_action":
            rec_text = f"customer retention level of **{fused_rec:.1%}**"
        else:
            rec_text = f"order quantity recommendation of **{fused_rec:.1f} units**"

        exp = (
            f"### Decision Executive Summary ({date})\n\n"
            f"Domain: **{dt.replace('_', ' ').title()}** | Product SKU: **{prod}** | Goal: **'{goal}'**\n\n"
            f"Final fused resolution: {rec_text}.\n\n"
            f"#### Conflict & Negotiation Status:\n"
        )
        if conflict_detected:
            exp += f"- **Divergence Detected!** (Divergence score: **{conflict_score:.2f}** > threshold 0.30).\n"
        else:
            exp += f"- **Aligned Assessment** (Divergence score: **{conflict_score:.2f}** <= threshold 0.30).\n"

        for aid, d in decisions.items():
            r = d.get("recommendation", 0.0)
            if dt == "price_adjustment":
                val_str = f"{r:+.2f} price delta"
            elif dt == "promotion_trigger":
                val_str = f"{r:.1%} discount"
            elif dt == "staffing_adjustment":
                val_str = f"{r:+.1f} hours"
            elif dt == "customer_retention_action":
                val_str = f"{r:.1%} retention level"
            else:
                val_str = f"{r:.1f} units"
            exp += f"  * **{aid.title()} Agent**: suggested {val_str} (Confidence: {d.get('confidence', 0.8):.2f}, Risk: {d.get('risk_score', 0.1):.2f})\n"

        exp += f"\n#### Adaptive Weight Allocation:\n"
        for aid, w in weights.items():
            exp += f"- **{aid.title()} Agent**: {w:.1%} weight share\n"

        if summary.get("overall_risk_score") is not None:
            exp += f"\n- **Risk Agent Modifier**: Portfolio risk index evaluated at {summary.get('overall_risk_score'):.2f}, scaling safety buffer.\n"

        exp += (
            f"\n#### Resolution Logic:\n"
            f"The Constrained LP Optimization Solver balanced domain utilities against operational limits, achieving optimal multi-stakeholder utility."
        )
        return exp


    def copilot_chat(self, chat_history: list[dict], retrieval_context: str, facts: dict | None = None) -> str:
        """
        Copilot chat response generator (§III-I).
        `retrieval_context` is the text grounding sent to a remote LLM; `facts`
        is the same state in structured form, used by the offline fallback.
        """
        user_message = chat_history[-1]["content"] if chat_history else ""
        prompt = f"Context:\n{retrieval_context}\n\nUser Question:\n{user_message}"
        prompt = redact_pii(prompt)
        
        if self.provider == "openai" and self.openai_client:
            try:
                response = self.openai_client.chat.completions.create(
                    model=settings.OPENAI_MODEL_NAME,
                    messages=[
                        {"role": "system", "content": _COPILOT_SYSTEM},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"OpenAI copilot failed: {e}")
                
        elif self.provider == "anthropic" and self.anthropic_client:
            try:
                response = self.anthropic_client.messages.create(
                    model=settings.ANTHROPIC_MODEL_NAME,
                    max_tokens=settings.LLM_MAX_TOKENS,
                    system=_COPILOT_SYSTEM,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.content[0].text.strip()
            except Exception as e:
                print(f"Anthropic copilot failed: {e}")

        return _offline_copilot_answer(user_message, facts or {})


_COPILOT_SYSTEM = (
    "You are the AI Business Control Tower Copilot. Help the SME owner understand their "
    "business state, alerts, forecasts and AMDIE decisions using only the provided context. "
    "Refer specifically to agent recommendations, weights and constraints, and suggest a "
    "concrete follow-up action where one makes sense."
)


def _offline_copilot_answer(message: str, facts: dict) -> str:
    """Deterministic, data-grounded answers used when no LLM provider is configured."""
    msg = message.lower()
    twin = facts.get("twin", {})
    events = facts.get("open_events", [])
    pending = facts.get("pending_actions", [])
    decisions = facts.get("recent_decisions", [])
    finance = twin.get("finance", {})
    outlook = twin.get("outlook_30d", {})
    low_stock = [p for p in twin.get("inventory", []) if p.get("low_stock")]

    def has(*words):
        return any(w in msg for w in words)

    if has("alert", "risk", "anomal", "event", "monitor", "wrong", "attention"):
        if not events and not pending:
            return f"No open alerts. Overall risk level is {twin.get('risk_level', 0):.2f}."
        lines = [f"There are {len(events)} open alert(s) (risk level {twin.get('risk_level', 0):.2f}):"]
        lines += [f"- {e['severity']}: {e['event_type'].replace('_', ' ')} ({e['entity_type']} {e['entity_id']})" for e in events[:6]]
        if pending:
            lines.append(f"{len(pending)} automated action(s) are waiting for your review on the dashboard.")
        return "\n".join(lines)

    if has("stock", "inventory", "reorder"):
        if not low_stock:
            return "All active products are above their minimum stock level."
        lines = [f"{len(low_stock)} product(s) are at or below minimum stock:"]
        lines += [f"- {p['name']}: {p['stock_level']} on hand (min {p['min_stock']})" for p in low_stock[:8]]
        lines.append("Run a reorder_quantity analysis on these to get an AMDIE-fused order quantity.")
        return "\n".join(lines)

    if has("cash", "budget", "money", "finance"):
        return (
            f"Cash balance is {finance.get('cash_balance', 0):,.2f} against a period budget of "
            f"{finance.get('period_budget', 0):,.2f}. Over the next 30 days the projected net cash flow is "
            f"{outlook.get('net_cash_flow', 0):+,.2f}, ending near {outlook.get('projected_cash', 0):,.2f}. "
            "Reorder recommendations are capped by the budget inside the AMDIE optimiser."
        )

    if has("forecast", "revenue", "sales", "predict"):
        s30 = twin.get("sales_30d", {})
        return (
            f"Last 30 days: {s30.get('total_units', 0)} units sold for {s30.get('total_revenue', 0):,.2f}. "
            f"Projected revenue for the next 30 days is {outlook.get('projected_revenue', 0):,.2f}."
        )

    if has("conflict", "decision", "why", "explain", "recommend"):
        if not decisions:
            return "No AMDIE decisions have been made yet. Trigger one from the dashboard."
        d = decisions[0]
        conflict = (
            f"Agents disagreed (conflict score {d['conflict_score']:.2f}), so AMDIE weighted them by "
            "reliability, confidence and context relevance and solved the constrained optimisation."
            if d["conflict_detected"] else "Agents were broadly aligned."
        )
        return (
            f"Latest decision: {d['decision_type'].replace('_', ' ')} for {d['product_id']} on {d['date']} "
            f"-> {d['fused_recommendation']:.2f}. {conflict} Open it on the dashboard for the per-agent breakdown."
        )

    return (
        f"{twin.get('business_name', 'Your business')} at a glance: {len(events)} open alert(s), "
        f"{len(low_stock)} low-stock product(s), cash {finance.get('cash_balance', 0):,.2f}, "
        f"risk level {twin.get('risk_level', 0):.2f}. Ask me about alerts, stock, cash, forecasts or a decision."
    )


llm_adapter = LLMAdapter()
