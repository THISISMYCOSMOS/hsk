# HSK Smart Execution

Verification-based AI Optimal Execution Agent · WHSK/USDT · HSK Chain Horizon Seoul Track 1

사용자가 정한 거래량·가격·비용 한도 안에서 직접 매칭, 복수 주문 매칭, 잔량 DEX 거래와 미체결 유지를 비교한다. 자산은 지갑에 보관하고, 사용자가 허용한 조건을 EIP-712 주문으로 서명한다. 기회 탐색에는 등록된 반대 주문과 HSKSwap 견적을 사용한다.

**브라우저에서 포크 정산까지 검증했다.** 매도자 1,000 WHSK 중 600 WHSK가 직접 매칭되고 400 WHSK가 HSKSwap에서 같은 거래로 처리됐다. 매도자는 80.713128 USDT를 받았고 매수자는 48.486163 USDT를 지불했다. 로컬 가스 사용량은 686,104였다. 비용 상한과 주문은 시연용이다. 실현 순절감액은 미측정이다. [포크 실행 증거](docs/agents/agent-d/browser-fork.json) · [3분 데모 영상](docs/agents/agent-d/fork-demo.mp4)

제출용 소스 ZIP은 프로젝트 루트에 풀고 아래 명령을 실행한다. ZIP에 포함된 INTEGRATION-SOURCES.json은 통합 커밋과 A 입력 파일 해시를 기록한다. Git 작업공간에서는 `make package`로 만들 수 있다.

## 실행

Node 22.23.1, npm 10.9.8, Python 3.12 백엔드, Foundry 1.10.0, solc 0.8.26으로 검증했다. 로컬 Chrome 또는 Playwright Chromium이 필요하다. Foundry는 PATH 또는 `~/.foundry/bin`에서 찾으며 오프라인 빌드를 위해 solc 0.8.26을 미리 설치해야 한다.

```sh
make setup
make dev
```

브라우저에서 http://127.0.0.1:5173 을 연다. Trade는 체인 177 읽기 전용이다. Demo Mode에서 체인 31337 EVM 지갑으로 서명하면 별도의 로컬 MOCK API가 정책 서명을 확인하고 데이터를 SQLite에 저장한다. 내장 이벤트 워커가 새 주문을 처리한다. 테스트 지갑의 한정 승인을 사용하는 포크 전체 경로는 다음과 같다.

```sh
make dev-fork
# 다른 터미널. 위 서버가 준비된 후 실행
make record-demo
```

포크 UI는 http://127.0.0.1:5189, 지갑용 RPC는 http://127.0.0.1:8754, chain ID는 31337이다. 스크립트가 매번 별도 포크에 계약을 배포하고 일회용 지갑에 테스트 잔액을 설정한다. `record-demo`는 로컬 Anvil의 테스트 계정을 브라우저 provider에 연결한다. 새 포크 상태에서 실행한다. [시연 절차](docs/DEMO.md)

| 명령 | 수행 작업 |
|---|---|
| `make setup` | 종속성 설치, 보관 입력 재현, 프런트엔드 빌드 |
| `make dev` | 로컬 FastAPI·워커와 Vite 기동. Agent A의 메인넷 읽기 어댑터 사용 |
| `make test` | TS 빌드, 브라우저 E2E, 기존 및 신규 Solidity·Python 회귀 시험 |
| `make test-fork` | 고정 블록 실제 QuoterV2 응답, C 계약 재빌드·포크 정산, 상태 변화에 따른 조건부 실행 |
| `make demo-local` | 보관 fixture로 직접+DEX, 비용 초과, 반대 주문 없음, 가격 한도 미달을 재실행 |
| `make backtest` | 기존 A/B 아카이브와 원자료 재검산 |
| `make market-report` | A의 30일 자료에서 풀 거래대금 및 관측 범위를 대조 |
| `make interfaces` | B의 실제 공통 모델 11개와 서명 fixture, C의 계약 벡터를 Python·viem에서 검사 |
| `make export-report` | 검산한 보관 결과 및 통합 근거를 JSON으로 출력 |
| `docker compose up -d --wait` | setup 후 PostgreSQL, API·워커, 프런트엔드, 테스트용 Anvil 기동 |

별도 역할 worktree에서는 실행기가 Git 등록 경로를 찾는다. 합쳐진 체크아웃에서는 그 안의 파일을 우선 사용한다. Compose는 통합 체크아웃을 기본으로 사용하고 분리된 경우 `AGENT_B_ROOT`를 지정한다. `make dev-fork`는 fork 전용 C 정산 계약을 배포한다. 기본 Compose의 일반 Anvil은 빈 개발 체인이다. [인터페이스·환경변수](docs/INTEGRATION.md)

## 시장 및 경제성

