"""MongoDB case-management operations; notes remain separate unbounded documents."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo.database import Database

from app.db.database import from_bson, insert_document, to_bson
from app.models.case import CaseNote, InvestigationCase

logger = logging.getLogger(__name__)


class CaseService:
    @staticmethod
    def create_case_from_alert(session: Database, alert_id: int, case_type: str,
                               assigned_to: int, summary: Optional[str] = None):
        alert = session["fraud_alerts"].find_one({"id": alert_id})
        if not alert:
            raise ValueError(f"Alert {alert_id} not found")
        if session["investigation_cases"].find_one({"alert_id": alert_id}):
            raise ValueError(f"Case already exists for alert {alert_id}")
        doc = insert_document(session, "investigation_cases", {
            "alert_id": alert_id, "transaction_id": alert["transaction_id"],
            "customer_id": alert["customer_id"], "case_type": case_type,
            "case_status": "open", "assigned_to": assigned_to,
            "summary": summary, "case_created_at": datetime.now(timezone.utc),
            "escalated": False,
        })
        return CaseService._format_case_response(InvestigationCase.model_validate(doc))

    @staticmethod
    def _find(session: Database, case_id: int):
        doc = session["investigation_cases"].find_one({"id": case_id})
        return InvestigationCase.model_validate(from_bson(doc)) if doc else None

    @staticmethod
    def get_case(session: Database, case_id: int):
        case = CaseService._find(session, case_id)
        return CaseService._format_case_response(case) if case else None

    @staticmethod
    def get_case_by_alert(session: Database, alert_id: int):
        doc = session["investigation_cases"].find_one({"alert_id": alert_id})
        case = InvestigationCase.model_validate(from_bson(doc)) if doc else None
        return CaseService._format_case_response(case) if case else None

    @staticmethod
    def _list(session, query, limit, offset):
        collection = session["investigation_cases"]
        total = collection.count_documents(query)
        docs = collection.find(query).sort("case_created_at", -1).skip(offset).limit(limit)
        return ([CaseService._format_case_response(
            InvestigationCase.model_validate(from_bson(doc))) for doc in docs], total)

    @staticmethod
    def get_active_cases(session: Database, limit=100, offset=0):
        return CaseService._list(
            session, {"case_status": {"$in": ["open", "under_investigation", "escalated"]}},
            limit, offset,
        )

    @staticmethod
    def get_cases_by_analyst(session: Database, analyst_id: int, limit=100, offset=0):
        return CaseService._list(session, {"assigned_to": analyst_id}, limit, offset)

    @staticmethod
    def update_case_status(session: Database, case_id: int, new_status: str,
                           summary=None, findings=None):
        case = CaseService._find(session, case_id)
        if not case:
            raise ValueError(f"Case {case_id} not found")
        if new_status not in ("open", "under_investigation", "closed", "escalated"):
            raise ValueError(f"Invalid status: {new_status}")
        changes = {"case_status": new_status, "updated_at": datetime.now(timezone.utc)}
        if summary is not None:
            changes["summary"] = summary
        if findings is not None:
            changes["findings"] = findings
        if new_status == "closed":
            changes["case_closed_at"] = datetime.now(timezone.utc)
        session["investigation_cases"].update_one(
            {"id": case_id}, {"$set": to_bson(changes)}
        )
        return CaseService.get_case(session, case_id)

    @staticmethod
    def add_case_note(session: Database, case_id: int, note_text: str,
                      analyst_id: int, note_type: str = "general"):
        if not session["investigation_cases"].find_one({"id": case_id}):
            raise ValueError(f"Case {case_id} not found")
        doc = insert_document(session, "case_notes", {
            "case_id": case_id, "analyst_id": analyst_id,
            "note_text": note_text, "note_type": note_type,
        })
        return CaseService._format_note_response(CaseNote.model_validate(doc))

    @staticmethod
    def get_case_notes(session: Database, case_id: int, limit=100, offset=0):
        collection = session["case_notes"]
        query = {"case_id": case_id}
        total = collection.count_documents(query)
        docs = collection.find(query).sort("created_at", -1).skip(offset).limit(limit)
        return ([CaseService._format_note_response(CaseNote.model_validate(from_bson(doc)))
                 for doc in docs], total)

    @staticmethod
    def escalate_case(session: Database, case_id: int, escalated_to: int,
                      escalation_reason: str, escalated_by: Optional[int] = None):
        if not session["investigation_cases"].find_one({"id": case_id}):
            raise ValueError(f"Case {case_id} not found")
        session["investigation_cases"].update_one(
            {"id": case_id}, {"$set": {
                "escalated": True, "escalation_reason": escalation_reason,
                "escalated_to": escalated_to, "case_status": "escalated",
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        return CaseService.get_case(session, case_id)

    @staticmethod
    def _format_case_response(case: InvestigationCase) -> Dict[str, Any]:
        data = case.model_dump()
        return {
            "case_id": data["id"], "alert_id": data["alert_id"],
            "transaction_id": data["transaction_id"], "customer_id": data["customer_id"],
            "case_type": data["case_type"], "case_status": data["case_status"],
            "assigned_to": data["assigned_to"], "summary": data.get("summary"),
            "findings": data.get("findings"), "case_created_at": data["case_created_at"],
            "case_closed_at": data.get("case_closed_at"), "case_notes": data.get("case_notes"),
            "escalated": data.get("escalated", False),
            "escalation_reason": data.get("escalation_reason"),
            "escalated_to": data.get("escalated_to"),
        }

    @staticmethod
    def _format_note_response(note: CaseNote) -> Dict[str, Any]:
        return {
            "note_id": note.id, "case_id": note.case_id,
            "analyst_id": note.analyst_id, "note_text": note.note_text,
            "note_type": note.note_type, "created_at": note.created_at,
        }
