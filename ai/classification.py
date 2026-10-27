"""Small train-on-start ML categorizer using TF-IDF and Logistic Regression."""
from pathlib import Path
import csv
from difflib import SequenceMatcher

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = BASE_DIR / "dataset" / "expenses.csv"
_model = None
_vectorizer = None

# Deterministic merchant knowledge base improves common, verified merchants;
# the TF-IDF model remains the fallback for unfamiliar descriptions.
MERCHANT_CATEGORIES = {
    "amazon": "Shopping", "apollo pharmacy": "Healthcare", "big bazaar": "Groceries",
    "blinkit": "Groceries", "d mart": "Groceries", "dmart": "Groceries", "dominos": "Food & Dining",
    "flipkart": "Shopping", "indian oil": "Transportation", "jio": "Bills & Utilities",
    "mcdonalds": "Food & Dining", "myntra": "Shopping", "netflix": "Entertainment",
    "ola": "Transportation", "pvr": "Entertainment", "reliance fresh": "Groceries",
    "starbucks": "Food & Dining", "swiggy": "Food & Dining", "uber": "Transportation",
    "walmart": "Groceries", "zepto": "Groceries", "zomato": "Food & Dining",
}

# These are used for receipt-free entries, where the user types what they bought
# rather than a shop name. Check longer phrases first to avoid partial matches.
DESCRIPTION_CATEGORIES = {
    "auto rickshaw": "Transportation", "autorickshaw": "Transportation", "rickshaw": "Transportation",
    "bus fare": "Transportation", "metro fare": "Transportation", "train fare": "Transportation",
    "petrol": "Transportation", "fuel": "Transportation", "cab ride": "Transportation",
    "soft drink": "Snacks", "cold drink": "Snacks", "chips": "Snacks", "snack": "Snacks",
    "biscuits": "Snacks", "chocolate": "Snacks", "juice": "Snacks", "tea": "Snacks", "coffee": "Snacks",
    "pencils": "Stationery", "pencil": "Stationery", "eraser": "Stationery", "pen": "Stationery",
    "notebook": "Stationery", "marker": "Stationery", "printout": "Stationery", "photocopy": "Stationery",
    "stationery": "Stationery", "stationary": "Stationery",
    "vegetables": "Groceries", "milk": "Groceries", "bread": "Groceries", "rice": "Groceries",
    "medicine": "Healthcare", "doctor": "Healthcare", "pharmacy": "Healthcare",
    "movie ticket": "Entertainment", "concert ticket": "Entertainment", "game subscription": "Entertainment",
    "mobile recharge": "Bills & Utilities", "electricity bill": "Bills & Utilities", "internet bill": "Bills & Utilities",
    "clothes": "Shopping", "shoes": "Shopping", "book": "Shopping",
}


def _load_model():
    global _model, _vectorizer
    if _model is not None:
        return
    with open(DATASET_PATH, newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    descriptions = [row["description"] for row in rows]
    labels = [row["category"] for row in rows]
    _vectorizer = TfidfVectorizer(ngram_range=(1, 2), lowercase=True)
    features = _vectorizer.fit_transform(descriptions)
    _model = LogisticRegression(max_iter=1000, random_state=42)
    _model.fit(features, labels)


def classify_expense(description: str, learned_rules: dict[str, str] | None = None) -> dict:
    cleaned = " ".join((description or "").lower().replace("'", "").split())
    if cleaned:
        # User-confirmed corrections take precedence over generic rules and ML.
        # Longest first prevents a broad phrase from hiding a more specific one.
        for phrase, category in sorted((learned_rules or {}).items(), key=lambda item: len(item[0]), reverse=True):
            if phrase == cleaned or phrase in cleaned:
                return {"category": category, "confidence": 100.0}
        for phrase, category in DESCRIPTION_CATEGORIES.items():
            if phrase in cleaned:
                return {"category": category, "confidence": 99.0}
        best_merchant = max(MERCHANT_CATEGORIES, key=lambda merchant: SequenceMatcher(None, cleaned, merchant).ratio())
        similarity = SequenceMatcher(None, cleaned, best_merchant).ratio()
        if similarity >= 0.84 or best_merchant in cleaned:
            return {"category": MERCHANT_CATEGORIES[best_merchant], "confidence": 99.0}
    _load_model()
    features = _vectorizer.transform([description or "unknown"])
    probabilities = _model.predict_proba(features)[0]
    best_index = probabilities.argmax()
    return {
        "category": _model.classes_[best_index],
        "confidence": round(float(probabilities[best_index]) * 100, 1),
    }
