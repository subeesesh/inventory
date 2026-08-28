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
                    model="gpt-4o-mini",
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
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
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


    def copilot_chat(self, chat_history: list[dict], retrieval_context: str) -> str:
        """
        Copilot chat response generator.
        """
        user_message = chat_history[-1]["content"] if chat_history else ""
        prompt = f"Context:\n{retrieval_context}\n\nUser Question:\n{user_message}"
        prompt = redact_pii(prompt)
        
        if self.provider == "openai" and self.openai_client:
            try:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are the AI Business Control Tower Copilot. Help the SME manager understand their dashboard, decisions, and operations using the provided context. Refer specifically to agent recommendations, weights, and constraints."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"OpenAI copilot failed: {e}")
                
        elif self.provider == "anthropic" and self.anthropic_client:
            try:
                response = self.anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    system="You are the AI Business Control Tower Copilot. Help the SME manager understand their dashboard, decisions, and operations using the provided context. Refer specifically to agent recommendations, weights, and constraints.",
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.content[0].text.strip()
            except Exception as e:
                print(f"Anthropic copilot failed: {e}")

        # Deterministic copilot answers
        if "conflict" in user_message.lower():
            return "Yes, there was a conflict detected between the Inventory agent (which wanted to reorder due to low safety stock) and the Finance agent (which restricted the cash spend). AMDIE resolved this by assigning higher weight to the agent with higher context relevance and running the constrained linear optimization solver."
        elif "budget" in user_message.lower():
            return "The Finance Ledger enforces a strict budget ceiling. Any reorder recommendation that exceeds the cash budget is mathematically capped in the linear programming constraints before solving the utility objective."
        else:
            return "Hello! I am your AI Business Control Tower Copilot. I can explain any past decision, drill down into agent weight scores, highlight inventory metrics, or detail budget constraint boundaries. Ask me about a specific product reorder decision!"

llm_adapter = LLMAdapter()
