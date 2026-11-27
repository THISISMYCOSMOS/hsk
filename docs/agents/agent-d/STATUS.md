# Agent D 상태 · 2026-11-27

브라우저에서 시작한 제한 승인·이중 EIP-712 서명 주문이 Agent B를 거쳐 Agent C의 HSKSwap 포크 정산과 지갑별 영수증 화면까지 연결됐다. 600 WHSK 직접 + 400 WHSK DEX가 한 거래에서 체결됐다. PostgreSQL Compose와 로컬 SQLite 경로를 제공한다.

| 단계 | 상태 |
|---|---|
| D0–D3 | 실제 A/B/C 인터페이스 대조, 서명 벡터, 지갑·한도 검토·메인넷 읽기·로컬 및 포크 주문 등록 구현 |
| D4–D8 | 주문장·서명 취소·자연어 초안·후보·SSE·영수증 UI 및 포크 재현 구현 |
| D9–D12 | 실제 30일 자료와 합성/백테스트 구분, 이벤트 워커 연결, Compose, 회귀·E2E 및 포크 검증 |
| D13–D15 | 3분 포크 영상, 재현 명령, README 및 증거 제공. 메인넷 배포·실거래·공식 제출 대기 |

신규 파일 범위는 `frontend/`, `scripts/integration/`, `scripts/demo/`, `scripts/export_report.py`, `tests/e2e/`, 루트 Makefile·Compose·README, `docs/{ARCHITECTURE,DEMO,INTEGRATION,HACKATHON_REQUIREMENTS}.md`, `docs/agents/agent-d/`, `reports/agent-d/`이다. 기존 압축 파일과 다른 담당자의 핵심 코드는 해당 출처를 유지한다. 실제 명령·수치·한계는 [테스트 보고서](TEST_REPORT.md), 미결 인터페이스는 [인계](HANDOFF.md)에 있다.