- **OBSERVED_MAINNET** · 2026-10-28~11-27 UTC, WHSK/USDT 0.30% 풀의 스왑 2,421건. 30일 거래대금 47,473.168591 USDT, 매수 718건·매도 1,703건, 내부 거래 간격 중앙값 6초·최대 159,318초였다. 대형 주문의 직접 체결 가능량과 실제 반대 주문 수요는 별도 지표다. [30일 데이터](frontend/public/evidence/market-30d.json)
- **OBSERVED_MAINNET** · 2026-11-27 18:03 KST, 블록 30,711,527에서 대시보드 경로로 조회한 1 WHSK 매도 견적은 0.079197 USDT였다. [견적 기록](docs/agents/agent-d/observed-quote.json) · [원본 블록](https://hsk.blockscout.com/block/0x97afbe061acc84d524c335ea8b52cb9bdb78ff1f581178b01ebbe815e2c5ce18)
- **BACKTEST** · 기존 자료의 스왑 로그 656건을 재검산했다. 610건이 기존 모델의 필터를 통과했다. 30일 가상 사전 주문 매칭률, 운영자 시나리오, 보관 시점의 견적은 Analytics에서 개별 가정과 함께 본다. [재현 보고서](reports/agent-d/integration.json)
- **운영비** · A의 24시간 백테스트에서 60초 주기 재평가 1,440회, 이벤트 방식 124회, 중복 억제·캐시 사용 시 112회였다. 이 실험의 실제 외부 RPC·LLM 호출은 0회다. 서비스 운영 청구액과 월간 순이익은 미측정이다. [운영 모드별 결과](frontend/public/evidence/market-30d.json)
- **AI와 알고리즘** · 기본 모드는 규칙으로 자연어 조건을 추출한다. Agent B의 선택적 로컬 모델 플래너는 허용된 도구를 고르고 화면에 호출 횟수를 남긴다. 가격, 체결량, 반올림, 서명 검증은 결정론적 코드가 수행한다. 이번 브라우저 검증은 기본 모드로 실행했다.
- CoW Protocol처럼 서명한 의도와 직접 매칭을 활용한다. 이 프로젝트의 탐색 범위는 HSK 단일 풀 및 단일 이벤트 워커다. 외부 Solver 간 경쟁, 다른 프로토콜 대비 성능 우위와 미래 가격 예측은 평가 범위 밖이다. [CoW Protocol](https://docs.cow.fi/cow-protocol)

## 제출 상태

정산 도메인, 비용 부담자, 실패 가스비, 견적 블록, 영수증 대조 기준은 [구조](docs/ARCHITECTURE.md)와 [테스트 결과](docs/agents/agent-d/TEST_REPORT.md)에 기록했다. 메인넷 배포 주소와 메인넷 체결 해시는 팀장 승인 및 실행 전이다. 현 검증 자료의 체결 해시는 포크 전용이다. [해커톤 요건과 공식 자료](docs/HACKATHON_REQUIREMENTS.md) · [기존 GitHub 저장소](https://github.com/THISISMYCOSMOS/hsk)

[제출용 소스 ZIP (e4ea3b3)](release/HSK-Smart-Execution-e4ea3b3.zip)

## Python 견적 CLI


프로젝트 루트에서 Python 3.11 이상으로 실행한다. Python 패키지 설치는 필요하지 않다.

```sh
python3 -m hsk sell 10 100 1000
python3 -m hsk buy 1 10 100
python3 -m hsk.headroom WHSK 10 100 1000 --match-bps 6000
python3 -m hsk --archive
python3 -B -m unittest discover -s tests -v
```

첫 두 명령은 각각 WHSK 매도 수량과 USDT 매수 예산을 입력받는다. `--scenario`로 가상 지정가·수량·비용을 입력하고 `--watch 30`으로 갱신할 수 있다. 세 번째 명령은 상대가 입력량의 60%를 사고 싶어 한다고 가정하여 같은 시작 블록의 DEX 견적 세 개를 비교한다. 매칭 대금은 양측 사이에서 이동하므로 **반대 주문의 DEX 매수 비용 + 잔량 DEX 수령액 − 전량 DEX 수령액**이 양측에 배분할 수 있는 비용 전 차이다. 실제 반대 주문의 가용성, 사용자별 배분, 승인·정산·가스 비용에 따라 순절감액은 달라진다. `--archive`는 팀이 보관한 과거 블록 예시다.

## 개발 인계

| 담당 | 인계 자료 |
| --- | --- |
| 감독 | [프로젝트 원문](docs/project-brief.ko.md) · [네 에이전트의 업무 지시 및 인수 기준](docs/agent-briefs.ko.md) |
| 시장 데이터 | [HSKSwap V3의 동일 블록 조회](docs/market.md) |
| 매칭·경제성 | [비용 단위, 후보 선택 및 순차 거래 비교](docs/economics.md) |
| 정산·보호 조건 | [EIP-712 로컬 정산 및 테스트](docs/settlement.md) |
| 실행 에이전트·인터페이스 | [거래 조건 입력, 시나리오 및 갱신 방법](docs/agent.md) |

금액별 실제 조회값, 비용 가정별 해석, 포크 재현 명령과 미측정 항목은 [감독 검증 기록](docs/validation.ko.md)에 있다. `hsk.headroom`의 `--extra-cost 0.03`은 경로 간 추가비용을 출력 토큰 0.03개로 가정해 양측 합산 결과를 계산한다.

메인넷 읽기와 가상 주문 처리는 Python 경로에서 수행한다. Solidity 프로토타입은 별도 로컬 테스트에서 승인 조건과 원자적 정산을 검증한다. 현재 견적 CLI에서 가상 주문을 정산 컨트랙트로 제출하는 경로는 없다.
