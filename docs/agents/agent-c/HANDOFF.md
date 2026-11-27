# Agent C 인터페이스 제안 v1

이 브랜치는 Agent C 소유 파일만 제공한다. Agent B와 D의 채택 및 공통 스키마 버전 합의가 필요하다. B에게 주 주문 하나와 반대 주문 배열, 사용자별 직접 지출·수령·서비스 비용, 주 주문 한 건의 잔여 DEX 수량을 제안한다. D에게 주문 단위·취소 의미 및 서명 fixture 대조를 요청한다. A에게 고정 블록 주소 및 가스 비교 재검증을 요청한다.

## B · 서명과 계획

B의 고정 WHSK 수량, exact-in 올림·exact-out 내림 제안을 반영했다. B 샌드박스의 도메인과 주문 필드가 다르므로 실제 정산에는 사용자가 아래 규격으로 새로 서명해야 한다. 계약용 JSON Schema는 `shared/typed-data/`, 정확한 Solidity ABI는 `shared/abi/Settlement-v1.json`, 컴파일된 생성 bytecode와 selector는 `Settlement-v1.build.json`에 있다. `data/fixtures/contract/direct-plan-v1.json`은 합성 서명·체결계획 예시다.

| 서명 필드 | 단위 및 의미 |
|---|---|
| owner, recipient | 서명할 EOA와 실제 출력 토큰 수취인. recipient는 0 또는 Settlement가 될 수 없다 |
| tokenIn, tokenOut, orderKind | 0은 WHSK 매도 exact-in, 1은 WHSK 매수 exact-out. 첫 배포에서는 고정 자산이 항상 WHSK |
| amountIn, amountOut | 매도는 고정 WHSK 입력과 최소 USDT 순수령. 매수는 최대 USDT 총지출과 고정 WHSK 출력 |
| validAfter, deadline | 양 끝을 포함하는 Unix 초. 계획 자체 만료는 executionDeadline |
| nonce, allowedExecutor | 소유자별 nonce. 첫 성공 체결이 같은 nonce를 해당 해시에 귀속. 0 executor는 배포 시 정한 운영자에게 허용. 그 외에는 두 주소가 일치해야 함 |
| partiallyFillable | false이면 한 번에 전량. true이면 WHSK 기준 누적 체결. 매도 한도는 비례 올림, 매수 한도는 비례 내림 |
| maxFeeAmount | 주문 전체의 USDT 최소 단위. 한 체결의 수수료는 floor(maxFeeAmount × 이번 WHSK 수량 / 전체 WHSK 수량) 이내. 남은 수수료 한도 이월 없음 |
| minImprovementAmount | 최적화 경로에서 이번 체결마다 요구하는 최소 차이, micro-USDT. 수수료 차감 후 각각의 단일 풀 견적보다 최소 1단위 유리해야 한다 |
| allowDex, allowDexFallback, immediate, executionPriority | allowDex는 혼합 경로 잔량 DEX 허용. 주 주문 전체를 DEX로 전환하려면 네 값이 true, true, true, 1이고 계획도 tryFallback이어야 한다. priority 0은 절감 우선, 1은 속도 우선 |
| 도메인 | name `HSK Smart Execution`, version `1`, 실제 체인 ID, 해당 배포 주소. uint256은 JSON에서 십진 문자열, 앱에서는 int/bigint로 복원 |

`settle(ExecutionPlan)`에서 legs[0]은 주 주문이다. 나머지는 서로 다른 소유자의 반대 주문이다. 각 leg의 directWHSK와 directUSDT는 수수료 전 양측 교환량이다. 주 주문 합계가 모든 반대 주문 합계와 각각 일치해야 한다. feeUSDT는 매도 출력에서 차감하거나 매수 입력에 더한다. 주 주문의 고정 체결량은 directWHSK + dexWHSK이며 반대 주문은 directWHSK다. dexCashLimit는 잔량을 매도할 때 최소 USDT, 매수할 때 최대 USDT다. DEX가 없으면 두 DEX 필드는 0이다. 전량 DEX fallback은 별도 경로로 주 주문의 해당 체결 수량 전체에 서명한 비례 가격 한도를 적용하고 서비스 수수료를 0으로 강제한다. 반대 주문은 대기한다.

