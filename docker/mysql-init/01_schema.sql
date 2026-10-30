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
    status          ENUM('OPEN', 'MATCHED', 'DISPATCHED', 'DELIVERED', 'CANCELLED') DEFAULT 'OPEN',
    description     TEXT,
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
    match_score     DECIMAL(5,2) NOT NULL,
    match_status    ENUM('PENDING', 'CONFIRMED', 'REJECTED', 'COMPLETED') DEFAULT 'PENDING',
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
    AND m.match_status IN ('PENDING', 'CONFIRMED')
WHERE r.status != 'DELIVERED'
GROUP BY r.zone
ORDER BY critical_requests DESC, open_requests DESC;

DELIMITER //

CREATE PROCEDURE auto_match_requests()
BEGIN
    INSERT INTO matches (request_id, supply_id, matched_qty, match_score, match_status)
    SELECT
        r.request_id,
        s.supply_id,
        LEAST(r.quantity, s.quantity),
        CASE WHEN s.zone = r.zone THEN 90 ELSE 60 END
          + CASE r.urgency WHEN 'CRITICAL' THEN 10 WHEN 'HIGH' THEN 5 ELSE 0 END AS score,
        'PENDING'
    FROM requests r
    INNER JOIN supplies s ON r.resource_type = s.resource_type
    WHERE r.status = 'OPEN'
    AND s.status = 'AVAILABLE'
    AND s.quantity > 0
    AND NOT EXISTS (SELECT 1 FROM matches m WHERE m.request_id = r.request_id)
    ORDER BY
        FIELD(r.urgency, 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'),
        CASE WHEN s.zone = r.zone THEN 0 ELSE 1 END
    LIMIT 10;

    UPDATE requests
    SET status = 'MATCHED'
    WHERE request_id IN (SELECT DISTINCT request_id FROM matches)
    AND status = 'OPEN';

    SELECT ROW_COUNT() AS matches_created;
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

CREATE USER IF NOT EXISTS 'crisislink_admin'@'%' IDENTIFIED BY 'admin_pass_123';
GRANT ALL PRIVILEGES ON crisislink.* TO 'crisislink_admin'@'%';

CREATE USER IF NOT EXISTS 'crisislink_org'@'%' IDENTIFIED BY 'org_pass_123';
GRANT SELECT, INSERT, UPDATE ON crisislink.requests TO 'crisislink_org'@'%';
GRANT SELECT, INSERT, UPDATE ON crisislink.supplies TO 'crisislink_org'@'%';
GRANT SELECT ON crisislink.matches TO 'crisislink_org'@'%';

FLUSH PRIVILEGES;
