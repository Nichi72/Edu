# -*- coding: utf-8 -*-
"""포함 비교 — 기준(선생님)에 있는 것이 제출(학생)에 다 있는가.

학생이 더 가진 것은 보지 않는다. 숫자 값·주석·공백은 이미 지워져 있다.
발견(Finding) 하나가 학생에게 보이는 한 줄이다. 학생용 문장은 구조 수준까지만 말하고 코드는 안 보여준다.
"""
from __future__ import annotations

import posixpath
import re
from collections import Counter
from dataclasses import dataclass, field

from . import csharp, unityyaml
from .bundle import Bundle

DEFAULT_CONFIG: dict = {
    # 기준 코드에 있어도 학생에게 요구하지 않는 문장 (정규식, 정규화된 문장 기준)
    "ignore_statements": [r"^Debug\.Log\(", r"^print\("],
    # 기준 씬에 있어도 안 보는 오브젝트 경로
    "ignore_objects": [],
    # 안 보는 컴포넌트 키
    "ignore_components": [],
    # 값까지 같아야 하는 것. 기준에 그 오브젝트·컴포넌트가 있을 때만 본다. 숫자는 허용 오차
    "value_rules": [
        {"object": "Main Camera", "component": "Camera", "fields": {"orthographic": 0, "orthographic size": 0.01}},
        {"object": "Main Camera", "component": "Transform", "fields": {"m_LocalPosition": 0.01}},
    ],
    # ProjectSettings.asset 에서 같아야 하는 키
    "project_settings": ["activeInputHandler"],
}


# 값 규칙의 지적은 학생에게도 기준 값을 보여 준다 (코드가 아니라 Inspector 설정이라서).
# 항목 이름은 Inspector 에 보이는 이름으로 바꿔서. 없는 이름은 m_ 만 떼고 그대로
FIELD_LABELS = {
    "m_LocalPosition": "Position", "m_LocalRotation": "Rotation", "m_LocalEulerAnglesHint": "Rotation",
    "m_LocalScale": "Scale",
    "orthographic": "Projection", "orthographic size": "Size", "field of view": "Field of View",
    "near clip plane": "Clipping Planes Near", "far clip plane": "Clipping Planes Far",
    "m_BackGroundColor": "Background", "m_Depth": "Depth",
}
VALUE_LABELS = {"orthographic": {0: "Perspective", 1: "Orthographic"}}


def _field_label(fld: str) -> str:
    if fld in FIELD_LABELS:
        return FIELD_LABELS[fld]
    return ".".join(p[2:] if p.startswith("m_") else p for p in fld.split("."))


def _fmt_value(fld: str, v) -> str:
    """학생이 Inspector 에 그대로 넣을 수 있는 꼴. 5 / (0, 0, -10) / Orthographic"""
    names = VALUE_LABELS.get(fld)
    if names and isinstance(v, (int, float)) and int(v) in names:
        return names[int(v)]
    if v is None:
        return "없음"
    if isinstance(v, bool):
        return "켬" if v else "끔"
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else f"{v:.3f}".rstrip("0").rstrip(".")
    if isinstance(v, dict):
        order = [k for k in ("x", "y", "z", "w", "r", "g", "b", "a") if k in v]
        if order and len(order) == len(v):
            return "(" + ", ".join(_fmt_value("", v[k]) for k in order) + ")"
        return ", ".join(f"{k}: {_fmt_value('', x)}" for k, x in v.items())
    return str(v)


@dataclass
class Finding:
    area: str        # 스크립트 / 씬 / 프리팹 / 머티리얼 / 설정
    where: str       # BirdMove.cs, SampleScene.unity …
    student: str     # 학생에게 보여줄 문장
    teacher: str     # 선생님용 상세


@dataclass
class Result:
    cp: str
    checks: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    @property
    def passed(self) -> int:
        return max(0, self.checks - len(self.findings))

    def add(self, area: str, where: str, student: str, teacher: str = "") -> None:
        self.findings.append(Finding(area, where, student, teacher))


def _base(p: str) -> str:
    return posixpath.basename(p)


def _stem(p: str) -> str:
    return posixpath.splitext(_base(p))[0]


