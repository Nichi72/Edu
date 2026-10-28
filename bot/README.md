# 채점 봇

설치·운영은 [docs/채점봇.md](../docs/채점봇.md) 를 본다. 여기는 개발용 메모.

```
run.bat                                   봇 켜기 (.env 필요)
.venv\Scripts\python -m pytest -q tests   엔진 테스트
.venv\Scripts\python -m grader.cli --pair 기준.zip 제출.zip --teacher
.venv\Scripts\python -m grader.cli --refs data/refs 제출.zip --target cp-07
```

- `grader/` 는 디스코드를 모른다. 비교 로직은 전부 여기 있고, 봇(`main.py`)은 받고 답하고 기록만 한다
- 서버 하나 = 수업 하나. 기준은 `data/guilds/<서버ID>/refs/<항목>.zip`, 원본은 그 서버 #채점실의 `[기준] <항목>` 메시지 첨부. 켜질 때 없는 것을 내려받는다. 과녁은 `state` 의 `target:<서버ID>`
- 자유 과제 모드(Play 실행 검사 B, LLM 피드백 C)는 `compare.Comparer` 옆에 층을 더하는 식으로 붙인다. 규칙 파일(`grader.yaml`)과 `Result.findings` 구조는 그대로 쓰면 된다
