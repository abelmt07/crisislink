# CrisisLink: Disaster Resource Coordination Platform

CrisisLink helps NGOs, government agencies, and volunteer groups coordinate resource requests and supplies during disasters. It matches requests to available supplies automatically, scores each match, tracks stock as it's allocated, and shows a live situation report.

Built for **Database Concepts for Data Science Lab (TEE7423)**, ESE Mini-Project.

**Live demo:** https://https://crisislink.streamlit.app/
## SDG Alignment

- **SDG 11: Sustainable Cities & Communities (Target 11.5):** reduces the time between a shortage appearing on the ground and a matching supply being dispatched.
- **SDG 17: Partnerships for the Goals (Target 17.16):** one shared schema connects NGOs, government agencies, hospitals, and CSR teams.

## Features

- Organizations post resource requests and supplies, each with a zone and urgency.
- `auto_match_requests()` matches open requests to available supplies, most urgent first.
- Each match gets a score out of 100 (see [Match Scoring](#match-scoring)).
- Supply stock is reduced as it's allocated, so the same stock can't be promised twice.
- Requests are marked `MATCHED` when fully covered and `PARTIAL` when partly covered.
- A per-zone situation report summarizes requested vs. matched quantities.
- Free-text field reports and an audit event stream are stored in MongoDB.

## Quick Start (Docker, recommended)

Requires Docker Desktop and Python 3.10+.

### 1. Create the `.env` file

In the project root, create a file named `.env`:

```
MYSQL_USER=root
MYSQL_PASSWORD=choose_a_password
MYSQL_HOST=localhost
MYSQL_PORT=3306
MONGO_URI=mongodb://localhost:27017
MONGO_DB=crisislink
```

`.env` holds local credentials and is listed in `.gitignore`. Don't commit it.

### 2. Start the databases

```bash
docker compose up -d
```

This starts MySQL 8 and MongoDB 6, and loads the schema and sample data automatically on first start. The scripts in `docker/mysql-init/` and `docker/mongo-init/` run only when the database volume is created. To rebuild from scratch, run `docker compose down -v` first.

### 3. Set up Python

```bash
python -m venv venv
venv\Scripts\activate                 # Windows (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
```

### 4. Run the app

```bash
streamlit run app.py
```

## Using Your Own Databases

- **MySQL:** set the values in `.env` to point at your server, then run `mysql -u root -p < docker/mysql-init/01_schema.sql` followed by `02_sample_data.sql`.
- **MongoDB Atlas:** set `MONGO_URI` in `.env` to your connection string, for example `mongodb+srv://user:pass@cluster.mongodb.net/`. Then run `mongosh "<uri>" docker/mongo-init/01_setup.js`.

## Tech Stack

| Layer | Technology |
|---|---|
| SQL | MySQL 8.0 |
| NoSQL | MongoDB 6 |
| Language | Python 3.10+ |
| Connectors | `mysql-connector-python`, `pymongo`, `python-dotenv` |
| UI | Streamlit dashboard |
| Testing | `unittest` |
| Logging | `logging` module, written to `logs/crisislink.log` |

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

**Status values**

- `requests.status`: `OPEN`, `MATCHED`, `PARTIAL`, `DISPATCHED`, `DELIVERED`, `CANCELLED`
- `supplies.status`: `AVAILABLE`, `RESERVED`, `DISPATCHED`, `DEPLETED`
- `matches.match_status`: `PENDING`, `CONFIRMED`, `REJECTED`, `COMPLETED`

### Normalization

- **1NF:** atomic columns, no repeating groups, every table has a primary key.
- **2NF:** `matches` uses a single-column primary key, so no non-key column can depend on part of a composite key.
- **3NF:** no transitive dependencies. `zone` is stored directly on each row rather than derived.
- **BCNF:** every determinant is a candidate key. `UNIQUE(request_id, supply_id)` on `matches` prevents duplicate pairings.

This avoids insertion, update, and deletion anomalies.

## Advanced SQL

1. **Full match report:** 4-table `INNER JOIN`.
2. **Zone summary:** `GROUP BY` with `SUM`, `COUNT`, `ROUND`, `COALESCE`, and a `LEFT JOIN`.
3. **Unmet requests:** `NOT IN` sub-query, ordered by urgency using `FIELD()`.
4. **`auto_match_requests()`:** stored procedure that allocates stock to OPEN requests, most urgent first (see [Matching](#matching)).
5. **`v_situation_report`:** view for the per-zone dashboard.

**Extra:** `trg_supply_depleted`, a `BEFORE UPDATE` trigger that sets `status = 'DEPLETED'` when a supply's quantity reaches zero.

## Matching

`auto_match_requests()` runs as follows:

1. Selects OPEN requests, ordered by urgency (CRITICAL, HIGH, MEDIUM, LOW), then by `request_id`.
2. For each request, repeatedly picks the best available supply of the same `resource_type` with stock left, and allocates `MIN(remaining request, supply quantity)`.
3. Inserts a scored match for each allocation and reduces the supply's quantity. A supply with zero quantity left is marked `DEPLETED`.
4. Sets the request to `MATCHED` if fully covered, or `PARTIAL` if partly covered. A request with no allocation stays `OPEN`.

Because requests are processed in urgency order, a CRITICAL request can use up stock before a HIGH request gets to it. This is intended.

### Match Scoring

Each match scores out of 100:

- **Zone:** 50 if the request and supply are in the same zone, otherwise 10.
- **Urgency:** CRITICAL 30, HIGH 20, MEDIUM 10, LOW 5.
- **Quantity coverage:** 20 if the supply covers the full request, otherwise 20 × (supply ÷ request).

`matching.py` implements the same rules, and `test_validation.py` checks them. The stored procedure and the Python function produce the same scores for the same inputs.

## Known Limitations

- Later runs of `auto_match_requests()` don't top up `PARTIAL` requests. Only `OPEN` requests are considered.
- Matches are created as `PENDING`. Confirming or rejecting a match isn't yet part of the procedure.
- Scores reflect zone, urgency, and quantity only. Distance, transport time, and supply expiry aren't modeled.

## MongoDB

- **`field_reports`:** free-text volunteer reports, indexed on `(zone, timestamp)`, `severity`, and `tags`.
- **`event_stream`:** audit log, indexed on `timestamp`, `(entity_type, entity_id)`, and `zone`.

Pipelines:

1. Zone-wise report summary: `$match`, `$group`, `$sort`, `$project`.
2. Critical reports with related events: `$match`, `$lookup`, `$size`, `$slice`.
3. Recent events feed: `$sort`, `$limit`, `$project`.

## Testing

```bash
python -m unittest test_validation -v
```

Covers the validators and the match-scoring function. Runs without a database. Expected result: 14 tests, `OK`.

## Project Structure

```
crisislink/
├── app.py                   # Streamlit dashboard
├── db_sql.py                # MySQL operations
├── db_nosql.py              # MongoDB operations
├── models.py                # Dataclasses
├── matching.py              # Score logic (reference, same rules as auto_match_requests)
├── utils.py                 # Validation and logging
├── config.py                # Connection settings (reads from .env)
├── test_validation.py       # Unit tests
├── requirements.txt
├── docker-compose.yml       # MySQL + MongoDB containers
├── docker/
│   ├── mysql-init/          # schema + sample data (auto-loaded)
│   └── mongo-init/          # collections + sample docs (auto-loaded)
└── logs/                    # created at runtime
```
