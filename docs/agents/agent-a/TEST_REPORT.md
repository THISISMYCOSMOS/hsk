# Agent A 시험 및 재현 기록

2026-11-27 KST. 저장소 루트에서 실행한다. 조회·수집·일반 분석은 Python 3.14.7의 표준 라이브러리로 수행했다. 운영 재생과 서명 ABI 시험은 B의 Python 3.12.3 환경을 사용했다. Foundry v1.10.0, solc 0.8.26, Node 22를 사용했다. 스키마 회귀 검사는 Python jsonschema를 사용한다. B/C의 다른 worktree는 읽기만 했다.

## 로컬에서 재생

```sh
python3 -B -m backtest.market_study --block 30709982
python3 -B -m backtest.break_even
python3 -B -m unittest -v backtest.test_validation
python3 -B -m backtest.archive_audit
```

6개 신규 회귀 검사 통과. 범위 연속성, 2,792건 원시·정제 수량 및 영수증 대조, stale cache·재조직, 조회 실패, 자기 매칭·만료·미래 입력 제외, 잔량 보전, 고정 빌드 해시 및 성공·오류 JSON Schema를 검사했다. A1 과거 라우팅 Python 8개와 Foundry 모의 정산 30개, A2 덮개 fixture 모의 정산 3개가 통과했다. B1은 원본 재생 결과 바이트 일치, 656개 로그, 610개 결정의 3개 비용 가정, 통제 10개, 예시 7개 및 S1-direct 필드 50개 대조를 통과했다. A2 과거 견적 Python도 다시 실행했다. `forge`는 PATH 또는 `~/.foundry/bin`에서 발견한다. 오프라인 컴파일러 캐시에 solc 0.8.26이 필요하다. [기존 실행 로그](../../../reports/economics/archive_audit.json)

## 메인넷 읽기 전용

```sh
python3 -B -m backtest.collect --end 30709982
python3 -B -m backtest.verify_network --block 30709982
python3 -B -m backtest.quote_grid --block 30709982
python3 -B -m backtest.provider_smoke --block 30709982
python3 -B -m backtest.replay_quotes --block 30709982
node backtest/probe_ws.mjs
```

최초 수집은 `python3 -B -m backtest.collect`로 당시 finalized 헤드를 고정했다. 고정된 종료 블록 재실행은 저장된 로그·영수증을 재사용한다. 새로 네트워크에서 전량 수집하려면 이 커밋의 별도 체크아웃에 원본 디렉터리를 비운 작업 사본을 사용한다. UTC 08:11:39 및 KST 17:11:39의 종료 시각과 시작 시각은 coverage.json에 있다. 5,000블록씩 260개 연속 RPC 구간을 질의했다. 첫 영수증 대량 배치는 HTTP 429를 반환해 호출을 8개씩 제한하고 간격을 두어 재실행했다. 최종 로그와 영수증 공백은 0이었다.

컨트랙트 7개의 실제 코드와 함수·Blockscout ABI 확인. eth_chainId, eth_getCode, eth_call, eth_estimateGas, eth_getLogs, receipt 확인. smoke에서 11개 공개 메서드에 대해 12개 사례가 통과했다(토큰 2종). 블록 30,592,078의 세 Quoter 결과는 수량과 종료 sqrtPriceX96까지 일치했다. WebSocket 후보의 eth_subscribe는 업그레이드 실패로 UNVERIFIED다. HTTP의 확정 로그 구독·재개는 성공했다. 18개 풀의 수량별 Quoter 실패는 결과에 그대로 보관했다. [RPC 실측](../../../config/network/probe.json) · [공급자 시험](../../../reports/economics/provider_smoke.json)

## 포크와 비용 모델

```sh
python3 -B -m backtest.fork_compare
python -B -m backtest.fork_compare --artifact data/fixtures/market/settlement-build.json
python -B -m backtest.guard_controls --repo . --commit 9092e56
python3 -B -m backtest.fee_model
python3 -B -m backtest.fill_sizes
python3 -B -m backtest.break_even
```

