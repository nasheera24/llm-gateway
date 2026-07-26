import time
from typing import Dict, Any, Tuple
from enum import Enum

class CircuitState(str, Enum):
    CLOSED = "CLOSED"      # Normal operation: requests pass through
    OPEN = "OPEN"          # Provider failing: fast-fail requests & divert to fallback
    HALF_OPEN = "HALF_OPEN"# Cooldown expired: test 1 probe request to verify recovery

class CircuitBreakerService:
    def __init__(self, failure_threshold: int = 3, recovery_time_sec: float = 10.0):
        self.failure_threshold = failure_threshold
        self.recovery_time_sec = recovery_time_sec
        # Store state per model: {model_name: {"state": CircuitState, "failures": int, "last_state_change": float, "opened_at": float}}
        self._breakers: Dict[str, Dict[str, Any]] = {}
        self._state_logs = []

    def _get_breaker(self, model_name: str) -> Dict[str, Any]:
        if model_name not in self._breakers:
            self._breakers[model_name] = {
                "state": CircuitState.CLOSED,
                "failures": 0,
                "last_state_change": time.time(),
                "opened_at": 0.0
            }
        return self._breakers[model_name]

    def _log_transition(self, model_name: str, old_state: CircuitState, new_state: CircuitState, reason: str):
        log_entry = {
            "timestamp": int(time.time()),
            "model_name": model_name,
            "old_state": old_state.value,
            "new_state": new_state.value,
            "reason": reason
        }
        self._state_logs.append(log_entry)

    def can_execute(self, model_name: str) -> Tuple[bool, CircuitState]:
        breaker = self._get_breaker(model_name)
        now = time.time()
        current_state = breaker["state"]

        if current_state == CircuitState.CLOSED:
            return True, CircuitState.CLOSED

        if current_state == CircuitState.OPEN:
            # Check if cooldown recovery period has passed
            if (now - breaker["opened_at"]) >= self.recovery_time_sec:
                breaker["state"] = CircuitState.HALF_OPEN
                breaker["last_state_change"] = now
                self._log_transition(model_name, CircuitState.OPEN, CircuitState.HALF_OPEN, "Cooldown expired. Probe request allowed.")
                return True, CircuitState.HALF_OPEN
            else:
                return False, CircuitState.OPEN

        if current_state == CircuitState.HALF_OPEN:
            # In half-open state, allow probe request
            return True, CircuitState.HALF_OPEN

        return True, CircuitState.CLOSED

    def record_success(self, model_name: str):
        breaker = self._get_breaker(model_name)
        old_state = breaker["state"]

        breaker["failures"] = 0
        if old_state == CircuitState.HALF_OPEN:
            breaker["state"] = CircuitState.CLOSED
            breaker["last_state_change"] = time.time()
            self._log_transition(model_name, old_state, CircuitState.CLOSED, "Probe request succeeded. Circuit closed.")

    def record_failure(self, model_name: str, reason: str = ""):
        breaker = self._get_breaker(model_name)
        old_state = breaker["state"]
        breaker["failures"] += 1
        now = time.time()

        if old_state == CircuitState.HALF_OPEN:
            # Probe failed in half-open state -> re-open circuit
            breaker["state"] = CircuitState.OPEN
            breaker["opened_at"] = now
            breaker["last_state_change"] = now
            self._log_transition(model_name, old_state, CircuitState.OPEN, f"Probe request failed: {reason}. Re-opening circuit.")

        elif breaker["failures"] >= self.failure_threshold:
            breaker["state"] = CircuitState.OPEN
            breaker["opened_at"] = now
            breaker["last_state_change"] = now
            self._log_transition(model_name, old_state, CircuitState.OPEN, f"Failures ({breaker['failures']}) exceeded threshold ({self.failure_threshold}). Circuit tripped OPEN.")

    def get_status(self) -> Dict[str, Any]:
        return {
            "breakers": {model: data["state"].value for model, data in self._breakers.items()},
            "details": self._breakers,
            "transition_logs": self._state_logs[-20:]  # last 20 transitions
        }

circuit_breaker = CircuitBreakerService()
