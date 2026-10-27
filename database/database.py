import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "expenses.db"


def connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                merchant TEXT NOT NULL,
                expense_date TEXT,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                confidence REAL,
                receipt_path TEXT,
                ocr_text TEXT,
                receipt_type TEXT,
                payment_app TEXT,
                payment_method TEXT,
                payment_status TEXT,
                user_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS learned_category_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                phrase TEXT NOT NULL,
                category TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, phrase)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS category_budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                monthly_limit REAL NOT NULL CHECK(monthly_limit > 0),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, category)
            )
            """
        )
        existing_columns = {column["name"] for column in conn.execute("PRAGMA table_info(expenses)")}
        for name, definition in {
            "receipt_type": "TEXT",
            "payment_app": "TEXT",
            "payment_method": "TEXT",
            "payment_status": "TEXT",
            "user_id": "INTEGER",
        }.items():
            if name not in existing_columns:
                conn.execute(f"ALTER TABLE expenses ADD COLUMN {name} {definition}")
    seed_demo_account()


def create_user(name: str, email: str, password_hash: str):
    with connection() as conn:
        return conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email.lower().strip(), password_hash),
        ).lastrowid


def seed_demo_account():
    """Create a repeatable account with varied 2026 data for demonstrations."""
    from werkzeug.security import generate_password_hash

    demo_email = "spendsense.demo.ai@gmail.com"
    with connection() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (demo_email,)).fetchone()
        if user is None:
            demo_user_id = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Demo Student", demo_email, generate_password_hash("Demo@2026")),
            ).lastrowid
        else:
            demo_user_id = user["id"]

        existing_count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (demo_user_id,)
        ).fetchone()[0]
        if existing_count:
            return

        records = [
            ("Campus Canteen", "2026-05-06", 160, "Food & Dining"),
            ("Metro Card", "2026-05-12", 350, "Transportation"),
            ("Notebook and pens", "2026-05-20", 240, "Stationery"),
            ("Fresh Basket", "2026-06-03", 1480, "Groceries"),
            ("Movie ticket", "2026-06-16", 320, "Entertainment"),
            ("Auto rickshaw", "2026-06-25", 180, "Transportation"),
            ("Mobile recharge", "2026-07-02", 299, "Bills & Utilities"),
            ("Cafe lunch", "2026-07-11", 460, "Food & Dining"),
            ("Medicine", "2026-07-23", 540, "Healthcare"),
            ("Monthly groceries", "2026-08-05", 2180, "Groceries"),
            ("Shoes", "2026-08-18", 1299, "Shopping"),
            ("Bus and metro", "2026-08-27", 410, "Transportation"),
            ("Snacks", "2026-09-04", 220, "Snacks"),
            ("Internet bill", "2026-09-09", 699, "Bills & Utilities"),
            ("Restaurant dinner", "2026-09-21", 980, "Food & Dining"),
            ("Weekly groceries", "2026-10-03", 1840, "Groceries"),
            ("Petrol", "2026-10-08", 1100, "Transportation"),
            ("Sandwich and soft drink", "2026-10-16", 250, "Snacks"),
            ("Online course book", "2026-10-21", 650, "Shopping"),
            ("Coffee with friends", "2026-10-25", 340, "Food & Dining"),
        ]
        conn.executemany(
            """
            INSERT INTO expenses
            (merchant, expense_date, amount, category, confidence, receipt_path, ocr_text,
             receipt_type, payment_app, payment_method, payment_status, user_id)
            VALUES (?, ?, ?, ?, ?, '', '', 'Manual expense', '', '', '', ?)
            """,
            [(merchant, expense_date, amount, category, 100.0, demo_user_id)
             for merchant, expense_date, amount, category in records],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO category_budgets (user_id, category, monthly_limit) VALUES (?, ?, ?)",
            [
                (demo_user_id, "Groceries", 2500),
                (demo_user_id, "Transportation", 1200),
                (demo_user_id, "Food & Dining", 1000),
                (demo_user_id, "Snacks", 400),
                (demo_user_id, "Shopping", 1000),
            ],
        )


def get_user_by_email(email: str):
    with connection() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()


def get_user(user_id: int):
    with connection() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def save_expense(expense):
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO expenses
            (merchant, expense_date, amount, category, confidence, receipt_path, ocr_text,
             receipt_type, payment_app, payment_method, payment_status, user_id)
            VALUES (:merchant, :expense_date, :amount, :category, :confidence, :receipt_path, :ocr_text,
                    :receipt_type, :payment_app, :payment_method, :payment_status, :user_id)
            """,
            expense,
        )


