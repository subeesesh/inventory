import numpy as np
import pandas as pd
from datetime import date, timedelta
from statsmodels.tsa.api import ExponentialSmoothing
from sqlalchemy.orm import Session
from backend.app.agents.base import BaseAgent, DecisionObject
from backend.app.retrieval import get_postgres_context, get_vector_context
from backend.app.vector_db import get_embedding, vector_db

class SalesAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="sales")

    def run(self, tenant_id: str, product_id: str, run_date: date, db: Session) -> DecisionObject:
        # Retrieve context from retrieval manager
        context = get_postgres_context(tenant_id, self.agent_id, product_id, run_date, db)
        product = context["product"]
        sales_records = context["sales"]
        inventory = context["inventory"]
        
        unit_price = product.unit_price if product else 10.0
        unit_cost = product.unit_cost if product else 5.0
        lead_time = inventory.lead_time_days if inventory else 5

        # 1. Forecast Demand using Exponential Smoothing or ARIMA
        # Prepare 90-day time series
        end_date = run_date
        start_date = run_date - timedelta(days=90)
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')
        
        # Aggregate sales by day
        sales_by_day = {r.date: r.qty_sold for r in sales_records}
        ts_data = [sales_by_day.get(d.date(), 0) for d in date_range]
        ts = pd.Series(ts_data, index=date_range, dtype=float)

        # Fit model
        forecast_val = 0.0
        std_error = 2.0
        
        try:
            # Fit simple Exponential Smoothing with additive trend
            model = ExponentialSmoothing(ts, trend='add', seasonal=None, initialization_method='estimated')
            fit = model.fit(smoothing_level=0.3, smoothing_trend=0.1, optimized=False)
            # Forecast lead_time days ahead
            forecast = fit.forecast(steps=lead_time)
            forecast_val = max(0.0, float(forecast.sum()))
            # Estimate residuals standard deviation for safety stock and intervals
            residuals = fit.resid
            std_error = float(np.std(residuals)) if len(residuals) > 1 else 2.0
        except Exception:
            # Fallback to simple moving average if fitting fails
            mean_daily = float(ts.mean())
            forecast_val = mean_daily * lead_time
            std_error = float(ts.std()) if len(ts) > 1 else 2.0

        # 2. Recommendation calculation
        # Safety buffer = 1.0 * std_error * sqrt(lead_time)
        safety_buffer = 1.0 * std_error * np.sqrt(lead_time)
        recommendation = max(0.0, round(forecast_val + safety_buffer, 2))

        # 3. Confidence & Risk metrics
        # interval_width is 95% confidence interval width for the lead time forecast
        # error margin = 1.96 * std_error * sqrt(lead_time)
        error_margin = 1.96 * std_error * np.sqrt(lead_time)
        interval_width = error_margin * 2
        
        denom = recommendation if recommendation > 0 else 1.0
        confidence = 1.0 - min(interval_width / (denom * 2), 1.0)
        confidence = max(0.0, min(1.0, float(confidence)))
        risk_score = 1.0 - confidence

        # 4. Priority: week-over-week demand growth rate
        try:
            this_week_sales = sum(ts_data[-7:])
            prev_week_sales = sum(ts_data[-14:-7])
            growth = (this_week_sales - prev_week_sales) / (prev_week_sales + 1.0)
            priority = max(0.0, min(1.0, float((growth + 1.0) / 2.0)))
        except Exception:
            priority = 0.5

        # 5. Expected Cost & Benefit
        expected_cost = recommendation * unit_cost
        expected_benefit = recommendation * unit_price

        # 6. Retrieve Vector DB knowledge to calculate historical similarity
        category = product.category if product else "Electronics"
        prod_name = product.name if product else "Product"
        vector_hits, query_text = get_vector_context(
            tenant_id=tenant_id,
            agent_id=self.agent_id,
            product_name=prod_name,
            category=category,
            decision_type="sales",
            current_date=run_date,
            limit=1
        )
        
        hist_sim = 0.5
        if vector_hits:
            hist_sim = max(0.0, min(1.0, float(vector_hits[0]["score"])))

        return DecisionObject(
            agent_id=self.agent_id,
            recommendation=recommendation,
            reason=f"Sales Agent recommends ordering {recommendation} units based on {lead_time}-day lead time forecast of {forecast_val:.2f} units and safety stock of {safety_buffer:.2f} units.",
            confidence=confidence,
            priority=priority,
            risk_score=risk_score,
            expected_cost=expected_cost,
            expected_benefit=expected_benefit,
            required_resources={"cash": expected_cost},
            historical_similarity=hist_sim
        )
