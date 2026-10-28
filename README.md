<<<<<< HEAD
# CrisisLink — Disaster Resource Coordination Platform

A CLI app that helps NGOs, government agencies, and volunteer groups coordinate resource
requests and supplies during disasters, with automatic matching, an audit trail, and a live
situation report.

Built for **Database Concepts for Data Science Lab (TEE7423)**, ESE Mini-Project.

## SDG Alignment

**SDG 11: Sustainable Cities & Communities** (Target 11.5): reduces the time between a
shortage appearing on the ground and a matching supply being dispatched.

**SDG 17: Partnerships for the Goals** (Target 17.16): one shared schema connects NGOs,
government agencies, hospitals, and CSR teams.

## Quick Start (Docker, recommended)

Requires Docker Desktop and Python 3.10+.

```bash
docker compose up -d                  # starts MySQL 8 + MongoDB 6, loads schema and sample data
python -m venv venv
venv\Scripts\activate                 # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
python main.py
```

Stop with `docker compose down`. Add `-v` to also wipe the data.

Docker runs the scripts in `docker/mysql-init/` and `docker/mongo-init/` automatically on
first start.

### Using your own databases instead

Edit `config.py`:
- `SQL_CONFIG`: your MySQL host, user, and password. Then run
  `mysql -u root -p < docker/mysql-init/01_schema.sql` and `02_sample_data.sql`.
- `MONGO_CONFIG["uri"]`: your MongoDB Atlas string, e.g. `mongodb+srv://user:pass@cluster.mongodb.net/`.
  Then run `mongosh "<uri>" docker/mongo-init/01_setup.js`.

## Tech Stack

| Layer | Technology |
|---|---|
| SQL | MySQL 8.0 |
| NoSQL | MongoDB 6 |
| Language | Python 3.10+ |
| Connectors | `mysql-connector-python`, `pymongo` |
| UI | CLI menu |
| Testing | `unittest` |
| Logging | `logging` module → `logs/crisislink.log` |

## Database Schema

```
organizations (org_id PK, org_name, org_type, contact_person, contact_phone,
               contact_email, zone, is_active, created_at)
     |
     +--< requests (request_id PK, org_id FK, resource_type, resource_name,
     |              quantity, unit, urgency, zone, status, description, ...)
     |
     +--< supplies (supply_id PK, org_id FK, resource_type, resource_name,
                    quantity, unit, zone, status, created_at)

requests --< matches >-- supplies
matches (match_id PK, request_id FK, supply_id FK, matched_qty, match_score,
         match_status, matched_at)
```

### Normalization

- **1NF**: atomic columns, no repeating groups, every table has a primary key.
- **2NF**: no partial dependencies. In `matches`, `matched_qty` and `match_score` depend on
  the whole `match_id`.
- **3NF**: no transitive dependencies. `zone` is stored directly rather than derived.
- **BCNF**: every determinant is a candidate key. `UNIQUE(request_id, supply_id)` on
  `matches` prevents duplicate pairings.

This avoids insertion, update, and deletion anomalies.

## Advanced SQL

1. **Full match report**: 4-table `INNER JOIN`.
2. **Zone summary**: `GROUP BY` with `SUM`, `COUNT`, `ROUND`, `COALESCE`, and a `LEFT JOIN`.
3. **Unmet requests**: `NOT IN` sub-query, ordered by urgency via `FIELD()`.
4. **`auto_match_requests()`**: stored procedure that inserts scored matches.
5. **`v_situation_report`**: view for the per-zone dashboard.

Extra: **`trg_supply_depleted`**, a `BEFORE UPDATE` trigger that sets `status = 'DEPLETED'`
when quantity reaches zero. Exercised by menu option 14.

## MongoDB

- **`field_reports`**: free-text volunteer reports, indexed on `(zone, timestamp)`,
  `severity`, and `tags`.
- **`event_stream`**: audit log, indexed on `timestamp`, `(entity_type, entity_id)`, and `zone`.

Pipelines:
1. Zone-wise report summary: `$match`, `$group`, `$sort`, `$project`.
2. Critical reports with related events: `$match`, `$lookup`, `$size`, `$slice`.
3. Recent events feed: `$sort`, `$limit`, `$project`.

## Testing

```bash
python -m unittest test_validation.py -v
```

Covers the validators and the match-scoring function. No database required.

## Project Structure

```
crisislink/
├── main.py                  # CLI entry point and menu
├── db_sql.py                # MySQL operations
├── db_nosql.py              # MongoDB operations
├── models.py                # Dataclasses
├── matching.py              # Score logic (reference)
├── utils.py                 # Validation and logging
├── config.py                # Connection settings
├── test_validation.py       # Unit tests
├── requirements.txt
├── docker-compose.yml       # One-command MySQL + MongoDB
├── docker/
│   ├── mysql-init/          # schema + sample data (auto-loaded)
│   └── mongo-init/          # collections + sample docs (auto-loaded)
└── logs/                    # created at runtime
```

## Rubric Coverage

| Criteria | Marks | Covered by |
|---|---|---|
| Application design & functionality | 2 | Normalized 4-table schema, modular code, working CLI |
| Python programming | 2 | Dataclasses, functions, exception handling, file logging |
| Database integration | 2 | MySQL and MongoDB both driven from Python |
| Advanced querying | 2 | JOIN, GROUP BY, sub-query, procedure, view, 3 pipelines |
| Code quality & documentation | 1 | README, ER description, docstrings, comments |
| Testing & error handling | 1 | `unittest` suite, validation loops, try/except, logging |

## Author

Abel, B.Tech AIML, Symbiosis Institute of Technology, Pune
=======
# crisislink
Disaster resource coordination platform using MySQL and MongoDB. Matches relief requests to supplies with SQL procedures, triggers, and a Streamlit dashboard.
>>>>>>> 739a4fc12beecb090be0410f261c4d0eed26dcd7