def save_learned_category_rule(user_id: int, phrase: str, category: str):
    """Store a user's approved manual-description category for future suggestions."""
    normalized = " ".join(phrase.lower().split())
    if not normalized or len(normalized) > 100:
        return
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO learned_category_rules (user_id, phrase, category)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, phrase) DO UPDATE SET category = excluded.category,
                created_at = CURRENT_TIMESTAMP
            """,
            (user_id, normalized, category),
        )


def get_learned_category_rules(user_id: int) -> dict[str, str]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT phrase, category FROM learned_category_rules WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return {row["phrase"]: row["category"] for row in rows}


def get_category_budgets(user_id: int) -> dict[str, float]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT category, monthly_limit FROM category_budgets WHERE user_id = ? ORDER BY category",
            (user_id,),
        ).fetchall()
    return {row["category"]: row["monthly_limit"] for row in rows}


def save_category_budgets(user_id: int, budgets: dict[str, float]):
    """Replace a user's monthly category limits with the submitted positive values."""
    with connection() as conn:
        conn.execute("DELETE FROM category_budgets WHERE user_id = ?", (user_id,))
        conn.executemany(
            "INSERT INTO category_budgets (user_id, category, monthly_limit) VALUES (?, ?, ?)",
            [(user_id, category, limit) for category, limit in budgets.items() if limit > 0],
        )


def clear_expenses(user_id: int) -> int:
    """Delete saved expense records while preserving uploaded receipt files."""
    with connection() as conn:
        result = conn.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
        return result.rowcount


def list_expenses(user_id: int):
    with connection() as conn:
        return conn.execute("SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()


def get_dashboard_data(user_id: int):
    expenses = list_expenses(user_id)
    by_category = defaultdict(float)
    for expense in expenses:
        by_category[expense["category"]] += expense["amount"]
    total = sum(expense["amount"] for expense in expenses)
    current_month = date.today().strftime("%Y-%m")
    current_month_spending = defaultdict(float)
    for expense in expenses:
        if (expense["expense_date"] or "").startswith(current_month):
            current_month_spending[expense["category"]] += expense["amount"]
    budget_status = []
    for category, limit in get_category_budgets(user_id).items():
        spent = current_month_spending[category]
        remaining = limit - spent
        budget_status.append({
            "category": category,
            "limit": limit,
            "spent": spent,
            "remaining": abs(remaining),
            "percent": min(round((spent / limit) * 100), 100) if limit else 0,
            "is_over": spent > limit,
        })
    budget_status.sort(key=lambda item: (not item["is_over"], -item["spent"] / item["limit"] if item["limit"] else 0))
    return {
        "total_spending": total,
        "transaction_count": len(expenses),
        "category_labels": list(by_category.keys()),
        "category_values": list(by_category.values()),
        "recent_expenses": expenses[:5],
        "top_category": max(by_category, key=by_category.get) if by_category else "No expenses yet",
        "budget_status": budget_status,
        "budget_month": current_month,
    }


def get_report_data(user_id: int, selected_year: int | None = None):
    expenses = list_expenses(user_id)
    current_year = date.today().year
    available_years = sorted(
        {current_year} | {int((expense["expense_date"] or expense["created_at"] or "0000")[:4]) for expense in expenses
         if (expense["expense_date"] or expense["created_at"] or "")[:4].isdigit()},
        reverse=True,
    )
    report_year = selected_year if selected_year in available_years else current_year
    year_expenses = [expense for expense in expenses if (expense["expense_date"] or expense["created_at"] or "").startswith(str(report_year))]
    by_category = defaultdict(float)
    by_merchant = defaultdict(float)
    by_month = [0.0] * 12
    for expense in year_expenses:
        by_category[expense["category"]] += expense["amount"]
        by_merchant[expense["merchant"]] += expense["amount"]
        raw_date = expense["expense_date"] or expense["created_at"] or ""
        if len(raw_date) >= 7 and raw_date[5:7].isdigit() and 1 <= int(raw_date[5:7]) <= 12:
            by_month[int(raw_date[5:7]) - 1] += expense["amount"]
    top_merchants = sorted(by_merchant.items(), key=lambda item: item[1], reverse=True)[:5]
    total = sum(by_category.values())
    insights = []
    if total:
        category, value = max(by_category.items(), key=lambda item: item[1])
        insights.append(f"{category} is your highest spending category at ₹{value:,.0f} ({value / total:.0%} of total spending).")
    populated_months = [(index, value) for index, value in enumerate(by_month) if value > 0]
    if len(populated_months) >= 2:
        previous, current = populated_months[-2:]
        if previous[1] > 0:
            change = ((current[1] - previous[1]) / previous[1]) * 100
            direction = "increased" if change >= 0 else "decreased"
            month_names = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
            insights.append(f"Your spending {direction} by {abs(change):.0f}% from {month_names[previous[0]]} to {month_names[current[0]]} {report_year}.")
    if not insights:
        insights.append("Add a few verified expenses to unlock personalized spending insights.")
    return {
        "category_labels": list(by_category.keys()), "category_values": list(by_category.values()),
        "month_labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "month_values": by_month, "report_year": report_year, "available_years": available_years,
        "top_merchants": top_merchants, "insights": insights,
    }
