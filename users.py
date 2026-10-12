"""Local user accounts for Hamza GSM Tool (stdlib only: sqlite3, hashlib, secrets).

- DB file lives next to the script (users.db), created on first app run.
- Passwords are hashed with PBKDF2-HMAC-SHA256 (200,000 iterations) + 16-byte salt.
- Plain passwords are NEVER stored.
"""

import hashlib
import secrets
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username   TEXT PRIMARY KEY,
    pw_hash    TEXT NOT NULL,
    salt       TEXT NOT NULL,
    is_admin   INTEGER NOT NULL DEFAULT 0,
    is_blocked INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    expires_at REAL
);
"""

# (label, seconds) -- None = lifetime. Expiry date = ab se itne seconds baad.
DURATIONS = [
    ("Lifetime", None),
    ("7 din", 7 * 86400),
    ("1 mahina", 30 * 86400),
    ("3 mahine", 90 * 86400),
    ("6 mahine", 180 * 86400),
    ("1 saal", 365 * 86400),
]

_ITERATIONS = 200_000
_DB_PATH = None  # set by init_db()


def init_db(path):
    """Point the module at a DB file and create the table if needed."""
    global _DB_PATH
    _DB_PATH = path
    con = sqlite3.connect(_DB_PATH)
    try:
        con.execute(SCHEMA)
        # migration: purani DB me expires_at column nahi hoga
        cols = [r[1] for r in con.execute("PRAGMA table_info(users)")]
        if "expires_at" not in cols:
            con.execute("ALTER TABLE users ADD COLUMN expires_at REAL")
        # meta table: recovery key jaisi cheezon ke liye (sirf is PC par)
        con.execute("CREATE TABLE IF NOT EXISTS meta "
                    "(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        con.commit()
    finally:
        con.close()


def _con():
    if not _DB_PATH:
        raise RuntimeError("init_db() pehle call karo")
    return sqlite3.connect(_DB_PATH)


def _new_salt():
    return secrets.token_bytes(16).hex()


def _hash(password, salt_hex):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"),
        bytes.fromhex(salt_hex), _ITERATIONS).hex()


def _validate(username, password):
    if not username or not str(username).strip():
        raise ValueError("Username khaali nahi ho sakta.")
    if not password:
        raise ValueError("Password khaali nahi ho sakta.")
    if len(password) < 4:
        raise ValueError("Password kam az kam 4 characters ka ho.")


def user_count():
    con = _con()
    try:
        return con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        con.close()


def admin_count():
    con = _con()
    try:
        return con.execute(
            "SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0]
    finally:
        con.close()


def create_user(username, password, is_admin=False, expires_at=None):
    """Create a user. expires_at: unix timestamp ya None (lifetime).

    Raises ValueError on bad input or duplicate name.
    """
    username = str(username).strip()
    _validate(username, password)
    salt = _new_salt()
    con = _con()
    try:
        exists = con.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if exists:
            raise ValueError(f"Username '{username}' pehle se mojood hai.")
        try:
            con.execute(
                "INSERT INTO users (username, pw_hash, salt, is_admin, is_blocked, created_at, expires_at)"
                " VALUES (?, ?, ?, ?, 0, ?, ?)",
                (username, _hash(password, salt), salt,
                 1 if is_admin else 0, time.time(), expires_at))
            con.commit()
        except sqlite3.IntegrityError:
            # v8.8 fix: race condition - doosri instance ne pehle bana diya
            con.rollback()
            raise ValueError(f"Username '{username}' pehle se mojood hai.")
    finally:
        con.close()


def verify(username, password):
    """Check credentials.

    Returns (status, is_admin) where status is one of:
      "ok"      -- correct password, account active
      "blocked" -- correct password but account is blocked
      "expired" -- correct password but subscription khatam
      "bad"     -- wrong username or password (never says which)
    """
    username = str(username or "").strip()
    con = _con()
    try:
        row = con.execute(
            "SELECT pw_hash, salt, is_admin, is_blocked, expires_at FROM users WHERE username = ?",
            (username,)).fetchone()
    finally:
        con.close()
    if not row:
        return ("bad", False)
    pw_hash, salt, is_admin, is_blocked, expires_at = row
    if _hash(password or "", salt) != pw_hash:
        return ("bad", False)
    if is_blocked:
        return ("blocked", bool(is_admin))
    if expires_at is not None and float(expires_at) < time.time():
        return ("expired", bool(is_admin))
    return ("ok", bool(is_admin))


def set_blocked(username, blocked):
    """Block (True) or unblock (False) a user. Refuses to block the last admin."""
    con = _con()
    try:
        row = con.execute(
            "SELECT is_admin FROM users WHERE username = ?", (username,)).fetchone()
        if not row:
            raise ValueError(f"Username '{username}' nahi mila.")
        if blocked and row[0] and admin_count() <= 1:
            raise ValueError("Aakhri admin ko block nahi kar sakte.")
        con.execute("UPDATE users SET is_blocked = ? WHERE username = ?",
                    (1 if blocked else 0, username))
        con.commit()
    finally:
        con.close()


def list_users():
    """Return [(username, is_admin, is_blocked, expires_at), ...] oldest first.
    expires_at: unix timestamp ya None (lifetime)."""
    con = _con()
    try:
        rows = con.execute(
            "SELECT username, is_admin, is_blocked, expires_at FROM users ORDER BY created_at"
        ).fetchall()
    finally:
        con.close()
    return [(u, bool(a), bool(b), e) for u, a, b, e in rows]


def get_meta(key):
    """meta value ya None."""
    con = _con()
    try:
        row = con.execute("SELECT value FROM meta WHERE key = ?",
                          (key,)).fetchone()
    finally:
        con.close()
    return row[0] if row else None


def set_meta(key, value):
    con = _con()
    try:
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    (key, value))
        con.commit()
    finally:
        con.close()


def get_expiry(username):
    """Unix timestamp ya None (lifetime). User na mile to None."""
    con = _con()
    try:
        row = con.execute("SELECT expires_at FROM users WHERE username = ?",
                          (username,)).fetchone()
    finally:
        con.close()
    return row[0] if row else None


def set_expiry(username, expires_at):
    """expiry set karo: unix timestamp ya None (lifetime)."""
    con = _con()
    try:
        cur = con.execute("UPDATE users SET expires_at = ? WHERE username = ?",
                          (expires_at, username))
        if cur.rowcount == 0:
            raise ValueError(f"Username '{username}' nahi mila.")
        con.commit()
    finally:
        con.close()


def expiry_from_duration(seconds):
    """DURATIONS se seconds -> unix timestamp (None = lifetime)."""
    if seconds is None:
        return None
    return time.time() + seconds


def fmt_expiry(expires_at):
    """'Lifetime' / '2026-11-08' / 'EXPIRED 2026-10-01'."""
    if expires_at is None:
        return "Lifetime"
    try:
        ts = float(expires_at)
    except (TypeError, ValueError):
        return "Lifetime"
    import datetime as _dt
    d = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    if ts < time.time():
        return f"EXPIRED {d}"
    return d


def reset_password(username, new_password):
    """Set a new password for a user."""
    if not new_password or len(new_password) < 4:
        raise ValueError("Password kam az kam 4 characters ka ho.")
    salt = _new_salt()
    con = _con()
    try:
        cur = con.execute("UPDATE users SET pw_hash = ?, salt = ? WHERE username = ?",
                          (_hash(new_password, salt), salt, username))
        if cur.rowcount == 0:
            raise ValueError(f"Username '{username}' nahi mila.")
        con.commit()
    finally:
        con.close()


def delete_user(username):
    """Delete a user. Refuses if it would delete the last admin."""
    con = _con()
    try:
        row = con.execute(
            "SELECT is_admin FROM users WHERE username = ?", (username,)).fetchone()
        if not row:
            raise ValueError(f"Username '{username}' nahi mila.")
        if row[0] and admin_count() <= 1:
            raise ValueError("Aakhri admin delete nahi ho sakta.")
        con.execute("DELETE FROM users WHERE username = ?", (username,))
        con.commit()
    finally:
        con.close()
