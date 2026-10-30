USE crisislink;

INSERT INTO organizations (org_name, org_type, contact_person, contact_phone, contact_email, zone) VALUES
('Goonj Foundation', 'NGO', 'Ravi Sharma', '9876543210', 'ravi@goonj.org', 'Zone-A'),
('NDRF Team 4', 'GOVT', 'Capt. Verma', '9876543211', 'verma@ndrf.gov.in', 'Zone-A'),
('Red Cross Pune', 'NGO', 'Priya Nair', '9876543212', 'priya@redcross.org', 'Zone-B'),
('Apollo Hospital', 'HOSPITAL', 'Dr. Mehta', '9876543213', 'mehta@apollo.com', 'Zone-B'),
('Tata CSR Team', 'CORPORATE', 'Anil Kumar', '9876543214', 'anil@tata.com', 'Zone-C');

INSERT INTO requests (org_id, resource_type, resource_name, quantity, unit, urgency, zone, description) VALUES
(1, 'FOOD', 'Cooked Meal Packets', 500, 'packets', 'CRITICAL', 'Zone-A', 'For flood-affected families in Pune'),
(1, 'WATER', 'Drinking Water Cans', 200, 'cans', 'CRITICAL', 'Zone-A', 'Clean water shortage'),
(2, 'MEDICINE', 'First Aid Kits', 100, 'kits', 'HIGH', 'Zone-A', 'For injured victims'),
(3, 'SHELTER', 'Tarpaulin Sheets', 300, 'sheets', 'HIGH', 'Zone-B', 'Temporary shelter'),
(3, 'CLOTHING', 'Blankets', 400, 'units', 'MEDIUM', 'Zone-B', 'For cold nights'),
(4, 'MEDICINE', 'Insulin Vials', 50, 'vials', 'CRITICAL', 'Zone-B', 'For diabetic patients'),
(5, 'FOOD', 'Baby Food', 150, 'packets', 'HIGH', 'Zone-C', 'For infants'),
(1, 'EQUIPMENT', 'Water Pumps', 10, 'units', 'MEDIUM', 'Zone-A', 'For draining water');

INSERT INTO supplies (org_id, resource_type, resource_name, quantity, unit, zone) VALUES
(1, 'FOOD', 'Cooked Meal Packets', 300, 'packets', 'Zone-A'),
(1, 'WATER', 'Drinking Water Cans', 500, 'cans', 'Zone-A'),
(3, 'MEDICINE', 'First Aid Kits', 200, 'kits', 'Zone-B'),
(3, 'SHELTER', 'Tarpaulin Sheets', 150, 'sheets', 'Zone-B'),
(5, 'CLOTHING', 'Blankets', 600, 'units', 'Zone-C'),
(5, 'FOOD', 'Baby Food', 100, 'packets', 'Zone-C'),
(2, 'EQUIPMENT', 'Water Pumps', 15, 'units', 'Zone-A'),
(4, 'MEDICINE', 'Insulin Vials', 80, 'vials', 'Zone-B');

CALL auto_match_requests();

