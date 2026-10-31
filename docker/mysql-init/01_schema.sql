-- ============================================
-- CrisisLink SQL Schema
-- ============================================
CREATE DATABASE IF NOT EXISTS crisislink;
USE crisislink;

CREATE TABLE organizations (
    org_id          INT PRIMARY KEY AUTO_INCREMENT,
    org_name        VARCHAR(150) NOT NULL UNIQUE,
    org_type        ENUM('NGO', 'GOVT', 'VOLUNTEER', 'HOSPITAL', 'CORPORATE') NOT NULL,
    contact_person  VARCHAR(100) NOT NULL,
    contact_phone   VARCHAR(15) NOT NULL,
    contact_email   VARCHAR(100) NOT NULL UNIQUE,
    zone            VARCHAR(50) NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE requests (
    request_id      INT PRIMARY KEY AUTO_INCREMENT,
    org_id          INT NOT NULL,
    resource_type   ENUM('FOOD', 'MEDICINE', 'WATER', 'SHELTER', 'CLOTHING', 'EQUIPMENT', 'OTHER') NOT NULL,
    resource_name   VARCHAR(200) NOT NULL,
    quantity        INT NOT NULL CHECK (quantity > 0),
    unit            VARCHAR(20) DEFAULT 'units',
    urgency         ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL') NOT NULL,
    zone            VARCHAR(50) NOT NULL,
    status          ENUM('OPEN', 'MATCHED', 'PARTIAL', 'DISPATCHED', 'DELIVERED', 'CANCELLED') DEFAULT 'OPEN',    description     TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(org_id),
    INDEX idx_status_urgency (status, urgency),
    INDEX idx_zone (zone)
);

CREATE TABLE supplies (
    supply_id       INT PRIMARY KEY AUTO_INCREMENT,
    org_id          INT NOT NULL,
    resource_type   ENUM('FOOD', 'MEDICINE', 'WATER', 'SHELTER', 'CLOTHING', 'EQUIPMENT', 'OTHER') NOT NULL,
    resource_name   VARCHAR(200) NOT NULL,
    quantity        INT NOT NULL CHECK (quantity >= 0),
    unit            VARCHAR(20) DEFAULT 'units',
    zone            VARCHAR(50) NOT NULL,
    status          ENUM('AVAILABLE', 'RESERVED', 'DISPATCHED', 'DEPLETED') DEFAULT 'AVAILABLE',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(org_id),
    INDEX idx_status_zone (status, zone),
    INDEX idx_resource_type (resource_type)
);

CREATE TABLE matches (
    match_id        INT PRIMARY KEY AUTO_INCREMENT,
    request_id      INT NOT NULL,
    supply_id       INT NOT NULL,
    matched_qty     INT NOT NULL,
    shortfall_qty   INT NOT NULL DEFAULT 0,
    match_score     DECIMAL(5,2) NOT NULL,
    match_status    ENUM('PENDING', 'CONFIRMED', 'DISPATCHED', 'REJECTED', 'COMPLETED') DEFAULT 'PENDING',    
    matched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (request_id) REFERENCES requests(request_id),
    FOREIGN KEY (supply_id) REFERENCES supplies(supply_id),
    INDEX idx_status (match_status),
    UNIQUE KEY uk_request_supply (request_id, supply_id)
);

CREATE VIEW v_situation_report AS
SELECT
    r.zone,
    COUNT(DISTINCT r.request_id) AS open_requests,
    COUNT(DISTINCT CASE WHEN r.urgency = 'CRITICAL' THEN r.request_id END) AS critical_requests,
    COUNT(DISTINCT m.match_id) AS active_matches,
    COALESCE(SUM(m.matched_qty), 0) AS total_matched_qty
FROM requests r
LEFT JOIN matches m ON r.request_id = m.request_id
    AND m.match_status <> 'REJECTED'
WHERE r.status NOT IN ('DELIVERED', 'CANCELLED')
GROUP BY r.zone
ORDER BY critical_requests DESC, open_requests DESC;

DELIMITER //

CREATE PROCEDURE auto_match_requests()
BEGIN
    DECLARE done INT DEFAULT FALSE;
    DECLARE v_req_id INT;
    DECLARE v_req_zone VARCHAR(50);
    DECLARE v_urgency VARCHAR(10);
    DECLARE v_orig_qty INT;
    DECLARE v_remaining INT;
    DECLARE v_type VARCHAR(20);
    DECLARE v_sup_id INT;
    DECLARE v_sup_zone VARCHAR(50);
    DECLARE v_sup_qty INT;
    DECLARE v_alloc INT;

        DECLARE req_cur CURSOR FOR
        SELECT r.request_id, r.zone, r.urgency, r.quantity,
               r.quantity - COALESCE((SELECT SUM(m.matched_qty) FROM matches m
                                      WHERE m.request_id = r.request_id
                                        AND m.match_status <> 'REJECTED'), 0),
               r.resource_type
        FROM requests r
        WHERE r.status IN ('OPEN', 'PARTIAL')
          AND r.quantity > COALESCE((SELECT SUM(m.matched_qty) FROM matches m
                                     WHERE m.request_id = r.request_id
                                       AND m.match_status <> 'REJECTED'), 0)
        ORDER BY FIELD(r.urgency, 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'), r.request_id;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;

    OPEN req_cur;
    req_loop: LOOP
        FETCH req_cur INTO v_req_id, v_req_zone, v_urgency, v_orig_qty, v_remaining, v_type;
        IF done THEN
            LEAVE req_loop;
        END IF;

        fill_loop: WHILE v_remaining > 0 DO
            SET v_sup_id = NULL;
            BEGIN
                DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_sup_id = NULL;
                SELECT supply_id, zone, quantity INTO v_sup_id, v_sup_zone, v_sup_qty
                FROM supplies
                WHERE resource_type = v_type
                  AND status = 'AVAILABLE'
                  AND quantity > 0
                  AND NOT EXISTS (SELECT 1 FROM matches m
                                  WHERE m.request_id = v_req_id
                                    AND m.supply_id = supplies.supply_id
                                    AND m.match_status = 'REJECTED')
                ORDER BY
                    (CASE WHEN zone = v_req_zone THEN 50 ELSE 10 END
                     + CASE WHEN quantity >= v_orig_qty THEN 20
                            ELSE 20 * quantity / NULLIF(v_orig_qty, 0) END) DESC,
                    supply_id
                LIMIT 1;
            END;

            IF v_sup_id IS NULL THEN
                LEAVE fill_loop;
            END IF;

            SET v_alloc = LEAST(v_remaining, v_sup_qty);

            INSERT INTO matches (request_id, supply_id, matched_qty, match_score, match_status)
            VALUES (
                v_req_id,
                v_sup_id,
                v_alloc,
                ROUND(
                    CASE WHEN v_sup_zone = v_req_zone THEN 50 ELSE 10 END
                    + CASE v_urgency WHEN 'CRITICAL' THEN 30 WHEN 'HIGH' THEN 20
                                     WHEN 'MEDIUM' THEN 10 WHEN 'LOW' THEN 5 ELSE 0 END
                    + CASE WHEN v_sup_qty >= v_orig_qty THEN 20
                           ELSE 20 * v_sup_qty / NULLIF(v_orig_qty, 0) END
                , 2),
                'PENDING'
            );

            UPDATE supplies
            SET status = IF(quantity - v_alloc <= 0, 'DEPLETED', status),
                quantity = quantity - v_alloc
            WHERE supply_id = v_sup_id;

            SET v_remaining = v_remaining - v_alloc;
        END WHILE;

                    UPDATE requests r
        SET r.status = CASE
            WHEN COALESCE((SELECT SUM(m.matched_qty) FROM matches m
                           WHERE m.request_id = r.request_id
                             AND m.match_status <> 'REJECTED'), 0) >= r.quantity
            THEN 'MATCHED' ELSE 'PARTIAL' END
        WHERE r.request_id = v_req_id
          AND EXISTS (SELECT 1 FROM matches m
                      WHERE m.request_id = r.request_id
                        AND m.match_status <> 'REJECTED');
    END LOOP;
    CLOSE req_cur;
END //

CREATE TRIGGER trg_supply_depleted
BEFORE UPDATE ON supplies
FOR EACH ROW
BEGIN
    IF NEW.quantity <= 0 THEN
        SET NEW.quantity = 0;
        SET NEW.status = 'DEPLETED';
    END IF;
END //

DELIMITER ;
