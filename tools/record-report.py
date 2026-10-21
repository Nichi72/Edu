# -*- coding: utf-8 -*-
"""수업 기록 보고서.

Unity 의 「기록」 메뉴(Assets/Editor/ChangeRecorder)가 남긴
    recordings/<세션>/events.jsonl      사건 한 줄씩
    recordings/<세션>/snapshots/        코드·씬·프리팹 사본
을 읽어 사람이 보는 타임라인 한 장을 만든다.
    recordings/<세션>/report.md

실행:  python tools/record-report.py [세션 폴더] [--video 마커번호=mm:ss]
       세션 폴더를 생략하면 가장 최근 세션.
       --video 1=00:12  → 마커 1 이 영상의 0분 12초에 보인다. 모든 줄에 영상 시각이 같이 붙는다.
       --video start=00:05 → 기록 시작이 영상 0분 5초.

보고서 구성
  1. 요약 (시간·마커·코드 저장·Play·에러 수)
  2. 마커 목록 — 수업에서 멈춘 지점. 교재의 빈칸 자리가 여기다
  3. 타임라인 — 마커로 절을 나눈 사건 목록. 코드 저장마다 직전 사본과의 diff
  4. 코드 최종본 — 세션 중 바뀐 .cs 의 마지막 상태

영상과 맞추기: 모든 줄에 경과 시간(hh:mm:ss)이 있고, 요약에 시작 벽시계 시각이 있다.
  기록기 창을 화면 한구석에 띄워 두면 영상에 기록기의 시계가 그대로 찍히고, 마커를 누르면 Scene 뷰에
  "마커 N" 알림이 떠서 영상에서 그 순간을 찾을 수 있다. 그 한 지점으로 --video 를 주면 된다.
"""
import datetime
import difflib
import io
import json
import pathlib
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 한 번에 보여줄 diff 줄 수. 코드는 전부, 씬·프리팹 같은 YAML 은 앞부분만
DIFF_LIMIT_CODE = 400
DIFF_LIMIT_OTHER = 40
NEW_FILE_LIMIT = 150


# ───────────────────────── 입력 ─────────────────────────
def pick_session(arg):
    if arg:
        p = pathlib.Path(arg)
        if not p.is_absolute():
            p = ROOT / p
        if not (p / "events.jsonl").exists():
            sys.exit(f"events.jsonl 이 없다: {p}")
        return p
    rec = ROOT / "recordings"
    if not rec.exists():
        sys.exit("recordings/ 폴더가 없다. Unity 에서 기록 ▸ 시작 을 먼저 누른다")
    sessions = sorted(d for d in rec.iterdir() if d.is_dir() and (d / "events.jsonl").exists())
    if not sessions:
        sys.exit("recordings/ 에 세션이 없다")
    return sessions[-1]


def load_events(sdir):
    evs = []
    for line in (sdir / "events.jsonl").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evs.append(json.loads(line))
        except json.JSONDecodeError:
            evs.append({"kind": "error", "e": evs[-1]["e"] if evs else 0, "t": "", "msg": "깨진 줄: " + line[:80]})
    return evs


def load_snapshot_index(sdir):
    """rel 경로 → [(seq, 파일명), ...]  기록 순서대로"""
    by_path = {}
    idx = sdir / "snapshots" / "index.tsv"
    if idx.exists():
        for line in idx.read_text(encoding="utf-8").splitlines():
            c = line.split("\t")
            if len(c) >= 4:
                by_path.setdefault(c[1], []).append((int(c[0]), c[3]))
    return by_path


def read_snap(sdir, name):
    p = sdir / "snapshots" / name
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8", errors="replace").splitlines()


# ───────────────────────── 표시 ─────────────────────────
def hms(e):
    e = int(round(float(e or 0)))
    return f"{e // 3600:02d}:{e % 3600 // 60:02d}:{e % 60:02d}"


def wall(t):
    try:
        return datetime.datetime.fromisoformat(t).strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return ""


