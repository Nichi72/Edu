# -*- coding: utf-8 -*-
"""교재 빌더.

docs/녹화교재/<묶음>/NN_제목.md  →  chNN.html,  개념_이름.md  →  concept-이름.html,  + index.html

서식은 docs/녹화교재/ 의 textbook.css · _chapter.css · _chapter.js 를 쓴다.

쓰는 기준은 docs/녹화교재/교재틀.md. 본보기는 docs/녹화교재/1024수업/02_Translate로_움직인다.md

md 규칙
  맨 위 <!-- --> 주석        원고 메모(상태 / 재료 / 분량 …). 페이지에 쓰이는 것은 파일: · 돌아가기: · 영상파일: 뿐이다
  # 07. 제목                 번호와 제목
  > **이번 시간에 만드는 것** — 한 줄   이어지는 > 1. 2. 3. 이 목표 목록
  ## 절 제목                 절. 7.1, 7.2 … 로 번호가 붙는다
  ### 1. 단계 제목  (영상 02:13)   단계. 괄호의 영상 시각은 칩이 된다
  ```csharp ... ```           코드 블록. ______ 는 빈칸으로 강조된다
  > 막히면: …  / > 멈춤 — …  / > **다음 시간 질문** — …   콜아웃
  - [ ] …                     체크리스트
  **용어** — 설명              「알아야 할 것」 절에서는 표로 바뀐다
  맨 끝 <!-- 교수용 … -->      원고에만 남는 메모. 페이지에는 찍지 않는다

  | 표 | 표 |                 표. 열 2~5 개. 둘째 줄은 |---|---|
  > **라벨** — …              굵은 말로 시작하는 인용은 그 말을 라벨로 쓰는 메모 상자가 된다 (예: **한 가지 더**)
  (영상 16:13 · 19:07)        영상 시각 여러 개. 본문 속 「(영상 08:02)」 도 칩이 된다
  머리말 파일: Assets/Script/BirdMove.cs   코드 블록 위에 찍히는 파일 이름. ```csharp 다른파일.cs 로 블록마다 바꿀 수 있다

실행:  python tools/build-recorded.py --src docs/녹화교재/1024수업
       그 폴더의 「숫자_제목.md」 · 「개념_*.md」 를 읽어 그 폴더에 html 을 쓴다. css·js 는 상대 경로로 가리킨다
       --bundle <파일>  모든 페이지를 css·js 까지 넣은 한 파일로도 묶는다. 아티팩트(잠금본)로 낼 때
       --src 없이 돌리면 docs/녹화교재/index.html 에 묶음 목록만 쓴다
"""
import argparse
import difflib
import html
import io
import os
import pathlib
import re
import sys
import urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "docs" / "녹화교재"      # textbook.css · _chapter.css · _chapter.js 가 있는 곳
SRC = ASSET_DIR
ASSET = ""                                   # SRC 에서 ASSET_DIR 로 가는 상대 경로 (같은 폴더면 "")
BOOK_TITLE = "플래피 버드로 배우는 Unity"
SUB_TITLE = ""                               # 묶음 이름. 비우면 책 이름만 찍는다
CUR = None                                   # 지금 파싱·렌더 중인 챕터 (본문 속 영상 칩에 쓴다)

# ───────────────────────── 코드 토큰 ─────────────────────────
KEYWORDS = "using|public|private|class|void|float|int|bool|string|if|else|new|return|true|false|null|static|var|this"
TYPES = ("MonoBehaviour|Vector3|Vector2|Time|Keyboard|Mouse|Debug|Transform|GameObject|Input|UnityEngine|InputSystem|"
         "BirdMoveByRid|BirdMove|Rigidbody|Collision|Collider|Mathf|Application|Quaternion")
TOK = re.compile(
    r"(?P<cmt>///?[^\n]*)"
    r"|(?P<str>\"[^\"\n]*\")"
    r"|(?P<blank>_{4,})"
    r"|(?P<num>\b\d+(?:\.\d+)?f?\b)"
    r"|(?P<key>\b(?:%s)\b)"
    r"|(?P<typ>\b(?:%s)\b)"
    r"|(?P<fn>\b[A-Za-z_]\w*(?=\())" % (KEYWORDS, TYPES))
TOK_CLASS = {"cmt": "tok-cmt", "str": "tok-str", "blank": "blank", "num": "tok-str",
             "key": "tok-key", "typ": "tok-lit", "fn": "tok-fn"}


def tokenize(code):
    code = html.escape(code, quote=False)
    return TOK.sub(lambda m: '<span class="%s">%s</span>' % (TOK_CLASS[m.lastgroup], m.group(m.lastgroup)), code)


