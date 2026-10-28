# -*- coding: utf-8 -*-
"""grader.yaml 읽기. 없으면 compare.DEFAULT_CONFIG 그대로."""
from __future__ import annotations

import pathlib

import yaml

HERE = pathlib.Path(__file__).resolve().parent.parent      # bot/
DEFAULT_PATH = HERE / "grader.yaml"


def load_config(path: str | pathlib.Path | None = None) -> dict:
    p = pathlib.Path(path) if path else DEFAULT_PATH
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{p}: 맨 바깥이 키: 값 꼴이어야 한다")
    return data
