import os
import yaml
import redis
from typing import Dict, Any, Tuple, Optional

class BudgetService:
    def __init__(self, pricing_path: str = "config/model_pricing.yaml", redis_url: Optional[str] = None):
        self.pricing_path = pricing_path
        self.pricing_table: Dict[str, Dict[str, float]] = {}
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = None
        self._in_memory_spend: Dict[str, float] = {}
        self.load_pricing()
        self._init_redis()

    def load_pricing(self):
        if os.path.exists(self.pricing_path):
            with open(self.pricing_path, "r") as f:
                data = yaml.safe_load(f) or {}
                self.pricing_table = data.get("models", {})

    def _init_redis(self):
        try:
            client = redis.Redis.from_url(self.redis_url, socket_timeout=1.0, decode_responses=True)
            client.ping()
            self.redis_client = client
        except Exception:
            self.redis_client = None

    def calculate_request_cost(self, model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
        pricing = self.pricing_table.get(model_name.lower(), {})
        input_price = pricing.get("input_price_per_1k", 0.0015)
        output_price = pricing.get("output_price_per_1k", 0.0020)

        input_cost = (prompt_tokens / 1000.0) * input_price
        output_cost = (completion_tokens / 1000.0) * output_price
        return round(input_cost + output_cost, 6)

    def record_spend(self, team_id: str, cost: float) -> float:
        redis_key = f"spend:{team_id}:monthly"
        if self.redis_client:
            try:
                new_spend = self.redis_client.incrbyfloat(redis_key, cost)
                return round(float(new_spend), 4)
            except Exception:
                pass

        current = self._in_memory_spend.get(team_id, 0.0)
        new_spend = current + cost
        self._in_memory_spend[team_id] = new_spend
        return round(new_spend, 4)

    def get_team_spend(self, team_id: str) -> float:
        redis_key = f"spend:{team_id}:monthly"
        if self.redis_client:
            try:
                val = self.redis_client.get(redis_key)
                return round(float(val), 4) if val else 0.0
            except Exception:
                pass

        return round(self._in_memory_spend.get(team_id, 0.0), 4)

    def check_budget_status(self, team_id: str, monthly_budget: float) -> Tuple[bool, float, float, bool]:
        """
        Returns: (can_proceed: bool, current_spend: float, spend_percent: float, warning_flag: bool)
        """
        current_spend = self.get_team_spend(team_id)
        spend_percent = (current_spend / monthly_budget * 100.0) if monthly_budget > 0 else 0.0
        
        warning_flag = spend_percent >= 80.0
        can_proceed = spend_percent < 100.0

        return can_proceed, current_spend, round(spend_percent, 2), warning_flag

budget_service = BudgetService()
