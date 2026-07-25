import os
import yaml
from typing import Dict, Any, Optional

class ConfigLoader:
    def __init__(self, config_path: str = "config/teams.yaml"):
        self.config_path = config_path
        self.teams_by_key: Dict[str, Dict[str, Any]] = {}
        self.teams_by_id: Dict[str, Dict[str, Any]] = {}
        self.load_config()

    def load_config(self):
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file not found at {self.config_path}")
        
        with open(self.config_path, "r") as f:
            data = yaml.safe_load(f) or {}
            teams = data.get("teams", {})
            for team_id, team_data in teams.items():
                team_data["team_id"] = team_id
                api_key = team_data.get("api_key")
                if api_key:
                    self.teams_by_key[api_key] = team_data
                self.teams_by_id[team_id] = team_data

    def get_team_by_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        return self.teams_by_key.get(api_key)

config = ConfigLoader()
