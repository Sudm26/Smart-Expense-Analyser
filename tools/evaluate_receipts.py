"""Run local OCR/extraction over receipt images and save a reviewable CSV.

Examples:
    python tools/evaluate_receipts.py "C:\\...\\RECEIPTS\\grocery" --limit 10
    python tools/evaluate_receipts.py "C:\\...\\RECEIPTS" --output receipt_predictions.csv
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.extraction import extract_receipt_fields
from ai.ocr import read_receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract merchant and total from receipt images.")
    parser.add_argument("input", type=Path, help="Receipt image or directory containing receipts")
    parser.add_argument("--output", type=Path, default=Path("receipt_predictions.csv"))
    parser.add_argument("--limit", type=int, help="Process only the first N images")
    args = parser.parse_args()

    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    images = [args.input] if args.input.is_file() else sorted(
        path for path in args.input.rglob("*") if path.suffix.lower() in image_extensions
    )
    if args.limit:
        images = images[:args.limit]
    if not images:
        raise SystemExit("No supported receipt images were found.")

    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["image", "merchant", "amount", "amount_source", "expense_date", "ocr_message"],
        )
        writer.writeheader()
        for index, image in enumerate(images, start=1):
            text, message, blocks = read_receipt(image)
            fields = extract_receipt_fields(text, blocks)
            row = {"image": str(image), "ocr_message": message, **fields}
            writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
            print(f"[{index}/{len(images)}] {image.name}: {fields['merchant']} | {fields['amount']}")


if __name__ == "__main__":
    main()
