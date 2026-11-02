"""Admin-only access to persisted MongoDB audit events."""

import re
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.permissions import UserRole
from app.core.security import require_role
from app.db.database import from_bson, get_db

router = APIRouter(prefix="/api/audit-logs", tags=["audit logs"])


def period_query(db, start_date: date | None, end_date: date | None):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, detail="Start date must not be after end date")
    query = {}
    if start_date or end_date:
        bounds = {}
        if start_date:
            bounds["$gte"] = datetime.combine(start_date, time.min, timezone.utc)
        if end_date:
            bounds["$lte"] = datetime.combine(end_date, time.max, timezone.utc)
        query["action_timestamp"] = bounds
    return query


@router.get("")
def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    actor: str | None = None,
    action: str | None = None,
    target_entity: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db=Depends(get_db),
    current_user=Depends(require_role(UserRole.ADMIN)),
):
    query = period_query(db, start_date, end_date)
    if actor:
        users = db["users"].find({"email": actor.strip().lower()}, {"id": 1})
        ids = [doc["id"] for doc in users]
        query["actor_id"] = {"$in": ids} if ids else -1
    if action:
        prefix = re.escape(action.lower())
        query["action"] = {"$regex": f"^{prefix}(?:_|$)", "$options": "i"}
    if target_entity:
        query["target_type"] = target_entity.lower()
    collection = db["audit_logs"]
    total = collection.count_documents(query)
    items = []
    for raw in collection.find(query).sort([("action_timestamp", -1), ("id", -1)]).skip(skip).limit(limit):
        event = from_bson(raw)
        user = db["users"].find_one({"id": event.get("actor_id")}) if event.get("actor_id") else None
        items.append({
            "id": event["id"],
            "timestamp": event["action_timestamp"],
            "actor": user["email"] if user else "System",
            "action": event["action"],
            "target_type": event["target_type"],
            "target_id": event.get("target_id"),
            "status": event["action_status"],
            "success": event["action_status"] == "success",
            "details": event.get("status_message") or "",
            "changes_before": event.get("changes_before"),
            "changes_after": event.get("changes_after"),
        })
    return {"total": total, "items": items}


@router.get("/compliance-report")
def compliance_report(
    report_type: str,
    start_date: date,
    end_date: date,
    db=Depends(get_db),
    current_user=Depends(require_role(UserRole.ADMIN)),
):
    query = period_query(db, start_date, end_date)
    if report_type == "user_access":
        query["action_category"] = "authentication"
    elif report_type == "data_changes":
        query["action"] = {"$regex": r"^(create_|update_|delete_)", "$options": "i"}
    elif report_type in {"alerts_review", "rule_modifications", "model_updates"}:
        target_map = {
            "alerts_review": ["fraud_alert"],
            "rule_modifications": ["fraud_rule"],
            "model_updates": ["model", "ml_model"],
        }
        query["target_type"] = {"$in": target_map[report_type]}
    elif report_type == "security_events":
        query["$or"] = [
            {"action_category": "authentication"},
            {"action_status": {"$ne": "success"}},
        ]
    else:
        raise HTTPException(422, detail="Unknown report type")
    collection = db["audit_logs"]
    docs = list(collection.find(query, {"actor_id": 1, "action_status": 1}))
    return {
        "summary": {
            "total_events": len(docs),
            "unique_users": len({doc.get("actor_id") for doc in docs if doc.get("actor_id") is not None}),
            "failed_actions": sum(doc.get("action_status") == "failure" for doc in docs),
            "exceptions": sum(doc.get("action_status") not in {"success", "failure"} for doc in docs),
        },
        "findings": [],
    }
