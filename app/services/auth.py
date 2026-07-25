from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import config

security = HTTPBearer(auto_error=False)

def authenticate_and_authorize(
    credentials: HTTPAuthorizationCredentials = Security(security),
    requested_model: str = ""
) -> dict:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header."
        )

    api_key = credentials.credentials
    team = config.get_team_by_api_key(api_key)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Team API Key. Authentication failed."
        )

    allowed_models = team.get("allowed_models", [])
    if requested_model and requested_model not in allowed_models:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Team '{team['name']}' is not authorized to use model '{requested_model}'. Allowed models: {allowed_models}"
        )

    return team

