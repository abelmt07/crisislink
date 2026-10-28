"""
models.py
---------
Dataclasses mirroring the four MySQL tables. Passed between main.py and db_sql.py.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Organization:
    org_id: Optional[int]
    org_name: str
    org_type: str
    contact_person: str
    contact_phone: str
    contact_email: str
    zone: str
    is_active: bool = True


@dataclass
class Request:
    request_id: Optional[int]
    org_id: int
    resource_type: str
    resource_name: str
    quantity: int
    unit: str
    urgency: str
    zone: str
    status: str = "OPEN"
    description: str = ""
    created_at: Optional[datetime] = None


@dataclass
class Supply:
    supply_id: Optional[int]
    org_id: int
    resource_type: str
    resource_name: str
    quantity: int
    unit: str
    zone: str
    status: str = "AVAILABLE"


@dataclass
class Match:
    match_id: Optional[int]
    request_id: int
    supply_id: int
    matched_qty: int
    match_score: float
    match_status: str = "PENDING"
