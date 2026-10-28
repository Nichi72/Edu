# -*- coding: utf-8 -*-
"""설정. bot/.env 에서 읽는다 (.env.example 참고).

서버 ID 는 안 적는다. 봇은 초대된 모든 서버에서 돌고, 서버 하나가 수업 하나다.
서버마다 `GRADING_CHANNEL` 이름(기본 채점실)의 채널을 선생님 채널로 쓴다. 없으면 봇이 만든다.
"""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field

from dotenv import load_dotenv

HERE = pathlib.Path(__file__).resolve().parent
load_dotenv(HERE / ".env")


@dataclass
class Settings:
    token: str
    instance: str
    grading_channel: str = "채점실"              # 서버마다 이 이름의 채널이 #채점실
    grading_channel_id: int = 0                 # 옛 설정 호환 — 이 ID 의 채널도 #채점실로 본다
    legacy_guild_id: int = 0                    # 옛 설정 호환 — 서버 없이 쌓인 옛 기록을 이 서버 것으로 본다
    teacher_ids: set[int] = field(default_factory=set)
    sheet_id: str = ""
    google_sa_json: str = ""
    data_dir: pathlib.Path = HERE / "data"
    catchup_days: int = 14
    max_attachment: int = 10 * 1024 * 1024


def _int(name: str, default: int = 0) -> int:
    v = os.environ.get(name, "").strip()
    return int(v) if v else default


def load() -> Settings:
    token = os.environ.get("DISCORD_TOKEN", "").strip()
    if not token:
        raise SystemExit("DISCORD_TOKEN 이 없다. bot/.env 를 .env.example 대로 만든다")
    teachers = {int(x) for x in os.environ.get("TEACHER_IDS", "").replace(" ", "").split(",") if x}
    s = Settings(
        token=token,
        instance=os.environ.get("INSTANCE", "").strip() or os.environ.get("COMPUTERNAME", "bot"),
        grading_channel=os.environ.get("GRADING_CHANNEL", "").strip().lstrip("#") or "채점실",
        grading_channel_id=_int("GRADING_CHANNEL_ID"),
        legacy_guild_id=_int("GUILD_ID"),
        teacher_ids=teachers,
        sheet_id=os.environ.get("SHEET_ID", "").strip(),
        google_sa_json=os.environ.get("GOOGLE_SA_JSON", "").strip(),
        data_dir=pathlib.Path(os.environ.get("DATA_DIR", "").strip() or HERE / "data"),
        catchup_days=_int("CATCHUP_DAYS", 14),
    )
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
