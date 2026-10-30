"""
config.py
---------
Central configuration for CrisisLink.

Values are read in this order:
1. Environment variables (your .env file or the shell)
2. Streamlit secrets (when deployed on Streamlit Community Cloud)
3. The local Docker defaults below
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _setting(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        try:
            import streamlit as st
            value = st.secrets.get(name)
        except Exception:
            value = None
    return value if value is not None else default


SQL_CONFIG = {
    "host": _setting("MYSQL_HOST", "localhost"),
    "port": int(_setting("MYSQL_PORT", "3306")),
    "user": _setting("MYSQL_USER", "root"),
    "password": _setting("MYSQL_PASSWORD", ""),
    "database": "crisislink",
    "ssl_disabled": False,
}

MONGO_CONFIG = {
    "uri": _setting("MONGO_URI", "mongodb://localhost:27017/"),
    "database": _setting("MONGO_DB", "crisislink_nosql"),
}