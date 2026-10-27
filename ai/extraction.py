"""Practical rule-based extraction from OCR text."""
import re
from datetime import datetime
from difflib import SequenceMatcher

KNOWN_MERCHANTS = (
    "Walmart", "DMart", "Reliance Fresh", "Big Bazaar", "Starbucks", "McDonalds",
    "Dominos", "Uber", "Ola", "Amazon", "Flipkart", "Myntra", "Netflix", "PVR",
    "Apollo Pharmacy", "Riverside Restaurant", "Indian Oil Corporation", "Costco", "Trader Joe's", "Whole Foods",
    "WinCo Foods", "SPAR", "MOD Pizza",
)

_MONEY_PATTERN = r"(?:[$₹]|Rs\.?|INR|USD|EUR|R)?\s*([0-9][0-9, .]{0,14})"
_TOTAL_LABELS = (
    ("grand total", 130), ("amount due", 125), ("balance due", 120),
    ("total due", 118), ("total paid", 115), ("order total", 112),
    ("check total", 110), ("take out total", 108), ("total", 95),
)


def _parse_amount(raw_amount: str) -> float:
    """Accept common OCR money formats such as 31.39, 31,39, and 1,299.00."""
    cleaned = raw_amount.replace(" ", "").replace("₹", "").replace("$", "")
    if "," in cleaned and "." not in cleaned:
        before, after = cleaned.rsplit(",", 1)
        # A final two-digit group is usually a decimal separator on receipts.
        cleaned = f"{before}.{after}" if len(after) == 2 else cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", "")
    return float(cleaned)


def _normalise_known_merchant(merchant: str) -> str:
    """Correct only strong OCR near-matches against our known merchant list."""
    normalized = re.sub(r"[^a-z]", "", merchant.lower())
    best_match = max(KNOWN_MERCHANTS, key=lambda name: SequenceMatcher(None, normalized, re.sub(r"[^a-z]", "", name.lower())).ratio())
    similarity = SequenceMatcher(None, normalized, re.sub(r"[^a-z]", "", best_match.lower())).ratio()
    return best_match if similarity >= 0.84 else merchant


def _find_merchant(lines: list[str], ocr_blocks: list[dict] | None = None) -> str | None:
    """Choose a likely business heading instead of blindly taking OCR's first line."""
    rejected_words = {
        "address", "approval", "balance", "batch", "cash", "change", "covers", "date",
        "email", "gst", "id", "invoice", "manager", "order", "receipt", "sale", "subtotal",
        "table", "tax", "time", "total", "transaction", "visa", "www",
    }
    candidates = []
    business_suffixes = {
        "cafe", "diner", "foods", "grill", "house", "hotel", "market", "mart",
        "pharmacy", "pizza", "restaurant", "store", "bistro", "bar",
    }

    # A full recognised brand must beat a shorter word from that same heading.
    # For example, OCR may return both "INDIAN OIL CORPORATION" and a separate
    # high-confidence "CORPORATION" block. The latter is not a useful merchant.
    header_text = " ".join(lines[:10]).lower()
    compact_header = re.sub(r"[^a-z]", "", header_text)
    for known_merchant in KNOWN_MERCHANTS:
        compact_known = re.sub(r"[^a-z]", "", known_merchant.lower())
        if compact_known in compact_header:
            return known_merchant

    # OCR blocks contain the evidence unavailable in plain text: location and confidence.
    # Merchant headings are normally in the top 35% of a receipt and highly readable.
    for block in ocr_blocks or []:
        compact = block["text"].strip()
        letters = re.sub(r"[^A-Za-z]", "", compact)
        words = re.findall(r"[A-Za-z]+", compact.lower())
        if block["top_ratio"] > 0.32 or block["confidence"] < 0.42:
            continue
        if len(letters) < 3 or len(words) > 4 or any(word in rejected_words for word in words):
            continue
        if any(character.isdigit() for character in compact) or compact.lower().startswith(("info", "http")):
            continue
        suffix_bonus = 30 if any(word in business_suffixes for word in words) else 0
        heading_size_bonus = min(block.get("height_ratio", 0) * 600, 24)
        score = 150 + (block["confidence"] * 70) - (block["top_ratio"] * 120) - (len(words) * 5) - abs(len(letters) - 12) + suffix_bonus + heading_size_bonus
        candidates.append((score, compact))

    for index, line in enumerate(lines[:14]):
        compact = line.strip()
        letters = re.sub(r"[^A-Za-z]", "", compact)
        words = re.findall(r"[A-Za-z]+", compact.lower())
        if len(letters) < 3 or len(words) > 4 or any(word in rejected_words for word in words):
            continue
        if any(character.isdigit() for character in compact) or compact.lower().startswith(("info", "http")):
            continue
        # Store headings are usually short and appear near the top.
        suffix_bonus = 30 if any(word in business_suffixes for word in words) else 0
        score = 100 - (index * 6) - (len(words) * 5) - abs(len(letters) - 12) + suffix_bonus
        candidates.append((score, compact))
    merchant = max(candidates, default=(0, ""))[1] or None
    if not merchant:
        return None
    return _normalise_known_merchant(merchant)


