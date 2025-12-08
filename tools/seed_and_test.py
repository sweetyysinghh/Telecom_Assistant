"""Seed test DB and run sample queries for the Telecom Assistant.

Run this script from the project root (where app.py lives):
    python tools\seed_and_test.py

It will:
 - Create minimal tables and sample rows needed for policy/billing queries (contract_terms, service_plans, customers, customer_usage)
 - Run a set of sample queries across categories using the orchestrator and print results

This helps verify that the routing and agents return answers for the sample queries.
"""
import sqlite3
import os
from telecom_assistant.config.config import Config
from telecom_assistant.orchestration.graph import run_orchestrator
from telecom_assistant.agents.knowledge_agents import process_knowledge_query
from telecom_assistant.agents.billing_agents import process_billing_query

DB_PATH = getattr(Config, 'DB_PATH', 'data/telecom.db')

def ensure_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def seed_db():
    """Create minimal schema and seed rows for testing."""
    ensure_dir(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # customers
    c.execute('''
    CREATE TABLE IF NOT EXISTS customers (
        customer_id TEXT PRIMARY KEY,
        name TEXT,
        email TEXT,
        phone_number TEXT,
        service_plan_id TEXT,
        account_status TEXT
    )
    ''')

    # service_plans
    c.execute('''
    CREATE TABLE IF NOT EXISTS service_plans (
        plan_id TEXT PRIMARY KEY,
        name TEXT,
        monthly_cost REAL,
        data_limit_gb REAL,
        voice_minutes INTEGER,
        sms_count INTEGER,
        description TEXT
    )
    ''')

    # contract_terms (for termination fees)
    c.execute('''
    CREATE TABLE IF NOT EXISTS contract_terms (
        plan_id TEXT,
        term_months INTEGER,
        early_termination_fee REAL,
        notes TEXT
    )
    ''')

    # customer_usage
    c.execute('''
    CREATE TABLE IF NOT EXISTS customer_usage (
        usage_id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id TEXT,
        billing_period_start TEXT,
        billing_period_end TEXT,
        data_used_gb REAL,
        voice_minutes_used INTEGER,
        sms_count_used INTEGER,
        additional_charges REAL,
        total_bill_amount REAL
    )
    ''')

    # billing_policies (optional)
    c.execute('''
    CREATE TABLE IF NOT EXISTS billing_policies (
        policy_id INTEGER PRIMARY KEY AUTOINCREMENT,
        policy_name TEXT,
        description TEXT
    )
    ''')

    # network_status table for outages
    c.execute('''
    CREATE TABLE IF NOT EXISTS network_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        area TEXT,
        status TEXT,
        updated_at TEXT,
        details TEXT
    )
    ''')

    # seed sample plan and contract
    c.execute("INSERT OR IGNORE INTO service_plans (plan_id, name, monthly_cost, data_limit_gb, voice_minutes, sms_count, description) VALUES (?,?,?,?,?,?,?)",
              ("PLAN_BASIC", "Basic Plan", 299.0, 10.0, 500, 100, "Suitable for light users"))
    c.execute("INSERT OR IGNORE INTO service_plans (plan_id, name, monthly_cost, data_limit_gb, voice_minutes, sms_count, description) VALUES (?,?,?,?,?,?,?)",
              ("PLAN_FAMILY", "Family Plus", 999.0, 200.0, 5000, 1000, "Good for families and heavy video streaming"))

    c.execute("INSERT OR IGNORE INTO contract_terms (plan_id, term_months, early_termination_fee, notes) VALUES (?,?,?,?)",
              ("PLAN_BASIC", 12, 150.0, "Pro-rated early termination fee for 12-month contract"))
    c.execute("INSERT OR IGNORE INTO contract_terms (plan_id, term_months, early_termination_fee, notes) VALUES (?,?,?,?)",
              ("PLAN_FAMILY", 24, 499.0, "Higher ETF for 24-month premium plan"))

    c.execute("INSERT OR IGNORE INTO customers (customer_id, name, email, phone_number, service_plan_id, account_status) VALUES (?,?,?,?,?,?)",
              ("CUST001", "Test User", "test@example.com", "9999999999", "PLAN_BASIC", "active"))

    # seed a usage row
    c.execute("INSERT INTO customer_usage (customer_id, billing_period_start, billing_period_end, data_used_gb, voice_minutes_used, sms_count_used, additional_charges, total_bill_amount) VALUES (?,?,?,?,?,?,?,?)",
              ("CUST001", "2025-11-01", "2025-11-30", 12.5, 450, 30, 50.0, 399.0))

    # seed a sample network incident for Mumbai West
    c.execute("INSERT OR IGNORE INTO network_status (area, status, updated_at, details) VALUES (?,?,?,?)",
              ("Mumbai West", "Outage", "2025-12-01", "Localized antenna maintenance affecting voice calls"))

    conn.commit()
    conn.close()
    print(f"Seeded database at: {DB_PATH}")


def run_samples():
    samples = [
        # Billing
        ("BILLING", "Why did my bill increase by 200 this month?"),
        ("BILLING", "I see a charge for international roaming but I haven’t traveled recently"),
        ("BILLING", "Can you explain the ‘Value Added Services’ charge on my bill?"),
        ("BILLING", "What’s the early termination fee if I cancel my contract?"),
        # Network
        ("NETWORK", "I can’t make calls from my home in Mumbai West"),
        ("NETWORK", "My data connection keeps dropping when I’m on the train"),
        ("NETWORK", "Why is my 5G connection slower than my friend’s?"),
        ("NETWORK", "I get a ‘No Service’ error in my basement apartment"),
        # Plans
        ("SERVICE", "What’s the best plan for a family of four who watches a lot of videos?"),
        ("SERVICE", "I need a plan with good international calling to the US"),
        ("SERVICE", "Which plan is best for someone who works from home and needs reliable data?"),
        ("SERVICE", "I’m a light user who mostly just calls and texts. What’s my cheapest option?"),
        # Knowledge
        ("KNOWLEDGE", "How do I set up VoLTE on my Samsung phone?"),
        ("KNOWLEDGE", "What are the APN settings for Android devices?"),
        ("KNOWLEDGE", "How can I activate international roaming before traveling?"),
        ("KNOWLEDGE", "What areas in Delhi have 5G coverage?"),
        # Edge cases
        ("JOKE", "Tell me a joke about telecom"),
        ("MULTI", "I need help with both my bill and network issues"),
        ("EMPTY", "")
    ]

    print("\nRunning sample queries through orchestrator:\n")
    for typ, q in samples:
        print(f"--- [{typ}] Query: {q}")
        try:
            resp = run_orchestrator(q, customer_id="CUST001")
            print("Response:\n", resp)
        except Exception as e:
            print("Error invoking orchestrator:", e)
        print("\n")


if __name__ == '__main__':
    seed_db()
    run_samples()
