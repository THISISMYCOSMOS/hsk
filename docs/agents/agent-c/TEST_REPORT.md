# Agent C 검증 보고서 · 2026-11-27 KST

로컬 Foundry 20개와 HSK 메인넷 고정 블록 포크 11개가 통과했다. 합성 지갑의 1,000 WHSK 양방향 직접 정산은 포크 영수증에서 470,874 gas를 썼다. 같은 초기 상태에서 WHSK 1,000개를 매도한 뒤 1,000개를 매수한 두 DEX 영수증의 합계는 226,144 gas였다. 서비스 수수료가 0인 이 사례에서 직접 정산이 추가로 사용한 가스는 244,730이다. 운영자의 경제적 이익이나 실제 사용자의 순절감액은 미측정이다.

## 증거와 측정 조건

| 분류 | 확인한 결과 |
|---|---|
| OBSERVED_MAINNET | 체인 177, 블록 30,592,078, 해시 `0x8e9ec7357cca666d04911b91bb3f5cf0292a7b4e5150a4e6febe30daa1280bda`. 2026-11-27 08:42:51 UTC에 공식 RPC로 재조회. factory, pool, router, quoter 및 토큰 decimals 일치. 해당 블록의 WHSK 1개 판매·구매 견적은 각각 80,573 / 81,061 micro-USDT |
| FORK_SIMULATION | 같은 블록의 HSKSwap 배포 코드와 토큰 저장 상태, 합성 지갑 잔액·서명으로 실행. 독립 Quoter와 Router 매도·매수 결과 일치. 풀 상태 변화 후 재견적, 부분 DEX, 환불, 실패, fallback 확인 |
| SYNTHETIC | 단위/퍼즈/invariant, EIP-712 언어 간 벡터, MOCK 로컬 배포. 퍼즈 256회, 상태 기반 invariant 96개 시퀀스 × 24회 = 2,304회 |
| BACKTEST | 보관된 B 세션 검증 코드를 별도 디렉터리에서 재실행. 과거 직접 매칭 관련 기대값 검산. 이전 순절감 추정치를 현 계약의 손익에 사용하지 않음 |
| EXECUTED_MAINNET | 이번 작업의 배포 및 사용자 거래 영수증 0건 |
| UNVERIFIED | 실제 배포 비용, 운영비, HSK/L1 비용 환산, 실현 절감 및 생산 환경의 총 비용, 테스트넷 시장 설정, 전 기간 시장 수요 |

## 가스

아래 값은 생성한 로컬 Anvil 체인 31337, Cancun EVM의 개별 트랜잭션 영수증 gasUsed다. 노드는 공식 RPC에서 위 블록만 읽었으며 로컬 발행 트랜잭션은 upstream으로 전송하지 않는다. 기준 DEX 두 거래는 매도·매수 순서로 실행했다. 다른 행의 시장 상태는 스냅샷으로 복원했다. 0→양수 ERC-20 최초 승인 비용은 별도다. 가스 단위에는 서비스 수수료, 법정통화 환산, 실제 HSK L1 데이터 게시료 또는 운영자 고정비가 포함되지 않는다.

| 경로 | WHSK 수량 | gasUsed | calldata bytes |
|---|---|---:|---:|
| 기존 DEX 순차 매도 | 1,000 | 109,310 | 228 |
| 기존 DEX 순차 매수 | 1,000 | 116,834 | 228 |
| 직접 매칭, 실시간 Quoter | 1,000 | 470,874 | 2,052 |
| 직접 매칭 + DEX 매도 | 600 + 400 | 656,132 | 2,052 |
| 직접 매칭 + DEX 매수 | 600 + 400 | 666,446 | 2,052 |
| 복수 직접 매칭 | 300 + 500, 200 대기 | 669,241 | 2,948 |
| 서명 가격 한도만 검사하는 연구 비교군 | 1,000 | 275,236 | 2,052 |
| 캐시와 현재 구간 상태 비교 연구군 | 1,000 | 288,372 | 2,052 |
| 단일 구간 경량 재계산 연구군 | 1,000 | 296,738 | 2,052 |
| NO_TRADE | 1,000 | 278,466 | 2,052 |
| DEX fallback | 1,000 | 470,922 | 2,052 |
| 승인 철회로 revert | 1,000 | 455,863 | 2,052 |
| 최초 WHSK / USDT 승인 | 유한 한도 | 46,261 / 46,195 | 각각 68 |

