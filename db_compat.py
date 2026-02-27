"""
Database compatibility layer: SQLite ↔ PostgreSQL.
Wraps psycopg2 to behave like sqlite3 so the rest of app.py needs minimal changes.
"""
import os
import re
import logging

DATABASE_URL = os.environ.get('DATABASE_URL', '')

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras
    DB_TYPE = 'postgres'
else:
    import sqlite3
    DB_TYPE = 'sqlite'
    DATABASE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lunagifts.db')


def _pg_convert(sql):
    """Convert SQLite-flavored SQL to PostgreSQL on the fly."""
    # ? → %s
    sql = sql.replace('?', '%s')

    # INSERT OR IGNORE → ON CONFLICT DO NOTHING
    if re.search(r'INSERT\s+OR\s+IGNORE', sql, re.IGNORECASE):
        sql = re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', sql, flags=re.IGNORECASE)
        sql = sql.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'

    # last_insert_rowid() → lastval()
    sql = re.sub(r'last_insert_rowid\s*\(\)', 'lastval()', sql, flags=re.IGNORECASE)

    # date('now') → CURRENT_DATE
    sql = re.sub(r"date\s*\(\s*'now'\s*\)", 'CURRENT_DATE', sql, flags=re.IGNORECASE)

    # datetime('now','-N days') → NOW() - INTERVAL 'N days'
    sql = re.sub(
        r"datetime\s*\(\s*'now'\s*,\s*'(-?\d+)\s+days?'\s*\)",
        lambda m: f"NOW() - INTERVAL '{abs(int(m.group(1)))} days'",
        sql, flags=re.IGNORECASE
    )

    # AUTOINCREMENT (DDL only, harmless to remove everywhere)
    sql = re.sub(r'\bAUTOINCREMENT\b', '', sql, flags=re.IGNORECASE)

    return sql


class _PgConnWrapper:
    """Makes a psycopg2 connection quack like sqlite3.Connection."""

    def __init__(self, conn):
        self._conn = conn
        self.row_factory = None  # silently ignored

    def execute(self, sql, params=None):
        sql = _pg_convert(sql)
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(sql, params or ())
        return cur

    def executemany(self, sql, params_list):
        sql = _pg_convert(sql)
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        for params in params_list:
            cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def connect_db():
    """Return a database connection (SQLite or PostgreSQL based on env)."""
    if DB_TYPE == 'postgres':
        conn = psycopg2.connect(DATABASE_URL)
        return _PgConnWrapper(conn)
    else:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        return conn


# --------------- Schema initialisation ---------------

def init_db():
    if DB_TYPE == 'postgres':
        _init_postgres()
    else:
        _init_sqlite()


def _init_sqlite():
    db = sqlite3.connect(DATABASE_FILE)
    _create_tables(db, 'sqlite')
    _run_migrations(db, 'sqlite')
    db.commit()
    db.close()


def _init_postgres():
    conn = psycopg2.connect(DATABASE_URL)
    w = _PgConnWrapper(conn)
    _create_tables(w, 'postgres')
    _run_migrations(w, 'postgres')
    w.commit()
    w.close()


