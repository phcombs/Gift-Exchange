"""SQLite storage. The only module that imports sqlite3.

Each call opens its own connection and closes it. Writes run inside BEGIN IMMEDIATE.
Error messages use ids, never names or addresses.
"""

import sqlite3
from contextlib import closing, contextmanager
from datetime import timezone
from pathlib import Path

from giftx import SCHEMA_VERSION
from giftx.compose import DEFAULT_BODY, DEFAULT_SUBJECT
from giftx.model import Person, Rejected, SendRecord, Sent, Unknown
from giftx.people import clean_email, clean_name

SCHEMA = """
CREATE TABLE groups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    subject TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE people (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    partner_id INTEGER REFERENCES people(id) ON DELETE SET NULL
);
CREATE TABLE draws (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL UNIQUE REFERENCES groups(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    locked_at TEXT
);
CREATE TABLE assignments (
    draw_id INTEGER NOT NULL REFERENCES draws(id) ON DELETE CASCADE,
    giver_id INTEGER NOT NULL REFERENCES people(id),
    recipient_id INTEGER NOT NULL REFERENCES people(id),
    PRIMARY KEY (draw_id, giver_id)
);
CREATE TABLE sends (
    id INTEGER PRIMARY KEY,
    draw_id INTEGER NOT NULL REFERENCES draws(id) ON DELETE CASCADE,
    giver_id INTEGER NOT NULL REFERENCES people(id),
    mode TEXT NOT NULL CHECK (mode IN ('practice','real')),
    status TEXT NOT NULL CHECK (status IN ('pending','sending','sent','failed','unknown')),
    to_address TEXT,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    image_name TEXT,
    started_at TEXT,
    finished_at TEXT,
    error TEXT,
    UNIQUE (draw_id, giver_id, mode)
);
CREATE INDEX people_group ON people(group_id);
"""


class StorageError(Exception):
    """Base class. The message is safe to show on the page."""


class NewerVersion(StorageError):
    def __init__(self):
        super().__init__("This data was made by a newer version of the app.")


class Locked(StorageError):
    def __init__(self):
        super().__init__(
            "Emails have started going out for this group, so only email addresses can be changed. "
            "Use \"Start a new exchange\" to change anything else."
        )


class NotFound(StorageError):
    pass


class DuplicateGroup(StorageError):
    pass


def _stamp(now):
    return now.astimezone(timezone.utc).isoformat(timespec="seconds")


