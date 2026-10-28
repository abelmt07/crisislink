"""
matching.py
-----------
Python version of the scoring idea used in the MySQL procedure. Useful for
explaining the score logic in a viva without opening the database.
"""


def calculate_match_score(request_zone, supply_zone, urgency, req_qty, sup_qty) -> float:
    """
    Return a match score out of 100.

    - Zone proximity (max 50): same zone is worth far more than cross-zone,
      because transport time matters most during a disaster.
    - Urgency (max 30): CRITICAL requests score highest so they surface first.
    - Quantity coverage (max 20): how much of the request one supply can cover.
    """
    score = 0

    # Zone proximity
    score += 50 if request_zone == supply_zone else 10

    # Urgency
    urgency_map = {"CRITICAL": 30, "HIGH": 20, "MEDIUM": 10, "LOW": 5}
    score += urgency_map.get(urgency.upper(), 0)

    # Quantity coverage
    if sup_qty >= req_qty:
        score += 20
    else:
        score += (sup_qty / req_qty) * 20

    return round(score, 2)
