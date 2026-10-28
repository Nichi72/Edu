# -*- coding: utf-8 -*-
"""기록. 로컬 SQLite 가 캐시, 구글 시트가 거울.

- 서버 하나 = 수업 하나. 학생·제출 행마다 guild_id(서버) 가 붙는다. 시트에는 「수업」(서버 이름) 열로 보인다
- 시트가 안 닿아도 채점은 멈추지 않는다. 못 보낸 행은 outbox 에 쌓였다가 나중에 올라간다
- 심장박동: 「상태」 시트 B2 에 30초마다 시각을 찍는다. 다른 컴에서 2분 안에 찍은 게 있으면 새 봇은 켜지지 않는다
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib
import sqlite3
from dataclasses import dataclass

log = logging.getLogger("store")

SUBMIT_HEADER = ["시각", "수업", "학번", "이름", "디스코드ID", "과녁", "결과", "도달", "빠진 것", "회차", "파일", "기기",
                 "메시지ID", "서버ID"]
ROSTER_HEADER = ["디스코드ID", "수업", "학번", "이름", "등록 시각", "서버ID"]
HEARTBEAT_STALE = 120          # 초


def label(sid: str | None, name: str | None) -> str:
    """화면에 보일 "학번 이름"."""
    return " ".join(x for x in (sid, name) if x).strip()


def parse_student(text: str) -> tuple[str, str] | None:
    """`20241234 홍길동` 또는 `홍길동 20241234` → (학번, 이름). 둘 중 하나라도 없으면 None.

    학번 = 숫자가 들어간 토큰, 이름 = 나머지. 각각 20자까지."""
    toks = text.split()
    sids = [t for t in toks if any(c.isdigit() for c in t)]
    names = [t for t in toks if not any(c.isdigit() for c in t)]
    if len(sids) != 1 or not names:
        return None
    sid, name = sids[0][:20], " ".join(names)[:20]
    if len(sid) < 2 or len(name) < 2:
        return None
    return sid, name


# ───────────────────────── 로컬 ─────────────────────────
class Local:
    def __init__(self, path: pathlib.Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS roster (user_id INTEGER PRIMARY KEY, name TEXT, registered_at TEXT,
                sid TEXT, guild_id INTEGER);
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER UNIQUE, user_id INTEGER, name TEXT,
                at TEXT, target TEXT, ok INTEGER, reached TEXT, summary TEXT, nth INTEGER,
                file TEXT, device TEXT, detail TEXT, sid TEXT, guild_id INTEGER);
            CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, payload TEXT, created TEXT);
        """)
        for table, col, typ in (("roster", "sid", "TEXT"), ("roster", "guild_id", "INTEGER"),
                                ("submissions", "sid", "TEXT"), ("submissions", "guild_id", "INTEGER")):
            cols = {r["name"] for r in self.db.execute(f"PRAGMA table_info({table})")}
            if col not in cols:                                  # 옛 DB 에 열을 더한다
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        self.db.commit()

    def migrate_legacy(self, guild_id: int) -> int:
        """서버 구분이 없던 때의 기록(guild_id 가 빈 행, 과녁 'target')을 그 서버 것으로 돌린다. 바꾼 행 수."""
        n = self.db.execute("UPDATE roster SET guild_id=? WHERE guild_id IS NULL", (guild_id,)).rowcount
        n += self.db.execute("UPDATE submissions SET guild_id=? WHERE guild_id IS NULL", (guild_id,)).rowcount
        old = self.get("target")
        if old:
            if not self.get(f"target:{guild_id}"):
                self.set(f"target:{guild_id}", old)
            self.set("target", None)
            n += 1
        self.db.commit()
        return n

    # 명단 — 학생 한 명은 수업(서버) 하나에 속한다
    def student(self, user_id: int) -> sqlite3.Row | None:
        """등록된 학생 (sid, name, guild_id, registered_at). 없으면 None."""
        return self.db.execute("SELECT * FROM roster WHERE user_id=?", (user_id,)).fetchone()

    def name_of(self, user_id: int) -> str | None:
        row = self.student(user_id)
        return row["name"] if row else None

    def register(self, user_id: int, sid: str, name: str, guild_id: int | None, when: str | None = None) -> None:
        self.db.execute("INSERT OR REPLACE INTO roster (user_id, sid, name, guild_id, registered_at) VALUES (?,?,?,?,?)",
                        (user_id, sid, name, guild_id, when or dt.datetime.now().isoformat(timespec="seconds")))
        self.db.commit()

    def set_guild(self, user_id: int, guild_id: int) -> None:
        self.db.execute("UPDATE roster SET guild_id=? WHERE user_id=?", (guild_id, user_id))
        self.db.commit()

    def roster(self, guild_id: int | None = None) -> list[sqlite3.Row]:
        if guild_id is None:
            return self.db.execute("SELECT * FROM roster ORDER BY sid, name").fetchall()
        return self.db.execute("SELECT * FROM roster WHERE guild_id=? ORDER BY sid, name", (guild_id,)).fetchall()

    # 제출
    def seen(self, message_id: int) -> bool:
        return self.db.execute("SELECT 1 FROM submissions WHERE message_id=?", (message_id,)).fetchone() is not None

    def count(self, user_id: int, target: str | None) -> int:
        return self.db.execute("SELECT COUNT(*) FROM submissions WHERE user_id=? AND IFNULL(target,'')=?",
                               (user_id, target or "")).fetchone()[0]

    def add_submission(self, **row) -> None:
        cols = ",".join(row)
        self.db.execute(f"INSERT OR IGNORE INTO submissions ({cols}) VALUES ({','.join('?' * len(row))})",
                        tuple(row.values()))
        self.db.commit()

    def latest(self, user_id: int, target: str | None = None) -> sqlite3.Row | None:
        if target:
            return self.db.execute("SELECT * FROM submissions WHERE user_id=? AND target=? ORDER BY id DESC LIMIT 1",
                                   (user_id, target)).fetchone()
        return self.db.execute("SELECT * FROM submissions WHERE user_id=? ORDER BY id DESC LIMIT 1",
                               (user_id,)).fetchone()

    def status(self, guild_id: int, target: str) -> dict[int, sqlite3.Row]:
        """그 수업, 그 과녁의 학생별 마지막 제출."""
        rows = self.db.execute("SELECT * FROM submissions WHERE guild_id=? AND target=? ORDER BY id",
                               (guild_id, target)).fetchall()
        return {r["user_id"]: r for r in rows}

    # 상태
    def get(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str | None) -> None:
        if value is None:
            self.db.execute("DELETE FROM state WHERE key=?", (key,))
        else:
            self.db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, value))
        self.db.commit()

    # outbox
    def enqueue(self, kind: str, payload: list) -> None:
        self.db.execute("INSERT INTO outbox (kind, payload, created) VALUES (?,?,?)",
                        (kind, json.dumps(payload, ensure_ascii=False), dt.datetime.now().isoformat(timespec="seconds")))
        self.db.commit()

    def outbox(self, limit: int = 50) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM outbox ORDER BY id LIMIT ?", (limit,)).fetchall()

    def dequeue(self, ids: list[int]) -> None:
        self.db.executemany("DELETE FROM outbox WHERE id=?", [(i,) for i in ids])
        self.db.commit()


