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
    """Query 3: open requests with no CONFIRMED match, via a NOT IN sub-query."""
    return _fetch_all(
        """
        SELECT r.request_id, r.resource_name, r.quantity, r.urgency,
               o.org_name, r.zone, r.created_at
        FROM requests r
        INNER JOIN organizations o ON r.org_id = o.org_id
        WHERE r.status = 'OPEN'
        AND r.request_id NOT IN (
            SELECT DISTINCT request_id FROM matches WHERE match_status = 'CONFIRMED'
        )
        ORDER BY FIELD(r.urgency, 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'), r.created_at ASC
        """
    )


def get_zone_summary() -> list:
    """Query 2: zone-wise requested vs matched quantities using GROUP BY."""
    return _fetch_all(
        """
        SELECT r.zone,
               COUNT(DISTINCT r.request_id) AS total_requests,
               SUM(r.quantity) AS total_requested_qty,
               COUNT(DISTINCT m.match_id) AS total_matches,
               COALESCE(SUM(m.matched_qty), 0) AS total_matched_qty,
               ROUND((COALESCE(SUM(m.matched_qty), 0) / SUM(r.quantity)) * 100, 2) AS fulfillment_pct
        FROM requests r
        LEFT JOIN matches m ON r.request_id = m.request_id AND m.match_status = 'CONFIRMED'
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
