# -*- coding: utf-8 -*-
"""수업 영상의 말을 타임스탬프와 함께 글로 옮긴다.

실행:  python tools/transcribe.py <영상.mp4> <세션폴더>/transcript.txt
준비:  python -m pip install faster-whisper   (처음 한 번. 모델은 첫 실행 때 내려받는다, 약 1.6GB)

- 한국어, CPU. 19분 영상이 4분 정도 걸린다 (12코어 기준)
- 결과 한 줄: [hh:mm:ss - hh:mm:ss] 말   — 시각은 영상 기준
- 이 파일이 세션 폴더에 있으면 record-report.py --video 가 타임라인에 말을 끼워 넣는다
"""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
video, out = sys.argv[1], sys.argv[2]

from faster_whisper import WhisperModel


def hms(s):
    s = int(round(s))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


model = None
for name in ["large-v3-turbo", "medium", "small"]:
    try:
        t0 = time.time()
        print(f"loading {name} ...", flush=True)
        model = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=max(4, os.cpu_count() or 4))
        print(f"loaded {name} in {time.time() - t0:.0f}s", flush=True)
        break
    except Exception as e:  # 다운로드 실패·지원 안 되는 이름 → 다음 모델
        print(f"{name} failed: {e}", flush=True)
        model = None
if model is None:
    sys.exit("no model")

t0 = time.time()
segments, info = model.transcribe(video, language="ko", vad_filter=True, beam_size=5, condition_on_previous_text=False)
print(f"duration={info.duration:.0f}s", flush=True)
n = 0
with open(out, "w", encoding="utf-8") as f:
    f.write(f"# transcript  model={name}  duration={info.duration:.0f}s  video={video}\n")
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        f.write(f"[{hms(seg.start)} - {hms(seg.end)}] {text}\n")
        f.flush()
        n += 1
        if n % 20 == 0:
            print(f"  {hms(seg.end)} / {hms(info.duration)}  ({time.time() - t0:.0f}s)", flush=True)
print(f"done: {n} segments in {time.time() - t0:.0f}s → {out}", flush=True)
