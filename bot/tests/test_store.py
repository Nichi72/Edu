# -*- coding: utf-8 -*-
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from store import Local, label, parse_student  # noqa: E402


def test_parse_student():
    assert parse_student("20241234 홍길동") == ("20241234", "홍길동")
    assert parse_student("홍길동 20241234") == ("20241234", "홍길동")
    assert parse_student("  1-03  김 철수 ") == ("1-03", "김 철수")
    assert parse_student("홍길동") is None            # 학번 없음
    assert parse_student("20241234") is None          # 이름 없음
    assert parse_student("1 2 홍길동") is None         # 학번이 둘
    assert label("20241234", "홍길동") == "20241234 홍길동" and label(None, "홍길동") == "홍길동"


def test_local_register_and_migration(tmp_path):
    db = tmp_path / "bot.db"
    old = sqlite3.connect(db)                          # 학번·서버 열이 없던 옛 DB
    old.executescript("""
        CREATE TABLE roster (user_id INTEGER PRIMARY KEY, name TEXT, registered_at TEXT);
        INSERT INTO roster VALUES (1, '옛학생', '2026-10-01T00:00:00');
        CREATE TABLE submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER UNIQUE, user_id INTEGER,
            name TEXT, at TEXT, target TEXT, ok INTEGER, reached TEXT, summary TEXT, nth INTEGER,
            file TEXT, device TEXT, detail TEXT);
    """)
    old.commit(); old.close()

    local = Local(db)
    st = local.student(1)
    assert st["name"] == "옛학생" and st["sid"] is None and st["guild_id"] is None
    local.register(2, "20241234", "홍길동", 500)
    local.register(3, "20249999", "김영희", 600)
    st = local.student(2)
    assert (st["sid"], st["name"], st["guild_id"]) == ("20241234", "홍길동", 500) and local.name_of(2) == "홍길동"
    local.set_guild(1, 500)
    assert [r["user_id"] for r in local.roster(500)] == [1, 2]       # 수업별 명단
    assert [r["user_id"] for r in local.roster()] == [1, 2, 3]

    local.add_submission(message_id=10, user_id=2, sid="20241234", name="홍길동", guild_id=500, at="10/28 20:00",
                         target="7일차", ok=1, reached="7일차", summary="", nth=1, file="x.zip", device="d", detail="")
    local.add_submission(message_id=11, user_id=3, sid="20249999", name="김영희", guild_id=600, at="10/28 20:01",
                         target="7일차", ok=0, reached="", summary="x", nth=1, file="y.zip", device="d", detail="")
    assert local.latest(2)["sid"] == "20241234"
    assert set(local.status(500, "7일차")) == {2}                    # 다른 수업의 제출은 안 섞인다
    assert set(local.status(600, "7일차")) == {3}


def test_migrate_legacy(tmp_path):
    local = Local(tmp_path / "bot.db")
    local.register(1, "1", "옛학생", None)                            # 서버 구분이 없던 때의 행
    local.add_submission(message_id=1, user_id=1, name="옛학생", at="", target="테스트", ok=1, nth=1, file="a.zip")
    local.set("target", "테스트")
    assert local.migrate_legacy(700) == 3
    assert local.student(1)["guild_id"] == 700 and set(local.status(700, "테스트")) == {1}
    assert local.get("target") is None and local.get("target:700") == "테스트"
    assert local.migrate_legacy(700) == 0                              # 두 번째는 할 일이 없다