PATH_NAMES = {
    "m_LocalPosition": "Position", "m_LocalRotation": "Rotation", "m_LocalScale": "Scale",
    "m_Name": "이름", "m_IsActive": "Active", "m_TagString": "Tag", "m_Layer": "Layer",
    "m_Enabled": "Enabled", "m_Materials": "Materials", "m_Script": "Script",
    "m_Mass": "Mass", "m_Drag": "Drag", "m_AngularDrag": "Angular Drag", "m_UseGravity": "Use Gravity",
    "m_IsKinematic": "Is Kinematic", "m_Constraints": "Constraints", "m_CollisionDetection": "Collision Detection",
    "m_IsTrigger": "Is Trigger", "m_Size": "Size", "m_Center": "Center", "m_Radius": "Radius",
    "m_BackGroundColor": "Background", "m_ClearFlags": "Clear Flags", "orthographic": "Projection(Orthographic)",
    "orthographic size": "Size", "field of view": "Field of View", "near clip plane": "Near", "far clip plane": "Far",
    "m_Color": "Color", "m_Intensity": "Intensity", "m_Type": "Type",
    "_BaseColor": "Base Color", "_Color": "Color", "_BaseMap": "Base Map", "_Smoothness": "Smoothness", "_Metallic": "Metallic",
}


def human(path):
    out = []
    for seg in path.split("."):
        if seg == "Array":
            continue
        m = re.fullmatch(r"data\[(\d+)\]", seg)
        if m and out:
            out[-1] += f"[{m.group(1)}]"
            continue
        out.append(PATH_NAMES.get(seg, seg[2:] if seg.startswith("m_") and len(seg) > 2 else seg))
    return ".".join(out)


def fence(lines, lang=""):
    return [f"```{lang}"] + lines + ["```"]


def unified(prev, cur, limit):
    """difflib 결과에서 파일 머리말을 떼고 +/- 수와 본문을 돌려준다"""
    diff = list(difflib.unified_diff(prev, cur, n=2, lineterm=""))
    body = [d for d in diff if not (d.startswith("---") or d.startswith("+++"))]
    plus = sum(1 for d in body if d.startswith("+"))
    minus = sum(1 for d in body if d.startswith("-"))
    if len(body) > limit:
        body = body[:limit] + [f"… ({len(body) - limit}줄 더. 전체는 snapshots/ 의 사본을 비교한다)"]
    return plus, minus, body


# ───────────────────────── 전처리 ─────────────────────────
def preprocess(evs):
    """소음을 줄인다. 원본 파일은 건드리지 않는다."""
    out = []
    # 값 변화가 잡힌 오브젝트의 '세부 불명' 변경은 같은 일을 두 번 적는 것이다
    prop_times = {}
    for ev in evs:
        if ev["kind"] == "prop":
            prop_times.setdefault(ev.get("obj"), []).append(float(ev["e"]))
    last_select = None
    steps = None
    for ev in evs:
        k = ev["kind"]
        if k == "touch" and "obj" in ev:
            if any(abs(t - float(ev["e"])) < 2.5 for t in prop_times.get(ev["obj"], [])):
                continue
        if k == "compile" and ev.get("state") == "start":
            continue
        if k == "select":
            key = ev.get("obj") or ev.get("asset")
            if key == last_select:
                continue
            last_select = key
        else:
            last_select = None
        # 연속 Step 은 하나로
        if k == "play" and ev.get("state") == "step":
            if steps is None:
                steps = dict(ev, count=1, first_frame=ev.get("frame"))
                out.append(steps)
            else:
                steps["count"] += 1
                steps["frame"] = ev.get("frame")
            continue
        steps = None
        out.append(ev)
    return out


