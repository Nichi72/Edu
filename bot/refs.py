# -*- coding: utf-8 -*-
"""기준(정답지) 보관. data/refs/7일차.zip 처럼 파일 이름이 곧 항목.

원본은 #채점실에 봇이 올린 `[기준] cp-07` 메시지의 첨부다. 다른 컴에서 켜도 거기서 다시 내려받는다.
"""
from __future__ import annotations

import logging
import pathlib
import re

from grader.bundle import Bundle, BundleError
from grader.compare import sort_key

log = logging.getLogger("refs")
NAME_RE = re.compile(r'^[^\s/\\:*?\"<>|]{1,30}$')   # 공백·경로 글자만 빼고 자유 (7일차, cp-07, 과제1)
MARK = "[기준]"


def valid_name(cp: str) -> bool:
    return bool(NAME_RE.match(cp))


class RefStore:
    def __init__(self, root: pathlib.Path):
        self.dir = root / "refs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Bundle] = {}

    def names(self) -> list[str]:
        return sorted((p.stem for p in self.dir.glob("*.zip")), key=sort_key)

    def has(self, cp: str) -> bool:
        return (self.dir / f"{cp}.zip").exists()

    def save(self, cp: str, data: bytes) -> Bundle:
        b = Bundle.from_zip_bytes(data, f"{cp}.zip")       # 깨진 zip 이면 여기서 BundleError
        (self.dir / f"{cp}.zip").write_bytes(data)
        self._cache[cp] = b
        return b

    def get(self, cp: str) -> Bundle:
        if cp not in self._cache:
            self._cache[cp] = Bundle.from_path(self.dir / f"{cp}.zip")
        return self._cache[cp]

    def all(self) -> list[tuple[str, Bundle]]:
        out = []
        for cp in self.names():
            try:
                out.append((cp, self.get(cp)))
            except BundleError as e:
                log.warning("기준 %s 를 못 읽는다: %s", cp, e)
        return out

    @staticmethod
    def parse_mark(content: str) -> str | None:
        """`[기준] cp-07 · …` 메시지에서 항목 이름."""
        m = re.match(r"\s*\[기준\]\s*(\S+)", content or "")
        return m.group(1) if m and valid_name(m.group(1)) else None
