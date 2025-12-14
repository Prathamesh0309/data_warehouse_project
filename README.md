Events Portal (Streamlit)

This project adds a Streamlit UI for listing events, registering users, and a dummy payment flow. Data is stored in a local MySQL database.

Files added:
- `db.py` - MySQL helper with init_db and CRUD functions for users, events, registrations, payments.
- `streamlit_app.py` - Streamlit UI and flow (login/signup, admin pages, user registration and dummy payment).
- `requirements.txt` - minimal dependencies.

Quick start

1. Install dependencies in a venv (recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure DB credentials using environment variables if not using defaults:

- DB_HOST (default 127.0.0.1)
- DB_PORT (default 3306)
- DB_USER (default root)
- DB_PASSWORD (default empty)
- DB_NAME (default events_db)

Example (zsh):

```bash
export DB_USER=root
export DB_PASSWORD=secret
export DB_NAME=events_db
```

3. Initialize DB (optional — `streamlit_app.py` will call `init_db()` automatically at startup):

```bash
python -c "import db; db.init_db()"
```

4. Run the Streamlit app:

```bash
streamlit run streamlit_app.py
```

Notes

- The sign-up form has an "Create as admin" checkbox for testing admin features. Use it carefully.
- Passwords are hashed with SHA-256 (sufficient for demo, not production-grade; use bcrypt/argon2 in production).
- Payment is simulated; `record_payment` marks payments as `paid` with a generated TXN id.

Next steps / Improvements

- Add password reset and email verification.
- Replace SHA-256 with bcrypt or argon2.
- Add input validation and better error handling.
- Add tests and CI pipeline.

