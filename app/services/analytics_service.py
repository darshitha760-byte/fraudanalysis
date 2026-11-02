"""MongoDB aggregation pipelines for transaction, alert, and risk analytics."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pymongo.database import Database

from app.db.database import from_bson, to_bson


class AnalyticsService:
    RISK_THRESHOLDS = {"LOW": (0, 30), "MEDIUM": (31, 70), "HIGH": (71, 100)}
    ANOMALY_THRESHOLDS = {
        "volume_spike": 1.5,
        "velocity_threshold": 5,
        "large_transaction": 10000,
    }

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    @staticmethod
    def _transaction_pipeline(query, assessment=True):
        pipeline = [{"$match": to_bson(query)}]
        if assessment:
            pipeline.extend([
                {"$lookup": {
                    "from": "fraud_assessments",
                    "localField": "id",
                    "foreignField": "transaction_id",
                    "as": "_assessment",
                }},
                {"$unwind": {"path": "$_assessment", "preserveNullAndEmptyArrays": True}},
            ])
        return pipeline

    @staticmethod
    def _numeric(value):
        if hasattr(value, "to_decimal"):
            return float(value.to_decimal())
        return float(value or 0)

    @staticmethod
    def get_transaction_statistics(session: Database, days=30, customer_id=None):
        cutoff = AnalyticsService._now() - timedelta(days=days)
        query = {"transaction_date": {"$gte": cutoff}}
        if customer_id is not None:
            query["customer_id"] = customer_id
        pipeline = AnalyticsService._transaction_pipeline(query)
        pipeline.extend([
            {"$group": {
                "_id": None,
                "count": {"$sum": 1},
                "volume": {"$sum": "$amount"},
                "average": {"$avg": "$amount"},
                "minimum": {"$min": "$amount"},
                "maximum": {"$max": "$amount"},
                "high": {"$sum": {"$cond": [{"$eq": [{"$toUpper": "$_assessment.risk_category"}, "HIGH"]}, 1, 0]}},
                "medium": {"$sum": {"$cond": [{"$eq": [{"$toUpper": "$_assessment.risk_category"}, "MEDIUM"]}, 1, 0]}},
                "low": {"$sum": {"$cond": [{"$eq": [{"$toUpper": "$_assessment.risk_category"}, "LOW"]}, 1, 0]}},
            }},
        ])
        result = list(session["transactions"].aggregate(pipeline))
        if not result:
            return {
                "total_transactions": 0, "total_volume": 0.0, "average_amount": 0.0,
                "high_risk_transactions": 0, "medium_risk_transactions": 0,
                "low_risk_transactions": 0, "min_amount": 0.0, "max_amount": 0.0,
                "days": days,
            }
        row = result[0]
        return {
            "total_transactions": row["count"],
            "total_volume": AnalyticsService._numeric(row["volume"]),
            "average_amount": AnalyticsService._numeric(row["average"]),
            "high_risk_transactions": row["high"],
            "medium_risk_transactions": row["medium"],
            "low_risk_transactions": row["low"],
            "min_amount": AnalyticsService._numeric(row["minimum"]),
            "max_amount": AnalyticsService._numeric(row["maximum"]),
            "days": days,
        }

    @staticmethod
    def get_transaction_trends(session: Database, days=30):
        cutoff = AnalyticsService._now() - timedelta(days=days)
        pipeline = [
            {"$match": {"transaction_date": {"$gte": cutoff}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$transaction_date", "timezone": "UTC"}},
                "transaction_count": {"$sum": 1},
                "total_volume": {"$sum": "$amount"},
                "average_amount": {"$avg": "$amount"},
            }},
        ]
        results = {row["_id"]: row for row in session["transactions"].aggregate(pipeline)}
        start = cutoff.date()
        trends = []
        for offset in range(days):
            date_key = (start + timedelta(days=offset)).isoformat()
            row = results.get(date_key, {})
            trends.append({
                "date": date_key,
                "transaction_count": int(row.get("transaction_count", 0)),
                "total_volume": AnalyticsService._numeric(row.get("total_volume")),
                "average_amount": AnalyticsService._numeric(row.get("average_amount")),
            })
        return trends

    @staticmethod
    def get_risk_distribution(session: Database, days=30):
        cutoff = AnalyticsService._now() - timedelta(days=days)
        result = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "total": 0}
        pipeline = [
            {"$match": {"assessment_timestamp": {"$gte": cutoff}}},
            {"$group": {"_id": {"$toUpper": "$risk_category"}, "count": {"$sum": 1}}},
        ]
        for row in session["fraud_assessments"].aggregate(pipeline):
            if row["_id"] in result:
                result[row["_id"]] = row["count"]
            result["total"] += row["count"]
        return result

    @staticmethod
    def get_alert_statistics(session: Database, days=30):
        cutoff = AnalyticsService._now() - timedelta(days=days)
        alerts = list(session["fraud_alerts"].find({
            "$or": [{"created_at": {"$gte": cutoff}}, {"alert_created_at": {"$gte": cutoff}}]
        }, {"alert_status": 1, "review_decision": 1, "review_timestamp": 1,
            "created_at": 1, "alert_created_at": 1}))
        total = len(alerts)
        statuses = [str(alert.get("alert_status", "")).lower() for alert in alerts]
        decisions = [str(alert.get("review_decision", "")).lower() for alert in alerts]
        approved = decisions.count("approved")
        rejected = decisions.count("rejected")
        resolved = approved + rejected
        review_times = []
        for alert in alerts:
            created = alert.get("created_at") or alert.get("alert_created_at")
            reviewed = alert.get("review_timestamp")
            if created and reviewed:
                review_times.append((reviewed - created).total_seconds() / 3600)
        return {
            "total_alerts": total,
            "pending_alerts": statuses.count("pending"),
            "under_review_alerts": statuses.count("under_review"),
            "resolved_alerts": statuses.count("resolved"),
            "dismissed_alerts": statuses.count("dismissed"),
            "approved_alerts": approved,
            "rejected_alerts": rejected,
            "approval_rate": approved / resolved * 100 if resolved else 0,
            "rejection_rate": rejected / resolved * 100 if resolved else 0,
            "average_review_time_hours": sum(review_times) / len(review_times) if review_times else 0,
            "days": days,
        }

    @staticmethod
    def _decision_count(session, decision):
        return session["fraud_alerts"].count_documents({
            "review_decision": {"$regex": f"^{decision}$", "$options": "i"}
        })

    @staticmethod
    def get_fraud_confirmed_rate(session: Database):
        total = session["fraud_alerts"].count_documents({})
        return AnalyticsService._decision_count(session, "approved") / total * 100 if total else 0.0

    @staticmethod
    def get_false_positive_rate(session: Database):
        total = session["fraud_alerts"].count_documents({})
        return AnalyticsService._decision_count(session, "rejected") / total * 100 if total else 0.0

    @staticmethod
    def get_customer_risk_profile(session: Database, customer_id: int):
        customer_doc = session["customers"].find_one({"id": customer_id})
        if not customer_doc:
            return {}
        rows = list(session["transactions"].aggregate([
            {"$match": {"customer_id": customer_id}},
            {"$lookup": {"from": "fraud_assessments", "localField": "id",
                         "foreignField": "transaction_id", "as": "assessment"}},
            {"$unwind": {"path": "$assessment", "preserveNullAndEmptyArrays": True}},
            {"$group": {
                "_id": None, "count": {"$sum": 1}, "amount": {"$avg": "$amount"},
                "high": {"$sum": {"$cond": [{"$eq": [{"$toUpper": "$assessment.risk_category"}, "HIGH"]}, 1, 0]}},
            }},
        ]))
        row = rows[0] if rows else {"count": 0, "amount": 0, "high": 0}
        return {
            "customer_id": customer_doc.get("customer_id", str(customer_id)),
            "total_transactions": row["count"],
            "high_risk_count": row["high"],
            "fraud_rate": row["high"] / row["count"] * 100 if row["count"] else 0,
            "average_transaction_amount": AnalyticsService._numeric(row.get("amount")),
            "suspicious_patterns": AnalyticsService._detect_customer_patterns(session, customer_id),
            "risk_profile": customer_doc.get("risk_profile", "low"),
        }

    @staticmethod
    def _detect_customer_patterns(session: Database, customer_id: int):
        cutoff = AnalyticsService._now() - timedelta(days=30)
        txns = list(session["transactions"].find(
            {"customer_id": customer_id, "transaction_date": {"$gte": cutoff}},
            {"amount": 1, "transaction_date": 1},
        ).sort("transaction_date", 1))
        if not txns:
            return []
        amounts = [from_bson(row)["amount"] for row in txns]
        average = sum(amounts, Decimal("0")) / len(amounts)
        patterns = []
        if len(txns) > 10:
            patterns.append("High transaction frequency")
        if any(amount > average * 3 for amount in amounts):
            patterns.append("Large transaction spike detected")
        if len(amounts) > 5 and all(amount > average for amount in amounts[-5:]):
            patterns.append("Sustained elevated transaction amounts")
        return patterns

    @staticmethod
    def get_high_risk_customers(session: Database, limit=10):
        customer_rows = session["transactions"].aggregate([
            {"$lookup": {"from": "fraud_assessments", "localField": "id",
                         "foreignField": "transaction_id", "as": "assessment"}},
            {"$unwind": {"path": "$assessment", "preserveNullAndEmptyArrays": True}},
            {"$group": {
                "_id": "$customer_id", "transactions": {"$sum": 1},
                "high": {"$sum": {"$cond": [{"$eq": [{"$toUpper": "$assessment.risk_category"}, "HIGH"]}, 1, 0]}},
                "average": {"$avg": "$amount"},
            }},
            {"$sort": {"high": -1, "transactions": -1}},
            {"$limit": limit},
        ])
        results = []
        for row in customer_rows:
            customer = session["customers"].find_one({"id": row["_id"]}) or {}
            results.append({
                "customer_id": customer.get("customer_id", str(row["_id"])),
                "total_transactions": row["transactions"],
                "high_risk_count": row["high"],
                "fraud_rate": row["high"] / row["transactions"] * 100 if row["transactions"] else 0,
                "average_transaction_amount": AnalyticsService._numeric(row.get("average")),
                "suspicious_patterns": [],
                "risk_profile": customer.get("risk_profile", "low"),
            })
        return results

    @staticmethod
    def get_geographic_risk_distribution(session: Database):
        result = {}
        pipeline = [
            {"$lookup": {"from": "customers", "localField": "customer_id", "foreignField": "id", "as": "customer"}},
            {"$unwind": {"path": "$customer", "preserveNullAndEmptyArrays": True}},
            {"$lookup": {"from": "fraud_assessments", "localField": "id", "foreignField": "transaction_id", "as": "assessment"}},
            {"$unwind": {"path": "$assessment", "preserveNullAndEmptyArrays": True}},
            {"$group": {
                "_id": {"$ifNull": ["$customer.country", "Unknown"]},
                "total_transactions": {"$sum": 1},
                "high_risk_count": {"$sum": {"$cond": [{"$eq": [{"$toUpper": "$assessment.risk_category"}, "HIGH"]}, 1, 0]}},
            }},
        ]
        for row in session["transactions"].aggregate(pipeline):
            count, high = row["total_transactions"], row["high_risk_count"]
            result[row["_id"]] = {
                "total_customers": 0, "total_transactions": count,
                "high_risk_count": high, "fraud_rate": high / count * 100 if count else 0,
            }
        for customer in session["customers"].find({}, {"country": 1}):
            country = customer.get("country") or "Unknown"
            result.setdefault(country, {
                "total_customers": 0, "total_transactions": 0,
                "high_risk_count": 0, "fraud_rate": 0.0,
            })
            result[country]["total_customers"] += 1
        return result

    @staticmethod
    def detect_transaction_anomalies(session: Database, hours_lookback=24):
        cutoff = AnalyticsService._now() - timedelta(hours=hours_lookback)
        recent_count = session["transactions"].count_documents({"transaction_date": {"$gte": cutoff}})
        if not recent_count:
            return []
        anomalies = []
        historical_cutoff = AnalyticsService._now() - timedelta(days=30)
        historical = session["transactions"].count_documents({"transaction_date": {"$lt": historical_cutoff}})
        baseline = historical / 30
        if baseline and recent_count > baseline * AnalyticsService.ANOMALY_THRESHOLDS["volume_spike"]:
            anomalies.append({
                "type": "volume_spike", "severity": "high",
                "description": f"Transaction volume {recent_count} is {recent_count / baseline:.1f}x historical average",
                "current_volume": recent_count, "expected_volume": int(baseline),
            })
        per_customer = session["transactions"].aggregate([
            {"$match": {"transaction_date": {"$gte": cutoff}}},
            {"$group": {"_id": "$customer_id", "count": {"$sum": 1},
                        "first": {"$min": "$transaction_date"}, "last": {"$max": "$transaction_date"}}},
            {"$match": {"count": {"$gte": AnalyticsService.ANOMALY_THRESHOLDS["velocity_threshold"]}}},
        ])
        for row in per_customer:
            span = (row["last"] - row["first"]).total_seconds()
            if span < 3600:
                anomalies.append({
                    "type": "velocity_anomaly", "severity": "high",
                    "description": f"Customer {row['_id']} made {row['count']} transactions in {span:.0f} seconds",
                    "customer_id": row["_id"], "transaction_count": row["count"],
                    "time_span_seconds": span,
                })
        for raw in session["transactions"].find({
            "transaction_date": {"$gte": cutoff},
            "amount": {"$gt": to_bson(Decimal(str(AnalyticsService.ANOMALY_THRESHOLDS["large_transaction"])))},
        }):
            txn = from_bson(raw)
            anomalies.append({
                "type": "large_transaction", "severity": "medium",
                "description": f"Transaction amount {float(txn['amount'])} exceeds threshold 10000.0",
                "transaction_id": txn["transaction_id"], "amount": float(txn["amount"]),
                "customer_id": txn["customer_id"],
            })
        return anomalies

    @staticmethod
    def _detect_volume_anomalies(session: Database, recent_transactions):
        recent_count = len(recent_transactions)
        cutoff = AnalyticsService._now() - timedelta(days=30)
        historical = session["transactions"].count_documents({"transaction_date": {"$lt": cutoff}})
        avg = historical / 30
        if avg and recent_count > avg * AnalyticsService.ANOMALY_THRESHOLDS["volume_spike"]:
            return [{"type": "volume_spike", "severity": "high",
                     "description": f"Transaction volume {recent_count} is {recent_count / avg:.1f}x historical average",
                     "current_volume": recent_count, "expected_volume": int(avg)}]
        return []

    @staticmethod
    def _detect_velocity_anomalies(transactions):
        grouped = {}
        for txn in transactions:
            grouped.setdefault(txn.customer_id, []).append(txn)
        results = []
        for customer_id, rows in grouped.items():
            if len(rows) < AnalyticsService.ANOMALY_THRESHOLDS["velocity_threshold"]:
                continue
            dates = sorted(row.transaction_date for row in rows)
            span = (dates[-1] - dates[0]).total_seconds()
            if span < 3600:
                results.append({
                    "type": "velocity_anomaly", "severity": "high",
                    "description": f"Customer {customer_id} made {len(rows)} transactions in {span:.0f} seconds",
                    "customer_id": customer_id, "transaction_count": len(rows),
                    "time_span_seconds": span,
                })
        return results

    @staticmethod
    def _detect_large_transaction_anomalies(transactions):
        threshold = Decimal(str(AnalyticsService.ANOMALY_THRESHOLDS["large_transaction"]))
        return [{
            "type": "large_transaction", "severity": "medium",
            "description": f"Transaction amount {float(row.amount)} exceeds threshold {float(threshold)}",
            "transaction_id": row.transaction_id, "amount": float(row.amount),
            "customer_id": row.customer_id,
        } for row in transactions if row.amount > threshold]

    @staticmethod
    def score_transaction_anomaly(session: Database, transaction_id: int):
        transaction = session["transactions"].find_one({"id": transaction_id})
        if not transaction:
            return 0.0
        tx = from_bson(transaction)
        pipeline = [
            {"$match": {"customer_id": tx["customer_id"]}},
            {"$group": {"_id": None, "average": {"$avg": "$amount"}, "count": {"$sum": 1}}},
        ]
        rows = list(session["transactions"].aggregate(pipeline))
        if not rows or not rows[0]["average"]:
            return 0.0
        average = rows[0]["average"]
        if hasattr(average, "to_decimal"):
            average = average.to_decimal()
        score = 0.0
        if tx["amount"] > average * 3:
            score += 50
        if tx.get("amount", 0) > 10000:
            score += 30
        hour = tx["transaction_date"].hour
        if 2 <= hour < 5:
            score += 20
        recent = session["transactions"].count_documents({
            "customer_id": tx["customer_id"],
            "transaction_date": {"$gte": tx["transaction_date"] - timedelta(hours=1)},
        })
        if recent >= 5:
            score += min(50, recent * 5)
        return min(100.0, score)

    @staticmethod
    def get_dashboard_overview(session: Database):
        txn = AnalyticsService.get_transaction_statistics(session, days=30)
        alert = AnalyticsService.get_alert_statistics(session, days=30)
        risk = AnalyticsService.get_risk_distribution(session, days=30)
        customers = AnalyticsService.get_high_risk_customers(session, limit=5)
        anomalies = AnalyticsService.detect_transaction_anomalies(session, hours_lookback=24)
        return {
            "total_transactions": txn["total_transactions"],
            "total_alerts": alert["total_alerts"],
            "fraud_confirmation_rate": AnalyticsService.get_fraud_confirmed_rate(session),
            "false_positive_rate": AnalyticsService.get_false_positive_rate(session),
            "approval_rate": alert["approval_rate"],
            "rejection_rate": alert["rejection_rate"],
            "average_review_time_hours": alert["average_review_time_hours"],
            "high_risk_customers_count": len(customers),
            "critical_anomalies": sum(item.get("severity") == "high" for item in anomalies),
            "pending_alerts": alert["pending_alerts"],
            "under_review_alerts": alert["under_review_alerts"],
            "risk_distribution": risk,
        }

    @staticmethod
    def _breakdown(session, field, output_field, days, include_risk=True):
        cutoff = AnalyticsService._now() - timedelta(days=days)
        pipeline = AnalyticsService._transaction_pipeline({"transaction_date": {"$gte": cutoff}})
        group = {
            "_id": {"$ifNull": [f"${field}", "Unknown"]},
            "count": {"$sum": 1}, "volume": {"$sum": "$amount"},
        }
        if include_risk:
            group["risk_total"] = {"$sum": {"$ifNull": ["$_assessment.risk_score", 0]}}
            group["high"] = {"$sum": {"$cond": [{"$eq": [{"$toUpper": "$_assessment.risk_category"}, "HIGH"]}, 1, 0]}}
        pipeline.extend([{"$group": group}, {"$sort": {"count": -1}}])
        rows = []
        for raw in session["transactions"].aggregate(pipeline):
            row = {
                output_field: raw["_id"], "count": raw["count"],
                "volume": AnalyticsService._numeric(raw["volume"]),
            }
            if include_risk:
                row["high_risk_count"] = raw.get("high", 0)
                row["average_risk_score"] = AnalyticsService._numeric(raw.get("risk_total")) / raw["count"] if raw["count"] else 0
                row["fraud_rate"] = raw.get("high", 0) / raw["count"] * 100 if raw["count"] else 0
            rows.append(row)
        return rows

    @staticmethod
    def get_merchant_category_analysis(session: Database, days=30):
        return [{
            "category": row["merchant_category"],
            "transaction_count": row["count"],
            "total_volume": row["volume"],
            "average_risk_score": row["average_risk_score"],
        } for row in AnalyticsService._breakdown(session, "merchant_category", "merchant_category", days)]

    @staticmethod
    def get_transaction_type_analysis(session: Database, days=30):
        return [{
            "transaction_type": row["transaction_type"], "count": row["count"],
            "volume": row["volume"], "high_risk_count": row["high_risk_count"],
            "average_risk_score": row["average_risk_score"],
        } for row in AnalyticsService._breakdown(session, "transaction_type", "transaction_type", days)]

    @staticmethod
    def get_payment_method_analysis(session: Database, days=30):
        return [{
            "payment_method": row["payment_method"], "count": row["count"],
            "volume": row["volume"], "high_risk_count": row["high_risk_count"],
            "fraud_rate": row["fraud_rate"],
        } for row in AnalyticsService._breakdown(session, "payment_method", "payment_method", days)]

    @staticmethod
    def get_geographic_analysis(session: Database, days=30):
        pipeline = AnalyticsService._transaction_pipeline({
            "transaction_date": {"$gte": AnalyticsService._now() - timedelta(days=days)}
        })
        pipeline.extend([
            {"$group": {
                "_id": {"country": {"$ifNull": ["$location_country", "Unknown"]},
                        "city": {"$ifNull": ["$location_city", None]}},
                "count": {"$sum": 1}, "volume": {"$sum": "$amount"},
                "risk_total": {"$sum": {"$ifNull": ["$_assessment.risk_score", 0]}},
                "high": {"$sum": {"$cond": [{"$eq": [{"$toUpper": "$_assessment.risk_category"}, "HIGH"]}, 1, 0]}},
            }},
            {"$sort": {"count": -1}},
        ])
        results = []
        for row in session["transactions"].aggregate(pipeline):
            count = row["count"]
            results.append({
                "country": row["_id"]["country"], "city": row["_id"]["city"],
                "transaction_count": count,
                "total_volume": AnalyticsService._numeric(row.get("volume")),
                "high_risk_count": row.get("high", 0),
                "average_risk_score": AnalyticsService._numeric(row.get("risk_total")) / count if count else 0,
            })
        return results

    @staticmethod
    def get_channel_analysis(session: Database, days=30):
        return [{
            "channel": row["channel"], "count": row["count"], "volume": row["volume"],
            "high_risk_count": row["high_risk_count"], "fraud_rate": row["fraud_rate"],
        } for row in AnalyticsService._breakdown(session, "channel", "channel", days)]

    @staticmethod
    def get_risk_score_distribution(session: Database, days=30):
        cutoff = AnalyticsService._now() - timedelta(days=days)
        rows = session["fraud_assessments"].aggregate([
            {"$match": {"assessment_timestamp": {"$gte": cutoff}}},
            {"$bucket": {
                "groupBy": "$risk_score",
                "boundaries": [0, 20, 40, 60, 80, 101],
                "default": "other",
                "output": {"count": {"$sum": 1}},
            }},
        ])
        result = list(rows)
        total = sum(row["count"] for row in result)
        return [{
            "risk_score_bucket": f"{row['_id']}-{int(row['_id']) + 19}" if isinstance(row["_id"], (int, float)) else str(row["_id"]),
            "count": row["count"],
            "percentage": row["count"] / total * 100 if total else 0,
        } for row in result]
