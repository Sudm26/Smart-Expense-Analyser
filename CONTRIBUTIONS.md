# Smart Expense Analyser contributions

This repository imports an existing local project. The team supplied and confirmed
the author identities and completed-work assignments below. Import commit dates
record when the files entered Git; they do not reconstruct development dates or
claim that the project was developed in this commit order. Sudhanshu Maurya is the
committer operating the shared laptop. AI assistance was used for implementation,
tests, documentation, and repository preparation.

| Contributor | GitHub | Confirmed commit email | Assigned files | Responsibilities | Import commit message |
| --- | --- | --- | --- | --- | --- |
| Aastha Tiwari | aasthat485-lgtm | aasthat485-lgtm@users.noreply.github.com | `app.py`, `requirements.txt`, `uploads/.gitkeep` | Flask routes, authentication, upload, manual expenses, integration | `feat: add Flask authentication and expense workflows` |
| Abhijay Kumar | algosetterabj | algosetterabj@users.noreply.github.com | `ai/`, `dataset/expenses.csv`, `tools/evaluate_receipts.py` | Image preprocessing, OCR, extraction, category prediction, receipt evaluation | `feat: add receipt recognition and expense classification` |
| Ashmit Pandey | Ashmitpandey005 | Ashmitpandey005@users.noreply.github.com | `database/__init__.py`, `database/database.py` | SQLite accounts, expenses, budgets, learned rules, demo data, reporting analytics | `feat: add expense storage budgets and reporting analytics` |
| Sudhanshu Maurya | Sudm26 | Sudm26@users.noreply.github.com | `templates/`, `static/`, `tools/test_expense_workflows.py`, `README.md`, `.gitignore`, `doc_build/create_project_docs.py` | Interface, charts, workflow tests, documentation, repository hygiene | `feat: add expense interface charts and project tooling` |

This contribution record is maintained with the documentation. It is an import
inventory based on the team's confirmation, not independent evidence of authorship.
Future commits should describe the actual changes made by their named authors.

## Local files excluded from publication

The virtual environment, Python caches, local SQLite database and sidecars,
uploaded receipts, private environment files and key files, generated reports,
render outputs, and receipt-evaluation exports stay local. `uploads/.gitkeep`
preserves the upload directory without publishing receipt images. Generated Word
documents have not been approved for publication.

The demo credentials documented in the README are public sample credentials.
Session signing keys are private environment configuration and are not committed.
Document generation in `doc_build/` is optional and requires `python-docx` and
Pillow in addition to the application dependencies.

## Validation and push review

Run from the project directory:

```powershell
.\.venv\Scripts\python.exe -m unittest tools.test_expense_workflows -v
git status --short --branch
git log --format="%h | %an <%ae> | committer: %cn <%ce> | %s"
git remote -v
git ls-remote --symref origin
```

The final import is validated as a complete project. Intermediate import commits
may reference modules that appear in subsequent commits.

Only after explicit push approval, and after checking for newly added remote
history, use:

```powershell
git fetch origin
git push --dry-run origin main
git push -u origin main
```

If remote history appears, inspect and integrate it before pushing. Do not force
push. Git Credential Manager can use the laptop's existing authorized GitHub
account; no teammate account login is needed. The pusher identity is separate
from each commit's author. GitHub attribution depends on the author email being
associated with the intended account; the team confirmed the addresses above.
