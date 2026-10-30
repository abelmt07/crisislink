"""
db_sql.py
---------
All MySQL operations: connection handling, inserts, the advanced queries
(JOIN, GROUP BY, sub-query, stored procedure, view), and the trigger demo.
"""

import logging

import mysql.connector
from mysql.connector import Error # type: ignore

from config import SQL_CONFIG
from models import Organization, Request, Supply
from datetime import datetime
from db_nosql import insert_event


def get_connection():
    """Open and return a new MySQL connection using SQL_CONFIG."""
    try:
        return mysql.connector.connect(**SQL_CONFIG)
    except Error as e:
        logging.error(f"SQL connection error: {e}")
        raise


def _run_insert(sql: str, params: tuple) -> int:
    """Execute an INSERT, commit, and return the new auto-increment id."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def _fetch_all(sql: str, params: tuple = ()) -> list:
    """Run a SELECT and return every row as a dict."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def insert_organization(org: Organization) -> int:
    """Insert an organization and return its org_id."""
    return _run_insert(
        """INSERT INTO organizations
           (org_name, org_type, contact_person, contact_phone, contact_email, zone)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (org.org_name, org.org_type, org.contact_person, org.contact_phone,
         org.contact_email, org.zone),
    )


def insert_request(req: Request) -> int:
    """Insert a request and return its request_id."""
    return _run_insert(
        """INSERT INTO requests
           (org_id, resource_type, resource_name, quantity, unit, urgency, zone, description)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (req.org_id, req.resource_type, req.resource_name, req.quantity,
         req.unit, req.urgency, req.zone, req.description),
    )


