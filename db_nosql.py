"""
db_nosql.py
-----------
MongoDB operations: inserts into field_reports and event_stream, plus the
three aggregation pipelines.
"""

from datetime import datetime

from pymongo import MongoClient

from config import MONGO_CONFIG


def get_db():
    """Return a handle to the CrisisLink MongoDB database."""
    client = MongoClient(MONGO_CONFIG["uri"], serverSelectionTimeoutMS=5000)
    return client[MONGO_CONFIG["database"]]


def insert_field_report(report: dict) -> str:
    """Insert a field report and return its report_id."""
    get_db().field_reports.insert_one(report)
    return report["report_id"]


def insert_event(event: dict) -> str:
    """Insert an audit event and return its event_id."""
    get_db().event_stream.insert_one(event)
    return event["event_id"]


def get_field_reports_by_zone() -> list:
    """Pipeline 1: zone-wise field report summary ($match, $group, $sort, $project)."""
    return list(get_db().field_reports.aggregate([
        {"$match": {"timestamp": {"$gte": datetime(2026, 10, 1)}}},
        {"$group": {
            "_id": "$zone",
            "total_reports": {"$sum": 1},
            "critical_reports": {"$sum": {"$cond": [{"$eq": ["$severity", "CRITICAL"]}, 1, 0]}},
            "latest_report": {"$max": "$timestamp"},
            "report_types": {"$addToSet": "$report_type"},
        }},
        {"$sort": {"critical_reports": -1}},
        {"$project": {
            "zone": "$_id", "total_reports": 1, "critical_reports": 1,
            "latest_report": 1, "report_types": 1, "_id": 0,
        }},
    ]))


def get_critical_reports_with_events() -> list:
    """Pipeline 2: critical reports joined to same-zone events ($lookup)."""
    return list(get_db().field_reports.aggregate([
        {"$match": {"severity": "CRITICAL"}},
        {"$lookup": {
            "from": "event_stream",
            "localField": "zone",
            "foreignField": "zone",
            "as": "related_events",
        }},
        {"$project": {
            "report_id": 1, "zone": 1, "description": 1, "severity": 1,
            "event_count": {"$size": "$related_events"},
            "recent_events": {"$slice": ["$related_events", 3]},
        }},
        {"$sort": {"event_count": -1}},
    ]))


def get_recent_events(limit: int = 10) -> list:
    """Pipeline 3: most recent events feed ($sort, $limit, $project)."""
    return list(get_db().event_stream.aggregate([
        {"$sort": {"timestamp": -1}},
        {"$limit": limit},
        {"$project": {
            "event_id": 1, "entity_type": 1, "action": 1,
            "actor_name": 1, "zone": 1, "timestamp": 1, "_id": 0,
        }},
    ]))