def code_block(code, name=None, path=None, lang="csharp"):
    """lang 은 펜스 뒤의 말. 「csharp 파일.cs」 처럼 파일 이름을 붙이면 그 이름을 쓴다.
    이름이 없으면 머리말 「파일:」, 그것도 없으면 BirdMove.cs / Assets/Scripts (예전 기본값)."""
    parts = [p for p in lang.split() if p not in ("전", "후")]
    lang = parts[0] if parts else "text"
    if lang != "csharp":
        return '<pre class="plain"><code>%s</code></pre>' % html.escape(code)
    default = (CUR.front.get("파일", "") if CUR else "").replace("\\", "/")
    if len(parts) > 1:
        name = parts[1]
    if name is None:
        name = default.rsplit("/", 1)[-1] if default else "BirdMove.cs"
    if path is None:
        path = default.rsplit("/", 1)[0] if "/" in default else "Assets/Scripts"
    return ('<div class="code"><div class="code__bar"><span class="code__dot"></span>'
            '<code class="code__name">%s</code><span class="code__path">%s</span></div>'
            '<pre><code>%s</code></pre></div>' % (html.escape(name), html.escape(path), tokenize(code.rstrip("\n"))))


# ───────────────────────── 인라인 ─────────────────────────
VIDEO_PAREN = r"\(\s*영상\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[·,]\s*\d{1,2}:\d{2}(?::\d{2})?)*)\s*\)"
VIDEO_BARE = r"영상\s+(\d{1,2}:\d{2}(?::\d{2})?)"


def video_chips(clocks):
    return " ".join(video_link(CUR, c) for c in re.split(r"\s*[·,]\s*", clocks.strip()))


def inline(text):
    """**굵게**, ==형광펜==, `코드`, [글](주소), 영상 시각 칩. 나머지는 이스케이프.
    **Play.** / **Play** 는 실행 표시(▶ Play) 로 바꾼다."""
    out = []
    pos = 0
    pat = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)]+)\)|" + VIDEO_PAREN + "|" + VIDEO_BARE + r"|==(.+?)==")
    for m in pat.finditer(text):
        out.append(html.escape(text[pos:m.start()], quote=False))
        if m.group(1) is not None:
            out.append("<code>%s</code>" % html.escape(m.group(1), quote=False))
        elif m.group(2) is not None:
            if m.group(2).strip() in ("Play", "Play."):
                out.append('<span class="play">▶ Play</span>')
            else:
                out.append("<strong>%s</strong>" % inline(m.group(2)))
        elif m.group(3) is not None:
            out.append('<a href="%s">%s</a>' % (html.escape(m.group(4)), inline(m.group(3))))
        elif m.group(7) is not None:
            out.append('<mark class="key">%s</mark>' % inline(m.group(7)))
        else:
            out.append(video_chips(m.group(5) or m.group(6)))
        pos = m.end()
    out.append(html.escape(text[pos:], quote=False))
    return "".join(out)


def table_html(rows):
    """rows[0] 이 머리줄. 열 수에 맞춰 디자인 시스템의 table__row--N 을 쓴다."""
    n = max(2, min(5, max(len(r) for r in rows)))
    def row(cells, head=False):
        cells = (cells + [""] * n)[:n]
        cls = "table__row table__row--%d%s" % (n, " table__row--head" if head else "")
        return '<div class="%s">%s</div>' % (cls, "".join("<span>%s</span>" % inline(c) for c in cells))
    return '<div class="table">' + row(rows[0], True) + "".join(row(r) for r in rows[1:]) + "</div>"


def spec_card(text):
    """```기획서 블록 → 기획서 카드.
    첫 줄 = 제목. 「✓ 」 끝낸 줄, 「▶ 」 지금 만드는 줄, 「· 」 아직인 줄. 들여쓴 줄은 바로 위 줄의 설명."""
    title, items = "", []
    for raw in text.split("\n"):
        if not raw.strip():
            continue
        s = raw.strip()
        if raw[:1].isspace() and items:
            items[-1][2].append(s)
        elif s[:1] in ("✓", "▶", "·"):
            items.append([{"✓": "is-done", "▶": "is-now", "·": "is-todo"}[s[0]], s[1:].strip(), []])
        elif not title:
            title = s
        else:
            items.append(["is-todo", s, []])
    lis = []
    for cls, t, subs in items:
        mark = {"is-done": "✓", "is-now": "▶", "is-todo": ""}[cls]
        sub = "".join('<div class="spec__sub">%s</div>' % inline(x) for x in subs)
        lis.append('<li class="%s"><span class="spec__mark">%s</span><span class="spec__t">%s%s</span></li>'
                   % (cls, mark, inline(t), sub))
    return ('<div class="spec"><div class="spec__head"><span class="spec__tag">기획서</span>%s</div>'
            '<ol class="spec__list">%s</ol></div>' % (inline(title), "".join(lis)))


def _word_diff(x, y):
    """한 줄의 전·후를 낱말 단위로 비교해 바뀐 칸만 <mark> 로 감싼다."""
    tx = re.findall(r"\w+|\s+|[^\w\s]", x)
    ty = re.findall(r"\w+|\s+|[^\w\s]", y)
    comment = x.lstrip().startswith("//") and y.lstrip().startswith("//")
    paint = (lambda s: html.escape(s, quote=False)) if comment else tokenize
    left, right = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, tx, ty, autojunk=False).get_opcodes():
        a, b = "".join(tx[i1:i2]), "".join(ty[j1:j2])
        if op == "equal":
            left.append(paint(a)); right.append(paint(b))
            continue
        if a:
            left.append('<mark class="chg-del">%s</mark>' % paint(a))
        if b:
            right.append('<mark class="chg-add">%s</mark>' % paint(b))
    l, r = "".join(left), "".join(right)
    if comment:
        l, r = '<span class="tok-cmt">%s</span>' % l, '<span class="tok-cmt">%s</span>' % r
    return l, r


