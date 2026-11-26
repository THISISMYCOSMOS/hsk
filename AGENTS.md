# AGENTS.md

이 저장소에서 일하는 코딩 에이전트(Codex, Claude 등)를 위한 안내다. 사람이 읽어도 된다.

## 먼저 읽을 것

1. `lp-defense/인계.md` — 지금까지의 모든 결정, 숫자, 대화 흐름, 다음 작업. **반드시 먼저 읽는다.**
2. `lp-defense/README.md` — 문서 목록.
3. 작업 주제에 따라 `lp-defense/피드백-검토.md`(주제 논의), `lp-defense/실제-위험.md`(체인 측정), `app/README.md`(코드).

## 지금 상태 (2026-11-26)

- HashKey Horizon Seoul 해커톤 Track 1. 마감 12-03 13:00 KST. 메인넷 계약 배포가 필수.
- 주제가 **LP 하락 방어 에이전트 → 주문 체결 최적화 에이전트로 바뀔 수 있다.** 팀 확정 전에는 계약 작업을 진행하지 않는다(`인계.md` 8·10·11절).

## 원칙

- **편향 금지가 1순위.** 유리한 결과만 고르지 않고, 불리한 결과도 그대로 적는다. 숫자에는 출처를 단다([직접] 체인·API 측정 / [모의] 계산 / [2차] 다른 자료).
- 같은 질문을 여러 번 받아도 근거 없이 결론을 바꾸지 않는다. 새 근거가 나오면 바꾸고 이유를 적는다.
- 메인넷 배포, 서명, 자금 이동은 팀의 명시적 승인 전에는 하지 않는다. 개인 키를 문서·저장소에 쓰지 않는다.
- 막힌 것(접근 차단 등)은 우회하지 않고 이유와 함께 적는다.
- 시험 결과는 통과·실패를 그대로 보고한다. 보고는 한국어, 결론부터, 짧게.
- 작업 브랜치: `claude/pensive-lovelace-e9b9pi`. 다른 브랜치에 푸시하거나 PR을 만들 때는 팀에 먼저 묻는다.

## 구조

```
lp-defense/          기획·근거·검증 문서, scripts/(Python 분석·백테스트, 원자료는 커밋 안 함)
app/contracts/       Foundry. LPGuardVault(LP 기획용), HSKSwap·Supra 인터페이스, 메인넷 포크 시험
app/agent/           Node 22 + TypeScript. RPC 클라이언트, 풀·NFT 읽기, Supra 증명
```

## 실행

```bash
# 계약 (Foundry 필요)
cd app/contracts && forge test -vv          # https://mainnet.hsk.xyz 블록 30,620,000 포크, 17개

# 에이전트
cd app/agent && npm install && npm run typecheck && npm test   # 단위 13개
npm run test:live                                              # 메인넷 읽기 5개(네트워크 필요)

# 분석 (데이터 폴더를 따로 만들어 그 안에서 실행)
python3 lp-defense/scripts/fetch.py chain
python3 lp-defense/scripts/ext.py ./ext.json
python3 lp-defense/scripts/risk_direct.py .
```

## 알아야 할 환경 사실

- HSK RPC `https://mainnet.hsk.xyz`는 **User-Agent 헤더가 없으면 403**. `eth_getLogs`는 5,000블록까지. 체인 ID 177, 블록 약 2초.
- 주소는 `lp-defense/개발-가이드.md` 3절과 `@hskswap/sdk-core`(체인 177)가 기준이다.
- `NODE_USE_ENV_PROXY=1`(npm 스크립트에 들어 있음)은 프록시 환경용이다. 프록시가 없으면 영향 없다.
- 이전 작업 환경(Claude 클라우드)에서는 DoraHacks 페이지와 팀원의 Notion 페이지에 접근할 수 없었다. 다른 환경에서는 될 수 있다.