def _label(key: str) -> str:
    if key.startswith("guid:"):
        return "(패키지 컴포넌트)"
    if key.startswith("prefab:"):
        return "프리팹 " + key[7:] + " 인스턴스"
    return key


def _norm_type(t: str) -> str:
    return re.sub(r"\s+", "", t).replace("System.Single", "float").replace("Single", "float")


def _close(a, b, tol) -> bool:
    if isinstance(a, dict):
        return isinstance(b, dict) and all(_close(v, b.get(k), tol) for k, v in a.items())
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= float(tol)
    return a == b


class Comparer:
    def __init__(self, config: dict | None = None):
        self.cfg = dict(DEFAULT_CONFIG)
        if config:
            self.cfg.update({k: v for k, v in config.items() if v is not None})
        self._ignore_stmt = [re.compile(p) for p in self.cfg["ignore_statements"]]
        self._ignore_obj = [re.compile(p) for p in self.cfg["ignore_objects"]]
        self._ignore_comp = set(self.cfg["ignore_components"])

    # ───────────────────────── 들머리 ─────────────────────────
    def compare(self, ref: Bundle, sub: Bundle, cp: str = "") -> Result:
        r = Result(cp=cp)
        self._scripts(ref, sub, r)
        self._scenes(ref, sub, r)
        self._prefabs(ref, sub, r)
        self._materials(ref, sub, r)
        self._settings(ref, sub, r)
        return r

    # ───────────────────────── 스크립트 ─────────────────────────
    def _scripts(self, ref: Bundle, sub: Bundle, r: Result) -> None:
        ref_files = [csharp.parse(ref.text(p), p) for p in ref.scripts()]
        sub_files = [csharp.parse(sub.text(p), p) for p in sub.scripts()]
        sub_classes: dict[str, tuple[csharp.CsClass, csharp.CsFile]] = {}
        for f in sub_files:
            for c in f.classes.values():
                sub_classes.setdefault(c.name, (c, f))
        sub_names = {_base(f.path) for f in sub_files}

        for rf in ref_files:
            base = _base(rf.path)
            if not rf.classes:
                continue
            r.checks += 1
            if base not in sub_names and not any(c in sub_classes for c in rf.classes):
                r.add("스크립트", base, f"{base} 파일이 없다", "기준 클래스: " + ", ".join(rf.classes))
                continue
            for rc in rf.classes.values():
                r.checks += 1
                hit = sub_classes.get(rc.name)
                if not hit:
                    r.add("스크립트", base, f"{base} 에 class {rc.name} 이(가) 없다",
                          "파일은 있는데 클래스 이름이 다르다")
                    continue
                sc, sf = hit
                if rc.base:
                    r.checks += 1
                    if rc.base != sc.base:
                        r.add("스크립트", base, f"class {rc.name} 이(가) {rc.base} 를 상속하지 않는다",
                              f"기준 `: {rc.base}` / 제출 `: {sc.base or '(없음)'}`")
                for u in sorted(rf.usings):
                    r.checks += 1
                    if u not in sf.usings:
                        r.add("스크립트", base, f"using {u}; 이 없다")
                self._fields(rc, sc, base, r)
                self._methods(rc, sc, base, r)

    def _fields(self, rc: csharp.CsClass, sc: csharp.CsClass, base: str, r: Result) -> None:
        for name, rf in rc.fields.items():
            r.checks += 1
            sf = sc.fields.get(name)
            teacher = "기준: " + " ".join(rf.modifiers + [rf.type, name])
            if sf is None:
                if name in sc.properties:
                    r.add("스크립트", base, f"{rc.name}: {name} 이(가) 변수가 아니라 프로퍼티다", teacher)
                else:
                    r.add("스크립트", base, f"{rc.name}: 변수 {name} 이(가) 없다", teacher)
                continue
            if _norm_type(sf.type) != _norm_type(rf.type):
                r.add("스크립트", base, f"{rc.name}: 변수 {name} 의 자료형이 다르다",
                      teacher + f" / 제출: {sf.type}")
                continue
            if rf.serialized and not sf.serialized:
                r.add("스크립트", base, f"{rc.name}: 변수 {name} 이(가) Inspector 에 안 보인다 (public 이 아니다)",
                      teacher + f" / 제출: {' '.join(sf.modifiers) or '(수식어 없음)'}")

    def _methods(self, rc: csharp.CsClass, sc: csharp.CsClass, base: str, r: Result) -> None:
        for name, rm in rc.methods.items():
            want = Counter(s for s in rm.statements if not self._ignored_stmt(s))
            r.checks += 1
            sm = sc.methods.get(name)
            if sm is None:
                r.add("스크립트", base, f"{rc.name}: {name}() 가 없다", f"기준 문장 {sum(want.values())}개")
                continue
            if not want:
                continue
            r.checks += 1
            missing = want - Counter(sm.statements)
            if missing:
                k = sum(missing.values())
                detail = "\n".join("  " + s for s in missing.elements())
                r.add("스크립트", base, f"{rc.name}: {name}() 안에 빠진 문장 {k}개", "빠진 문장:\n" + detail)

    def _ignored_stmt(self, s: str) -> bool:
        return any(p.search(s) for p in self._ignore_stmt)

    # ───────────────────────── 씬 ─────────────────────────
    def _scenes(self, ref: Bundle, sub: Bundle, r: Result) -> None:
        rmap, smap = ref.guid_map(), sub.guid_map()
        sub_scenes = sub.scenes()
        for rp in ref.scenes():
            base = _base(rp)
            sp = rp if rp in sub.files else next((p for p in sub_scenes if _base(p) == base), None)
            if sp is None and len(sub_scenes) == 1:
                sp = sub_scenes[0]
            r.checks += 1
            if sp is None:
                r.add("씬", base, f"씬 {base} 이(가) 없다", "제출 씬: " + ", ".join(map(_base, sub_scenes)))
                continue
            rm = unityyaml.build(ref.text(rp), rp, rmap)
            sm = unityyaml.build(sub.text(sp), sp, smap)
            self._objects(rm, sm, r, "씬", base)
            self._value_rules(rm, sm, r, base)

    def _objects(self, rm: unityyaml.UnityFile, sm: unityyaml.UnityFile, r: Result, area: str, where: str) -> None:
        for path, ro in rm.objects.items():
            if any(p.search(ro.path) for p in self._ignore_obj):
                continue
            r.checks += 1
            so = sm.objects.get(path)
            if so is None:
                same = sm.find_by_name(ro.name)
                if not same:
                    r.add(area, where, f"오브젝트 {ro.name} 이(가) 없다", f"기준 경로 {ro.path}")
                    continue
                so = same[0]
                r.add(area, where, f"오브젝트 {ro.name} 의 부모(위치)가 기준과 다르다",
                      f"기준 {ro.path} / 제출 {so.path}")
            if ro.active and not so.active:
                r.checks += 1
                r.add(area, where, f"오브젝트 {ro.name} 이(가) 꺼져 있다 (체크 해제)")
            want = Counter(c.key for c in ro.comps if c.key not in self._ignore_comp)
            have = Counter(c.key for c in so.comps)
            for key, cnt in want.items():
                r.checks += 1
                if have[key] < cnt:
                    r.add(area, where, f"{ro.name} 에 {_label(key)} 컴포넌트가 없다",
                          f"기준 {cnt}개 / 제출 {have[key]}개 ({key})")

    def _value_rules(self, rm: unityyaml.UnityFile, sm: unityyaml.UnityFile, r: Result, where: str) -> None:
        for rule in self.cfg["value_rules"]:
            ro = rm.objects.get(rule["object"]) or next(iter(rm.find_by_name(rule["object"])), None)
            so = sm.objects.get(rule["object"]) or next(iter(sm.find_by_name(rule["object"])), None)
            if ro is None or so is None:
                continue
            rc = next((c for c in ro.comps if c.key == rule["component"]), None)
            sc = next((c for c in so.comps if c.key == rule["component"]), None)
            if rc is None or sc is None:
                continue
            for fld, tol in (rule.get("fields") or {}).items():
                rv = unityyaml.value_at(rc.data, fld)
                if rv is None:
                    continue
                r.checks += 1
                sv = unityyaml.value_at(sc.data, fld)
                if not _close(rv, sv, tol):
                    r.add("씬", where,
                          f"{ro.name} 의 {_field_label(fld)} 값을 {_fmt_value(fld, rv)} 에 맞춘다"
                          f" (지금 {_fmt_value(fld, sv)})",
                          f"기준 {rv} / 제출 {sv} ({rule['component']} {fld})")

    # ───────────────────────── 프리팹 · 머티리얼 · 설정 ─────────────────────────
    def _prefabs(self, ref: Bundle, sub: Bundle, r: Result) -> None:
        rmap, smap = ref.guid_map(), sub.guid_map()
        subs = {_base(p): p for p in sub.prefabs()}
        for rp in ref.prefabs():
            base = _base(rp)
            r.checks += 1
            sp = subs.get(base)
            if sp is None:
                r.add("프리팹", base, f"프리팹 {_stem(rp)} 이(가) 없다")
                continue
            rm = unityyaml.build(ref.text(rp), rp, rmap)
            sm = unityyaml.build(sub.text(sp), sp, smap)
            self._objects(rm, sm, r, "프리팹", base)

    def _materials(self, ref: Bundle, sub: Bundle, r: Result) -> None:
        have = {_base(p) for p in sub.materials()}
        for rp in ref.materials():
            r.checks += 1
            if _base(rp) not in have:
                r.add("머티리얼", _base(rp), f"머티리얼 {_stem(rp)} 이(가) 없다")

    def _settings(self, ref: Bundle, sub: Bundle, r: Result) -> None:
        for key in self.cfg["project_settings"]:
            rv = ref.project_setting(key)
            if rv is None:
                continue
            r.checks += 1
            sv = sub.project_setting(key)
            if sv != rv:
                r.add("설정", "ProjectSettings", f"Project Settings 의 {key} 가 기준과 다르다",
                      f"기준 {rv} / 제출 {sv}")