def compare_html(before, after, lang, lang_after=""):
    """```csharp 전 / ```csharp 후 두 블록 → 나란히 놓은 비교. 새 줄은 초록, 지운 줄은 빨강, 바뀐 칸만 강조."""
    a_raw, b_raw = before.rstrip("\n").split("\n"), after.rstrip("\n").split("\n")
    body = [l for l in a_raw + b_raw if l.strip()]
    ind = min((len(l) - len(l.lstrip(" ")) for l in body), default=0)
    a, b = [l[ind:] for l in a_raw], [l[ind:] for l in b_raw]
    left, right = [], []
    line = lambda kind, h: '<span class="chg-line chg-line--%s">%s</span>' % (kind, h or " ")
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            left += [tokenize(x) for x in a[i1:i2]]
            right += [tokenize(y) for y in b[j1:j2]]
        elif op == "delete":
            left += [line("del", tokenize(x)) for x in a[i1:i2]]
        elif op == "insert":
            right += [line("add", tokenize(y)) for y in b[j1:j2]]
        else:
            # 바뀐 덩어리 안에서 순서를 지키며 가장 비슷한 줄끼리 짝을 짓는다. 짝이 없으면 지운 줄 / 새 줄
            ai, bj = a[i1:i2], b[j1:j2]
            pair, start = {}, 0
            for ii, x in enumerate(ai):
                best, best_r = None, 0.55
                for jj in range(start, len(bj)):
                    r = difflib.SequenceMatcher(None, x.strip(), bj[jj].strip()).ratio()
                    if r > best_r:
                        best, best_r = jj, r
                if best is not None:
                    pair[ii] = best
                    start = best + 1
            right_mod = {}
            for ii, x in enumerate(ai):
                if ii in pair:
                    lx, ry = _word_diff(x, bj[pair[ii]])
                    left.append(line("mod", lx))
                    right_mod[pair[ii]] = ry
                else:
                    left.append(line("del", tokenize(x)))
            for jj, y in enumerate(bj):
                right.append(line("mod", right_mod[jj]) if jj in right_mod else line("add", tokenize(y)))
    default = (CUR.front.get("파일", "") if CUR else "").replace("\\", "/")
    names = [p for p in lang.split()[1:] if p.endswith(".cs")]
    fname = names[0] if names else (default.rsplit("/", 1)[-1] if default else "")
    names_r = [p for p in lang_after.split()[1:] if p.endswith(".cs")]
    fname_r = names_r[0] if names_r else fname          # 「후」 블록에 파일 이름이 따로 있으면 오른쪽은 그 이름
    pane = lambda cls, label, rows, name: ('<div class="code code--%s"><div class="code__bar"><span class="code__dot"></span>'
                                           '<code class="code__name">%s</code><span class="code__path">%s</span></div>'
                                           '<pre><code>%s</code></pre></div>' % (cls, label, html.escape(name), "\n".join(rows)))
    return '<div class="compare">%s%s</div>' % (pane("before", "바꾸기 전", left, fname), pane("after", "바꾼 뒤", right, fname_r))


