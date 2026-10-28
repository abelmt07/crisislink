// Runs automatically on first container start (mongo:6 docker-entrypoint-initdb.d).
// Also runnable manually: mongosh "<uri>" docker/mongo-init/01_setup.js
db = db.getSiblingDB("crisislink_nosql");

db.field_reports.createIndex({ zone: 1, timestamp: -1 });
db.field_reports.createIndex({ severity: 1 });
db.field_reports.createIndex({ tags: 1 });

db.field_reports.insertMany([
  {
    report_id: "FR-2026-001", org_id: 1, org_name: "Goonj Foundation",
    zone: "Zone-A", district: "Pune", report_type: "SITUATION", severity: "CRITICAL",
    description: "Water levels rising in low-lying areas. 200 families stranded. Urgent need for boats and drinking water.",
    reported_by: "Ravi Sharma", timestamp: new Date("2026-10-26T08:30:00Z"),
    tags: ["flood", "rescue", "water"]
  },
  {
    report_id: "FR-2026-002", org_id: 3, org_name: "Red Cross Pune",
    zone: "Zone-B", district: "Mumbai", report_type: "MEDICAL", severity: "HIGH",
    description: "Shortage of insulin and first aid supplies at relief camp.",
    reported_by: "Priya Nair", timestamp: new Date("2026-10-26T09:00:00Z"),
    tags: ["medical", "insulin", "shortage"]
  },
  {
    report_id: "FR-2026-003", org_id: 2, org_name: "NDRF Team 4",
    zone: "Zone-A", district: "Pune", report_type: "DAMAGE", severity: "HIGH",
    description: "Bridge collapsed near river. Access road blocked.",
    reported_by: "Capt. Verma", timestamp: new Date("2026-10-26T10:15:00Z"),
    tags: ["infrastructure", "bridge", "blocked"]
  }
]);

db.event_stream.createIndex({ timestamp: -1 });
db.event_stream.createIndex({ entity_type: 1, entity_id: 1 });
db.event_stream.createIndex({ zone: 1 });

db.event_stream.insertMany([
  {
    event_id: "EV-2026-001", entity_type: "REQUEST", entity_id: 1, action: "CREATED",
    actor_org_id: 1, actor_name: "Goonj Foundation",
    details: { resource_name: "Cooked Meal Packets", quantity: 500, urgency: "CRITICAL" },
    timestamp: new Date("2026-10-26T08:00:00Z"), zone: "Zone-A"
  },
  {
    event_id: "EV-2026-002", entity_type: "MATCH", entity_id: 1, action: "CREATED",
    actor_org_id: 1, actor_name: "System",
    details: { request_id: 1, supply_id: 1, matched_qty: 300, score: 85.5 },
    timestamp: new Date("2026-10-26T08:05:00Z"), zone: "Zone-A"
  },
  {
    event_id: "EV-2026-003", entity_type: "SUPPLY", entity_id: 3, action: "CREATED",
    actor_org_id: 3, actor_name: "Red Cross Pune",
    details: { resource_name: "First Aid Kits", quantity: 200 },
    timestamp: new Date("2026-10-26T08:30:00Z"), zone: "Zone-B"
  }
]);
