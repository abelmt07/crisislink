"""
test_lifecycle_db.py
--------------------
Integration tests for the match lifecycle. Needs the local database running
and a freshly built sample dataset, because it changes data.
"""

import unittest

from db_nosql import get_db
from db_sql import advance_match, get_connection


def _query_one(sql, params=()):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def _match_id(request_id, supply_id):
    row = _query_one("SELECT match_id FROM matches WHERE request_id = %s AND supply_id = %s",
                     (request_id, supply_id))
    return row["match_id"]


def _match_status(match_id):
    return _query_one("SELECT match_status FROM matches WHERE match_id = %s",
                      (match_id,))["match_status"]


def _request_status(request_id):
    return _query_one("SELECT status FROM requests WHERE request_id = %s",
                      (request_id,))["status"]


def _supply(supply_id):
    return _query_one("SELECT quantity, status FROM supplies WHERE supply_id = %s",
                      (supply_id,))


class TestMatchLifecycle(unittest.TestCase):

    def test_full_flow_completes_match_and_logs_each_step(self):
        mid = _match_id(1, 1)
        for action in ("confirm", "dispatch", "deliver"):
            advance_match(mid, action, "test")
        self.assertEqual(_match_status(mid), "COMPLETED")
        # Request 1 still has a pending match on supply 6, so it stays PARTIAL
        self.assertEqual(_request_status(1), "PARTIAL")
        logged = get_db().event_stream.count_documents(
            {"entity_type": "MATCH", "entity_id": mid})
        self.assertGreaterEqual(logged, 3)

    def test_reject_returns_quantity_to_supply(self):
        mid = _match_id(1, 6)
        before = _supply(6)
        self.assertEqual(before["status"], "DEPLETED")
        advance_match(mid, "reject", "test")
        after = _supply(6)
        self.assertEqual(after["quantity"], before["quantity"] + 100)
        self.assertEqual(after["status"], "AVAILABLE")
        self.assertEqual(_match_status(mid), "REJECTED")

    def test_invalid_transitions_are_refused(self):
        mid = _match_id(4, 4)
        advance_match(mid, "reject", "test")
        with self.assertRaises(ValueError):
            advance_match(mid, "confirm", "test")
        with self.assertRaises(ValueError):
            advance_match(mid, "fly", "test")


if __name__ == "__main__":
    unittest.main()