# ───────────────────────── 사건 한 줄 ─────────────────────────
def describe(ev):
    k = ev["kind"]
    g = ev.get
    if k == "select":
        return f"선택 · {g('obj') or g('asset')}" + (f" 외 {g('count') - 1}개" if g("count") else "")
    if k == "go_create":
        comps = ", ".join(g("comps", []))
        extra = f" (+자식 {g('children')}개)" if g("children") else ""
        return f"**생성** {g('obj')}{extra}  [{comps}]"
    if k == "go_destroy":
        return f"**삭제** {g('obj')}"
    if k == "go_parent":
        return f"**부모 변경** {g('obj')}: {g('from')} → {g('to')}"
    if k == "comp_add":
        return f"**컴포넌트 추가** {g('comp')} @ {g('obj')}"
    if k == "comp_remove":
        return f"**컴포넌트 제거** {g('comp')} @ {g('obj')}"
    if k == "prop":
        if g("comp") == "GameObject" and g("path") == "m_Name":
            return f"**이름 변경** {g('from')} → {g('to')}"
        return f"**값** {g('obj')} · {g('comp')} · {human(g('path', ''))}: `{g('from')}` → `{g('to')}`"
    if k == "asset_prop":
        return f"**값** {g('asset')} · {human(g('path', ''))}: `{g('from')}` → `{g('to')}`"
    if k == "touch":
        return f"변경 · {g('obj') or g('asset')} (무엇이 바뀌었는지는 못 잡음)"
    if k == "asset_create":
        return f"**에셋 생성** {g('asset')} ({g('type')})"
    if k == "asset_delete":
        return f"**에셋 삭제** {g('asset')}"
    if k == "asset_move":
        return f"**에셋 이동** {g('from')} → {g('asset')}"
    if k == "asset_import":
        return f"에셋 변경 · {g('asset')}"
    if k == "scene_save":
        return f"**씬 저장** {g('scene')}"
    if k == "scene_open":
        return f"**씬 열기** {g('scene')}"
    if k == "scene_new":
        return "**새 씬**"
    if k == "prefab_stage":
        return f"**프리팹 편집 {'열기' if g('state') == 'open' else '닫기'}** {g('asset')}"
    if k == "play":
        s = g("state")
        if s == "start":
            return "**▶ Play**"
        if s == "stop":
            return f"**■ Stop**  ({float(g('seconds', 0)):.0f}초)"
        if s == "pause":
            return f"**❚❚ Pause**  frame {g('frame')}"
        if s == "unpause":
            return f"**▶ 다시 진행**  frame {g('frame')}"
        if s == "step":
            n = g("count", 1)
            return f"**Step ×{n}**  frame {g('first_frame')} → {g('frame')}" if n > 1 else f"**Step**  frame {g('frame')}"
    if k == "compile":
        errs = g("errors") or []
        head = f"**컴파일** {float(g('seconds', 0)):.1f}초 · 에러 {len(errs)}"
        if g("warnings"):
            head += f" · 경고 {g('warnings')}"
        if errs:
            return head + "\n" + "\n".join(f"    - `{e}`" for e in errs)
        return head
    if k == "log":
        where = f"  — {g('where')}" if g("where") else ""
        return f"**Console {g('type')}** {g('msg')}{where}"
    if k == "log_summary":
        return "Console 반복 · " + " / ".join(g("items", []))
    if k == "play_summary":
        return "Play 중 · " + " / ".join(g("items", []))
    if k == "undo":
        return f"**{'다시 실행' if g('redo') else '되돌리기'}** {g('name')}"
    if k == "children_order":
        return f"순서 변경 · {g('obj')}"
    if k == "prefab_update":
        return f"프리팹 인스턴스 갱신 ×{g('count')}"
    if k == "reload":
        return "에디터 리로드 (컴파일 또는 Play 진입)"
    if k == "editor_quit":
        return "**에디터 종료**"
    if k == "error":
        return f"기록기 오류 · {g('where')}: {g('msg')}"
    return f"{k} · " + ", ".join(f"{a}={b}" for a, b in ev.items() if a not in ("t", "e", "n", "kind"))