def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def clock_to_sec(txt):
    parts = [int(x) for x in txt.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


# ───────────────────────── md 파싱 ─────────────────────────
class Chapter:
    def __init__(self, path):
        self.path = path
        sm = re.match(r"(\d+)[_-]", path.stem)
        self.slug = "ch" + sm.group(1) if sm else path.stem   # cp-07 / 01_제목 → ch01
        self.concept = path.stem.startswith("개념_")          # 개념_if.md → 개념 정리 페이지
        if self.concept:
            self.slug = "concept-" + path.stem[3:]
        self.front = {}                       # 머리말 주석의 키: 값
        self.teacher = ""                     # 맨 끝 교수용 주석
        self.num = ""
        self.title = ""
        self.goal_lead = ""
        self.goals = []
        self.lead = []                        # 제목 아래, 첫 절 전: [("p"|"html"|"goals", html)] md 순서대로
        self.sections = []                    # [{"title", "id", "blocks": [html...]}]


def parse(path):
    global CUR
    ch = Chapter(path)
    CUR = ch
    text = path.read_text(encoding="utf-8")

    # 머리말 주석 — 제목 줄 앞이든 뒤든, 첫 절(## ) 전에 나오는 첫 주석
    m = re.search(r"<!--(.*?)-->", text, re.S)
    if m and "\n## " not in text[:m.start()]:
        for line in m.group(1).splitlines():
            km = re.match(r"\s*([^\s:]+):\s*(.*)", line)
            if km:
                ch.front[km.group(1)] = km.group(2).strip()
        text = text[:m.start()] + text[m.end():]
    # 꼬리 교수용 주석 — 마지막 주석이 파일 끝까지 이어지면
    k = text.rfind("<!--")
    if k >= 0 and text.rstrip().endswith("-->"):
        ch.teacher = text.rstrip()[k + 4:-3].strip("\n")
        text = text[:k]

    lines = text.splitlines()
    i = 0
    cur = None          # 현재 절
    blocks = None       # 현재 절의 블록 목록 (절 전이면 ch.lead 로)
    know = False        # 「알아야 할 것」 절인가

    def flush_para(buf):
        if not buf:
            return
        para = " ".join(s.strip() for s in buf)
        tm = re.match(r"\*\*(.+?)\*\*\s*[—-]\s*(.*)", para)
        if know and tm:
            blocks.append(("term", tm.group(1), tm.group(2)))
        elif blocks is None:
            ch.lead.append(("p", inline(para)))
        else:
            blocks.append(("html", "<p>%s</p>" % inline(para)))
        buf.clear()

    buf = []
    while i < len(lines):
        line = lines[i]
        s = line.strip()

        if s.startswith("# ") and not ch.title:
            flush_para(buf)
            tm = re.match(r"#\s*(\d+)\.\s*(.*)", s)
            ch.num, ch.title = (tm.group(1), tm.group(2)) if tm else ("", s[2:])
            i += 1
            continue
        if s.startswith("## "):
            flush_para(buf)
            title = s[3:].strip()
            cur = {"title": title, "id": "s%d" % (len(ch.sections) + 1), "blocks": []}
            ch.sections.append(cur)
            blocks = cur["blocks"]
            know = title.startswith("알아야")
            i += 1
            continue
        if s.startswith("### "):
            flush_para(buf)
            h = s[4:].strip()
            vm = re.search(VIDEO_PAREN + r"\s*$", h)
            chip = ""
            if vm:
                h = h[:vm.start()].strip()
                chip = ("video", vm.group(1))
            blocks.append(("h3", h, chip))
            i += 1
            continue
        if s.startswith("|"):
            flush_para(buf)
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = split_row(lines[i])
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):   # |---|---| 구분줄은 버린다
                    rows.append(cells)
                i += 1
            if rows:
                (ch.lead if blocks is None else blocks).append(("html", table_html(rows)))
            continue
        if s.startswith("```"):
            flush_para(buf)
            lang = s[3:].strip() or "text"
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            words = lang.split()
            body = "\n".join(code)
            target = ch.lead if blocks is None else blocks
            if words[0] == "기획서":
                target.append(("html", spec_card(body)))
            elif blocks is not None and words[0] == "csharp" and "후" in words[1:] and blocks and blocks[-1][0] == "before":
                prev = blocks.pop()
                blocks.append(("html", compare_html(prev[1], body, prev[2], lang)))
            elif blocks is not None and words[0] == "csharp" and "전" in words[1:]:
                blocks.append(("before", body, lang))         # 바로 다음 「후」 블록과 짝을 짓는다
            else:
                target.append(("html", code_block(body, lang=lang)))
            continue
        if s.startswith(">"):
            flush_para(buf)
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(lines[i].strip()[1:].strip())
                i += 1
            # 목표 블록
            if q and q[0].startswith("**이번 시간에 만드는 것**"):
                ch.goal_lead = inline(re.sub(r"^\*\*이번 시간에 만드는 것\*\*\s*[—-]\s*", "", q[0]))
                for g in q[1:]:
                    gm = re.match(r"\d+\.\s*(.*)", g)
                    if gm:
                        ch.goals.append(inline(gm.group(1)))
                ch.lead.append(("goals", ""))
                continue
            body = " ".join(x for x in q if x)
            label, kind = "메모", "tip"
            lm = re.match(r"(막히면|멈춤|용어 주의|\*\*[^*]+\*\*)\s*[:—-]\s*(.*)", body)
            if lm:
                label = lm.group(1).strip("*")
                body = lm.group(2)
                kind = {"막히면": "tip", "멈춤": "warn", "다음 시간 질문": "info", "용어 주의": "warn",
                        "목표": "info"}.get(label, "tip")
            (ch.lead if blocks is None else blocks).append(
                ("html", '<div class="callout callout--%s"><span class="callout__label">%s</span><span>%s</span></div>'
                 % (kind, inline(label), inline(body))))
            continue
        if re.match(r"-\s*\[[ x]\]", s):
            flush_para(buf)
            items = []
            while i < len(lines) and re.match(r"-\s*\[[ x]\]", lines[i].strip()):
                items.append(inline(re.sub(r"-\s*\[[ x]\]\s*", "", lines[i].strip())))
                i += 1
            blocks.append(("html", '<div class="card">' + "".join(
                '<div class="check" data-check><span class="check__box"></span><span>%s</span></div>' % it for it in items) + "</div>"))
            continue
        if s.startswith("- "):
            flush_para(buf)
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(inline(lines[i].strip()[2:]))
                i += 1
            blocks.append(("html", "<ul>" + "".join("<li>%s</li>" % it for it in items) + "</ul>"))
            continue
        if re.match(r"\d+\.\s", s) and blocks is not None:
            flush_para(buf)
            items = []
            while i < len(lines) and re.match(r"\d+\.\s", lines[i].strip()):
                items.append(inline(re.sub(r"^\d+\.\s*", "", lines[i].strip())))
                i += 1
            blocks.append(("html", "<ol>" + "".join("<li>%s</li>" % it for it in items) + "</ol>"))
            continue
        if s == "---" or s == "":
            flush_para(buf)
            i += 1
            continue
        buf.append(line)
        i += 1
    flush_para(buf)
    return ch


