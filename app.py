from pathlib import Path
from uuid import uuid4
from datetime import date
import os
import secrets

from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from ai.classification import classify_expense
from ai.extraction import extract_receipt_fields
from ai.ocr import read_receipt
from database.database import (
    clear_expenses, create_user, get_dashboard_data, get_report_data, get_user, get_user_by_email,
    get_category_budgets, get_learned_category_rules, init_db, list_expenses, save_category_budgets,
    save_expense, save_learned_category_rule,
)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
CATEGORIES = ["Snacks", "Stationery", "Transportation", "Food & Dining", "Groceries", "Shopping", "Healthcare", "Entertainment", "Bills & Utilities", "Other"]

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to access your expenses.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


@app.context_processor
def inject_user():
    return {"current_user": get_user(session["user_id"]) if "user_id" in session else None}


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name, email, password = request.form.get("name", "").strip(), request.form.get("email", "").strip(), request.form.get("password", "")
        if len(name) < 2 or "@" not in email or len(password) < 6:
            flash("Enter a name, a valid email, and a password with at least 6 characters.", "error")
        elif get_user_by_email(email):
            flash("An account with that email already exists. Please sign in.", "error")
        else:
            session["user_id"] = create_user(name, email, generate_password_hash(password))
            flash("Account created. Your expense history is private to this account.", "success")
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = get_user_by_email(request.form.get("email", ""))
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "error")
    return render_template("auth.html", mode="login")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", **get_dashboard_data(session["user_id"]))


@app.route("/budgets", methods=["GET", "POST"])
@login_required
def budgets():
    if request.method == "POST":
        submitted_budgets = {}
        for category in CATEGORIES:
            raw_limit = request.form.get(category, "").strip()
            if not raw_limit:
                continue
            try:
                limit = float(raw_limit)
            except ValueError:
                flash(f"Enter a valid amount for {category}.", "error")
                return render_template("budgets.html", categories=CATEGORIES, budgets=get_category_budgets(session["user_id"]))
            if limit <= 0:
                flash(f"{category} must be greater than ₹0, or leave it blank.", "error")
                return render_template("budgets.html", categories=CATEGORIES, budgets=get_category_budgets(session["user_id"]))
            submitted_budgets[category] = limit
        save_category_budgets(session["user_id"], submitted_budgets)
        flash("Monthly category thresholds saved.", "success")
        return redirect(url_for("dashboard"))
    return render_template("budgets.html", categories=CATEGORIES, budgets=get_category_budgets(session["user_id"]))


@app.route("/add-expense", methods=["GET", "POST"])
@login_required
def add_expense():
    """Review a receipt-free expense and its category prediction before saving."""
    form_data = {
        "merchant": "",
        "expense_date": date.today().isoformat(),
        "amount": "",
        "category": "Other",
        "confidence": 0,
    }
    detected = False
    if request.method == "POST":
        description = request.form.get("merchant", "").strip()
        form_data.update(
            merchant=description,
            expense_date=request.form.get("expense_date") or date.today().isoformat(),
            amount=request.form.get("amount", "").strip(),
        )
        if not description:
            flash("Describe what you bought or how you travelled first.", "error")
        else:
            prediction = classify_expense(description, get_learned_category_rules(session["user_id"]))
            form_data.update(prediction)
            detected = True
    return render_template("manual_expense.html", expense=form_data, detected=detected)


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "GET":
        return render_template("upload.html")

    receipt = request.files.get("receipt")
    if not receipt or not receipt.filename:
        flash("Please choose a receipt image.", "error")
        return redirect(url_for("upload"))
    if not allowed_file(receipt.filename):
        flash("Use a PNG, JPG, JPEG, or WEBP image.", "error")
        return redirect(url_for("upload"))

    filename = f"{uuid4().hex}_{secure_filename(receipt.filename)}"
    file_path = app.config["UPLOAD_FOLDER"] / filename
    receipt.save(file_path)

    ocr_text, ocr_message, ocr_blocks = read_receipt(file_path)
    extracted = extract_receipt_fields(ocr_text, ocr_blocks)
    # Uploaded historical receipts should be recorded on the upload date by default.
    # The review screen remains editable when the user needs a different date.
    extracted["expense_date"] = date.today().isoformat()
    prediction = classify_expense(extracted["merchant"])

    return render_template(
        "review.html",
        expense={**extracted, **prediction, "ocr_text": ocr_text, "receipt_path": filename},
        ocr_message=ocr_message,
    )


@app.route("/expenses", methods=["GET"])
@login_required
def expenses():
    return render_template("expenses.html", expenses=list_expenses(session["user_id"]))


@app.route("/expenses", methods=["POST"])
@login_required
def create_expense():
    expense = {
        "merchant": request.form.get("merchant", "").strip() or "Unknown merchant",
        "expense_date": request.form.get("expense_date") or None,
        "amount": request.form.get("amount", type=float) or 0,
        "category": request.form.get("category", "Other"),
        "confidence": request.form.get("confidence", type=float) or 0,
        "receipt_path": request.form.get("receipt_path", ""),
        "ocr_text": request.form.get("ocr_text", ""),
        "receipt_type": request.form.get("receipt_type", "Physical receipt"),
        "payment_app": request.form.get("payment_app", ""),
        "payment_method": request.form.get("payment_method", ""),
        "payment_status": request.form.get("payment_status", ""),
        "user_id": session["user_id"],
    }
    if expense["receipt_type"] == "Manual expense":
        expense["ocr_text"] = f"Manual description: {expense['merchant']}"
    save_expense(expense)
    if expense["receipt_type"] == "Manual expense" and request.form.get("learn_correction") == "yes":
        save_learned_category_rule(expense["user_id"], expense["merchant"], expense["category"])
        flash(f"Saved and will remember '{expense['merchant']}' as {expense['category']}.", "success")
    else:
        flash("Expense saved successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/expenses/clear", methods=["POST"])
@login_required
def clear_demo_data():
    deleted_count = clear_expenses(session["user_id"])
    flash(f"Cleared {deleted_count} saved expense record(s). Your uploaded images were kept.", "success")
    return redirect(url_for("dashboard"))


@app.route("/reports")
@login_required
def reports():
    requested_year = request.args.get("year", type=int)
    return render_template("reports.html", **get_report_data(session["user_id"], requested_year))


if __name__ == "__main__":
    UPLOAD_FOLDER.mkdir(exist_ok=True)
    init_db()
    app.run(debug=True)
