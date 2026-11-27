# Agent A 인계 · 2026-11-27 KST

## 공통 인터페이스 변경 요청

B·C·D의 검토를 위해 새 MarketSnapshot·DexQuote 전송 스키마 v1.0 제안을 `shared/proposals/agent-a-v1/`에 둔다. 기존 주문 스키마, ABI, Typed Data, 타 에이전트의 파일은 수정하지 않았다. B의 실제 `read_market(provider)`가 기대하는 고정 블록 봉투를 따른다. 공통 버전 채택 여부는 담당자 합의 대상이다.

## Agent B

`backend.app.market_data.provider.MarketData`는 Python 표준 라이브러리로 실행된다. `get_chain_state()`에서 블록 번호와 해시를 확보하고 같은 번호로 풀 상태, 매도 exact-in, 매수 exact-out, 잔액과 승인을 요청한다. 각 응답의 해시를 첫 응답과 대조한다. 잔액·견적은 JSON에서 10진 문자열, API의 수량 인자는 Python int다. 매도 최소수령은 올림, 매수 최대지출은 내림한다. 가스 견적과 거래 영수증은 별도 메서드다. 12개 크기별 두 순서의 순차 비교와 비용 민감도는 `reports/economics/fill_sizes.json`에 있다. 정산 비용과 체인 가격이 바뀌면 기존 최소 경제 수량을 폐기한다. 비용 상한을 확보하지 못하면 실행 후보를 보류한다.

`subscribe_market_events`는 확정 블록의 WHSK/USDT Swap·Mint·Burn·Initialize 로그를 폴링하고 빈 배치를 건너뛴다. 최종 성공 범위 다음 블록으로 재개한다. 처리 성공 후 소비자가 (chain_id, block_hash, transactionHash, logIndex)를 보관한다. 호가 신선도·지갑 변경·실행 직전 견적 재계산은 별도 트리거가 필요하다. `config/network/websocket.json`에 공개 주소 구독 시도 결과가 있다. 원본 receipt와 log의 Ethereum JSON-RPC hex 수량은 원문 보존 필드다.

## Agent C

`config/verified_contracts.json`에는 고정 블록별 코드 크기·SHA-256, 함수 calldata·응답, Blockscout 검증 ABI가 있다. 가스 오라클은 EIP-1967 구현체 주소를 조회했다. `reports/economics/reference_quotes.json`, `settlement_fork.json`, `fee_model.json`으로 시세·순차 경로·수수료를 대조한다. 테스트용 빌드는 `data/fixtures/market/settlement-build.json`으로 고정했다. 새 빌드는 같은 실험을 다시 실행한다.

정산 계약은 한 트랜잭션에서 사용자별 독립 Quoter 견적과 비교한다. 시장 전체의 순차 기준선, 운영자 가스 지출, 실패·취소·서버 비용은 오프체인에서 추가로 검사한다. fallback에서 주 주문만 수행하므로 두 사용자의 완료를 요구하는 A/B와 직접 비교할 수 없다. `no_trade`도 트랜잭션을 제출하면 가스를 사용한다.

## Agent D

`reports/economics/market.json`의 18개 풀 통계 및 `data/raw/30709982/coverage.json`은 OBSERVED_MAINNET이다. `preorders.json`의 모든 주문은 SYNTHETIC이며 표는 BACKTEST다. `settlement_fork.json`은 FORK_SIMULATION이고 `fee_model.json`은 해당 실행을 이용한 가정별 원가 분석이다. `realized_net_usdt`의 null은 미측정이다. 기준 블록 30,592,078의 데모는 1,000 WHSK 매도·600 WHSK 매수·400 WHSK 잔량 매도다. 화면에서 포크 거래 해시를 메인넷 탐색기에 연결하지 않는다.

## 재현 및 검증

명령과 버전, 관측 구간과 실패 복구는 [시험 기록](TEST_REPORT.md)에, 판정과 수치는 [독립 평가](../../../reports/economics/ASSESSMENT.ko.md)에 있다.