class Storage:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self._open_schema()

    # ------------------------------------------------------------ connections

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    @contextmanager
    def _write(self):
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")

    @contextmanager
    def _read(self):
        with closing(self._connect()) as conn:
            yield conn

    def _open_schema(self):
        with self._write() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise NewerVersion()
            if version == 0:
                for statement in SCHEMA.split(";"):
                    if statement.strip():
                        conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _draw_row(conn, group_id):
        return conn.execute(
            "SELECT id, locked_at FROM draws WHERE group_id = ?", (group_id,)
        ).fetchone()

    def _clear_unlocked_draw(self, conn, group_id):
        """Raise Locked if the group's draw is locked; otherwise delete it. True if one was deleted."""
        row = self._draw_row(conn, group_id)
        if row is None:
            return False
        if row[1] is not None:
            raise Locked()
        conn.execute("DELETE FROM draws WHERE id = ?", (row[0],))
        return True

    @staticmethod
    def _group_of(conn, person_id):
        row = conn.execute("SELECT group_id FROM people WHERE id = ?", (person_id,)).fetchone()
        if row is None:
            raise NotFound(f"Person {person_id} was not found.")
        return row[0]

    # ------------------------------------------------------------ groups

    def create_group(self, name):
        name = clean_name(name)
        if not name:
            raise StorageError("The group name is blank.")
        with self._write() as conn:
            exists = conn.execute(
                "SELECT 1 FROM groups WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            if exists:
                raise DuplicateGroup(f"There is already a group called {name}.")
            cur = conn.execute(
                "INSERT INTO groups (name, subject, body) VALUES (?, ?, ?)",
                (name, DEFAULT_SUBJECT, DEFAULT_BODY),
            )
            return cur.lastrowid

    def list_groups(self):
        with self._read() as conn:
            return [
                (row[0], row[1])
                for row in conn.execute("SELECT id, name FROM groups ORDER BY name COLLATE NOCASE")
            ]

    def delete_group(self, group_id):
        with self._write() as conn:
            row = self._draw_row(conn, group_id)
            if row is not None and row[1] is not None:
                raise Locked()
            # assignments/sends reference people without cascade: remove the draw first
            conn.execute("DELETE FROM draws WHERE group_id = ?", (group_id,))
            conn.execute("UPDATE people SET partner_id = NULL WHERE group_id = ?", (group_id,))
            conn.execute("DELETE FROM people WHERE group_id = ?", (group_id,))
            conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))

    def get_message(self, group_id):
        with self._read() as conn:
            row = conn.execute("SELECT subject, body FROM groups WHERE id = ?", (group_id,)).fetchone()
        if row is None:
            raise NotFound(f"Group {group_id} was not found.")
        return row[0], row[1]

    def set_message(self, group_id, subject, body):
        with self._write() as conn:
            conn.execute(
                "UPDATE groups SET subject = ?, body = ? WHERE id = ?", (subject, body, group_id)
            )

    # ------------------------------------------------------------ people

    def list_people(self, group_id):
        with self._read() as conn:
            rows = conn.execute(
                "SELECT id, group_id, name, email, partner_id FROM people "
                "WHERE group_id = ? ORDER BY name COLLATE NOCASE, id",
                (group_id,),
            ).fetchall()
        return [Person(*row) for row in rows]

    def add_person(self, group_id, name, email):
        with self._write() as conn:
            if conn.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone() is None:
                raise NotFound(f"Group {group_id} was not found.")
            self._clear_unlocked_draw(conn, group_id)
            cur = conn.execute(
                "INSERT INTO people (group_id, name, email) VALUES (?, ?, ?)",
                (group_id, clean_name(name), clean_email(email)),
            )
            return cur.lastrowid

    def add_people(self, group_id, rows):
        """Add several (name, email) pairs in one transaction. Returns their ids."""
        with self._write() as conn:
            if conn.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone() is None:
                raise NotFound(f"Group {group_id} was not found.")
            if rows:
                self._clear_unlocked_draw(conn, group_id)
            return [
                conn.execute(
                    "INSERT INTO people (group_id, name, email) VALUES (?, ?, ?)",
                    (group_id, clean_name(name), clean_email(email)),
                ).lastrowid
                for name, email in rows
            ]

    def rename_person(self, pid, name):
        with self._write() as conn:
            self._clear_unlocked_draw(conn, self._group_of(conn, pid))
            conn.execute("UPDATE people SET name = ? WHERE id = ?", (clean_name(name), pid))

    def update_email(self, pid, email):
        """Allowed on a locked draw; keeps the draw (matches don't depend on addresses)."""
        with self._write() as conn:
            self._group_of(conn, pid)
            conn.execute("UPDATE people SET email = ? WHERE id = ?", (clean_email(email), pid))

    def delete_person(self, pid):
        with self._write() as conn:
            self._clear_unlocked_draw(conn, self._group_of(conn, pid))
            conn.execute("DELETE FROM people WHERE id = ?", (pid,))

    def set_couple(self, a, b):
        if a == b:
            raise StorageError("A person can't be their own partner.")
        with self._write() as conn:
            group = self._group_of(conn, a)
            if self._group_of(conn, b) != group:
                raise StorageError("Both people must be in the same group.")
            self._clear_unlocked_draw(conn, group)
            conn.execute(
                "UPDATE people SET partner_id = NULL WHERE id IN (?, ?) OR partner_id IN (?, ?)",
                (a, b, a, b),
            )
            conn.execute("UPDATE people SET partner_id = ? WHERE id = ?", (b, a))
            conn.execute("UPDATE people SET partner_id = ? WHERE id = ?", (a, b))

    def clear_couple(self, pid):
        with self._write() as conn:
            self._clear_unlocked_draw(conn, self._group_of(conn, pid))
            conn.execute(
                "UPDATE people SET partner_id = NULL WHERE id = ? OR partner_id = ?", (pid, pid)
            )

    # ------------------------------------------------------------ draws

    def save_draw(self, group_id, assignment, now):
        """Store a new draw for the group, replacing an unlocked one. Raises Locked."""
        with self._write() as conn:
            members = {
                row[0] for row in conn.execute("SELECT id FROM people WHERE group_id = ?", (group_id,))
            }
            if set(assignment) != members or set(assignment.values()) != members:
                raise StorageError("The draw doesn't match the group's current people. Draw again.")
            self._clear_unlocked_draw(conn, group_id)
            draw_id = conn.execute(
                "INSERT INTO draws (group_id, created_at) VALUES (?, ?)", (group_id, _stamp(now))
            ).lastrowid
            conn.executemany(
                "INSERT INTO assignments (draw_id, giver_id, recipient_id) VALUES (?, ?, ?)",
                [(draw_id, g, r) for g, r in assignment.items()],
            )
            return draw_id

    def draw_status(self, group_id):
        """(draw_id | None, locked_at | None, [(giver_id, giver_name)]). Never reads recipients."""
        with self._read() as conn:
            row = self._draw_row(conn, group_id)
            if row is None:
                return None, None, []
            givers = conn.execute(
                "SELECT p.id, p.name FROM assignments a JOIN people p ON p.id = a.giver_id "
                "WHERE a.draw_id = ? ORDER BY p.name COLLATE NOCASE, p.id",
                (row[0],),
            ).fetchall()
            return row[0], row[1], [(g[0], g[1]) for g in givers]

    def get_assignments(self, draw_id):
        """giver -> recipient. Only Reveal and the send preparation call this."""
        with self._read() as conn:
            return dict(
                conn.execute(
                    "SELECT giver_id, recipient_id FROM assignments WHERE draw_id = ?", (draw_id,)
                ).fetchall()
            )

    def discard_draw(self, group_id):
        """"Start a new exchange": delete the draw and its send records. Returns real emails sent."""
        with self._write() as conn:
            row = self._draw_row(conn, group_id)
            if row is None:
                return 0
            sent = conn.execute(
                "SELECT COUNT(*) FROM sends WHERE draw_id = ? AND mode = 'real' AND status = 'sent'",
                (row[0],),
            ).fetchone()[0]
            conn.execute("DELETE FROM draws WHERE id = ?", (row[0],))
            return sent

    # ------------------------------------------------------------ sends

    _RECORD_SQL = (
        "SELECT s.id, s.draw_id, d.group_id, s.giver_id, p.name, s.mode, s.status, s.to_address, "
        "s.subject, s.body, s.image_name, s.started_at, s.finished_at, s.error "
        "FROM sends s JOIN draws d ON d.id = s.draw_id JOIN people p ON p.id = s.giver_id "
    )

    @staticmethod
    def _insert_records(conn, draw_id, mode, rows):
        conn.executemany(
            "INSERT INTO sends (draw_id, giver_id, mode, status, subject, body, image_name) "
            "VALUES (?, ?, ?, 'pending', ?, ?, ?)",
            [(draw_id, r.giver_id, mode, r.subject, r.body, r.image_name) for r in rows],
        )

    def create_real_records(self, draw_id, rows, now):
        """Lock the draw and store the real records. False if it was already locked (records exist)."""
        with self._write() as conn:
            row = conn.execute("SELECT locked_at FROM draws WHERE id = ?", (draw_id,)).fetchone()
            if row is None:
                raise NotFound(f"Draw {draw_id} was not found.")
            if row[0] is not None:
                return False
            conn.execute("UPDATE draws SET locked_at = ? WHERE id = ?", (_stamp(now), draw_id))
            self._insert_records(conn, draw_id, "real", rows)
            return True

    def replace_practice_records(self, draw_id, rows):
        with self._write() as conn:
            conn.execute("DELETE FROM sends WHERE draw_id = ? AND mode = 'practice'", (draw_id,))
            self._insert_records(conn, draw_id, "practice", rows)

    def sendable(self, draw_id, mode, only=None):
        """Records the pipeline may send: pending first, then failed; each by giver name."""
        sql = self._RECORD_SQL + (
            "WHERE s.draw_id = ? AND s.mode = ? AND s.status IN ('pending', 'failed') "
        )
        args = [draw_id, mode]
        if only is not None:
            sql += "AND s.id = ? "
            args.append(only)
        sql += "ORDER BY s.status = 'failed', p.name COLLATE NOCASE, s.id"
        with self._read() as conn:
            return [SendRecord(*row) for row in conn.execute(sql, args)]

    def claim(self, send_id, now, to_address):
        """pending|failed -> sending, writing the address actually used. True if this caller got it."""
        with self._write() as conn:
            cur = conn.execute(
                "UPDATE sends SET status = 'sending', started_at = ?, finished_at = NULL, error = NULL, "
                "to_address = ? WHERE id = ? AND status IN ('pending', 'failed')",
                (_stamp(now), to_address, send_id),
            )
            return cur.rowcount == 1

    def record(self, send_id, result, now):
        """sending -> sent | failed | unknown."""
        if isinstance(result, Sent):
            status, error = "sent", None
        elif isinstance(result, Rejected):
            status, error = "failed", result.reason
        elif isinstance(result, Unknown):
            status, error = "unknown", result.reason
        else:
            raise TypeError(f"not a send result: {type(result).__name__}")
        with self._write() as conn:
            conn.execute(
                "UPDATE sends SET status = ?, error = ?, finished_at = ? "
                "WHERE id = ? AND status = 'sending'",
                (status, error, _stamp(now), send_id),
            )

    def recover_all_sending(self):
        """After a restart nothing can be in flight: every 'sending' record becomes 'unknown'."""
        with self._write() as conn:
            return conn.execute(
                "UPDATE sends SET status = 'unknown', error = 'the app stopped while sending' "
                "WHERE status = 'sending'"
            ).rowcount

    def mark_went(self, send_id):
        """unknown -> sent only."""
        with self._write() as conn:
            return conn.execute(
                "UPDATE sends SET status = 'sent', error = NULL WHERE id = ? AND status = 'unknown'",
                (send_id,),
            ).rowcount == 1

    def reset_to_pending(self, send_id):
        """Real sent|failed|unknown -> pending, for "Send again"."""
        with self._write() as conn:
            return conn.execute(
                "UPDATE sends SET status = 'pending', error = NULL, started_at = NULL, finished_at = NULL "
                "WHERE id = ? AND mode = 'real' AND status IN ('sent', 'failed', 'unknown')",
                (send_id,),
            ).rowcount == 1

    def status_rows(self, draw_id, mode):
        with self._read() as conn:
            return [
                SendRecord(*row)
                for row in conn.execute(
                    self._RECORD_SQL + "WHERE s.draw_id = ? AND s.mode = ? "
                    "ORDER BY p.name COLLATE NOCASE, s.id",
                    (draw_id, mode),
                )
            ]

    def images_in_use(self):
        with self._read() as conn:
            return {
                row[0]
                for row in conn.execute("SELECT DISTINCT image_name FROM sends WHERE image_name IS NOT NULL")
            }

    def image_users(self):
        """{image name: [group names]} for every image named on a send record."""
        users = {}
        with self._read() as conn:
            for name, group in conn.execute(
                "SELECT DISTINCT s.image_name, g.name FROM sends s "
                "JOIN draws d ON d.id = s.draw_id JOIN groups g ON g.id = d.group_id "
                "WHERE s.image_name IS NOT NULL ORDER BY g.name COLLATE NOCASE"
            ):
                users.setdefault(name, []).append(group)
        return users