영수증 JSON과 calldata는 `reports/gas/anvil-raw.json`, 요약은 `anvil-receipts.json`이다. `fork-call-traces.json`에는 시나리오별 호출 내부 가스, 동적으로 실행된 SSTORE 및 하위 호출 수, 전후 견적을 기록했다. 하위 호출 수에는 Quoter의 되돌려진 풀 호출이 포함된다. 이 값은 별도 Foundry 호출 측정으로 가스 배정·따뜻해진 저장 슬롯·가스 환급·트랜잭션 기본비의 처리 범위가 영수증과 다르다. SSTORE 명령 실행과 영구 상태 변경을 구별해야 한다.

## 실시간 경제성 검증

- **채택한 Quoter 방식**은 각 주문마다 같은 초기 상태·동일 고정 수량의 단일 풀 견적을 구하고, 수수료를 반영한 개별 가격과 개선 조건을 검사한다. 혼합 정산은 스왑 후 실제 토큰 잔액 변화로 한 번 더 검사한다. 각 Quoter 호출은 450,000 gas, 묶음은 최대 8개 주문으로 제한한다. 초과/불완전 견적은 실행을 중단한다. 단일 풀의 한 순간을 비교하므로 거래 제출 이전의 가격 변동과 순서 변경, 타 DEX 경로, 시세의 공정성은 별도 위험이다.
- **Method A** 연구 계약은 양방향 고정 수량이 같은 tickSpacing 구간 내부에서 끝나는 것을 경계값으로 증명한 후 미리 계산한 두 견적과 가격·틱·활성 유동성을 결합한다. 상태가 바뀌면 거부한다. 캐시 준비 비용은 별도이며 다중 구간에는 적용할 수 없다. 일반 다중 틱 상태 동일성을 보이려면 경로상의 bitmap과 초기화 틱별 liquidityNet 등도 묶어야 한다.
- **Method B** 경량 연구 계약은 현재 구간의 Q96 정수 계산과 실제 틱 경계를 강제한다. 양방향 1, 10, 100, 1,000 WHSK 총 8개 견적이 같은 블록 Quoter와 0 최소 단위 오차였다. 큰 수량의 구간 통과는 거부했다. 다른 블록·경계값·유동성 분포에 대한 검증 범위가 좁아 운영 ABI는 실제 Quoter를 사용한다.
- **Method C** 서명 한도만 적용한 동일 직접 경로와 비교하면 실제 Quoter 검증 비용 차이는 195,638 gas였다. 가격 한도만으로 동시점 DEX 대비 개선을 판정할 수 없다. 세 연구 비교군은 테스트 디렉터리에 있다.
- 포크에서 먼저 매수 거래가 들어오자 WHSK 1개 매도 견적이 80,573에서 80,604 micro-USDT로 바뀌었다. 종전의 80,574 제안에 대해 NO_TRADE 또는 동의한 주 주문만 DEX fallback으로 처리했다. 별도 LP 예치에서는 sqrt 가격이 그대로인 상태에서 WHSK 1,000개 매도 견적이 80,558,131에서 80,558,235로 바뀌어 기존 제안을 거부했다.
- 같은 초기 상태에서 1,000 WHSK 매수의 독립 견적은 81,074,846 micro-USDT, 1,000 WHSK 선행 매도 후 실제 매수는 81,043,712였다. 차이는 31,134 micro-USDT다. 운영 계약은 사용자별 독립 비교를 채택한다. 순차 DEX와 전체 비용을 비교할 때는 같은 초기 스냅샷에서 실제 경로를 차례대로 재생해야 한다.