def _label_priority(value: str) -> int:
    """Return how strongly a text label signals the amount finally charged."""
    normalized = re.sub(r"[^a-z]", " ", value.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if any(word in normalized for word in (
        "subtotal", "tax", "tip", "gratuity", "change", "tender", "cash", "number", "item", "sold", "count",
    )):
        return 0
    for label, priority in _TOTAL_LABELS:
        if label in normalized:
            return priority
    # OCR variants such as TOTL / TOTA / T0TAL are common on low-resolution scans.
    compact = normalized.replace(" ", "")
    return 88 if re.search(r"t[o0]ta?[l1|!]?", compact) else 0


def _amount_from_value(value: str) -> float | None:
    """Parse a plausible currency value from a single OCR block."""
    match = re.search(_MONEY_PATTERN, value, re.IGNORECASE)
    if not match:
        return None
    try:
        amount = _parse_amount(match.group(1))
    except ValueError:
        return None
    return amount if 0 < amount < 10_000_000 else None


def _extract_total_from_blocks(ocr_blocks: list[dict]) -> float | None:
    """Use receipt layout: total label left, numeric value on the same row/right."""
    candidates: list[tuple[float, float]] = []
    for label in ocr_blocks:
        priority = _label_priority(label["text"])
        if not priority:
            continue
        label_amount = _amount_from_value(label["text"])
        if label_amount is not None:
            candidates.append((priority + label.get("confidence", 0) * 10, label_amount))
        for value in ocr_blocks:
            if value is label:
                continue
            # Price columns are generally to the right of their labels; allow a small
            # overlap for narrow, centered receipts.
            vertical_gap = abs(value.get("top_ratio", 0) - label.get("top_ratio", 0))
            horizontal_ok = value.get("left_ratio", 0) >= label.get("left_ratio", 0) + 0.05
            same_variant = value.get("source") == label.get("source")
            if vertical_gap > 0.026 or not horizontal_ok or not same_variant:
                continue
            amount = _amount_from_value(value["text"])
            if amount is None:
                continue
            proximity = max(0, 12 - vertical_gap * 400)
            right_bonus = value.get("left_ratio", 0) * 10
            candidates.append((priority + proximity + right_bonus + value.get("confidence", 0) * 8, amount))
    return max(candidates, default=(0, None))[1]


def _extract_payment_receipt(text: str, ocr_blocks: list[dict]) -> dict | None:
    """Extract fields from PhonePe/GPay/Paytm-style payment confirmation screens."""
    compact_text = re.sub(r"[^a-z]", "", text.lower())
    if "paidto" not in compact_text or not ("success" in compact_text or "paymentdetails" in compact_text):
        return None

    sorted_blocks = sorted(ocr_blocks, key=lambda block: block["top_ratio"])
    paid_to_block = next(
        (block for block in sorted_blocks if "paidto" in re.sub(r"[^a-z]", "", block["text"].lower())),
        None,
    )
    merchant = "Unknown merchant"
    merchant_top = None
    if paid_to_block:
        candidates = []
        for block in sorted_blocks:
            value = block["text"].strip()
            letters = re.sub(r"[^A-Za-z]", "", value)
            distance = block["top_ratio"] - paid_to_block["top_ratio"]
            if not 0.02 <= distance <= 0.16 or "@" in value or len(letters) < 3:
                continue
            if any(word in value.lower() for word in ("payment", "detail", "message", "upi")):
                continue
            candidates.append((block["confidence"] - distance, block))
        if candidates:
            merchant_block = max(candidates, key=lambda item: item[0])[1]
            merchant = _normalise_known_merchant(merchant_block["text"].strip())
            merchant_top = merchant_block["top_ratio"]

    amount = 0.0
    if merchant_top is not None:
        # Payment screenshots place the paid amount on the same horizontal row as the merchant.
        nearby_blocks = [
            block for block in sorted_blocks
            if abs(block["top_ratio"] - merchant_top) <= 0.035 and block["left_ratio"] >= 0.45
        ]
        for block in nearby_blocks:
            digits = re.search(r"\d+(?:[,.]\d{1,2})?", block["text"])
            if digits:
                amount = _parse_amount(digits.group(0))
                break
    if amount == 0.0:
        amount_matches = re.findall(r"(?:₹|Rs\.?|INR|\$|\{)\s*([0-9][0-9,. ]*)", text, re.IGNORECASE)
        if amount_matches:
            amount = _parse_amount(amount_matches[0])

    date_match = re.search(
        r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b",
        text,
        re.IGNORECASE,
    )
    expense_date = None
    if date_match:
        try:
            expense_date = datetime.strptime(date_match.group(1).title(), "%d %B %Y").date().isoformat()
        except ValueError:
            pass

    lowered = text.lower()
    payment_app = "PhonePe" if "phonepe" in lowered else "Google Pay" if "gpay" in lowered or "google pay" in lowered else "Paytm" if "paytm" in lowered else "Digital payment"
    status = "Successful" if "success" in lowered else "Pending"
    return {
        "merchant": merchant,
        "expense_date": expense_date,
        "amount": amount,
        "amount_source": "Payment confirmation amount",
        "receipt_type": "Digital payment",
        "payment_app": payment_app,
        "payment_method": "UPI" if "upi" in compact_text else "Digital payment",
        "payment_status": status,
    }


def extract_receipt_fields(text: str, ocr_blocks: list[dict] | None = None) -> dict:
    payment_receipt = _extract_payment_receipt(text, ocr_blocks or [])
    if payment_receipt:
        return payment_receipt
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    merchant = _find_merchant(lines, ocr_blocks) or "Unknown merchant"
    if merchant == "Unknown merchant" or re.fullmatch(r"[+()\d\s-]+", merchant):
        flattened_text = " ".join(lines)
        # Covers both a normal email and a common OCR variant such as
        # "infoerestaurant _ COm" when @ and . are misread.
        email_match = re.search(
            r"\binfo(?:@|e)?([a-z][a-z-]{2,}?)(?:\.|\s*[_\s]+)c[o0]m\b", flattened_text, re.IGNORECASE
        )
        domain_match = re.search(
            r"(?:@|www\.)?([a-z][a-z0-9-]*)\.(?:com|in|org|net|co|io)\b", flattened_text, re.IGNORECASE
        )
        if email_match:
            merchant = email_match.group(1).replace("-", " ").title()
        elif domain_match:
            domain = domain_match.group(1).lower()
            merchant = domain.replace("-", " ").title()
        merchant = re.sub(r"(?i)(restaurant|cafe|mart|store|hotel)$", r" \1", merchant).strip().title()

    date_match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", text)
    expense_date = None
    if date_match:
        raw_date = date_match.group(1).replace("-", "/")
        for date_format in ("%d/%m/%Y", "%d/%m/%y", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                expense_date = datetime.strptime(raw_date, date_format).date().isoformat()
                break
            except ValueError:
                pass
    if expense_date is None:
        written_date = re.search(
            r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{2,4})\b",
            text,
            re.IGNORECASE,
        )
        if written_date:
            for date_format in ("%d %B %Y", "%d %B %y"):
                try:
                    expense_date = datetime.strptime(written_date.group(1).title(), date_format).date().isoformat()
                    break
                except ValueError:
                    pass

    # Layout-aware matching handles labels and values OCR reads as separate blocks.
    # It also avoids treating a later tip, cash tender, or subtotal as the total.
    amount = _extract_total_from_blocks(ocr_blocks or []) or 0.0
    amount_source = "Final total (layout matched)" if amount else "No amount found"
    if amount == 0.0:
        total_word = r"t[o0]ta?[l1\]\|!]?"
        money_value = r"([0-9][0-9, .]*)"
        currency = r"(?:Rs\.?|INR|USD|EUR|₹|\$|S)?"
        total_patterns = (
            rf"\b(?:grand\s+{total_word}|amount\s+due|balance\s+due|total\s+due|order\s+total|check\s+total|{total_word}\s+paid)\s*[:.= -]*\s*{currency}\s*{money_value}",
            rf"\b{total_word}\s*[:.= -]*\s*{currency}\s*{money_value}",
        )
        for pattern in total_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    amount = _parse_amount(matches[-1])
                    amount_source = "Final total"
                    break
                except ValueError:
                    continue
    if amount == 0.0:
        subtotal_matches = re.findall(
            r"\bsubtotal\b\s*[:.]?\s*(?:Rs\.?|INR|USD|₹|\$|S)?\s*([\d,.]+)", text, re.IGNORECASE
        )
        if subtotal_matches:
            amount = _parse_amount(subtotal_matches[-1])
            amount_source = "Subtotal only — final total was not visible"
    return {
        "merchant": merchant, "expense_date": expense_date, "amount": amount, "amount_source": amount_source,
        "receipt_type": "Physical receipt", "payment_app": "", "payment_method": "", "payment_status": "",
    }
