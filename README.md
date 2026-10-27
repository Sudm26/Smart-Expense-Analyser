# Smart Expense AI — MVP

This is a Flask MVP for the AI-Powered Smart Expense & Receipt Analyzer.

## What works now

- Receipt-image upload and safe local storage
- Review screen where every AI/extracted field is editable
- SQLite database for saved expenses
- Dashboard with total spending, category chart, and recent transactions
- Expense-history table
- ML category prediction: TF-IDF + Logistic Regression, trained using `dataset/expenses.csv`
- Three-pass EasyOCR reads original, contrast-enhanced, and thresholded receipt images; merchant selection uses OCR confidence, heading size, and top-of-receipt position
- Layout-aware extraction pairs final-total labels with their nearby amount, excluding subtotal, tip, tax, tender, change, and item-count rows

## Run it

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Then open <http://127.0.0.1:5000>.

The app reads its session signing key from the `SECRET_KEY` environment variable.
Without it, a random key is generated for local development; restarting the app
signs out existing sessions. For a persistent private key in a PowerShell session:

```powershell
$env:SECRET_KEY = (.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))")
python app.py
```

Keep this key private. The application does not automatically load `.env` files.

## Receipt OCR

EasyOCR is included in `requirements.txt`. The first OCR request can take longer because its English recognition model may need to download once. Start with receipt images that are clear, upright, and well lit.

To run the supplied receipt set through the extractor and create a review CSV:

```powershell
.venv\Scripts\python.exe tools\evaluate_receipts.py "C:\path\to\RECEIPTS" --output receipt_predictions.csv
```

The tool is intentionally a review workflow: OCR cannot reliably reconstruct ink that is blurred, covered, or absent from the photograph. Corrected CSV values can later become labelled training data for a dedicated detector.

## Suggested demo flow

1. Upload a tested receipt image.
2. Show raw OCR text and extracted merchant/date/total.
3. Show the ML category and confidence score.
4. Correct a value, then save it.
5. Return to the dashboard and show the updated chart/history.

## Important files

- `app.py`: Flask routes and upload/review/save workflow
- `ai/ocr.py`: EasyOCR adapter and receipt preprocessing
- `ai/extraction.py`: receipt text to structured fields
- `tools/evaluate_receipts.py`: batch-review receipt predictions as CSV
- `ai/classification.py`: TF-IDF + Logistic Regression predictor
- `dataset/expenses.csv`: starter labelled training examples
- `database/database.py`: SQLite code

## Demo account

Sign in with **spendsense.demo.ai@gmail.com** / **Demo@2026**.
This is an application login; it does not create a Gmail mailbox.
The demo includes 20 sample expenses from May through October 2026 and category budgets,
so reports show category shares and month-to-month spending changes.

Reports default to the current year and display January–December on the x axis.
Use the year selector to inspect an older year without combining years.
Uploaded receipts default to today's date; edit the date on the review screen before saving if needed.

Run workflow checks with `.venv\Scripts\python.exe -m unittest tools.test_expense_workflows -v`.
