"""
main.py
-------
CrisisLink CLI entry point. Run with: python main.py
"""

import logging
from datetime import datetime

import db_nosql
import db_sql
from models import Organization, Request, Supply
from utils import (
    get_valid_input,
    new_event_id,
    new_report_id,
    setup_logging,
    validate_email,
    validate_enum,
    validate_phone,
    validate_positive_int,
)

RESOURCE_TYPES = ["FOOD", "MEDICINE", "WATER", "SHELTER", "CLOTHING", "EQUIPMENT", "OTHER"]
URGENCY_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ORG_TYPES = ["NGO", "GOVT", "VOLUNTEER", "HOSPITAL", "CORPORATE"]


def print_menu():
    """Print the numbered main menu."""
    print("\n" + "=" * 50)
    print("       CRISISLINK -- MAIN MENU")
    print("=" * 50)
    print("1.  Add Organization")
    print("2.  Add Request")
    print("3.  Add Supply")
    print("4.  Run Auto-Match")
    print("5.  View All Requests")
    print("6.  View All Supplies")
    print("7.  View All Matches")
    print("8.  View Situation Report")
    print("9.  View Unmet Requests")
    print("10. View Zone Summary")
    print("11. Add Field Report (MongoDB)")
    print("12. View Field Reports by Zone (MongoDB)")
    print("13. View Recent Events (MongoDB)")
    print("14. Dispatch Supply (exercises trg_supply_depleted)")
    print("0.  Exit")
    print("=" * 50)


def _show_orgs():
    """Print the org list so the user can pick an org_id."""
    for o in db_sql.get_all_organizations():
        print(f"  {o['org_id']}. {o['org_name']} ({o['zone']})")


def add_organization():
    """Prompt for organization details and insert them into MySQL."""
    print("\n--- Add Organization ---")
    name = input("Name: ").strip()
    org_type = get_valid_input(f"Type {ORG_TYPES}: ", lambda x: validate_enum(x, ORG_TYPES),
                               "Invalid type", str.upper)
    contact = input("Contact person: ").strip()
    phone = get_valid_input("Phone (10 digits): ", validate_phone, "Invalid phone")
    email = get_valid_input("Email: ", validate_email, "Invalid email")
    zone = input("Zone (e.g., Zone-A): ").strip()
    try:
        org_id = db_sql.insert_organization(
            Organization(None, name, org_type, contact, phone, email, zone))
        print(f"  + Organization added with ID {org_id}")
        logging.info(f"Org added: {name}")
    except Exception as e:
        print(f"  x Error: {e}")
        logging.error(f"Failed to add org: {e}")


def add_request():
    """Prompt for a resource request and insert it, logging an event to MongoDB."""
    print("\n--- Add Request ---")
    _show_orgs()
    org_id = get_valid_input("Org ID: ", validate_positive_int, "Invalid ID", int)
    rtype = get_valid_input(f"Resource type {RESOURCE_TYPES}: ",
                            lambda x: validate_enum(x, RESOURCE_TYPES), "Invalid type", str.upper)
    rname = input("Resource name: ").strip()
    qty = get_valid_input("Quantity: ", validate_positive_int, "Invalid quantity", int)
    unit = input("Unit (e.g., packets): ").strip() or "units"
    urgency = get_valid_input(f"Urgency {URGENCY_LEVELS}: ",
                              lambda x: validate_enum(x, URGENCY_LEVELS), "Invalid urgency", str.upper)
    zone = input("Zone: ").strip()
    desc = input("Description: ").strip()
    try:
        req_id = db_sql.insert_request(
            Request(None, org_id, rtype, rname, qty, unit, urgency, zone, "OPEN", desc))
        print(f"  + Request added with ID {req_id}")
        db_nosql.insert_event({
            "event_id": new_event_id(), "entity_type": "REQUEST", "entity_id": req_id,
            "action": "CREATED", "actor_org_id": org_id, "actor_name": "User",
            "details": {"resource_name": rname, "quantity": qty, "urgency": urgency},
            "timestamp": datetime.now(), "zone": zone,
        })
    except Exception as e:
        print(f"  x Error: {e}")
        logging.error(f"Failed to add request: {e}")


