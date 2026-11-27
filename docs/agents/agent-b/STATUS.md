# Agent B 개발 상태 · 2026-11-27 KST

브랜치 `agent-b-engine`은 `9ec804a`에서 시작했다. B0 인터페이스부터 주문 등록, 자동 경제성 검증, 로컬 포크 정산, 영수증 기반 잔량 갱신까지 연결했다. 포크에서 3명이 주문을 등록하고 추가 실행 버튼 없이 한 번의 복수 매칭 정산을 완료했다. [포크 영수증](fork-receipt.json)

## 해커톤 신규 작업

| 단계 | 생성·수정한 경로 | 이번에 검증한 범위 |
|---|---|---|
| B0 | `backend/app/schemas`, `shared/engine-0.1` | 주문 의미·반올림, 11개 자료형 JSON Schema와 fixture, C 정산 서명과 B 정책 서명 분리 |
| B1 | `backend/app/models`, `orderbook`, `backend/migrations` | EIP-712 소유자 복구, 주문 해시 멱등성, 소유자별 nonce, 취소·만료, 원본 비공개, 이력·잔량·트랜잭션 outbox |
| B2–B4 | `backend/app/quote_engine`, `optimizer`, `economics` | A 고정 블록 견적, 단일·복수·혼합·잔량 유지·승인된 DEX 전환, 개별 보수적 순절감, 수량별 탐색, 사용자/운영자 회계 |
| B5–B6, B9 | `backend/app/execution`, `agent/worker.py`, `monitoring` | FORK calldata·eth_call·가스 추정·최신 블록·예산 검사, 예약·nonce 기록, 응답 유실 복구, 영수증과 누적 체결량, 시장 로그 체크포인트 |
| B7–B8 | `backend/app/agent/intent.py`, `tools.py`, `backend/app/api` | 한국어 조건 추출, 옵션형 로컬 모델 도구 선택, 등록·견적·시뮬레이션·실행 조회, SSE 재개, 상태·비용·사용량 |
| 검증·인계 | `backend/tests`, `backend/requirements.txt`, `docs/agents/agent-b` | 원자료 재실행, Python/viem/Solidity digest 비교, PostgreSQL 동시성, 로컬 포크 재현, OpenAPI·원시 결과 |

시작 커밋과 작업 중 확인한 공용 체크아웃에 마스터 `AGENTS.md`가 없었다. 이전 브랜치의 파일은 LP 방어 전략용이었다. 제공한 Agent B 역할서, 공통 지침, 공용 체크아웃의 `docs/project-brief.ko.md`를 적용했다. 팀의 공통 정식 버전 승격은 조율 대상이다. 기존 미커밋 파일, A/C/D 담당 경로 및 main을 편집하지 않았다.

## 공식 자료와 채택 근거

- 주최 측은 Track 1의 온체인 분석·자율 거래, 권장 제품 활용 시 가점 가능성, 제출용 Git 링크·영상, 데모 팀 메인넷 배포를 안내한다. 개별 제품별 점수와 별도 인증 조건은 미확인이다. [서울 행사 공지](https://luma.com/mwn8lt3q?locale=ko)
- HSK 메인넷 177의 WHSK·USDT 주소, RPC·탐색기 정보를 대조했다. HSKSwap QuoterV2 실측 3행은 응답 원문과 블록 해시를 저장했다. [토큰 계약](https://docs.hskchain.net/docs/Build-on-HashKey-Chain/Token-Contracts) · [네트워크](https://docs.hskchain.net/docs/Build-on-HashKey-Chain/network-info) · [실측](reference-quotes.json)
- HashFans와 HSP 개발 가이드의 mandate, 지급, 검증 흐름을 검토했다. CCIP Router는 체인 간 메시지 전달용이다. 이번 단일 체인 거래 경로가 실제 사용한 인프라는 HSK RPC와 HSKSwap이다. HSP·CCIP 가점을 산정하지 않았다. [HashFans](https://hashfans.io/) · [HSP 가이드/API](https://hsp-hackathon.hashkeymerchant.com/docs) · [HSP 공식 상점 자료](https://hashfans.io/assets/merchant-docs-all-in-one.pdf) · [CCIP Router](https://docs.chain.link/ccip/getting-started)
- API·DB·서명·도구호출 구현은 공식 API를 확인하고 사용한 런타임 패키지 버전을 고정했다. [FastAPI](https://fastapi.tiangolo.com/tutorial/) · [Pydantic](https://docs.pydantic.dev/2.11/concepts/serialization/) · [SQLAlchemy](https://docs.sqlalchemy.org/en/20/) · [Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html) · [web3.py](https://web3py.readthedocs.io/en/v7.12.0/) · [eth-account](https://eth-account.readthedocs.io/en/stable/eth_account.html) · [Ollama 도구 호출](https://docs.ollama.com/capabilities/tool-calling)

## 검증 경계

실제 체인 견적은 OBSERVED_MAINNET, 보관 자료 재생은 BACKTEST, 로컬 주문장 시험은 SYNTHETIC, 실제 HSK 계약 코드를 포크한 정산은 FORK_SIMULATION이다. EXECUTED_MAINNET 영수증은 없다. 운영 RPC·AI·서버 단가와 모든 비용을 포함한 메인넷 순이익은 UNVERIFIED다. 공식 제출 영상 및 메인넷 배포는 팀 통합 작업이다. 이번 변경은 로컬 브랜치에만 기록했다.

FORK 서비스에 붙는 외부 지갑·운영자 정책, 재시작 후 장기 운영, 실사용 주문 밀도와 다중 풀의 경제성, 로컬 모델의 실제 응답 품질은 미검증이다. 고정 블록·수량별 사용자 비교는 각각 같은 초기 풀 상태에서 시작한다. 여러 사용자 DEX 순차 거래를 재생한 합산 성과로 사용할 수 없다.
