# -*- coding: utf-8 -*-
"""C# 파일에서 구조를 뽑는다 — 클래스 / 필드 / 메서드 / 문장.

컴파일러가 아니다. 수업 수준의 코드(MonoBehaviour 한두 개, 중첩 없는 메서드)를 정확히 다루는 것이 목표다.
주석·공백·문자열 내용·숫자 값은 비교 대상이 아니므로 뽑는 단계에서 지운다.

    "transform.position += new Vector3(0f, -fallSpeed, 0f);"  →  "transform.position+=new Vector3(N,-fallSpeed,N)"
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MODIFIERS = {"public", "private", "protected", "internal", "static", "readonly", "const", "new", "override",
             "virtual", "abstract", "sealed", "extern", "unsafe", "volatile", "partial", "async", "ref", "out",
             "in", "event"}
TYPE_KEYWORDS = {"class", "struct", "enum", "interface", "record", "delegate", "namespace"}
SERIALIZE_ATTR = re.compile(r"\bSerializeField\b")
NUM = re.compile(r"(?<![A-Za-z_\d.])\d+(?:\.\d+)?(?:[eE][+-]?\d+)?[fFdDmMuUlL]*(?![A-Za-z_\d])")
PUNCT = re.compile(r"\s*([=+\-*/%<>!&|^~?:,;.()\[\]{}])\s*")


@dataclass
class CsField:
    name: str
    type: str
    modifiers: list[str]
    serialized: bool          # Inspector 에 보이는가 (public 이거나 [SerializeField])


@dataclass
class CsMethod:
    name: str
    params: str
    statements: list[str]


@dataclass
class CsClass:
    name: str
    base: str
    fields: dict[str, CsField] = field(default_factory=dict)
    methods: dict[str, CsMethod] = field(default_factory=dict)
    properties: set[str] = field(default_factory=set)


@dataclass
class CsFile:
    path: str
    usings: set[str]
    classes: dict[str, CsClass]


# ───────────────────────── 1. 지우기 ─────────────────────────
def strip(src: str) -> str:
    """주석을 지우고 문자열은 "S", 문자는 'C' 로 바꾼다. 전처리 지시문(#if …)은 줄째 버린다."""
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
            continue
        if c == "@" and nxt == '"':                       # @"…" 안에서는 "" 가 따옴표 하나
            j = i + 2
            while j < n:
                if src[j] == '"':
                    if j + 1 < n and src[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            out.append('"S"')
            i = j + 1
            continue
        if c == "$" and nxt == '"':                       # $"…" 는 보통 문자열처럼
            i += 1
            continue
        if c == '"':
            j = i + 1
            while j < n and src[j] != '"':
                if src[j] == "\\":
                    j += 1
                j += 1
            out.append('"S"')
            i = j + 1
            continue
        if c == "'":
            j = i + 1
            while j < n and src[j] != "'":
                if src[j] == "\\":
                    j += 1
                j += 1
            out.append("'C'")
            i = j + 1
            continue
        out.append(c)
        i += 1
    code = "".join(out)
    return re.sub(r"^[ \t]*#.*$", "", code, flags=re.M)


def match_brace(s: str, i: int) -> int:
    """s[i] 가 '{' 일 때 짝이 되는 '}' 의 위치. 못 찾으면 끝."""
    depth = 0
    for k in range(i, len(s)):
        if s[k] == "{":
            depth += 1
        elif s[k] == "}":
            depth -= 1
            if depth == 0:
                return k
    return len(s) - 1


def norm(s: str) -> str:
    """문장 하나를 비교용 글자열로. 공백 압축, 구두점 주변 공백 제거, 숫자 → N."""
    s = re.sub(r"\s+", " ", s).strip()
    s = PUNCT.sub(r"\1", s)
    s = NUM.sub("N", s)
    return s


def _split_top(s: str, sep: str) -> list[str]:
    """괄호 안이 아닌 sep 에서만 자른다."""
    out, buf, depth = [], [], 0
    for c in s:
        if c in "([<{":
            depth += 1
        elif c in ")]>}":
            depth -= 1
        if c == sep and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(c)
    out.append("".join(buf))
    return out


# ───────────────────────── 2. 파일 → 클래스 ─────────────────────────
CLASS_RE = re.compile(r"\b(?:class|struct)\s+(\w+)\s*(?::\s*([^{]+?))?\s*\{")
USING_RE = re.compile(r"^\s*using\s+(?:static\s+)?([\w\.]+)\s*;", re.M)


def parse(src: str, path: str = "") -> CsFile:
    code = strip(src)
    usings = set(USING_RE.findall(code))
    classes: dict[str, CsClass] = {}
    pos = 0
    while True:
        m = CLASS_RE.search(code, pos)
        if not m:
            break
        start = m.end() - 1
        end = match_brace(code, start)
        cls = _parse_class(m.group(1), (m.group(2) or "").strip(), code[start + 1:end])
        classes.setdefault(cls.name, cls)
        pos = m.end()          # 중첩 클래스도 각각 하나로 잡힌다
    return CsFile(path=path, usings=usings, classes=classes)


def _members(body: str) -> list[tuple[str, str | None]]:
    """클래스 본문을 (머리, 블록) 목록으로. 필드는 블록이 None."""
    members: list[tuple[str, str | None]] = []
    buf: list[str] = []
    i, n, paren = 0, len(body), 0
    while i < n:
        c = body[i]
        if c == "(":
            paren += 1
        elif c == ")":
            paren -= 1
        if c == ";" and paren == 0:
            head = "".join(buf).strip()
            if head:
                members.append((head, None))
            buf = []
            i += 1
            continue
        if c == "{" and paren == 0:
            head = "".join(buf).strip()
            j = match_brace(body, i)
            if _is_initializer(head):              # `= new Vector3 { … }`, `= { 1, 2 }`, 람다
                buf.append(body[i:j + 1])
                i = j + 1
                continue
            members.append((head, body[i + 1:j]))
            buf = []
            i = j + 1
            continue
        buf.append(c)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        members.append((tail, None))
    return members


def _is_initializer(head: str) -> bool:
    h = head.rstrip()
    return h.endswith(("=", "=>", "]", ",")) or bool(re.search(r"\bnew\b\s*[\w<>\[\],\.]*$", h))


def _strip_attrs(head: str) -> tuple[str, str]:
    attrs = []
    while True:
        m = re.match(r"\s*\[([^\]]*)\]\s*", head)
        if not m:
            break
        attrs.append(m.group(1))
        head = head[m.end():]
    return head.strip(), " ".join(attrs)


METHOD_RE = re.compile(r"^(.*?)\b([\w<>\[\],\.\?]+)\s+(\w+)\s*\((.*)\)\s*(?:where\b.*)?$", re.S)
CTOR_RE = re.compile(r"^(.*?)\b(\w+)\s*\((.*)\)\s*(?::\s*(?:base|this)\s*\(.*\))?\s*$", re.S)


def _parse_class(name: str, base: str, body: str) -> CsClass:
    cls = CsClass(name=name, base=norm(base))
    for head, block in _members(body):
        head, attrs = _strip_attrs(head)
        if not head:
            continue
        if any(re.search(rf"\b{kw}\b", head.split("(")[0]) for kw in TYPE_KEYWORDS):
            continue                                   # 중첩 타입은 바깥 루프가 따로 잡는다
        if block is not None:
            m = METHOD_RE.match(head)
            if m and m.group(3) not in ("if", "for", "foreach", "while", "switch", "using", "lock"):
                cls.methods[m.group(3)] = CsMethod(m.group(3), norm(m.group(4)), statements(block))
                continue
            m = CTOR_RE.match(head)
            if m and m.group(2) == name:
                cls.methods[name] = CsMethod(name, norm(m.group(3)), statements(block))
                continue
            toks = _decl_tokens(head)
            if toks:
                cls.properties.add(toks[-1])           # `public int Score { get; set; }`
            continue
        # 블록 없는 멤버: 필드 (또는 => 식 본문 메서드)
        if "=>" in head and "(" in head.split("=>")[0]:
            m = METHOD_RE.match(head.split("=>")[0].strip())
            if m:
                cls.methods[m.group(3)] = CsMethod(m.group(3), norm(m.group(4)), [norm(head.split("=>", 1)[1])])
            continue
        for f in _fields(head, attrs):
            cls.fields.setdefault(f.name, f)
    return cls


def _decl_tokens(decl: str) -> list[str]:
    decl = decl.split("=", 1)[0]
    decl = re.sub(r"\s*([<>,\[\]])\s*", r"\1", decl)
    return decl.split()


def _fields(head: str, attrs: str) -> list[CsField]:
    parts = _split_top(head, ",")
    toks = _decl_tokens(parts[0])
    if len(toks) < 2:
        return []
    mods = [t for t in toks[:-2] if t in MODIFIERS]
    typ = toks[-2]
    if typ in MODIFIERS or toks[-1] in MODIFIERS:
        return []
    names = [toks[-1]] + [re.match(r"\s*(\w+)", p).group(1) for p in parts[1:] if re.match(r"\s*(\w+)", p)]
    serialized = "public" in mods or bool(SERIALIZE_ATTR.search(attrs))
    return [CsField(n, typ, mods, serialized) for n in names]


# ───────────────────────── 3. 메서드 본문 → 문장 ─────────────────────────
def statements(block: str) -> list[str]:
    """중괄호를 평평하게 편 문장 목록. `if(x)` 같은 머리도 문장 하나로 센다."""
    out: list[str] = []
    buf: list[str] = []
    i, n, paren = 0, len(block), 0
    while i < n:
        c = block[i]
        if c == "(":
            paren += 1
        elif c == ")":
            paren -= 1
        if c == ";" and paren == 0:
            s = norm("".join(buf))
            if s:
                out.append(s)
            buf = []
            i += 1
            continue
        if c == "{" and paren == 0:
            head_raw = "".join(buf)
            j = match_brace(block, i)
            if _is_initializer(head_raw.strip()):
                buf.append(block[i:j + 1])
                i = j + 1
                continue
            head = norm(head_raw)
            if head:
                out.append(head)
            out.extend(statements(block[i + 1:j]))
            buf = []
            i = j + 1
            continue
        buf.append(c)
        i += 1
    tail = norm("".join(buf))
    if tail:
        out.append(tail)
    return out