def add_supply():
    """Prompt for a supply listing and insert it, logging an event to MongoDB."""
    print("\n--- Add Supply ---")
    _show_orgs()
    org_id = get_valid_input("Org ID: ", validate_positive_int, "Invalid ID", int)
    rtype = get_valid_input(f"Resource type {RESOURCE_TYPES}: ",
                            lambda x: validate_enum(x, RESOURCE_TYPES), "Invalid type", str.upper)
    rname = input("Resource name: ").strip()
    qty = get_valid_input("Quantity: ", validate_positive_int, "Invalid quantity", int)
    unit = input("Unit: ").strip() or "units"
    zone = input("Zone: ").strip()
    try:
        sup_id = db_sql.insert_supply(Supply(None, org_id, rtype, rname, qty, unit, zone))
        print(f"  + Supply added with ID {sup_id}")
        db_nosql.insert_event({
            "event_id": new_event_id(), "entity_type": "SUPPLY", "entity_id": sup_id,
            "action": "CREATED", "actor_org_id": org_id, "actor_name": "User",
            "details": {"resource_name": rname, "quantity": qty},
            "timestamp": datetime.now(), "zone": zone,
        })
    except Exception as e:
        print(f"  x Error: {e}")
        logging.error(f"Failed to add supply: {e}")


def run_auto_match():
    """Call the auto-match stored procedure and report how many matches it created."""
    print("\n--- Run Auto-Match ---")
    try:
        print(f"  + {db_sql.run_auto_match()} matches created")
    except Exception as e:
        print(f"  x Error: {e}")
        logging.error(f"Auto-match failed: {e}")


def view_requests():
    """List every request."""
    print("\n--- All Requests ---")
    rows = db_sql.get_all_requests()
    if not rows:
        print("  No requests found.")
    for r in rows:
        print(f"  [{r['request_id']}] {r['resource_name']} x{r['quantity']} "
              f"| {r['urgency']} | {r['zone']} | {r['status']}")


def view_supplies():
    """List every supply."""
    print("\n--- All Supplies ---")
    rows = db_sql.get_all_supplies()
    if not rows:
        print("  No supplies found.")
    for s in rows:
        print(f"  [{s['supply_id']}] {s['resource_name']} x{s['quantity']} "
              f"| {s['zone']} | {s['status']}")


def view_matches():
    """Show the full 4-table match report."""
    print("\n--- All Matches ---")
    rows = db_sql.get_all_matches()
    if not rows:
        print("  No matches found.")
    for m in rows:
        print(f"  Match {m['match_id']}: {m['requested_item']} ({m['requesting_org']}) "
              f"<- {m['supplied_item']} ({m['supplying_org']}) "
              f"| Qty: {m['matched_qty']} | Score: {m['match_score']} | {m['match_status']}")


def view_situation_report():
    """Print the v_situation_report view as a table."""
    print("\n--- Situation Report ---")
    rows = db_sql.get_situation_report()
    if not rows:
        print("  No data.")
        return
    print(f"  {'Zone':<10} {'Open':<6} {'Critical':<10} {'Matches':<10} {'Matched Qty':<12}")
    for r in rows:
        print(f"  {r['zone']:<10} {r['open_requests']:<6} {r['critical_requests']:<10} "
              f"{r['active_matches']:<10} {r['total_matched_qty']:<12}")


def view_unmet():
    """List open requests that have no confirmed match."""
    print("\n--- Unmet Requests ---")
    rows = db_sql.get_unmet_requests()
    if not rows:
        print("  All requests met!")
    for r in rows:
        print(f"  [{r['request_id']}] {r['resource_name']} x{r['quantity']} "
              f"| {r['urgency']} | {r['org_name']} | {r['zone']}")


def view_zone_summary():
    """Print the per-zone fulfilment summary."""
    print("\n--- Zone Summary ---")
    rows = db_sql.get_zone_summary()
    if not rows:
        print("  No data.")
    for r in rows:
        print(f"  {r['zone']}: {r['total_requests']} requests, "
              f"{r['total_matched_qty']} matched ({r['fulfillment_pct']}%)")


