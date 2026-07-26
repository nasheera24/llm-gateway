import time
from typing import List, Dict, Any

class AuditService:
    def __init__(self):
        self._audit_logs: List[Dict[str, Any]] = []

    def log_change(self, actor: str, team_id: str, field_changed: str, old_value: Any, new_value: Any):
        entry = {
            "timestamp": int(time.time()),
            "actor": actor,
            "team_id": team_id,
            "field_changed": field_changed,
            "old_value": old_value,
            "new_value": new_value
        }
        self._audit_logs.append(entry)

    def get_audit_logs(self, team_id: str = None) -> List[Dict[str, Any]]:
        if team_id:
            return [log for log in self._audit_logs if log["team_id"] == team_id]
        return self._audit_logs

audit_service = AuditService()