# ───────────────────────── 본문 ─────────────────────────
def parse_clock(txt):
    """mm:ss 또는 hh:mm:ss → 초"""
    parts = [float(x) for x in txt.strip().split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def main():
    args = sys.argv[1:]
    video_spec = None
    if "--video" in args:
        i = args.index("--video")
        if i + 1 >= len(args):
            sys.exit("--video 뒤에 마커번호=mm:ss 가 필요하다")
        video_spec = args[i + 1]
        del args[i:i + 2]
    sdir = pick_session(args[0] if args else None)
    raw = load_events(sdir)
    if not raw:
        sys.exit("사건이 없다")
    by_path = load_snapshot_index(sdir)
    raw.sort(key=lambda e: float(e.get("e", 0)))   # 안정 정렬: 같은 시각이면 파일 순서
    evs = preprocess(raw)

    start = next((e for e in raw if e["kind"] == "session_start"), raw[0])
    stop = next((e for e in reversed(raw) if e["kind"] == "session_stop"), None)
    end_e = float(stop["e"]) if stop else float(raw[-1]["e"])
    markers = [e for e in raw if e["kind"] == "marker"]
    files = [e for e in raw if e["kind"] == "file"]
    code_saves = [e for e in files if e["path"].endswith(".cs")]
    plays = [e for e in raw if e["kind"] == "play" and e.get("state") == "start"]
    compile_errors = sum(len(e.get("errors") or []) for e in raw if e["kind"] == "compile")
    console_errors = sum(1 for e in raw if e["kind"] == "log" and e.get("type") in ("Error", "Exception", "Assert"))

    try:
        start_dt = datetime.datetime.fromisoformat(start["t"])
        when = start_dt.strftime("%Y-%m-%d %H:%M") + " ~ " + (start_dt + datetime.timedelta(seconds=end_e)).strftime("%H:%M")
    except (ValueError, KeyError):
        when = sdir.name

    # 영상 시각: 영상_시각 = 경과 + offset
    video_offset = None
    if video_spec:
        key, _, clock = video_spec.partition("=")
        try:
            vsec = parse_clock(clock)
        except ValueError:
            sys.exit(f"--video 시각을 읽을 수 없다: {clock}")
        if key.strip() == "start":
            video_offset = vsec
        else:
            m = next((x for x in markers if str(x.get("n")) == key.strip()), None)
            if m is None:
                sys.exit(f"마커 {key} 가 기록에 없다. 있는 마커: {[x.get('n') for x in markers]}")
            video_offset = vsec - float(m["e"])

    def stamp(e):
        if video_offset is None:
            return f"`{hms(e)}`"
        v = float(e) + video_offset
        return f"`{hms(e)}` 영상 `{hms(v) if v >= 0 else '-' + hms(-v)}`"

    out = []
    out.append(f"# 수업 기록 — {when}  ({end_e / 60:.0f}분)")
    out.append("")
    out.append(f"{start.get('project', '')} · Unity {start.get('unity', '')} · 씬 {start.get('scene', '')}  ")
    out.append(f"세션 폴더 `{sdir.relative_to(ROOT).as_posix() if sdir.is_relative_to(ROOT) else sdir}`" + ("" if stop else "  · **끝 표시가 없다 (기록 ▸ 끝 을 안 누름)**"))
    out.append("")
    out.append("| 마커 | 코드 저장 | 파일 저장(전체) | Play | 컴파일 에러 | Console 에러 | 사건 |")
    out.append("|---|---|---|---|---|---|---|")
    out.append(f"| {len(markers)} | {len(code_saves)} | {len(files)} | {len(plays)}회 | {compile_errors} | {console_errors} | {len(raw)} |")
    out.append("")

    out.append("## 마커 — 수업에서 멈춘 지점")
    out.append("")
    if markers:
        for m in markers:
            out.append(f"- {stamp(m['e'])}  마커 {m.get('n')}" + (f" — {m['text']}" if m.get("text") else ""))
    else:
        out.append("- (없음. Ctrl+Shift+M 을 안 눌렀다)")
    out.append("")

    if code_saves:
        out.append("## 코드 저장 — 파일별")
        out.append("")
        per = {}
        for e in code_saves:
            per.setdefault(e["path"], []).append(hms(e["e"]))
        for p, ts in per.items():
            out.append(f"- `{p}`: {len(ts)}회  ({', '.join(ts)})")
        out.append("")

    out.append("## 타임라인")
    out.append("")
    if video_offset is None:
        out.append("시간은 기록 시작 후 경과. 괄호는 벽시계. 코드는 저장할 때마다 직전 사본과의 차이.  ")
        out.append("영상과 맞추려면 `--video 마커번호=mm:ss` 를 주고 다시 만든다.")
    else:
        out.append(f"시간은 기록 시작 후 경과, 그 옆이 영상 시각 (`--video {video_spec}`). 괄호는 벽시계.")
    out.append("")

    for ev in evs:
        k = ev["kind"]
        t = hms(ev.get("e", 0))
        ts = stamp(ev.get("e", 0))
        w = wall(ev.get("t", ""))
        if k == "session_start":
            out.append(f"### {t} 시작  ({w})")
            out.append("")
            continue
        if k == "session_stop":
            out.append("")
            out.append(f"### {t} 끝  ({w})  — {ev.get('reason', '')}")
            out.append("")
            continue
        if k == "marker":
            out.append("")
            out.append(f"### {t} ■ 마커 {ev.get('n')}" + (f" — {ev['text']}" if ev.get("text") else "") + f"  ({w})")
            out.append("")
            continue
        if k == "file":
            rel = ev["path"]
            is_code = rel.endswith(".cs")
            snapname = ev["snap"].split("/")[-1]
            lst = by_path.get(rel, [])
            i = next((n for n, (s, name) in enumerate(lst) if name == snapname), None)
            cur = read_snap(sdir, snapname)
            prev = read_snap(sdir, lst[i - 1][1]) if (i is not None and i > 0) else None
            if cur is None:
                out.append(f"- {ts} **저장** {rel} (사본 없음)")
                continue
            if prev is None:
                out.append(f"- {ts} **새 파일** {rel} ({ev.get('lines')}줄)")
                if is_code:
                    body = cur[:NEW_FILE_LIMIT] + ([f"… ({len(cur) - NEW_FILE_LIMIT}줄 더)"] if len(cur) > NEW_FILE_LIMIT else [])
                    out.extend("  " + l for l in fence(body, "csharp"))
                continue
            plus, minus, body = unified(prev, cur, DIFF_LIMIT_CODE if is_code else DIFF_LIMIT_OTHER)
            if plus == 0 and minus == 0:
                out.append(f"- {ts} 저장 · {rel} (내용 같음)")
                continue
            out.append(f"- {ts} **저장** {rel}  (+{plus} −{minus})")
            out.extend("  " + l for l in fence(body, "diff"))
            continue
        desc = describe(ev)
        if "\n" in desc:
            first, rest = desc.split("\n", 1)
            out.append(f"- {ts} {first}")
            out.append(rest)
        else:
            out.append(f"- {ts} {desc}")

    # 코드 최종본
    changed_cs = []
    for rel, lst in by_path.items():
        if rel.endswith(".cs") and any(seq > 0 for seq, _ in lst):
            changed_cs.append((rel, lst[-1][1]))
    if changed_cs:
        out.append("")
        out.append("## 코드 최종본 — 세션 중 바뀐 파일")
        out.append("")
        for rel, name in sorted(changed_cs):
            cur = read_snap(sdir, name) or []
            out.append(f"### {rel}")
            out.append("")
            out.extend(fence(cur, "csharp"))
            out.append("")

    report = sdir / "report.md"
    report.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"보고서: {report}")
    print(f"사건 {len(raw)} · 마커 {len(markers)} · 코드 저장 {len(code_saves)} · Play {len(plays)}회")


if __name__ == "__main__":
    main()
