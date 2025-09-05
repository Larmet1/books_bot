import os
import sqlite3
from typing import Optional, Tuple, List, Dict, Any

_DB_PATH = os.path.join(os.path.dirname(__file__), "books.sqlite3")
_connection: Optional[sqlite3.Connection] = None


def get_connection() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        # Fast SQLite pragmas
        cur = _connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA cache_size=-20000;")  # ~20MB page cache
        cur.execute("PRAGMA foreign_keys=ON;")
        _connection.commit()
    return _connection


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            tg_user_id INTEGER UNIQUE NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            author TEXT NOT NULL,
            genre TEXT NOT NULL,
            photo_id TEXT,
            status TEXT NOT NULL DEFAULT 'my',
            is_favorite INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    # Indexes to speed up queries
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_tg_user_id ON users(tg_user_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_books_user_id ON books(user_id);")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_created_at ON books(created_at DESC);"
    )

    conn.commit()

    # --- Gentle migration: add is_favorite if missing ---
    try:
        cur.execute("PRAGMA table_info(books);")
        cols = [row[1] for row in cur.fetchall()]
        if "is_favorite" not in cols:
            cur.execute(
                "ALTER TABLE books ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0;"
            )
            conn.commit()
    except Exception:
        pass

    # --- Create m2m table for statuses ---
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS book_statuses (
            book_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(book_id, status),
            FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_book_statuses_book_id ON book_statuses(book_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_book_statuses_status ON book_statuses(status);"
    )
    conn.commit()

    # --- One-time backfill from legacy books.status ('in','read') ---
    try:
        cur.execute(
            """
            INSERT OR IGNORE INTO book_statuses (book_id, status)
            SELECT id, status FROM books WHERE status IN ('in','read')
            """
        )
        conn.commit()
    except Exception:
        pass


def ensure_user(tg_user_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE tg_user_id = ?", (tg_user_id,))
    row = cur.fetchone()
    if row:
        return int(row["id"])
    cur.execute("INSERT INTO users (tg_user_id) VALUES (?)", (tg_user_id,))
    conn.commit()
    return int(cur.lastrowid)


def add_book_for_user(
    tg_user_id: int,
    name: str,
    author: str,
    genre: str,
    photo_id: Optional[str] = None,
    status: str = "my",
) -> int:
    user_id = ensure_user(tg_user_id)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO books (user_id, name, author, genre, photo_id, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, name, author, genre, photo_id, status),
    )
    conn.commit()
    return int(cur.lastrowid)


# --- Queries (lists) ---


def list_all_books(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT b.id, b.name, b.author, b.genre, b.photo_id, b.status, b.is_favorite, u.tg_user_id
        FROM books b
        JOIN users u ON u.id = b.user_id
        ORDER BY b.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    return [dict(row) for row in cur.fetchall()]


def list_user_books(
    tg_user_id: int, limit: int = 50, offset: int = 0
) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT b.id, b.name, b.author, b.genre, b.photo_id, b.status, b.is_favorite, u.tg_user_id
        FROM books b
        JOIN users u ON u.id = b.user_id
        WHERE u.tg_user_id = ?
        ORDER BY b.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (tg_user_id, limit, offset),
    )
    return [dict(row) for row in cur.fetchall()]


def get_book(book_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT b.id, b.name, b.author, b.genre, b.photo_id, b.status, b.is_favorite, u.tg_user_id
        FROM books b
        JOIN users u ON u.id = b.user_id
        WHERE b.id = ?
        """,
        (book_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


# --- Carousel helpers ---


def count_all_books() -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM books")
    row = cur.fetchone()
    return int(row[0]) if row else 0


def count_user_books(tg_user_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) AS c
        FROM books b
        JOIN users u ON u.id = b.user_id
        WHERE u.tg_user_id = ?
        """,
        (tg_user_id,),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def get_all_book_by_index(index: int) -> Optional[Dict[str, Any]]:
    # index is 0-based
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT b.id, b.name, b.author, b.genre, b.photo_id, b.status, b.is_favorite
        FROM books b
        ORDER BY b.created_at DESC
        LIMIT 1 OFFSET ?
        """,
        (index,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def get_user_book_by_index(tg_user_id: int, index: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT b.id, b.name, b.author, b.genre, b.photo_id, b.status, b.is_favorite, u.tg_user_id
        FROM books b
        JOIN users u ON u.id = b.user_id
        WHERE u.tg_user_id = ?
        ORDER BY b.created_at DESC
        LIMIT 1 OFFSET ?
        """,
        (tg_user_id, index),
    )
    row = cur.fetchone()
    return dict(row) if row else None


# --- Status-based helpers ---


def count_user_books_by_status(tg_user_id: int, status: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) AS c
        FROM books b
        JOIN users u ON u.id = b.user_id
        WHERE u.tg_user_id = ? AND b.status = ?
        """,
        (tg_user_id, status),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def get_user_book_by_status_and_index(
    tg_user_id: int, status: str, index: int
) -> Optional[Dict[str, Any]]:
    # Legacy function kept for compatibility; now proxies to m2m
    return get_user_book_by_status_and_index_m2m(tg_user_id, status, index)


def update_book_status(book_id: int, status: str) -> None:
    # Legacy setter (single status) no longer used; noop keeps compatibility
    return None


# --- Favorite helpers ---
def toggle_favorite(book_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE books SET is_favorite = CASE is_favorite WHEN 1 THEN 0 ELSE 1 END WHERE id = ?",
        (book_id,),
    )
    conn.commit()
    cur.execute("SELECT is_favorite FROM books WHERE id = ?", (book_id,))
    row = cur.fetchone()
    return int(row[0]) if row else 0


def count_user_favorites(tg_user_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) AS c
        FROM books b
        JOIN users u ON u.id = b.user_id
        WHERE u.tg_user_id = ? AND b.is_favorite = 1
        """,
        (tg_user_id,),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def get_user_favorite_by_index(tg_user_id: int, index: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT b.id, b.name, b.author, b.genre, b.photo_id, b.status, b.is_favorite, u.tg_user_id
        FROM books b
        JOIN users u ON u.id = b.user_id
        WHERE u.tg_user_id = ? AND b.is_favorite = 1
        ORDER BY b.created_at DESC
        LIMIT 1 OFFSET ?
        """,
        (tg_user_id, index),
    )
    row = cur.fetchone()
    return dict(row) if row else None


# --- M2M status helpers ---
def toggle_status(book_id: int, status: str) -> int:
    if status not in {"in", "read"}:
        return 0
    conn = get_connection()
    cur = conn.cursor()
    # Try delete first; if exists -> remove and return 0 (now none active)
    cur.execute(
        "DELETE FROM book_statuses WHERE book_id = ? AND status = ?", (book_id, status)
    )
    if cur.rowcount > 0:
        conn.commit()
        return 0
    # Insert the requested status and ensure exclusivity: remove the opposite one
    opposite = "read" if status == "in" else "in"
    cur.execute(
        "INSERT OR IGNORE INTO book_statuses (book_id, status) VALUES (?, ?)",
        (book_id, status),
    )
    cur.execute(
        "DELETE FROM book_statuses WHERE book_id = ? AND status = ?",
        (book_id, opposite),
    )
    conn.commit()
    return 1


def count_user_books_by_status_m2m(tg_user_id: int, status: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) AS c
        FROM books b
        JOIN users u ON u.id = b.user_id
        JOIN book_statuses s ON s.book_id = b.id AND s.status = ?
        WHERE u.tg_user_id = ?
        """,
        (status, tg_user_id),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def get_user_book_by_status_and_index_m2m(
    tg_user_id: int, status: str, index: int
) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT b.id, b.name, b.author, b.genre, b.photo_id, b.status, b.is_favorite, u.tg_user_id
        FROM books b
        JOIN users u ON u.id = b.user_id
        JOIN book_statuses s ON s.book_id = b.id AND s.status = ?
        WHERE u.tg_user_id = ?
        ORDER BY b.created_at DESC
        LIMIT 1 OFFSET ?
        """,
        (status, tg_user_id, index),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def list_book_statuses(book_id: int) -> List[str]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT status FROM book_statuses WHERE book_id = ? ORDER BY status", (book_id,)
    )
    return [row[0] for row in cur.fetchall()]


def delete_book(book_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM books WHERE id = ?", (book_id,))
    conn.commit()
    return cur.rowcount > 0