직접 경로는 풀 스왑을 보내지 않는다. 비교용 Quoter는 pool.swap을 내부에서 모의 실행하고 되돌린다. 사용자가 이후 실제로 정산한 수량과 같은 수량을 최초 풀 상태에서 각각 비교한다. 매도·매수 독립 견적을 더해 순차 DEX 총거래라고 표시하면 안 된다. 운영자는 `eth_call`에 자신의 from, 실제 계약 주소, settle calldata와 블록을 지정하고 return enum 및 예상 가스를 확인한다. 시뮬레이션 이후 블록 정렬·가격·승인 상태는 바뀔 수 있다.

## D · 지갑과 영수증

1. 배포 manifest의 chainId·settlement·검증 상태를 확인하고 `eth_signTypedData_v4`로 서명한다. 벡터의 31337/0x1234는 테스트 값이다. ERC-1271 지갑 서명은 초기 지원 범위 밖이다.
2. 서명은 토큰 승인을 대체하지 않는다. ERC-20 `approve(settlement, finiteAmount)`를 따로 요청한다. 매도는 사용자가 체결할 WHSK, 매수는 수수료를 포함한 USDT 최대 지출 범위가 기준이다. exact-out은 한도 내에서 입력을 임시 수령하고 같은 트랜잭션에서 잔액을 소유자에게 돌려준다. 승인 변경·취소 가스의 실제 지불자는 사용자다.
3. 주문 하나 취소는 소유자가 `cancelOrder(order)`, 해당 nonce의 모든 서명 무효화는 `invalidateNonce(nonce)`를 호출한다. 서버에서 삭제한 주문도 이미 배포된 서명은 온체인 취소 전까지 유효하다. `filledAmount(hash)`, `isOrderCancelled(hash)`, `invalidNonce(owner, nonce)`, `nonceOrder(owner,nonce)`를 갱신한다.
4. 영수증 status가 0이면 체결 상태 및 사용자 청구는 복원된다. status 1이면 `PlanResult`의 0/1/2가 각각 NO_TRADE/최적화/fallback이다. 실제 사용자 지출·수령·서비스 비용은 `OrderFilled`, 매칭 금액은 `DirectTrade`, DEX 실제 금액은 `DexTrade`에서 읽는다. 같은 자산 이동을 이벤트별로 합산하지 않는다.
5. `InvalidSignature`는 서명/도메인, `InactiveOrder`는 시각/nonce/취소, `FillLimit`은 잔량 또는 부분 허용, `FeeLimit`은 서비스 수수료, `InvalidPlan`은 만료/중복/수량 구조, `Forbidden`은 실행자/정지 상태를 확인한다. `TransferMismatch`면 잔액·승인·실제 토큰 변화를 재조회한다. 가격/DEX/Quoter 오류는 새 블록에서 재견적한다. Quoter 가스 상한 초과나 Router revert는 빈 revert data를 포함해 전파될 수 있다.
6. 계약 재배포 시 verifyingContract가 변경되며 새 주소에 서명과 ERC-20 승인이 각각 필요하다. 이전 계약의 기존 승인은 사용자가 직접 철회한다.

## A · 경제성 검증에 필요한 자료

`reports/gas/anvil-raw.json`은 독립 로컬 트랜잭션의 원본 calldata/영수증이다. `anvil-receipts.json`은 gasUsed, `fork-call-traces.json`은 Foundry 호출 안에서 실행된 SSTORE 및 하위 호출 수다. SSTORE 수에는 모의 스왑과 되돌려진 쓰기도 포함된다. 상태 일치 비교군의 캐시 생성 비용은 별도다. `data/fixtures/contract/hsk-177.json`은 A와 별개로 재조회한 주소와 견적 원문이다.

운영자가 성공·실패·NO_TRADE·fallback 제출 가스를 낸다. 사용자 서비스 수수료는 성공한 최적화 leg에서만 서명 한도 내에 부과한다. A/B는 사용자별 초기 승인 비용과 운영자의 가스·L1 데이터 수수료·RPC·서버비를 각 부담자에게 배분해 동적 최소 체결량을 계산해야 한다. 서명한 최소 차이를 이들 비용과 같은 것으로 간주하면 안 된다. C의 풀 견적에는 AMM 수수료와 가격 충격이 이미 반영된다.

MarketSnapshot, DexQuote, ExecutionCandidate, CostBreakdown, UserSavings, SimulationResult, ExecutionReceipt, AgentEvent의 팀 공통 JSON 버전과 예시는 A/B/D 담당 모델과 조율이 필요하다. 현 브랜치의 서명 및 실행 ABI는 C의 제안 버전이며 팀 전역 합의는 대기 중이다.
