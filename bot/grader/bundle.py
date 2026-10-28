# -*- coding: utf-8 -*-
"""제출물·기준 묶음. zip 이나 폴더를 메모리로 읽어 들인다.

학생이 보낸 zip 은 믿지 않는다: 경로 탈출(..), 절대 경로, 너무 많은 파일, 너무 큰 파일을 막고
Library/Temp 같은 쓰레기는 버린다. 학생이 제출 버튼 대신 프로젝트 폴더를 통째로 압축해도 받아 준다.
"""
from __future__ import annotations

import io
import json
import pathlib
import posixpath
import zipfile
from dataclasses import dataclass, field

MAX_ENTRIES = 4000
MAX_TOTAL = 80 * 1024 * 1024
MAX_FILE = 8 * 1024 * 1024
SKIP_TOP = {"library", "temp", "obj", "logs", "usersettings", ".git", ".vs", ".idea", "build", "builds",
            "memorycaptures", "recordings", "제출", ".venv", "node_modules"}
KEEP_EXT = {".cs", ".unity", ".prefab", ".mat", ".meta", ".asset", ".txt", ".json", ".asmdef",
            ".physicmaterial", ".physicsmaterial", ".anim", ".controller", ".inputactions"}
MANIFEST = "submit-manifest.json"


class BundleError(ValueError):
    """사람에게 그대로 보여줘도 되는 이유."""


@dataclass
class Bundle:
    files: dict[str, bytes]                  # 루트 기준 슬래시 경로 → 내용
    manifest: dict = field(default_factory=dict)
    name: str = ""

    # ── 만들기 ─────────────────────────────────────────────
    @classmethod
    def from_zip_bytes(cls, data: bytes, name: str = "") -> "Bundle":
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise BundleError("zip 파일이 아니다. Unity 메뉴 「제출 ▸ 과제 zip 만들기」 로 만든 zip 을 올린다")
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_ENTRIES:
            raise BundleError(f"파일이 너무 많다 ({len(infos)}개). Library 폴더가 섞인 것 같다")
        total = sum(i.file_size for i in infos)
        if total > MAX_TOTAL:
            raise BundleError(f"풀었을 때 너무 크다 ({total // (1024 * 1024)} MB). Library 폴더가 섞인 것 같다")
        raw: dict[str, bytes] = {}
        for i in infos:
            p = _clean(i.filename)
            if p is None or i.file_size > MAX_FILE:
                continue
            raw[p] = zf.read(i)
        return cls._finish(raw, name)

    @classmethod
    def from_path(cls, path: str | pathlib.Path) -> "Bundle":
        p = pathlib.Path(path)
        if p.is_file():
            return cls.from_zip_bytes(p.read_bytes(), p.name)
        if not p.is_dir():
            raise BundleError(f"없는 경로: {p}")
        raw: dict[str, bytes] = {}
        for f in p.rglob("*"):
            if not f.is_file():
                continue
            rel = _clean(f.relative_to(p).as_posix())
            if rel is None or f.stat().st_size > MAX_FILE:
                continue
            raw[rel] = f.read_bytes()
        return cls._finish(raw, p.name)

    @classmethod
    def _finish(cls, raw: dict[str, bytes], name: str) -> "Bundle":
        raw = _strip_common_root(raw)
        files = {p: b for p, b in raw.items() if _wanted(p)}
        manifest = {}
        if MANIFEST in files:
            try:
                manifest = json.loads(files[MANIFEST].decode("utf-8-sig"))
            except (ValueError, UnicodeDecodeError):
                manifest = {}
        if not any(p.startswith("Assets/") for p in files):
            raise BundleError("Assets 폴더가 안 보인다. Unity 프로젝트에서 만든 zip 이 맞는지 본다")
        return cls(files=files, manifest=manifest, name=name)

    # ── 읽기 ─────────────────────────────────────────────
    def text(self, path: str) -> str:
        return self.files[path].decode("utf-8-sig", errors="replace")

    def has(self, path: str) -> bool:
        return path in self.files

    def by_ext(self, ext: str, under: str = "Assets/") -> list[str]:
        return sorted(p for p in self.files if p.startswith(under) and p.lower().endswith(ext))

    def scripts(self) -> list[str]:
        """학생이 쓴 스크립트. Editor/·Plugins/ 아래는 도구라서 뺀다."""
        return [p for p in self.by_ext(".cs") if not _is_tool_path(p)]

    def scenes(self) -> list[str]:
        return self.by_ext(".unity")

    def prefabs(self) -> list[str]:
        return self.by_ext(".prefab")

    def materials(self) -> list[str]:
        return self.by_ext(".mat")

    def guid_map(self) -> dict[str, str]:
        """.meta 의 guid → 에셋 경로. 씬이 가리키는 스크립트·프리팹을 이름으로 풀 때 쓴다."""
        out: dict[str, str] = {}
        for p, b in self.files.items():
            if not p.endswith(".meta"):
                continue
            head = b[:400].decode("utf-8", errors="ignore")
            for line in head.splitlines():
                if line.startswith("guid:"):
                    out[line[5:].strip()] = p[:-5]
                    break
        return out

    def project_setting(self, key: str) -> str | None:
        """ProjectSettings.asset 의 최상위 `key: value` 한 줄."""
        p = "ProjectSettings/ProjectSettings.asset"
        if p not in self.files:
            return None
        # PlayerSettings: 아래 2칸 들여쓰기 — 더 깊은 곳의 같은 이름은 안 본다
        for line in self.text(p).splitlines():
            if line.startswith(key + ":") or line.startswith("  " + key + ":"):
                return line.split(":", 1)[1].strip()
        return None

    def summary(self) -> str:
        return (f"스크립트 {len(self.scripts())}, 씬 {len(self.scenes())}, 프리팹 {len(self.prefabs())}, "
                f"머티리얼 {len(self.materials())}, 파일 {len(self.files)}")


# ── 경로 정리 ─────────────────────────────────────────────
def _clean(name: str) -> str | None:
    p = name.replace("\\", "/")
    if p.startswith("/") or ":" in p.split("/")[0]:
        return None
    parts = [s for s in p.split("/") if s not in ("", ".")]
    if not parts or any(s == ".." for s in parts):
        return None
    if parts[0] == "__MACOSX" or parts[-1] == ".DS_Store":
        return None
    return posixpath.join(*parts)


def _strip_common_root(raw: dict[str, bytes]) -> dict[str, bytes]:
    """`내프로젝트/Assets/...` 처럼 폴더째 압축했으면 맨 위 폴더를 벗긴다."""
    for _ in range(3):
        if any(p.startswith(("Assets/", "ProjectSettings/")) for p in raw) or MANIFEST in raw:
            return raw
        tops = {p.split("/", 1)[0] for p in raw if "/" in p}
        if len(tops) != 1:
            return raw
        top = tops.pop()
        raw = {p.split("/", 1)[1]: b for p, b in raw.items() if p.startswith(top + "/")}
    return raw


def _wanted(p: str) -> bool:
    top = p.split("/", 1)[0].lower()
    if top in SKIP_TOP:
        return False
    if p == MANIFEST:
        return True
    if not p.startswith(("Assets/", "ProjectSettings/", "Packages/")):
        return False
    ext = posixpath.splitext(p)[1].lower()
    return ext in KEEP_EXT


def _is_tool_path(p: str) -> bool:
    parts = p.split("/")
    return any(s in ("Editor", "Plugins", "editor", "plugins") for s in parts[:-1])
