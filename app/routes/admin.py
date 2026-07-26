from typing import Optional, List, Any
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Header, status
from app.config import config
from app.services.budget_service import budget_service
from app.services.audit_service import audit_service

router = APIRouter(prefix="/v1/admin", tags=["Admin API"])

class UpdateLimitsRequest(BaseModel):
    rate_limit_rpm: Optional[int] = None
    monthly_budget_usd: Optional[float] = None
    allowed_models: Optional[List[str]] = None

@router.get("/teams/{team_id}/limits")
async def get_team_limits(team_id: str):
    team = config.teams_by_id.get(team_id)
    if not team:
        raise HTTPException(status_code=404, detail=f"Team '{team_id}' not found.")

    monthly_budget = team.get("monthly_budget_usd", 100.0)
    can_proceed, current_spend, spend_percent, warning_flag = budget_service.check_budget_status(
        team_id, monthly_budget
    )

    return {
        "team_id": team_id,
        "team_name": team["name"],
        "plan": team["plan"],
        "rate_limit_rpm": team.get("rate_limit_rpm", 60),
        "monthly_budget_usd": monthly_budget,
        "current_spend_usd": current_spend,
        "spend_percent": spend_percent,
        "budget_warning_80_percent": warning_flag,
        "budget_exceeded_100_percent": not can_proceed,
        "allowed_models": team.get("allowed_models", [])
    }

@router.put("/teams/{team_id}/limits")
async def update_team_limits(
    team_id: str,
    body: UpdateLimitsRequest,
    x_admin_user: str = Header("admin_user", alias="X-Admin-User")
):
    team = config.teams_by_id.get(team_id)
    if not team:
        raise HTTPException(status_code=404, detail=f"Team '{team_id}' not found.")

    updated_fields = {}

    if body.rate_limit_rpm is not None:
        old_rpm = team.get("rate_limit_rpm", 60)
        team["rate_limit_rpm"] = body.rate_limit_rpm
        audit_service.log_change(x_admin_user, team_id, "rate_limit_rpm", old_rpm, body.rate_limit_rpm)
        updated_fields["rate_limit_rpm"] = body.rate_limit_rpm

    if body.monthly_budget_usd is not None:
        old_budget = team.get("monthly_budget_usd", 100.0)
        team["monthly_budget_usd"] = body.monthly_budget_usd
        audit_service.log_change(x_admin_user, team_id, "monthly_budget_usd", old_budget, body.monthly_budget_usd)
        updated_fields["monthly_budget_usd"] = body.monthly_budget_usd

    if body.allowed_models is not None:
        old_models = team.get("allowed_models", [])
        team["allowed_models"] = body.allowed_models
        audit_service.log_change(x_admin_user, team_id, "allowed_models", old_models, body.allowed_models)
        updated_fields["allowed_models"] = body.allowed_models

    return {
        "status": "success",
        "message": f"Updated limits for team '{team_id}' successfully.",
        "updated_by": x_admin_user,
        "updated_fields": updated_fields
    }

@router.get("/spending")
async def get_spending_dashboard():
    dashboard = []
    for team_id, team in config.teams_by_id.items():
        monthly_budget = team.get("monthly_budget_usd", 100.0)
        can_proceed, current_spend, spend_percent, warning_flag = budget_service.check_budget_status(
            team_id, monthly_budget
        )
        dashboard.append({
            "team_id": team_id,
            "team_name": team["name"],
            "plan": team["plan"],
            "monthly_budget_usd": monthly_budget,
            "current_spend_usd": current_spend,
            "spend_percent": spend_percent,
            "warning_flag": warning_flag
        })
    return {"teams_spending": dashboard}

@router.get("/audit-logs")
async def get_audit_logs(team_id: Optional[str] = None):
    return {"audit_logs": audit_service.get_audit_logs(team_id)}
