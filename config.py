"""
config.py
---------
Central configuration for CrisisLink.

Defaults point at the local Docker setup (docker compose up -d).
To use your own MySQL or MongoDB Atlas instead, change these values.
"""

# SQL (MySQL). Matches MYSQL_ROOT_PASSWORD in docker-compose.yml.
SQL_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "crisislink_docker_pw",
    "database": "crisislink",
}

# MongoDB. Local Docker instance by default.
# For Atlas: "mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/"
MONGO_CONFIG = {
    "uri": "mongodb://localhost:27017/",
    "database": "crisislink_nosql",
}
