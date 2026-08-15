import base64
import hashlib
import hmac
import os
import secrets

from psycopg.rows import dict_row

from app.config import read_secret, require_production_value
from app.database import connect

SESSION_DAYS = 7


def hash_password(password: str):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str):
    try:
        _, salt_value, digest_value = encoded.split("$", 2)
        salt = base64.b64decode(salt_value)
        expected = base64.b64decode(digest_value)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def ensure_initial_admin():
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM users)")
            if cursor.fetchone()[0]:
                return
            email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
            password = read_secret("ADMIN_PASSWORD", "")
            require_production_value("ADMIN_EMAIL", email, min_length=3)
            require_production_value("ADMIN_PASSWORD", password, min_length=20)
            if not email or len(password) < 12:
                raise RuntimeError("ADMIN_EMAIL and an ADMIN_PASSWORD of at least 12 characters are required")
            cursor.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s)",
                (email, hash_password(password)),
            )


def login(email: str, password: str):
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM users WHERE email = %s AND is_active = TRUE", (email.strip().lower(),))
            user = cursor.fetchone()
            if user is None or not verify_password(password, user["password_hash"]):
                return None
            token = secrets.token_urlsafe(32)
            cursor.execute(
                """INSERT INTO sessions (user_id, token_hash, expires_at)
                   VALUES (%s, %s, NOW() + make_interval(days => %s))""",
                (user["id"], hashlib.sha256(token.encode()).hexdigest(), SESSION_DAYS),
            )
            return token


def session_user(token: str | None):
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT users.id, users.email FROM sessions
                   JOIN users ON users.id = sessions.user_id
                   WHERE sessions.token_hash = %s AND sessions.expires_at > NOW()
                     AND users.is_active = TRUE""",
                (token_hash,),
            )
            return cursor.fetchone()


def logout(token: str | None):
    if not token:
        return
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM sessions WHERE token_hash = %s", (hashlib.sha256(token.encode()).hexdigest(),))