두 번째와 세 번째 명령의 `python`에는 eth-abi와 eth-utils가 필요하다. `9092e56`은 로컬 agent-c-contract 브랜치에 있다. 검증용 생성 bytecode는 해당 커밋의 `shared/abi/Settlement-v1.build.json`과 바이트 단위로 일치했다. Anvil은 매 실행마다 loopback 임시 포트에서 시작하며 upstream은 공식 RPC다. 변경 메서드는 별도 로컬 체인 ID 31337 및 기준 블록 해시 검증 후 이 포트로만 전달된다. 합성 지갑에 WHSK를 래핑하고 비교 대상과 다른 풀에서 포크 잔고를 옮겨 양측 자금을 맞췄다. DEX 및 정산 승인 상태는 각 대조 경로에 맞게 초기화했다. Foundry 연구 비교군은 별도 임시 사본에서 블록 30,592,078로 고정해 실행했다.

첫 Anvil 실행에서 자동 채굴 완료 전에 receipt가 null로 돌아왔다. 채굴 결과를 기다리는 로직으로 고쳐 성공·실패 status를 확인했다. 초기 C 빌드로 잔량 경로 681,236 gas를 측정한 뒤, C의 버전 갱신을 반영한 고정 빌드에서는 **680,872 gas**를 얻었다. 최종 수수료 분석에는 후자를 사용했다. A/B 두 기준선, C 원자적 잔량 경로, D 복수 경로와 3자 순차 대조군, E fallback·NO_TRADE, 주문 취소·만료 revert의 잔고 변화와 결과를 확인했다. C 연구용 포크 테스트 11개를 독립 재실행했다. 포크 서명·블록 시각에 따른 calldata 바이트와 가스는 재실행 때 소폭 달라질 수 있다. [포크 결과](../../../reports/economics/settlement_fork.json) · [연구 비교군](../../../reports/economics/guard_controls.json)

## 실제 B 워커 재생

```sh
python -B -m backtest.operations --engine /private/tmp/hsk-agent-b-engine --block 30709982
```

`--engine`은 Agent B 체크아웃 경로다. B 커밋 `587570f`의 worker·orderbook·optimizer·시장 모듈 6개 해시와 측정 당시 해시가 모두 일치했다. B의 설치된 backend 의존성 환경에서 실행한다. 각 모드는 새 프로세스·SQLite 메모리 DB로 시작한다. 합성 서명을 프로세스 안에서 생성하고 두 주문을 등록한다. 현재 B·C의 서명 도메인이 달라서 운영 재생의 합성 주문과 C 포크 서명을 서로 교환하지 않는다.

같은 이벤트 112개를 대상으로 CPU·프로세스 peak RSS·DB statement·주문 평가시간·RPC 메서드 수를 계측했다. 저장한 실제 eth_call 응답을 실제 B 어댑터와 A 공급자로 재생했다. 미평가 상태는 평가한 log ID의 차집합이며 네트워크 전송 손실을 의미하지 않는다. SQL 트랜잭션 제어문과 계측 전 준비 비용은 읽기·쓰기 건수에서 제외했다. `event_to_trigger_p50_seconds`는 평가 시점에 사용한 마지막 이벤트의 나이로, 변동이 없는 구간에서 매우 길 수 있다. 시계 지연 및 결과 처리시간은 실서비스 지표로 외삽할 수 없다. [워커 계측](../../../reports/economics/operations.json)

## 작업 기록

초기 명령은 `git clone https://github.com/THISISMYCOSMOS/hsk.git .`, `git switch -c agent-a-data`, `git log --all -- AGENTS.md`, `git worktree list`였다. 주소·selector는 보관된 자료, 공식 토큰 문서와 cast sig를 대조했다. 수집 원본, fixture, 대상 계약 해시, 결과 및 실행 명령을 보존했다. 메인넷 제품 거래·배포·토큰 승인, 클라우드 청구, 사용자 인터뷰 및 서비스 수수료율은 확인하지 못했다.