def insert_supply(sup: Supply) -> int:
    """Insert a supply and return its supply_id."""
    return _run_insert(
        """INSERT INTO supplies
           (org_id, resource_type, resource_name, quantity, unit, zone)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (sup.org_id, sup.resource_type, sup.resource_name, sup.quantity, sup.unit, sup.zone),
    )


def get_all_organizations() -> list:
    """Return active organizations (used to show a picker in the CLI)."""
    return _fetch_all("SELECT org_id, org_name, zone FROM organizations WHERE is_active = TRUE")


def get_all_requests() -> list:
    """Return all requests, newest first."""
    return _fetch_all("SELECT * FROM requests ORDER BY created_at DESC")


def get_all_supplies() -> list:
    """Return all supplies, newest first."""
    return _fetch_all("SELECT * FROM supplies ORDER BY created_at DESC")


def get_all_matches() -> list:
    """Query 1: full match report using a 4-table INNER JOIN."""
    return _fetch_all(
        """
        SELECT
            m.match_id, r.request_id, r.resource_name AS requested_item,
            r.quantity AS requested_qty, r.urgency,
            o1.org_name AS requesting_org, r.zone AS request_zone,
            s.supply_id, s.resource_name AS supplied_item,
            s.quantity AS available_qty,
            o2.org_name AS supplying_org, s.zone AS supply_zone,
            m.matched_qty, m.match_score, m.match_status
        FROM matches m
        INNER JOIN requests r ON m.request_id = r.request_id
        INNER JOIN supplies s ON m.supply_id = s.supply_id
        INNER JOIN organizations o1 ON r.org_id = o1.org_id
        INNER JOIN organizations o2 ON s.org_id = o2.org_id
        ORDER BY m.match_score DESC
        """
    )


def run_auto_match() -> int:
    """Query 4: call the auto_match_requests stored procedure. Returns matches created."""
    conn = get_connection()
    cursor = conn.cursor()
    count = 0
    try:
        cursor.callproc("auto_match_requests")
        for result in cursor.stored_results():
            row = result.fetchone()
            if row:
                count = row[0]
        conn.commit()
        return count
    finally:
        cursor.close()
        conn.close()


def get_situation_report() -> list:
    """Query 5: read the v_situation_report view."""
    return _fetch_all("SELECT * FROM v_situation_report")

def get_unmet_requests() -> list:
    """Query 3: requests still short of stock (OPEN or PARTIAL), with the unmet amount."""
    return _fetch_all(
        """
        SELECT r.request_id, r.resource_name, r.quantity, r.urgency,
               o.org_name, r.zone, r.created_at,
               r.quantity - COALESCE(m.allocated, 0) AS unmet_qty
        FROM requests r
        INNER JOIN organizations o ON r.org_id = o.org_id
        LEFT JOIN (
            SELECT request_id, SUM(matched_qty) AS allocated
            FROM matches
            WHERE match_status <> 'REJECTED'
            GROUP BY request_id
        ) m ON r.request_id = m.request_id
        WHERE r.status IN ('OPEN', 'PARTIAL')
          AND r.quantity > COALESCE(m.allocated, 0)
        ORDER BY FIELD(r.urgency, 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'), r.created_at ASC
        """
    )


def get_zone_summary() -> list:
    """Query 2: zone-wise requested vs matched quantities using GROUP BY.
    Matches are totalled per request first, so a request with several
    matches is not counted twice. REJECTED matches are excluded."""
    return _fetch_all(
        """
        SELECT r.zone,
               COUNT(*) AS total_requests,
               SUM(r.quantity) AS total_requested_qty,
               SUM(COALESCE(m.match_count, 0)) AS total_matches,
               SUM(COALESCE(m.allocated, 0)) AS total_matched_qty,
               ROUND(SUM(COALESCE(m.allocated, 0)) / SUM(r.quantity) * 100, 2) AS fulfillment_pct
        FROM requests r
        LEFT JOIN (
            SELECT request_id, COUNT(*) AS match_count, SUM(matched_qty) AS allocated
            FROM matches
            WHERE match_status <> 'REJECTED'
            GROUP BY request_id
        ) m ON r.request_id = m.request_id
        GROUP BY r.zone
        ORDER BY fulfillment_pct ASC
        """
    )


def dispatch_supply(supply_id: int, qty_to_dispatch: int) -> dict:
    """
    Reduce a supply's quantity. If it reaches zero, trg_supply_depleted
    automatically sets status to DEPLETED. Returns the updated row.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT quantity FROM supplies WHERE supply_id = %s", (supply_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"No supply with id {supply_id}")
        new_qty = max(row["quantity"] - qty_to_dispatch, 0)
        cursor.execute("UPDATE supplies SET quantity = %s WHERE supply_id = %s",
                       (new_qty, supply_id))
        conn.commit()
        cursor.execute("SELECT * FROM supplies WHERE supply_id = %s", (supply_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


# ------------------------------------------------------------
# MATCH LIFECYCLE
# PENDING -> CONFIRMED -> DISPATCHED -> COMPLETED
# PENDING or CONFIRMED -> REJECTED (quantity returns to the supply)
# ------------------------------------------------------------

MATCH_TRANSITIONS = {
    "confirm":  (("PENDING",), "CONFIRMED"),
    "dispatch": (("CONFIRMED",), "DISPATCHED"),
    "deliver":  (("DISPATCHED",), "COMPLETED"),
    "reject":   (("PENDING", "CONFIRMED"), "REJECTED"),
}


def _recompute_request_status(cursor, request_id: int) -> str:
    """Set a request's status from its non-rejected matches and return it."""
    cursor.execute("SELECT quantity, status FROM requests WHERE request_id = %s FOR UPDATE",
                   (request_id,))
    req = cursor.fetchone()
    if req is None or req["status"] == "CANCELLED":
        return req["status"] if req else None

    cursor.execute(
        "SELECT match_status, matched_qty FROM matches "
        "WHERE request_id = %s AND match_status <> 'REJECTED'",
        (request_id,))
    rows = cursor.fetchall()
    allocated = sum(r["matched_qty"] for r in rows)
    statuses = {r["match_status"] for r in rows}

    if allocated == 0:
        new_status = "OPEN"
    elif allocated < req["quantity"]:
        new_status = "PARTIAL"
    elif statuses == {"COMPLETED"}:
        new_status = "DELIVERED"
    elif statuses <= {"DISPATCHED", "COMPLETED"}:
        new_status = "DISPATCHED"
    else:
        new_status = "MATCHED"

    cursor.execute("UPDATE requests SET status = %s WHERE request_id = %s",
                   (new_status, request_id))
    return new_status


def advance_match(match_id: int, action: str, actor_name: str) -> dict:
    """
    Move a match through its lifecycle, keep the supply and request in step,
    and write an audit event. Rejecting a match returns its quantity to the supply.
    Raises ValueError if the action is unknown or not allowed from the current state.
    """
    if action not in MATCH_TRANSITIONS:
        raise ValueError(f"Unknown action: {action}")
    allowed_from, to_state = MATCH_TRANSITIONS[action]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cursor.execute("SELECT * FROM matches WHERE match_id = %s FOR UPDATE", (match_id,))
        match = cursor.fetchone()
        if match is None:
            raise ValueError(f"No match with id {match_id}")
        old_status = match["match_status"]
        if old_status not in allowed_from:
            raise ValueError(f"Cannot {action} match {match_id}: it is {old_status}")

        if to_state == "REJECTED":
            cursor.execute("UPDATE supplies SET quantity = quantity + %s WHERE supply_id = %s",
                           (match["matched_qty"], match["supply_id"]))
            cursor.execute("UPDATE supplies SET status = 'AVAILABLE' "
                           "WHERE supply_id = %s AND status = 'DEPLETED' AND quantity > 0",
                           (match["supply_id"],))

        cursor.execute("UPDATE matches SET match_status = %s WHERE match_id = %s",
                       (to_state, match_id))
        new_request_status = _recompute_request_status(cursor, match["request_id"])

        cursor.execute("SELECT zone FROM requests WHERE request_id = %s", (match["request_id"],))
        zone = cursor.fetchone()["zone"]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    insert_event({
        "event_id": f"EV-{datetime.now():%Y%m%d%H%M%S%f}",
        "entity_type": "MATCH",
        "entity_id": match_id,
        "action": action.upper(),
        "actor_name": actor_name,
        "zone": zone,
        "timestamp": datetime.now(),
        "details": {
            "from": old_status,
            "to": to_state,
            "request_id": match["request_id"],
            "supply_id": match["supply_id"],
            "matched_qty": match["matched_qty"],
            "request_status": new_request_status,
        },
    })
    return {"match_id": match_id, "from": old_status, "to": to_state,
            "request_status": new_request_status}