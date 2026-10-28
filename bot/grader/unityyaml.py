# -*- coding: utf-8 -*-
"""Unity 씬·프리팹(YAML)에서 오브젝트와 컴포넌트를 뽑는다.

Unity YAML 은 문서마다 `--- !u!<클래스ID> &<파일ID>` 머리가 붙은 여러 문서다.
문서 하나씩 PyYAML 로 읽고, 못 읽는 문서는 `키: 값` 줄만 긁는 느슨한 방식으로 넘어간다.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field

import yaml

DOC_RE = re.compile(r"^--- !u!(\d+) &(-?\d+)( stripped)?[ \t]*$", re.M)
GUID_RE = re.compile(r"guid:\s*([0-9a-fA-F]{32})")

# 패키지 스크립트 — 어느 프로젝트에서나 guid 가 같다. 모르는 guid 는 guid 그대로 비교하므로 틀려도 채점은 안 깨진다
KNOWN_SCRIPTS = {
    "a79441f348de89743a2939f4d699eac1": "UniversalAdditionalCameraData",
    "474bcb49853aa07438625e644c072ee6": "UniversalAdditionalLightData",
    "172515602e62fb746b5d573b38a5fe58": "Volume",
}


class _Loader(yaml.SafeLoader):
    pass


# 오브젝트 이름 "Yes"/"On" 이 True 가 되거나 날짜로 바뀌면 안 된다. 숫자와 null 만 변환한다
_Loader.yaml_implicit_resolvers = {
    k: [(t, r) for (t, r) in v if t in ("tag:yaml.org,2002:int", "tag:yaml.org,2002:float", "tag:yaml.org,2002:null")]
    for k, v in _Loader.yaml_implicit_resolvers.items()
}


@dataclass
class UDoc:
    class_id: int
    file_id: int
    type_name: str
    data: dict
    raw: str
    stripped: bool = False


@dataclass
class Comp:
    type: str          # Unity 타입 이름 (Transform, Camera, MonoBehaviour …)
    key: str           # 비교 키. MonoBehaviour 는 스크립트 이름, 모르면 guid:…
    data: dict


@dataclass
class GObj:
    name: str
    path: str          # 부모/자식 경로
    active: bool
    comps: list[Comp] = field(default_factory=list)
    prefab: str | None = None   # 프리팹 인스턴스면 프리팹 이름


@dataclass
class UnityFile:
    path: str
    objects: dict[str, GObj]    # 경로 → 오브젝트 (같은 경로가 둘이면 #2, #3)

    def find_by_name(self, name: str) -> list[GObj]:
        return [o for o in self.objects.values() if o.name == name]


# ───────────────────────── 문서 쪼개기 ─────────────────────────
def parse_docs(text: str) -> list[UDoc]:
    parts = DOC_RE.split(text)
    docs: list[UDoc] = []
    for k in range(1, len(parts) - 3, 4):
        cid, fid, stripped, body = int(parts[k]), int(parts[k + 1]), bool(parts[k + 2]), parts[k + 3]
        data = _load(body)
        if not data:
            continue
        type_name, inner = next(iter(data.items()))
        docs.append(UDoc(cid, fid, str(type_name), inner if isinstance(inner, dict) else {}, body, stripped))
    return docs


def _load(body: str) -> dict | None:
    try:
        d = yaml.load(body, Loader=_Loader)
        if isinstance(d, dict) and d:
            return d
    except yaml.YAMLError:
        pass
    return _loose(body)


def _loose(body: str) -> dict | None:
    """PyYAML 이 못 읽을 때: 첫 줄의 타입 이름과 들여쓰기 2칸짜리 `키: 값` 만 긁는다."""
    lines = body.splitlines()
    if not lines:
        return None
    m = re.match(r"^(\w+):\s*$", lines[0])
    if not m:
        return None
    inner: dict = {}
    for line in lines[1:]:
        mm = re.match(r"^  (\w+):\s*(.*)$", line)
        if mm:
            inner[mm.group(1)] = _scalar(mm.group(2))
    return {m.group(1): inner}


def _scalar(v: str):
    v = v.strip()
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)
    mm = re.fullmatch(r"\{(.*)\}", v)
    if mm:
        out = {}
        for pair in mm.group(1).split(","):
            if ":" in pair:
                a, b = pair.split(":", 1)
                out[a.strip()] = _scalar(b)
        return out
    return v


def _fid(v) -> int:
    if isinstance(v, dict):
        try:
            return int(v.get("fileID", 0) or 0)
        except (TypeError, ValueError):
            return 0
    return 0


# ───────────────────────── 모델 만들기 ─────────────────────────
def build(text: str, path: str, guid_map: dict[str, str] | None = None) -> UnityFile:
    guid_map = guid_map or {}
    docs = parse_docs(text)
    by_id = {d.file_id: d for d in docs}
    gos = {d.file_id: d for d in docs if d.class_id == 1}
    transforms = {d.file_id: d for d in docs if d.class_id in (4, 224)}
    t_of_go = {_fid(t.data.get("m_GameObject")): t for t in transforms.values()}

    def parent_go(go_id: int) -> int | None:
        t = t_of_go.get(go_id)
        if not t:
            return None
        f = _fid(t.data.get("m_Father"))
        ft = transforms.get(f) if f else None
        return _fid(ft.data.get("m_GameObject")) if ft else None

    def go_path(go_id: int) -> str:
        names, seen = [], set()
        cur: int | None = go_id
        while cur and cur not in seen and cur in gos:
            seen.add(cur)
            names.append(str(gos[cur].data.get("m_Name") or ""))
            cur = parent_go(cur)
        return "/".join(reversed(names))

    def transform_path(t_id: int) -> str:
        t = transforms.get(t_id)
        return go_path(_fid(t.data.get("m_GameObject"))) if t else ""

    def script_key(d: UDoc) -> str:
        m = re.search(r"m_Script:\s*\{[^}]*\}", d.raw)
        g = GUID_RE.search(m.group(0)) if m else None
        if not g:
            return "MonoBehaviour"
        guid = g.group(1).lower()
        if guid in guid_map:
            return posixpath.splitext(posixpath.basename(guid_map[guid]))[0]
        return KNOWN_SCRIPTS.get(guid, "guid:" + guid)

    objects: dict[str, GObj] = {}

    def put(path: str, obj: GObj):
        key, k = path, 2
        while key in objects:
            key = f"{path}#{k}"
            k += 1
        objects[key] = obj

    for gid, g in gos.items():
        comps: list[Comp] = []
        for c in g.data.get("m_Component") or []:
            d = by_id.get(_fid(c.get("component")) if isinstance(c, dict) else 0)
            if not d:
                continue
            key = script_key(d) if d.class_id == 114 else d.type_name
            comps.append(Comp(d.type_name, key, d.data))
        active = str(g.data.get("m_IsActive", 1)) != "0"
        put(go_path(gid), GObj(str(g.data.get("m_Name") or ""), go_path(gid), active, comps))

    # 프리팹 인스턴스: 이름은 m_Name 수정값 → 없으면 프리팹 파일 이름
    for d in docs:
        if d.class_id != 1001:
            continue
        g = GUID_RE.search(d.raw.split("m_SourcePrefab", 1)[-1]) if "m_SourcePrefab" in d.raw else None
        guid = g.group(1).lower() if g else ""
        prefab = posixpath.splitext(posixpath.basename(guid_map[guid]))[0] if guid in guid_map else (guid[:8] or "?")
        name = prefab
        mods = (d.data.get("m_Modification") or {}).get("m_Modifications") or []
        for mod in mods:
            if isinstance(mod, dict) and mod.get("propertyPath") == "m_Name" and mod.get("value") is not None:
                name = str(mod["value"])
                break
        parent = transform_path(_fid((d.data.get("m_Modification") or {}).get("m_TransformParent")))
        path = f"{parent}/{name}" if parent else name
        put(path, GObj(name, path, True, [Comp("PrefabInstance", "prefab:" + prefab, {})], prefab=prefab))

    return UnityFile(path=path, objects=objects)


def value_at(data: dict, dotted: str):
    """`m_LocalPosition` 또는 `m_TaaSettings.m_Quality` 같은 경로로 값을 꺼낸다."""
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur
