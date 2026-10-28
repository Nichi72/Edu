# -*- coding: utf-8 -*-
"""디스코드 없이 채점기만 돌려본다.

  python -m grader.cli --refs data/refs  제출.zip [--target cp-07] [--teacher]
  python -m grader.cli --ref cp-06=기준.zip --ref cp-07=기준7.zip  제출.zip --target cp-07
  python -m grader.cli --pair 기준폴더 제출폴더          # 기준 하나와 바로 비교

--refs 폴더에는 cp-06.zip 처럼 이름이 곧 항목인 zip(또는 폴더)이 들어 있다.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from .bundle import Bundle, BundleError
from .compare import Comparer, evaluate, sort_key
from .config import load_config
from .report import result_text, student_message, teacher_detail


def load_refs(refs_dir: str | None, pairs: list[str]) -> list[tuple[str, Bundle]]:
    refs: list[tuple[str, Bundle]] = []
    if refs_dir:
        for p in sorted(pathlib.Path(refs_dir).iterdir()):
            if p.name.startswith(".") or p.suffix in (".yaml", ".yml", ".json", ".md"):
                continue
            refs.append((p.stem, Bundle.from_path(p)))
    for pair in pairs:
        cp, _, path = pair.partition("=")
        refs.append((cp, Bundle.from_path(path)))
    refs.sort(key=lambda x: sort_key(x[0]))
    return refs


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # 윈도우 콘솔에서 한글이 깨지지 않게
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("submission", nargs="?", help="학생 제출 zip 또는 폴더")
    ap.add_argument("--refs", help="기준 zip 들이 있는 폴더")
    ap.add_argument("--ref", action="append", default=[], help="cp-06=경로 (여러 번)")
    ap.add_argument("--pair", nargs=2, metavar=("기준", "제출"), help="기준 하나와 바로 비교")
    ap.add_argument("--target", help="과녁 항목 (기본: 가장 뒤 기준)")
    ap.add_argument("--teacher", action="store_true", help="선생님용 상세까지")
    ap.add_argument("--config", help="grader.yaml 경로")
    a = ap.parse_args(argv)

    comparer = Comparer(load_config(a.config))
    try:
        if a.pair:
            ref, sub = Bundle.from_path(a.pair[0]), Bundle.from_path(a.pair[1])
            r = comparer.compare(ref, sub, pathlib.Path(a.pair[0]).stem)
            print(result_text(r, teacher=a.teacher))
            return 0 if r.ok else 1
        if not a.submission:
            ap.error("제출물 경로가 없다")
        refs = load_refs(a.refs, a.ref)
        if not refs:
            ap.error("기준이 없다. --refs 나 --ref 를 준다")
        sub = Bundle.from_path(a.submission)
    except BundleError as e:
        print("읽기 실패:", e)
        return 2
    target = a.target or refs[-1][0]
    p = evaluate(refs, sub, comparer, target)
    print(student_message(p, nth=0))
    if a.teacher:
        print("\n── 선생님용 ──")
        print(teacher_detail(p))
    return 0 if p.target_ok else 1


if __name__ == "__main__":
    sys.exit(main())