# ───────────────────────── HTML 렌더 ─────────────────────────
def video_link(ch, clock):
    sec = clock_to_sec(clock)
    src = ch.front.get("영상파일", "")
    label = "영상 %s" % clock
    if not src:
        return '<span class="tag">%s</span>' % label
    url = "file:///" + urllib.parse.quote(src.replace("\\", "/").lstrip("/"), safe="/:") + "#t=%d" % sec
    return '<a class="tag" href="%s" target="_blank" title="영상을 이 시각에서 연다">%s</a>' % (url, label)


def render_blocks(ch, blocks):
    out = []
    terms = []

    def flush_terms():
        if terms:
            out.append('<div class="table terms"><div class="table__row table__row--head table__row--2"><span>용어</span><span>뜻</span></div>'
                       + "".join('<div class="table__row table__row--2"><span><strong>%s</strong></span><span>%s</span></div>'
                                 % (inline(t), inline(d)) for t, d in terms) + "</div>")
            terms.clear()

    for b in blocks:
        if b[0] == "term":
            terms.append((b[1], b[2]))
            continue
        flush_terms()
        if b[0] == "h3":
            chip = video_chips(b[2][1]) if b[2] else ""
            out.append('<h3 class="step">%s %s</h3>' % (inline(b[1]), chip))
        elif b[0] == "before":                                  # 짝 없는 「전」 블록은 그냥 코드로
            out.append(code_block(b[1], lang=b[2]))
        else:
            out.append(b[1])
    flush_terms()
    return "\n".join(out)


def render_lead(ch):
    """제목 아래를 md 순서대로. 목표 블록 앞의 첫 문단만 큰 글씨(lead)."""
    goals = ""
    if ch.goals:
        goals = ('<div class="card"><div class="label" style="margin-bottom:12px">이번 시간에 만드는 것</div>'
                 + ('<p class="meta" style="margin-bottom:8px">%s</p>' % ch.goal_lead if ch.goal_lead else "")
                 + '<ul class="goals">' + "".join('<li><span class="n">%d</span><span>%s</span></li>' % (k + 1, g) for k, g in enumerate(ch.goals))
                 + "</ul></div>")
    out, seen_goals, lead_used = [], False, False
    for kind, h in ch.lead:
        if kind == "goals":
            out.append(goals)
            seen_goals = True
        elif kind == "p":
            if not seen_goals and not lead_used:
                out.append('<p class="lead">%s</p>' % h)
                lead_used = True
            else:
                out.append("<p>%s</p>" % h)
        else:
            out.append(h)
    return "\n".join(out)