# ───────────────────────── 구글 시트 ─────────────────────────
@dataclass
class Heartbeat:
    instance: str
    at: dt.datetime | None

    def alive(self, now: dt.datetime) -> bool:
        return self.at is not None and (now - self.at).total_seconds() < HEARTBEAT_STALE


class Sheet:
    """gspread 는 동기 호출이다. 봇에서는 asyncio.to_thread 로 감싼다. 수업이 여러 개여도 시트는 하나."""

    def __init__(self, sheet_id: str, sa_json: str):
        import gspread
        self.gc = gspread.service_account(filename=sa_json)
        self.sh = self.gc.open_by_key(sheet_id)
        self.submit = self._ws("제출", SUBMIT_HEADER)
        self.roster = self._ws("명단", ROSTER_HEADER)
        self.state = self._ws("상태", None)

    def _ws(self, title: str, header: list[str] | None):
        try:
            ws = self.sh.worksheet(title)
        except Exception:
            ws = self.sh.add_worksheet(title=title, rows=1000, cols=max(14, len(header or [])))
            if header:
                ws.append_row(header)
        if header and not ws.row_values(1):
            ws.append_row(header)
        elif header and ws.row_values(1) != header:
            log.warning("시트 「%s」 머리글이 다르다. 기대: %s / 실제: %s — 열 이름으로 맞춰 읽는다",
                        title, header, ws.row_values(1))
        return ws

    def append(self, kind: str, row: list) -> None:
        ws = self.submit if kind == "submission" else self.roster
        ws.append_row([str(x) if x is not None else "" for x in row], value_input_option="RAW")

    def read_roster(self) -> list[tuple[int, str, str, str, int | None]]:
        """(디스코드ID, 학번, 이름, 등록 시각, 서버ID). 열은 머리글 이름으로 찾는다 (옛 시트는 열이 적다)."""
        rows = self.roster.get_all_values()
        if not rows:
            return []
        idx = {h.strip(): i for i, h in enumerate(rows[0])}
        c_uid, c_sid, c_name = idx.get("디스코드ID", 0), idx.get("학번"), idx.get("이름", 1)
        c_when, c_gid = idx.get("등록 시각"), idx.get("서버ID")

        def cell(r, i):
            return r[i].strip() if i is not None and i < len(r) else ""

        out = []
        for r in rows[1:]:
            if cell(r, c_uid).isdigit() and cell(r, c_name):
                gid = int(cell(r, c_gid)) if cell(r, c_gid).isdigit() else None
                out.append((int(cell(r, c_uid)), cell(r, c_sid), cell(r, c_name), cell(r, c_when), gid))
        return out

    def heartbeat(self, instance: str) -> None:
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        self.state.update("A1:B2", [["instance", instance], ["heartbeat", now]])

    def read_heartbeat(self) -> Heartbeat:
        vals = self.state.get("A1:B2")
        d = {r[0]: (r[1] if len(r) > 1 else "") for r in vals if r}
        at = None
        if d.get("heartbeat"):
            try:
                at = dt.datetime.fromisoformat(d["heartbeat"])
            except ValueError:
                at = None
        return Heartbeat(d.get("instance", ""), at)
