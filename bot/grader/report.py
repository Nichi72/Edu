# -*- coding: utf-8 -*-
"""결과를 글로. 학생용(DM)과 선생님용(#채점실) 두 가지."""
from __future__ import annotations

from .compare import Progress, Result, sort_key

MAX_LINES = 8          # 학생에게 한 번에 보여줄 빠진 것 수
DISCORD_LIMIT = 1900


def student_message(p: Progress, nth: int = 1, when: str = "") -> str:
    lines: list[str] = []
    head = "📦 제출 받음"
    if when:
        head += f" — {when}"
    if nth:
        head += f" ({nth}번째 제출)"
    lines.append(head)

    if not p.results:
        lines.append("아직 채점 기준이 없다. 선생님이 `/진도` 로 기준을 올리면 그때 다시 올려도 된다.")
        return "\n".join(lines)

    reached = p.reached
    tr = p.target_result
    if reached:
        lines.append(f"도달한 진도: {reached} ✅")
    elif p.closest is not None and p.closest is not tr:
        c = p.closest
        lines.append(f"도달한 진도: 없음 — 가장 가까운 항목 {c.cp} ({c.checks}개 중 {c.passed}개)")
    else:
        lines.append("도달한 진도: 없음")

    # 보여줄 실패: 과녁이 있으면 과녁, 없으면 도달 다음 항목
    show = tr if tr is not None else next((r for r in p.results if not r.ok and
                                           (reached is None or sort_key(r.cp) > sort_key(reached))), None)
    if show is not None and not show.ok:
        lines.append(f"{show.cp} ❌  {show.checks}개 중 {show.passed}개 충족")
        for f in show.findings[:MAX_LINES]:
            lines.append(f"  • {f.where}: {f.student}")
        rest = len(show.findings) - MAX_LINES
        if rest > 0:
            lines.append(f"  • … 외 {rest}개")

    if p.target:
        if tr is None:
            lines.append(f"→ 과녁 {p.target} 의 기준이 아직 없다")
        elif p.target_ok:
            lines.append(f"→ 오늘 과녁 {p.target} **통과** 🎉")
        else:
            lines.append(f"→ 오늘 과녁 {p.target} 미통과. 고쳐서 다시 올리면 된다")
    return _clip("\n".join(lines))


def teacher_line(name: str, p: Progress, nth: int = 1, when: str = "") -> str:
    tr = p.target_result
    mark = "✅ 통과" if p.target_ok else "❌ 미통과"
    bits = [f"`{when}`" if when else "", f"**{name}**", f"{p.target or '-'} {mark}", f"({nth}번째)"]
    if tr and not tr.ok:
        bits.append(f"· {tr.checks}개 중 {tr.passed}개")
        bits.append("· " + "; ".join(f.student for f in tr.findings[:3]))
    reached = p.reached
    if reached and reached != p.target:
        bits.append(f"· 도달 {reached}")
    return " ".join(b for b in bits if b)


def teacher_detail(p: Progress) -> str:
    out: list[str] = []
    for r in p.results:
        out.append(f"{'✅' if r.ok else '❌'} {r.cp}  {r.passed}/{r.checks}")
        for f in r.findings:
            out.append(f"  - [{f.area}] {f.where}: {f.student}")
            if f.teacher:
                out.extend("      " + ln for ln in f.teacher.splitlines())
    return _clip("\n".join(out) or "(결과 없음)")


def result_text(r: Result, teacher: bool = False) -> str:
    out = [f"{'✅' if r.ok else '❌'} {r.cp or '비교'}  {r.passed}/{r.checks}"]
    for f in r.findings:
        out.append(f"  - [{f.area}] {f.where}: {f.student}")
        if teacher and f.teacher:
            out.extend("      " + ln for ln in f.teacher.splitlines())
    return "\n".join(out)


def _clip(s: str) -> str:
    return s if len(s) <= DISCORD_LIMIT else s[:DISCORD_LIMIT - 20] + "\n… (잘림)"