def render(ch, chapters, concepts=()):
    global CUR
    CUR = ch
    n = ch.num
    pre = ((n.lstrip("0") or n) + ".") if n else ""          # 절 번호 앞머리. 개념 페이지는 번호 없이 1, 2, 3
    secs = ch.sections
    toc_subs = "".join('<a class="toc__sub" href="#%s">%s%d %s</a>' % (s["id"], pre, k + 1, inline(s["title"]))
                       for k, s in enumerate(secs))
    nav_items = []
    for c in chapters:
        if c.slug == ch.slug:
            nav_items.append('<div class="toc__current"><div>%s · %s</div>%s</div>' % (c.num, inline(c.title), toc_subs))
        else:
            nav_items.append('<a class="toc__item" href="%s.html"><span class="toc__num">%s</span>%s</a>' % (c.slug, c.num, inline(c.title)))
    if concepts:
        nav_items.append('<div class="navpart label">개념 정리</div>')
        for c in concepts:
            if c.slug == ch.slug:
                nav_items.append('<div class="toc__current"><div>%s</div>%s</div>' % (inline(c.title), toc_subs))
            else:
                nav_items.append('<a class="toc__item" href="%s.html"><span class="toc__num">+</span>%s</a>' % (c.slug, inline(c.title)))

    body_secs = []
    for k, s in enumerate(secs):
        body_secs.append('<section class="section" id="%s"><div class="eyebrow">%s%d</div><h2>%s</h2>\n%s\n</section>'
                         % (s["id"], pre, k + 1, inline(s["title"]), render_blocks(ch, s["blocks"])))

    rail = "".join('<a class="railitem" href="#%s">%s%d %s</a>' % (s["id"], pre, k + 1, inline(s["title"]))
                   for k, s in enumerate(secs))

    if ch.concept:
        back = ch.front.get("돌아가기", "")
        back_c = next((c for c in chapters if c.slug == back), None)
        navpair = '<div class="navpair">%s%s</div>' % (
            '<a href="index.html"><div class="l">목차</div><div class="t">%s</div></a>' % html.escape(SUB_TITLE or BOOK_TITLE),
            ('<a href="%s.html"><div class="l">돌아가기</div><div class="t">%s · %s</div></a>' % (back_c.slug, back_c.num, inline(back_c.title)))
            if back_c else '<a href="index.html"><div class="l">돌아가기</div><div class="t">목차</div></a>')
    else:
        idx = [c.slug for c in chapters].index(ch.slug)
        prev_c = chapters[idx - 1] if idx > 0 else None
        next_c = chapters[idx + 1] if idx + 1 < len(chapters) else None
        navpair = '<div class="navpair">%s%s</div>' % (
            ('<a href="%s.html"><div class="l">이전</div><div class="t">%s · %s</div></a>' % (prev_c.slug, prev_c.num, inline(prev_c.title))) if prev_c
            else '<a href="index.html"><div class="l">이전</div><div class="t">목차</div></a>',
            ('<a href="%s.html"><div class="l">다음</div><div class="t">%s · %s</div></a>' % (next_c.slug, next_c.num, inline(next_c.title))) if next_c
            else '<a href="index.html"><div class="l">다음</div><div class="t">목차</div></a>')

    sub_bits = ('<span>%s</span>\n    <span class="topbar__sep">/</span>' % html.escape(SUB_TITLE)) if SUB_TITLE else ""

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(ch.num or '개념')} · {html.escape(ch.title)} — {BOOK_TITLE}</title>
<link rel="stylesheet" href="{ASSET}textbook.css">
<link rel="stylesheet" href="{ASSET}_chapter.css">
<style>
  .step .tag {{ margin-left: 8px; vertical-align: middle; font-weight: 600; }}
  p .tag, li .tag, .table .tag, .callout .tag {{ font-size: 12px; padding: 1px 7px; vertical-align: 1px; }}
  .callout > .callout__label {{ text-transform: none; letter-spacing: 0.2px; }}
  .table__row--head code {{ text-transform: none; }}
  mark.key {{ background: #fff0a0; color: var(--text); font-weight: 700; padding: 1px 3px; border-radius: 3px;
              -webkit-box-decoration-break: clone; box-decoration-break: clone; }}   /* 꼭 읽어야 하는 한 문장 */
  mark.key code {{ background: rgba(0, 0, 0, .06); }}
  .play {{ display: inline-block; font-size: 12.5px; font-weight: 700; color: #fff; background: var(--accent-text);
           border-radius: 999px; padding: 2px 10px; margin-right: 4px; vertical-align: 1px; letter-spacing: .3px; white-space: nowrap; }}   /* 표 머리줄의 코드 이름도 대소문자 그대로 */   /* 용어 상자 제목은 코드 이름이라 대소문자를 바꾸면 안 된다 */
  .doc__body .table {{ margin: 14px 0; }}
  .terms .table__row--2 > span:first-child {{ overflow-wrap: anywhere; }}
  pre.plain {{ background: var(--bg-muted); border-radius: var(--radius-card); padding: 14px 16px; overflow: auto; font-family: var(--font-code); font-size: 14px; }}
  .callout--info {{ background: var(--accent-bg); border-left: 3px solid var(--accent); }}
  .callout--info > .callout__label {{ color: var(--accent-text); }}
  .spec {{ border: 1px solid var(--line); border-radius: var(--radius-card); padding: 14px 16px; margin: 4px 0 20px; background: var(--bg-subtle); }}
  .spec__head {{ font-size: 13px; font-weight: 700; color: var(--text-subtle); margin-bottom: 8px; }}
  .spec__tag {{ display: inline-block; font-size: 11px; font-weight: 700; color: var(--accent-text); background: var(--accent-bg); border-radius: 4px; padding: 1px 7px; margin-right: 8px; }}
  .spec__list {{ list-style: none; margin: 0; padding: 0; }}
  .spec__list li {{ display: flex; gap: 10px; align-items: baseline; padding: 6px 10px; border-radius: 6px; color: var(--text-muted); font-size: 15.5px; line-height: 1.5; }}
  .spec__list li.is-done {{ color: var(--text-faint); }}
  .spec__list li.is-done .spec__mark {{ color: var(--accent); }}
  .spec__list li.is-now {{ background: var(--accent-bg); color: var(--text); font-weight: 700; }}
  .spec__list li.is-now .spec__mark {{ color: var(--accent-text); }}
  .spec__list li.is-now::after {{ content: "지금"; margin-left: auto; font-size: 11px; font-weight: 700; color: var(--accent-text); white-space: nowrap; }}
  .spec__mark {{ width: 14px; flex: none; text-align: center; }}
  .spec__sub {{ font-weight: 400; font-size: 14px; color: var(--text-muted); margin-top: 2px; }}
  .compare {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; margin: 14px 0; }}
  .compare .code pre {{ font-size: 12.5px; padding: 16px; }}
  .code--before .code__dot {{ background: #f2545b; }}
  .chg-line {{ display: inline-block; min-width: 100%; border-radius: 2px; }}
  .chg-line--add {{ background: rgba(30, 215, 96, .16); }}
  .chg-line--del {{ background: rgba(242, 84, 91, .16); text-decoration: line-through; text-decoration-color: rgba(242, 84, 91, .85); }}
  .chg-line--mod {{ background: rgba(255, 255, 255, .05); }}
  mark.chg-add {{ background: rgba(30, 215, 96, .38); color: #fff; border-radius: 3px; padding: 0 1px; }}
  mark.chg-del {{ background: rgba(242, 84, 91, .38); color: #fff; text-decoration: line-through; border-radius: 3px; padding: 0 1px; }}
  @media (max-width: 860px) {{ .compare {{ grid-template-columns: minmax(0, 1fr); }} }}
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar__in">
    <span>{BOOK_TITLE}</span>
    <span class="topbar__sep">/</span>
    {sub_bits}
    <span class="topbar__now">{html.escape(ch.num or "개념 정리")}</span>
  </div>
</div>

<div class="doc">
  <nav class="doc__nav">
    <div class="navblock">
      <button class="navtoggle" type="button" aria-expanded="false">
        <span class="navtoggle__t">목차</span>
        <span class="navtoggle__n">{html.escape(ch.num or "개념")} · {inline(ch.title)}</span>
        <span class="navtoggle__i" aria-hidden="true">▾</span>
      </button>
      <div class="navwrap">
        <div class="navpart label"><a href="index.html">목차</a></div>
        {"".join(nav_items)}
        <div class="navfoot"><div class="meta num">챕터 · {len(chapters)}</div></div>
      </div>
    </div>
  </nav>

  <article class="doc__body">
    <section class="section">
      <div class="eyebrow">{("Chapter " + html.escape(ch.num)) if ch.num else "개념 정리"}</div>
      <h1>{inline(ch.title)}</h1>
      {render_lead(ch)}
    </section>

    {chr(10).join(body_secs)}

    <section class="section">{navpair}</section>
  </article>

  <aside class="doc__rail">
    <div class="label railtitle">이 페이지 내용</div>
    {rail}
  </aside>
</div>
<script src="{ASSET}_chapter.js"></script>
</body>
</html>
"""


def books_html():
    """기본 목차에만: 하위 폴더로 따로 빌드한 묶음(그 폴더에 index.html 이 있는 것)으로 가는 링크."""
    if SRC != ASSET_DIR:
        return ""
    books = []
    for d in sorted(p for p in SRC.iterdir() if p.is_dir() and (p / "index.html").exists()):
        t = re.search(r"<h1>(.*?)</h1>", (d / "index.html").read_text(encoding="utf-8"), re.S)
        books.append('<a class="toc__item" href="%s/index.html"><span class="toc__num">→</span>%s</a>'
                     % (urllib.parse.quote(d.name), t.group(1) if t else html.escape(d.name)))
    if not books:
        return ""
    return '<div class="label" style="margin:28px 0 8px">교재</div>' + "".join(books)


def concept_rows(concepts):
    if not concepts:
        return ""
    return ('<div class="label" style="margin:28px 0 8px">개념 정리 — 챕터에서 쓴 것을 더 깊게</div>'
            + "".join('<a class="toc__item" href="%s.html"><span class="toc__num">+</span>%s</a>' % (c.slug, inline(c.title))
                      for c in concepts))


def render_index(chapters, concepts=()):
    rows = []
    for c in chapters:
        rows.append('<a class="toc__item" href="%s.html"><span class="toc__num">%s</span>%s</a>'
                    % (c.slug, c.num, inline(c.title)))
    name = SUB_TITLE or BOOK_TITLE
    top = ('<span>%s</span><span class="topbar__sep">/</span><span>%s</span>' % (BOOK_TITLE, html.escape(SUB_TITLE))
           if SUB_TITLE else '<span>%s</span>' % BOOK_TITLE)
    lead = '<p class="lead">기획서의 한 줄을 목표로 두고, 그걸 만드는 데 필요한 것을 그때 배운다.</p>' if chapters else ""
    chap = ('<div class="label" style="margin:28px 0 8px">챕터</div>' + "".join(rows)) if rows else ""
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(name)}</title>
<link rel="stylesheet" href="{ASSET}textbook.css">
<link rel="stylesheet" href="{ASSET}_chapter.css">
<style>
  .cover {{ max-width: 760px; margin: 0 auto; padding: 56px 24px; }}
  .cover .toc__item {{ display: flex; align-items: center; gap: 12px; padding: 14px 16px; border: 1px solid var(--line); border-radius: var(--radius-card); margin: 10px 0; font-size: 17px; }}
  .cover .toc__item .toc__num {{ width: auto; }}
</style>
</head>
<body>
<div class="topbar"><div class="topbar__in">{top}</div></div>
<div class="cover">
  <div class="eyebrow">목차</div>
  <h1>{html.escape(name)}</h1>
  {lead}
  {chap}
  {concept_rows(concepts)}
  {books_html()}
</div>
</body>
</html>
"""


ROUTER = r"""
/* 한 파일로 묶은 교재 — 한 번에 한 페이지만 보인다. 링크는 #페이지--절 */
(function () {
  var pages = [].slice.call(document.querySelectorAll('.bk-page'));
  function show(t) {
    var slug = t.split('--')[0];
    var pg = document.querySelector('.bk-page[data-page="' + slug + '"]') || pages[0];
    pages.forEach(function (p) { p.hidden = (p !== pg); });
    var el = t.indexOf('--') > 0 ? document.getElementById(t) : null;
    if (el) { el.scrollIntoView(); } else { window.scrollTo(0, 0); }
  }
  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[href^="#"]');
    if (!a) return;
    var t = a.getAttribute('href').slice(1);
    if (!t) return;
    e.preventDefault();
    try { history.pushState(null, '', '#' + t); } catch (err) {}
    show(t);
  });
  window.addEventListener('popstate', function () { show(location.hash.slice(1) || 'index'); });
  show('index');
})();
"""


def bundle(pages, out_path):
    """여러 페이지를 css·js 까지 넣은 한 HTML 로 묶는다. 아티팩트(잠금본)로 낼 때 쓴다.
    페이지마다 id 앞에 「슬러그--」 를 붙이고, 페이지 사이 링크를 #슬러그--id 로 바꾼다."""
    styles, bodies = [], []
    for slug, page in pages:
        head, body = page.split("</head>", 1)
        for st in re.findall(r"<style>(.*?)</style>", head, re.S):
            if st not in styles:
                styles.append(st)
        body = re.search(r"<body>(.*)</body>", body, re.S).group(1)
        body = re.sub(r"<script[^>]*></script>", "", body)
        body = re.sub(r'(?<![\w-])id="([^"]+)"', lambda m: 'id="%s--%s"' % (slug, m.group(1)), body)

        def link(m, slug=slug):
            href = m.group(1)
            if href.startswith("#"):
                return 'href="#%s--%s"' % (slug, href[1:])
            mm = re.match(r"([\w-]+)\.html(?:#(.+))?$", href)
            assert mm, "묶을 수 없는 링크: %s (%s)" % (href, slug)
            return 'href="#%s"' % (mm.group(1) + ("--" + mm.group(2) if mm.group(2) else ""))
        body = re.sub(r'href="([^"]+)"', link, body)
        bodies.append('<div class="bk-page" data-page="%s" hidden>%s</div>' % (slug, body))
    css = "".join("<style>\n%s\n</style>\n" % (ASSET_DIR / n).read_text(encoding="utf-8")
                  for n in ("textbook.css", "_chapter.css"))
    css += "".join("<style>%s</style>\n" % st for st in styles)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)     # 주석에는 옛 교재 이야기(cp-04 …)가 남아 있다
    js =(ASSET_DIR / "_chapter.js").read_text(encoding="utf-8")
    out = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(SUB_TITLE or BOOK_TITLE)}</title>
{css}<style>.bk-page[hidden] {{ display: none; }}</style>
</head>
<body>
{chr(10).join(bodies)}
<script>{js}</script>
<script>{ROUTER}</script>
</body>
</html>
"""
    out_path.write_text(out, encoding="utf-8")
    return out


def main():
    global SRC, ASSET, SUB_TITLE
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", help="챕터 md 가 있는 폴더. 없으면 docs/녹화교재/index.html 에 묶음 목록만 쓴다")
    ap.add_argument("--subtitle", help="위쪽 막대와 목차에 찍히는 묶음 이름. 비우면 책 이름만")
    ap.add_argument("--bundle", help="모든 페이지를 한 파일로도 묶어 이 경로에 쓴다 (아티팩트용)")
    a = ap.parse_args()
    if not a.src:
        (SRC / "index.html").write_text(render_index([]), encoding="utf-8")
        print("→", (SRC / "index.html").relative_to(ROOT).as_posix(), "· 묶음 목록")
        return
    SRC = (ROOT / a.src).resolve()
    mds = sorted(p for p in SRC.glob("*.md") if re.match(r"\d+[_-]", p.stem))
    cmds = sorted(SRC.glob("개념_*.md"))
    if a.subtitle:
        SUB_TITLE = a.subtitle
    ASSET = os.path.relpath(ASSET_DIR, SRC).replace("\\", "/") + "/"
    if ASSET == "./":
        ASSET = ""
    if not mds:
        sys.exit("%s 에 챕터 md 가 없다" % SRC)
    chapters = [parse(p) for p in mds]
    concepts = [parse(p) for p in cmds]
    pages = [("index", render_index(chapters, concepts))]
    for ch in chapters + concepts:
        out = SRC / (ch.slug + ".html")
        page = render(ch, chapters, concepts)
        out.write_text(page, encoding="utf-8")
        pages.append((ch.slug, page))
        print("→", out.relative_to(ROOT).as_posix(), "·", len(ch.sections), "절")
    (SRC / "index.html").write_text(pages[0][1], encoding="utf-8")
    print("→", (SRC / "index.html").relative_to(ROOT).as_posix())
    if a.bundle:
        bp = pathlib.Path(a.bundle).resolve()
        bundle(pages, bp)
        print("→", bp, "· 한 파일 묶음 %.0f KB" % (bp.stat().st_size / 1024))


if __name__ == "__main__":
    main()