def add_field_report():
    """Prompt for a field report and store it in MongoDB."""
    print("\n--- Add Field Report ---")
    org_id = get_valid_input("Org ID: ", validate_positive_int, "Invalid", int)
    zone = input("Zone: ").strip()
    district = input("District: ").strip()
    rtype = input("Report type (SITUATION/MEDICAL/DAMAGE/RESOURCE): ").strip().upper()
    severity = get_valid_input("Severity (LOW/MEDIUM/HIGH/CRITICAL): ",
                               lambda x: validate_enum(x, URGENCY_LEVELS), "Invalid", str.upper)
    desc = input("Description: ").strip()
    reporter = input("Reported by: ").strip()
    report = {
        "report_id": new_report_id(), "org_id": org_id, "org_name": "User",
        "zone": zone, "district": district, "report_type": rtype, "severity": severity,
        "description": desc, "reported_by": reporter,
        "timestamp": datetime.now(), "tags": [],
    }
    try:
        print(f"  + Field report added: {db_nosql.insert_field_report(report)}")
    except Exception as e:
        print(f"  x Error: {e}")
        logging.error(f"Failed to add field report: {e}")


def view_field_reports_by_zone():
    """Show the MongoDB zone summary pipeline output."""
    print("\n--- Field Reports by Zone ---")
    rows = db_nosql.get_field_reports_by_zone()
    if not rows:
        print("  No data.")
    for r in rows:
        print(f"  {r['zone']}: {r['total_reports']} reports "
              f"({r['critical_reports']} critical) | Types: {r['report_types']}")


def view_recent_events():
    """Show the 10 most recent audit events from MongoDB."""
    print("\n--- Recent Events ---")
    rows = db_nosql.get_recent_events(10)
    if not rows:
        print("  No events yet.")
    for e in rows:
        print(f"  [{e['timestamp']}] {e['entity_type']} #{e['entity_id']} "
              f"{e['action']} by {e['actor_name']} ({e['zone']})")


def dispatch_supply():
    """Reduce a supply's quantity; the DB trigger flips status to DEPLETED at zero."""
    print("\n--- Dispatch Supply ---")
    for s in db_sql.get_all_supplies():
        print(f"  [{s['supply_id']}] {s['resource_name']} -- {s['quantity']} {s['unit']} "
              f"({s['status']})")
    supply_id = get_valid_input("Supply ID: ", validate_positive_int, "Invalid ID", int)
    qty = get_valid_input("Quantity to dispatch: ", validate_positive_int, "Invalid", int)
    try:
        updated = db_sql.dispatch_supply(supply_id, qty)
        print(f"  + Supply {supply_id}: {updated['quantity']} {updated['unit']} left, "
              f"status {updated['status']}")
        if updated["status"] == "DEPLETED":
            print("  (trg_supply_depleted fired: quantity hit zero)")
    except Exception as e:
        print(f"  x Error: {e}")
        logging.error(f"Dispatch failed: {e}")


ACTIONS = {
    "1": add_organization,
    "2": add_request,
    "3": add_supply,
    "4": run_auto_match,
    "5": view_requests,
    "6": view_supplies,
    "7": view_matches,
    "8": view_situation_report,
    "9": view_unmet,
    "10": view_zone_summary,
    "11": add_field_report,
    "12": view_field_reports_by_zone,
    "13": view_recent_events,
    "14": dispatch_supply,
}


def main():
    """Run the menu loop until the user chooses Exit."""
    setup_logging()
    logging.info("CrisisLink started")
    while True:
        print_menu()
        choice = input("Enter choice: ").strip()
        if choice == "0":
            print("Goodbye!")
            break
        action = ACTIONS.get(choice)
        if action is None:
            print("  x Invalid choice")
            continue
        try:
            action()
        except Exception as e:
            logging.error(f"Menu error: {e}")
            print(f"  x Error: {e}")


if __name__ == "__main__":
    main()
