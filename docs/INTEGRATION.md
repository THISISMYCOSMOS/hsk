# 통합 명세

| 담당 | 소비한 인터페이스 | 검증 |
|---|---|---|
| A | `MarketData` v1.0, `config/network/mainnet.json`, 시장·운영비 보고서 | chain 177, fixed block/hash, WHSK 18·USDT 6, 풀과 QuoterV2, 원자료 건수·거래대금 |
| B | `backend.app.api.main:create_app`, `shared/engine-0.1`, SQL 주문장, SSE | 11개 모델·fixture, Python 서명 복구, 브라우저 등록·취소, 포크 영수증의 주문 ID 대조 |
| C | `shared/abi/Settlement-v1.json`, `shared/typed-data/order-v1.json`, 계약 벡터 | viem·Solidity digest 대조, 실제 포크 배포 코드 해시, 이벤트·지갑 변화량 |

메인넷 네트워크 및 토큰 주소의 공식 출처는 [HSK 토큰 문서](https://docs.hskchain.net/docs/Build-on-HashKey-Chain/Token-Contracts)다. DEX 주소는 A의 `config/verified_contracts.json`, C의 `shared/abi/sources-v1.json`에서 출처와 블록을 확인한다.

## 서명 및 체결 단위

B v0.1은 WHSK 매도 EXACT_IN과 WHSK 매수 EXACT_OUT의 고정 WHSK 수량을 지원한다. 매도 시 총 최소 수령 USDT는 올림, 매수 시 총 최대 지출 USDT는 내림한다. 부분 체결 한도도 같은 방향을 적용한다. JSON은 10진 문자열, TS 연산은 bigint, Python은 int, C 수량은 uint256이다. Trade의 독립적인 메인넷 단일 풀 견적은 다른 고정 방향도 읽을 수 있다.

정책 도메인은 HSK Smart Execution Sandbox v0.1이다. 포크 정산 도메인은 HSK Smart Execution v1, chainId 31337, 현재 배포 주소다. 포크는 두 서명을 요구한다. 브라우저가 검토한 수량·한도·주소·기한·비용·권한으로 digest를 독립 계산해 응답과 대조한다. 포크의 고정 원본 블록 해시와 지갑이 조회한 배포 코드 해시를 확인한 뒤 필요한 최대 지출량만 승인한다. 제출 전 잔액·allowance·계정·체인을 다시 확인한다. 승인 비용은 별도 거래다.

주문 생성은 `/orders/typed-data`, 포크는 추가로 `/orders/settlement-typed-data`, 등록은 `POST /orders`다. 소유자 오프체인 취소는 Cancel typed data와 `POST /orders/{id}/cancel`을 사용한다. C 계약의 개별 주문 취소 및 nonce 무효화에는 별도 온체인 호출이 필요하다. 최신 B 공개 주문 모델에는 등록 시각 필드가 없다. 등록 이벤트의 시간은 Agent Activity에서 확인한다.

후보는 `/quotes`, 실행별 후보 비교는 `/executions/{id}/comparison`, 영수증은 `/executions/{id}/receipt`, 상태 이벤트는 `/agent/events/stream`이다. 자연어 초안은 `/agent/intent`, 주문 설명과 도구 선택은 `/agent/ask`를 사용한다. [Agent B OpenAPI](agents/agent-b/openapi.json)

## 환경

| 설정 | 용도 |
|---|---|
| AGENT_A_ROOT, AGENT_B_ROOT, AGENT_C_ROOT | 통합 체크아웃 또는 역할 worktree 자동 발견을 재정의 |
| BACKEND_BOOTSTRAP_PYTHON | 가상환경 생성용 Python 3.12 경로 |
| AGENT_B_PYTHON | 기존 의존성 환경 사용. 기본은 .runtime/venv/bin/python |
| AGENT_B_API | Vite의 /engine 프록시 대상. 기본 127.0.0.1:8765 |
| VITE_HSK_RPC | 독립 브라우저 읽기 RPC. 기본 https://mainnet.hsk.xyz |
| HSK_FORK_RPC | 읽기 전용 archive RPC. A 재현 스크립트는 A network manifest의 RPC 사용 |
| HSK_LOCAL_PLANNER_MODEL | Agent B의 선택적 로컬 모델 이름. 기본 규칙 모드 |
| HSK_WEB_PORT, HSK_ANVIL_PORT | Compose의 루프백 공개 포트. 기본 5173, 8545 |
| CHROME_BIN | E2E/시연용 Chrome 실행 파일. Mac 기본 Chrome을 먼저 사용 |

Docker가 없는 환경에서는 make dev로 SQLite 통합을 실행한다. Linux의 Chromium은 frontend에서 `npx playwright install chromium`으로 설치할 수 있다. 제출 영상 생성에는 ffmpeg가 필요하다. 빌드된 정적 프런트엔드는 동일 출처의 /engine 프록시가 필요하며 Compose에 포함했다.
