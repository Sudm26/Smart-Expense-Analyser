import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import database.database as db
from app import app
from werkzeug.security import check_password_hash


class ExpenseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent)
        self.db_patch = patch.object(db, 'DB_PATH', Path(self.temp.name) / 'test.db')
        self.db_patch.start()
        db.init_db()
        self.user = db.get_user_by_email('spendsense.demo.ai@gmail.com')
        self.client = app.test_client()
        self.old_upload_folder = app.config['UPLOAD_FOLDER']
        app.config['UPLOAD_FOLDER'] = Path(self.temp.name)
        with self.client.session_transaction() as session:
            session['user_id'] = self.user['id']

    def tearDown(self):
        app.config['UPLOAD_FOLDER'] = self.old_upload_folder
        self.db_patch.stop()
        __import__("gc").collect()
        self.temp.cleanup()

    def test_demo_login_and_repeatable_seed(self):
        self.assertTrue(check_password_hash(self.user['password_hash'], 'Demo@2026'))
        before = len(db.list_expenses(self.user['id']))
        db.init_db()
        self.assertEqual(len(db.list_expenses(self.user['id'])), before)
        report = db.get_report_data(self.user['id'], 2026)
        self.assertEqual(sum(value > 0 for value in report['month_values']), 6)
        self.assertGreaterEqual(len(report['insights']), 2)
        response = self.client.post('/login', data={'email': self.user['email'], 'password': 'Demo@2026'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get('/reports?year=2026').status_code, 200)
        # Clearing expenses retains budgets; reseeding must not fail or duplicate budgets.
        db.clear_expenses(self.user['id'])
        db.init_db()
        self.assertEqual(len(db.list_expenses(self.user['id'])), before)

    def test_year_filter_and_twelve_months(self):
        with db.connection() as conn:
            conn.execute("INSERT INTO expenses (merchant,expense_date,amount,category,user_id) VALUES ('Older','2025-10-01',99999,'Other',?)", (self.user['id'],))
        report = db.get_report_data(self.user['id'], 2026)
        self.assertEqual(len(report['month_labels']), 12)
        self.assertEqual(report['month_labels'][0], 'Jan')
        self.assertEqual(report['month_labels'][-1], 'Dec')
        self.assertEqual(report['month_values'][9], 4180)
        self.assertEqual(db.get_report_data(self.user['id'], 2025)['month_values'][9], 99999)
        self.assertEqual(db.get_report_data(self.user['id'])['report_year'], date.today().year)

    def test_old_receipt_defaults_to_today_and_edited_date_saves(self):
        with patch('app.read_receipt', return_value=('Old receipt', 'Read', [])), patch('app.extract_receipt_fields', return_value={'merchant': 'Test shop', 'expense_date': '2019-01-02', 'amount': 100}), patch('app.classify_expense', return_value={'category': 'Groceries', 'confidence': 95}):
            response = self.client.post('/upload', data={'receipt': (io.BytesIO(b'test image'), 'old.jpg')}, content_type='multipart/form-data')
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="expense_date" value="' + date.today().isoformat() + '"', html)
        response = self.client.post('/expenses', data={'merchant': 'Test shop', 'expense_date': '2026-09-15', 'amount': '100', 'category': 'Groceries'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(db.list_expenses(self.user['id'])[0]['expense_date'], '2026-09-15')


if __name__ == '__main__':
    unittest.main()
