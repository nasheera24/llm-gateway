import os
import time
import httpx
from typing import Dict, Any, Optional

class AlertingService:
    def __init__(self):
        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
        self.alert_history = []

    async def send_slack_alert(self, event_type: str, details: Dict[str, Any]):
        alert_entry = {
            "timestamp": int(time.time()),
            "event_type": event_type,
            "details": details
        }
        self.alert_history.append(alert_entry)

        # Build Slack Block Kit payload
        slack_payload = {
            "text": f"🚨 *LLM Gateway Alert: {event_type}*",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"🚨 LLM Gateway Alert: {event_type}"}
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join([f"• *{k}*: `{v}`" for k, v in details.items()])
                    }
                }
            ]
        }

        if self.slack_webhook_url:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(self.slack_webhook_url, json=slack_payload, timeout=5.0)
            except Exception as e:
                print(f"[Alerting] Failed to dispatch Slack webhook: {e}")

    def get_alert_history(self) -> list:
        return self.alert_history[-20:]

alerting_service = AlertingService()