def _create_tables(db, flavour):
    """Create all tables.  DDL is written in SQLite style and auto-converted for PG."""
    if flavour == 'postgres':
        # PostgreSQL-native DDL for precise types
        db.execute('''CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            last_name TEXT DEFAULT '',
            photo_url TEXT DEFAULT '',
            balance DOUBLE PRECISION DEFAULT 0,
            referral_code TEXT DEFAULT '',
            referred_by BIGINT DEFAULT 0,
            deposited_balance DOUBLE PRECISION DEFAULT 0,
            total_topup DOUBLE PRECISION DEFAULT 0,
            total_earned DOUBLE PRECISION DEFAULT 0,
            free_scratch_used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active DOUBLE PRECISION DEFAULT 0
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS inventory (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            gift_id INTEGER NOT NULL,
            gift_name TEXT NOT NULL,
            gift_image TEXT NOT NULL,
            gift_price DOUBLE PRECISION NOT NULL,
            item_type TEXT DEFAULT 'gift',
            case_id INTEGER DEFAULT 0,
            acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            reward DOUBLE PRECISION NOT NULL,
            link TEXT DEFAULT '',
            channel_id TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            reward_type TEXT DEFAULT 'stars',
            reward_gift_id DOUBLE PRECISION DEFAULT 0,
            goal_type TEXT DEFAULT '',
            goal_amount DOUBLE PRECISION DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS completed_tasks (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            task_id INTEGER NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, task_id)
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT NOT NULL,
            bonus_paid INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(referred_id)
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS promo_codes (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL DEFAULT 0,
            case_id INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            gift_id INTEGER DEFAULT 0,
            scratch_id INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS promo_uses (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            promo_id INTEGER NOT NULL,
            discount_applied INTEGER DEFAULT 0,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, promo_id)
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            amount DOUBLE PRECISION NOT NULL,
            gifts_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'pending',
            error_msg TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP DEFAULT NULL,
            retry_count INTEGER DEFAULT 0
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS star_transactions (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            charge_id TEXT NOT NULL UNIQUE,
            amount DOUBLE PRECISION NOT NULL,
            refunded INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS crash_games (
            id SERIAL PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'waiting',
            target_multiplier DOUBLE PRECISION DEFAULT 1.00,
            current_multiplier DOUBLE PRECISION DEFAULT 1.00,
            start_time DOUBLE PRECISION DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS crash_bets (
            id SERIAL PRIMARY KEY,
            game_id INTEGER NOT NULL,
            user_id BIGINT NOT NULL,
            bet_amount DOUBLE PRECISION NOT NULL,
            status TEXT NOT NULL DEFAULT 'playing',
            cashout_multiplier DOUBLE PRECISION DEFAULT 0,
            win_amount DOUBLE PRECISION DEFAULT 0,
            first_name TEXT DEFAULT '',
            photo_url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS crash_history (
            id SERIAL PRIMARY KEY,
            game_id INTEGER NOT NULL,
            final_multiplier DOUBLE PRECISION NOT NULL,
            finished_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
    else:
        # SQLite DDL (original)
        db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            last_name TEXT DEFAULT '',
            photo_url TEXT DEFAULT '',
            balance REAL DEFAULT 0,
            referral_code TEXT DEFAULT '',
            referred_by INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            gift_id INTEGER NOT NULL,
            gift_name TEXT NOT NULL,
            gift_image TEXT NOT NULL,
            gift_price REAL NOT NULL,
            acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(telegram_id)
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            reward REAL NOT NULL,
            link TEXT DEFAULT '',
            channel_id TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS completed_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, task_id)
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            bonus_paid INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(referred_id)
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL,
            value REAL NOT NULL DEFAULT 0,
            case_id INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS promo_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            promo_id INTEGER NOT NULL,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, promo_id)
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            gifts_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'pending',
            error_msg TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP DEFAULT NULL,
            FOREIGN KEY (user_id) REFERENCES users(telegram_id)
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS star_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            charge_id TEXT NOT NULL UNIQUE,
            amount REAL NOT NULL,
            refunded INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS crash_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL DEFAULT 'waiting',
            target_multiplier REAL DEFAULT 1.00,
            current_multiplier REAL DEFAULT 1.00,
            start_time REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS crash_bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            bet_amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'playing',
            cashout_multiplier REAL DEFAULT 0,
            win_amount REAL DEFAULT 0,
            first_name TEXT DEFAULT '',
            photo_url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS crash_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            final_multiplier REAL NOT NULL,
            finished_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')


def _run_migrations(db, flavour):
    """Add columns that may be missing from older schema versions."""
    migrations = [
        ('users', 'referral_code', "TEXT DEFAULT ''"),
        ('users', 'referred_by', 'INTEGER DEFAULT 0'),
        ('users', 'deposited_balance', 'REAL DEFAULT 0' if flavour == 'sqlite' else 'DOUBLE PRECISION DEFAULT 0'),
        ('users', 'total_topup', 'REAL DEFAULT 0' if flavour == 'sqlite' else 'DOUBLE PRECISION DEFAULT 0'),
        ('users', 'total_earned', 'REAL DEFAULT 0' if flavour == 'sqlite' else 'DOUBLE PRECISION DEFAULT 0'),
        ('users', 'free_scratch_used', 'INTEGER DEFAULT 0'),
        ('inventory', 'item_type', "TEXT DEFAULT 'gift'"),
        ('inventory', 'case_id', 'INTEGER DEFAULT 0'),
        ('tasks', 'reward_type', "TEXT DEFAULT 'stars'"),
        ('tasks', 'reward_gift_id', 'REAL DEFAULT 0' if flavour == 'sqlite' else 'DOUBLE PRECISION DEFAULT 0'),
        ('tasks', 'goal_type', "TEXT DEFAULT ''"),
        ('tasks', 'goal_amount', 'REAL DEFAULT 0' if flavour == 'sqlite' else 'DOUBLE PRECISION DEFAULT 0'),
        ('promo_codes', 'gift_id', 'INTEGER DEFAULT 0'),
        ('promo_codes', 'scratch_id', 'INTEGER DEFAULT 0'),
        ('promo_uses', 'discount_applied', 'INTEGER DEFAULT 0'),
        ('users', 'last_active', 'REAL DEFAULT 0' if flavour == 'sqlite' else 'DOUBLE PRECISION DEFAULT 0'),
        ('withdrawals', 'retry_count', 'INTEGER DEFAULT 0'),
    ]

    if flavour == 'postgres':
        for table, col, typedef in migrations:
            try:
                db.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typedef}')
            except Exception:
                pass
    else:
        for table, col, typedef in migrations:
            try:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {col} {typedef}')
            except Exception:
                pass