## 재현

Foundry 1.10.0, solc 0.8.26, optimizer 200, viaIR, Paris 대상으로 빌드했다. Python 도구에는 eth-account·eth-abi·eth-utils, TS 벡터에는 Node 22와 viem이 필요하다. 아래 명령은 저장소 루트 기준이며 `forge`와 `anvil`을 PATH에 둔다.

```sh
(cd contracts && forge fmt --check && forge test --offline --no-match-contract ForkTest -vv)
(cd contracts && HSK_FORK_TEST=true forge test --match-contract ForkTest --fork-url https://mainnet.hsk.xyz --fork-block-number 30592078 -vvvvv --json) > /tmp/hsk-fork.json
python3 contracts/script/summarize_trace.py /tmp/hsk-fork.json
python3 contracts/script/observe.py
python3 contracts/script/fork_receipts.py /tmp/anvil-receipts.json /tmp/anvil-raw.json
python3 contracts/script/check_vectors.py
node contracts/script/check_vectors.ts
python3 contracts/script/export_abi.py
(cd contracts && DEPLOYER=0x0000000000000000000000000000000000000123 forge script script/DeployLocal.s.sol --offline --chain-id 31337)
```

포크에서 기존 매도·매수, 가격·유동성 변화, 실패와 fallback을 하나씩 실행하려면 위 포크 명령에 `--match-test testForkRequoteAndConditionalFallback`, `testForkLiquidityUpdate` 또는 `testForkRevertBenchmark`를 지정한다. 외부 RPC 없이 기본 테스트를 실행하면 포크 suite는 명시적으로 skip된다. 로컬 캐시 쓰기 경고와 선택적 invariant selector 조회 경고는 테스트 결과와 별도로 관찰됐다. 상태 기반 테스트가 실행한 대상과 호출 수는 Foundry 출력에 있다.

실제 배포 전 입력은 `EXPECTED_CHAIN_ID`, `DEPLOYER`, `PAUSE_ADMIN`, `SETTLE_OPERATOR`, `FEE_RECIPIENT`, `DEPLOY_BUDGET_WEI`, `GAS_PRICE_CAP_WEI`다. 로컬 포크 31337 또는 테스트넷 133이면 그 네트워크에서 검증된 WHSK, USDT, POOL, ROUTER, QUOTER 환경 변수도 지정한다. `forge script script/Deploy.s.sol --rpc-url "$RPC_URL"`은 배포 예행연습 명령이다. 177에서는 스크립트가 broadcast를 시작하지 않는다. 예산 계산은 L1 비용을 제외한 사전 추정으로 실제 수수료 상한은 별도 확인한다. 배포 주소를 채운 manifest는 `python3 contracts/script/verify_deployment.py "$RPC_URL" manifest.json`으로 확인한다. 이 도구는 동일 블록에서 생성자 eth_call의 전체 런타임과 eth_getCode 및 모든 역할/시장 getter를 비교한다. 해당 검사는 Anvil 포크에서 통과했다. 실제 배포 지갑 및 테스트넷 실행은 미검증이다.

## 연동 및 보안 한계

수취·지출 양쪽 잔액 차, 제한된 승인·승인 초기화, ECDSA low-s·도메인, 수수료 누적 상한, 고정 주소, 실행자와 정지 권한 분리, 재진입 차단, 실패 시 전체 복구를 검사했다. 사전 검증 시점과 블록 포함 사이의 잔액·승인 변경은 여전히 실패 가스를 유발한다. USDT 프록시 구현 및 외부 시장 계약 변화는 A의 재검증 대상이다. 계약에는 잔여 자산 회수 관리자 함수가 없으며 직접 보낸 기부 토큰은 남을 수 있다. B/D의 실제 지갑/서버 연동과 독립 보안 감사, 서비스 요율 결정은 남아 있다. 공통 포맷에 필요한 변경 요청은 HANDOFF에 기록했다.