# ───────────────────────── 진도: 기준 여러 개를 차례로 ─────────────────────────
_NUM = re.compile(r"\d+")


def prefix(cp: str) -> str:
    """항목 이름에서 숫자를 뺀 나머지 = '계열'. 7일차·8일차 는 같은 계열, 과제1 은 다른 계열."""
    return _NUM.sub("", cp.lower()).strip()


def sort_key(cp: str) -> tuple[str, tuple[int, ...]]:
    """계열이 같으면 이름 속 숫자 순서로 (2일차 < 7일차 < 10일차). 숫자가 없으면 그 이름 혼자 한 계열."""
    return (prefix(cp), tuple(int(n) for n in _NUM.findall(cp)))


@dataclass
class Progress:
    """기준 여러 개에 대본 결과.

    코드는 자라기만 하지 않는다 — cp-06 의 문장이 cp-07 에서 바뀌므로, cp-07 상태인 학생은 cp-06 기준에는
    떨어진다. 그래서 "앞 항목 전부 통과"가 아니라 **통과한 것 중 가장 높은 항목**을 도달 진도로 본다.
    """
    target: str | None
    results: list[Result]          # 항목 순서대로

    @property
    def reached(self) -> str | None:
        ok = [r.cp for r in self.results if r.ok]
        return ok[-1] if ok else None

    @property
    def closest(self) -> Result | None:
        """통과한 게 없을 때 가장 가까웠던 항목 (충족 비율이 가장 높은 것)."""
        fails = [r for r in self.results if not r.ok and r.checks]
        return max(fails, key=lambda r: (r.passed / r.checks, sort_key(r.cp))) if fails else None

    @property
    def target_result(self) -> Result | None:
        return next((r for r in self.results if r.cp == self.target), None)

    @property
    def target_ok(self) -> bool:
        tr = self.target_result
        return bool(tr and tr.ok)


def evaluate(refs: list[tuple[str, Bundle]], sub: Bundle, comparer: Comparer,
             target: str | None) -> Progress:
    """refs: (cp, 기준) 목록. target 과 계열이 같은 것 중 target 이하를 순서대로 본다. 과녁이 없으면 전부."""
    chain = sorted(refs, key=lambda x: sort_key(x[0]))
    if target:
        want = prefix(target)
        chain = [(c, b) for c, b in chain if prefix(c) == want and sort_key(c) <= sort_key(target)]
    results = [comparer.compare(b, sub, c) for c, b in chain]
    return Progress(target=target, results=results)
