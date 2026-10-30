-- ============================================================
-- CrisisLink: all SQL used by db_sql.py, extracted in one file
-- Placeholders: %s = value passed in from Python (MySQL connector)
-- Table definitions, procedure, view and trigger are in schema.sql
-- ============================================================


-- ------------------------------------------------------------
-- INSERTS (db_sql.insert_organization / insert_request / insert_supply)
-- ------------------------------------------------------------

INSERT INTO organizations
    (org_name, org_type, contact_person, contact_phone, contact_email, zone)
VALUES (%s, %s, %s, %s, %s, %s);

INSERT INTO requests
    (org_id, resource_type, resource_name, quantity, unit, urgency, zone, description)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s);

INSERT INTO supplies
    (org_id, resource_type, resource_name, quantity, unit, zone)
VALUES (%s, %s, %s, %s, %s, %s);


-- ------------------------------------------------------------
-- LISTS (db_sql.get_all_organizations / get_all_requests / get_all_supplies)
-- ------------------------------------------------------------

SELECT org_id, org_name, zone
FROM organizations
WHERE is_active = TRUE;

SELECT * FROM requests ORDER BY created_at DESC;

SELECT * FROM supplies ORDER BY created_at DESC;


-- ------------------------------------------------------------
-- QUERY 1: full match report (four-table INNER JOIN)
-- db_sql.get_all_matches()
-- ------------------------------------------------------------

SELECT
    m.match_id, r.request_id, r.resource_name AS requested_item,
    r.quantity AS requested_qty, r.urgency,
    o1.org_name AS requesting_org, r.zone AS request_zone,
    s.supply_id, s.resource_name AS supplied_item,
    s.quantity AS available_qty,
    o2.org_name AS supplying_org, s.zone AS supply_zone,
    m.matched_qty, m.match_score, m.match_status
FROM matches m
INNER JOIN requests r      ON m.request_id = r.request_id
INNER JOIN supplies s      ON m.supply_id = s.supply_id
INNER JOIN organizations o1 ON r.org_id = o1.org_id
INNER JOIN organizations o2 ON s.org_id = o2.org_id
ORDER BY m.match_score DESC;


-- ------------------------------------------------------------
-- QUERY 2: zone summary (GROUP BY, LEFT JOIN, COALESCE, ROUND)
-- db_sql.get_zone_summary()
-- Only CONFIRMED matches count towards fulfilment.
-- ------------------------------------------------------------

SELECT r.zone,
       COUNT(DISTINCT r.request_id) AS total_requests,
       SUM(r.quantity) AS total_requested_qty,
       COUNT(DISTINCT m.match_id) AS total_matches,
       COALESCE(SUM(m.matched_qty), 0) AS total_matched_qty,
       ROUND((COALESCE(SUM(m.matched_qty), 0) / SUM(r.quantity)) * 100, 2) AS fulfillment_pct
FROM requests r
LEFT JOIN matches m
       ON r.request_id = m.request_id AND m.match_status = 'CONFIRMED'
GROUP BY r.zone
ORDER BY fulfillment_pct ASC;


-- ------------------------------------------------------------
-- QUERY 3: unmet requests (NOT IN sub-query, FIELD ordering)
-- db_sql.get_unmet_requests()
-- ------------------------------------------------------------

SELECT r.request_id, r.resource_name, r.quantity, r.urgency,
       o.org_name, r.zone, r.created_at
FROM requests r
INNER JOIN organizations o ON r.org_id = o.org_id
WHERE r.status = 'OPEN'
  AND r.request_id NOT IN (
      SELECT DISTINCT request_id
      FROM matches
      WHERE match_status = 'CONFIRMED'
  )
ORDER BY FIELD(r.urgency, 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'), r.created_at ASC;


-- ------------------------------------------------------------
-- QUERY 4: auto-match stored procedure
-- db_sql.run_auto_match()  (called with cursor.callproc)
-- ------------------------------------------------------------

CALL auto_match_requests();


-- ------------------------------------------------------------
-- QUERY 5: situation report view
-- db_sql.get_situation_report()
-- ------------------------------------------------------------

SELECT * FROM v_situation_report;


-- ------------------------------------------------------------
-- DISPATCH (db_sql.dispatch_supply)
-- Python reads the current quantity, computes the new value
-- (clamped at 0), then writes it. The trigger trg_supply_depleted
-- sets status = DEPLETED when the new quantity reaches zero.
-- ------------------------------------------------------------

SELECT quantity FROM supplies WHERE supply_id = %s;

UPDATE supplies SET quantity = %s WHERE supply_id = %s;

SELECT * FROM supplies WHERE supply_id = %s;
