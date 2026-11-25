# API 명세

2026-11-25 작성. 1절은 새로 만들 계약, 2절은 에이전트 서버의 REST API, 3절은 채팅 도구, 4절은 저장 자료, 5절은 우리가 부르는 외부 API다. 함수 이름과 필드는 구현하면서 바꿀 수 있지만, 권한과 검사 항목은 바꾸지 않는다.

## 1. 스마트컨트랙트 `LPGuardVault`

### 1-1. 배포 시 고정값 (immutable)

| 이름 | 값 |
| --- | --- |
| `npm` | NonfungiblePositionManager `0xDF0A…0cad5` |
| `router` | SwapRouter02 `0x2c16…D8F3` |
| `factory` | `0x972c…c742` |
| `usdt` | `0xf1b5…9029` |
| `supra` | Supra Pull `0x16f7…C3dD` |
| `pairIndex` | 풀별 Supra 쌍 번호. WETH/USDT 풀 → 1, WHSK/USDT 풀 → 517. 배포 때 두 풀만 등록하고 바꿀 수 없다. |

관리자(owner) 변수는 두지 않는다.

### 1-2. 자료형

```solidity
struct Policy {
    uint160   refSqrtPriceX96;        // 등록 기준가
    uint160[4] lineSqrtPriceX96;      // 25·50·75·100% 회수선. 엄격히 감소. [3]은 범위 하단 가격.
    uint16[4] cumBps;                 // 누적 회수 비율(L0 기준). 증가, [3] == 10000. 기본 [2500,5000,7500,10000], 강한 방어 [4000,7000,9000,10000]
    uint16    maxSellLossBps;         // 한 번 매도의 최대 손실(오라클 가치 대비, 수수료 포함). 기본 150, 최대 500
    uint16    maxOracleDevBps;        // 풀 가격이 오라클보다 이만큼 넘게 낮으면 거부. 기본 300, 최대 1000
    uint32    oracleMaxAge;           // 초. 기본 120, 최대 600
    uint8     accelSteps;             // 키퍼가 가격 도달 단계보다 앞당길 수 있는 단계 수. 0 또는 1
    address   keeper;                 // 실행자. 0 주소면 소유자만 실행
    uint64    expiry;                 // 이 시각 이후 실행 불가(인출은 가능)
}

struct Position {
    address owner;
    address pool;
    address token0;          // 위험자산
    uint128 L0;              // 예치 시점 유동성
    uint128 removed;         // 지금까지 뺀 유동성
    uint8   stepDone;        // 0~4
    bool    paused;
    uint256 pendingSell;     // 팔지 못하고 금고에 남은 위험자산 양
    Policy  policy;
}
```

### 1-3. 함수

| 함수 | 호출자 | 하는 일 | 주요 검사 |
| --- | --- | --- | --- |
| `deposit(uint256 tokenId, Policy p)` | NFT 소유자 | NFT를 금고로 옮기고 L0·풀·token0을 기록 | 사전 `approve` 필요. 풀이 등록된 두 풀 중 하나, token1이 USDT, 유동성 > 0, 정책 유효성 |
| `updatePolicy(uint256 tokenId, Policy p)` | 소유자 | 정책 교체 | 이미 끝난 단계는 되돌리지 않음. 정책 유효성 |
| `setPaused(uint256 tokenId, bool paused)` | 소유자 | 실행 중지·재개 | - |
| `withdraw(uint256 tokenId)` | 소유자 | NFT와 `pendingSell` 잔량을 소유자에게 돌려주고 기록 삭제 | 언제든 가능(중지·만료와 무관) |
| `executeStep(uint256 tokenId, uint8 step, uint256 sellAmount, bytes proof)` | 키퍼 또는 소유자 | 회수 → 수령 → 수수료와 USDT 원금 전달 → 위험자산 `sellAmount`만큼 매도 | 아래 1-4 |
| `sellPending(uint256 tokenId, uint256 sellAmount, bytes proof)` | 키퍼 또는 소유자 | 금고에 남은 위험자산을 나눠 매도 | 오라클 검사, 최소 수령액, `sellAmount ≤ pendingSell` |
| `getPosition(uint256 tokenId) view` | 누구나 | `Position` 반환 | - |
| `priceStep(uint256 tokenId) view returns (uint8)` | 누구나 | 지금 풀 가격이 도달한 단계(0~4) | - |
| `liquidityForStep(uint256 tokenId, uint8 step) view returns (uint128)` | 누구나 | 그 단계에서 뺄 유동성 | - |

`onERC721Received`는 `deposit` 도중 NPM에서 오는 것만 받는다. 그 밖의 NFT 직접 전송은 거부한다.

### 1-4. `executeStep` 처리 순서

1. `paused`가 아니고 `block.timestamp < expiry`인지 확인한다.
2. 호출자가 소유자거나 `policy.keeper`인지 확인한다.
3. `step == stepDone + 1`인지 확인한다.
4. 가격 조건을 확인한다. 키퍼는 `step ≤ priceStep + accelSteps`, 소유자는 가격 조건 없이 다음 단계를 실행할 수 있다(수동 방어).
5. 오라클을 검사한다. `supra.verifyOracleProofV2(proof)`에서 이 풀의 쌍을 찾고, `block.timestamp − ts/1000 ≤ oracleMaxAge`인지 본다. 풀 가격이 `오라클 × (1 − maxOracleDevBps)`보다 낮으면 `PoolBelowOracle`로 거부한다.
6. 뺄 유동성 `dL = L0 × cumBps[step] / 10000 − removed`를 계산한다. 남은 유동성보다 크면 남은 만큼만 뺀다.
7. `npm.decreaseLiquidity(tokenId, dL, 0, 0, block.timestamp)`로 원금 `(a0, a1)`을 받는다.
8. `npm.collect(tokenId, this, max, max)`로 `(c0, c1)`을 받는다. 수수료는 `(c0 − a0, c1 − a1)`이다.
9. 수수료 두 토큰과 원금 USDT `a1`을 소유자에게 보내고, `pendingSell += a0`로 둔다.
10. `sellAmount > 0`이면 `min(sellAmount, pendingSell)`을 판다.
    - `minOut = 오라클가치(sellAmount) × (1 − maxSellLossBps)`
    - `router.exactInputSingle(token0, usdt, 3000, owner, amountIn, minOut, 0)`. 받는 사람은 소유자다.
    - 라우터 승인은 이번 매도량만큼만 하고, 끝나면 0으로 되돌린다.
11. `removed`와 `stepDone`을 갱신하고 `StepExecuted` 이벤트를 남긴다.

매도가 `minOut`을 못 채우면 거래 전체가 되돌아간다(회수 포함). 키퍼는 `eth_call`로 먼저 모의 실행해 보고, 실패하면 `sellAmount`를 줄인다. `sellAmount = 0`으로 회수만 하고, 매도는 `sellPending`으로 나눠 할 수 있다.

### 1-5. 이벤트

```solidity
event Deposited(uint256 indexed tokenId, address indexed owner, address pool, uint128 L0, Policy policy);
event PolicyUpdated(uint256 indexed tokenId, Policy policy);
event Paused(uint256 indexed tokenId, bool paused);
event StepExecuted(uint256 indexed tokenId, uint8 step, address caller, uint128 liquidityRemoved,
                   uint256 principal0, uint256 principal1, uint256 fee0, uint256 fee1,
                   uint256 poolPriceE18, uint256 oraclePriceE18);
event Sold(uint256 indexed tokenId, uint256 amountIn, uint256 usdtOut, uint256 minOut, uint256 pendingLeft);
event Withdrawn(uint256 indexed tokenId, address indexed owner, uint256 pendingReturned);
```

### 1-6. 오류

| 오류 | 뜻 | 화면 문구 예 |
| --- | --- | --- |
| `NotOwner()` | 소유자 전용 함수 | "이 포지션의 주인만 할 수 있어요." |
| `NotExecutor()` | 소유자·키퍼가 아님 | - |
| `PausedOrExpired()` | 중지 또는 만료 | "보호가 꺼져 있어요." |
| `WrongStep(uint8 expected)` | 순서가 틀림 | - |
| `PriceNotReached(uint8 priceStep)` | 가격이 아직 회수선 위 | "아직 첫 회수선 위예요." |
| `OracleStale(uint256 age)` | 오라클 값이 오래됨 | "외부 가격 확인이 늦어 기다렸어요." |
| `PoolBelowOracle(uint256 poolE18, uint256 oracleE18)` | 풀 가격이 외부보다 너무 낮음 | "HSKSwap 가격이 외부보다 3% 넘게 낮아 팔지 않았어요." |
| `PairNotFound()` | 증명에 이 풀의 쌍이 없음 | - |
| `InvalidPolicy(uint8 code)` | 정책 값 오류 | 입력칸 옆에 표시 |
| `UnsupportedPool()` | 등록되지 않은 풀 | "WETH/USDT, WHSK/USDT 0.30% 풀만 지원해요." |
| (라우터) `Too little received` | 최소 수령액 미달 | "팔면 손실이 1.5%를 넘어 나눠 팔기로 했어요." |

## 2. 에이전트 서버 REST API

기본 주소 `/api`. 응답은 JSON이다. 금액은 문자열로 된 정수(최소 단위)와 사람이 읽는 숫자를 함께 준다. 쓰기 작업은 서버가 서명하지 않고, 사용자가 지갑에서 서명할 거래(`to`, `data`, `value`)를 돌려준다.

공통 오류 형식:

```json
{ "error": { "code": "POOL_NOT_SUPPORTED", "message": "WETH/USDT, WHSK/USDT 0.30% 풀만 지원해요." } }
```

### 2-1. 시장

**`GET /api/pools`** 두 풀의 현재 상태와 신호.

```json
[{
  "pool": "0xb92b…4c16", "pair": "WETH/USDT", "fee": 3000,
  "price": 1695.89, "oraclePrice": 1681.07, "oracleAt": 1764004430, "deviationPct": 0.88,
  "liquidityUsdt": 83630, "liquidityVs24hMedian": 1.00,
  "volume24hUsdt": 812.4, "volumeVs7dAvg": 1.21, "netSellRatio24h": 0.18, "fallFrom7dHighPct": -4.1,
  "lastSwapAt": 1764003900, "signals": { "volumeHigh": false, "sellPressure": false, "risk": false },
  "aproHskUsd": null, "updatedAt": 1764004440
}]
```

**`GET /api/pools/:pool/history?hours=168`** 시간별 가격, 오라클 가격, 거래대금(그래프용).

**`POST /api/quote/sell`** 매도 비용.

요청 `{ "pool": "0xb92b…", "amountIn": "420000000000000000" }`
응답:

```json
{ "amountIn": 0.42, "quoteOut": 698.1, "poolValue": 712.3, "oracleValue": 706.0,
  "lossVsPoolPct": 1.97, "lossVsOraclePct": 1.12, "formulaOut": 698.0,
  "recommendedChunks": 2, "chunkLossPct": 1.1, "quoteBlock": 30596000 }
```

### 2-2. 포지션

**`GET /api/wallets/:address/positions`** 지갑의 HSKSwap NFT와 금고에 맡긴 NFT.

```json
{ "inWallet": [{ "tokenId": 36, "pool": "0x4ff5…", "pair": "WHSK/USDT", "rangeLow": 0.0727, "rangeHigh": 0.0889,
                 "inRange": true, "amount0": 612.3, "amount1": 49.8, "valueUsdt": 99.3, "supported": true }],
  "inVault": [ { "tokenId": 37, "stepDone": 1, "paused": false } ] }
```

**`GET /api/positions/:tokenId`** 포지션 상세. 정책, 단계, 현재 가치, "그냥 들고 있기"와 비교, 다음 회수선과 남은 거리, 금고에 남은 위험자산.

**`POST /api/positions/:tokenId/preview`** 정책 미리보기.

요청 `{ "refPrice": 0.0835, "cumBps": [2500,5000,7500,10000], "maxSellLossBps": 150 }`
응답: 회수선 가격 4개와 sqrtPriceX96 값, 단계별 뺄 양·예상 수령액·매도 비용, 두 방향 시나리오(하단까지 하락 / 기준가로 반등) 표, 해당 범위·폭의 백테스트 요약([모의] 표시), LP 자체 비용 안내 문구.

**`GET /api/positions/:tokenId/scenario?pct=25`** "지금 25% 빼면?"

```json
{ "removePct": 25, "token0Out": 153.1, "usdtOut": 12.4, "sellQuote": 12.3, "sellLossPct": 0.6,
  "ifFallToLower": { "keep": 88.1, "act": 90.6, "protected": 2.5 },
  "ifReboundToRef": { "keep": 101.2, "act": 100.4, "forgone": 0.8 }, "block": 30596000 }
```

**`GET /api/positions/:tokenId/events`** 금고 이벤트(예치, 단계 실행, 매도, 인출)와 Blockscout 거래 링크.

**`GET /api/positions/:tokenId/decisions`** 에이전트 판단 기록(4절 `decisions` 표).

### 2-3. 거래 만들기 (사용자 서명용)

**`POST /api/tx/build`**

요청 `{ "action": "approve" | "deposit" | "updatePolicy" | "pause" | "resume" | "withdraw" | "manualStep", "tokenId": 37, "policy": { ... } }`
응답 `{ "chainId": 177, "to": "0x…", "data": "0x…", "value": "0", "summary": "NFT #37을 금고에 맡기고 보호를 켭니다." }`

`manualStep`은 소유자가 직접 다음 단계를 실행하는 거래다. 서버가 Supra 증명을 받아 `data`에 넣고, 증명 유효 시간(120초)을 응답에 함께 준다.

### 2-4. 백테스트와 채팅

**`GET /api/backtest?path=HSKSwap%20WETH&width=0.1&schedule=front`** 미리 계산한 결과(JSON 파일). 모든 값에 `"kind": "simulated"`를 붙인다.

**`POST /api/chat`**

요청 `{ "tokenId": 37, "message": "왜 아까 40%를 뺐어?", "history": [...] }`
응답 `{ "answer": "…", "facts": [{ "label": "회수 시 풀 가격", "value": 0.0822, "source": "tx 0x…" }], "proposedTx": null }`

`proposedTx`는 사용자가 일시정지나 정책 변경을 요청했을 때만 2-3 형식으로 채운다. 서명은 사용자가 한다.

### 2-5. 운영

**`GET /api/health`** RPC 블록 높이, Supra 응답 시간, 키퍼 잔고(HSK), 마지막 루프 시각.

## 3. 채팅 도구 (LLM 함수 호출)

LLM은 아래 도구의 결과에 있는 숫자만 말한다. 거래 서명 도구는 없다.

| 도구 | 입력 | 출력 |
| --- | --- | --- |
| `get_position` | tokenId | 2-2 포지션 상세 |
| `get_pool_state` | pool | 2-1 풀 상태와 신호 |
| `scenario` | tokenId, pct | 2-2 시나리오 |
| `quote_sell` | pool, amount | 2-1 매도 비용 |
| `get_decisions` | tokenId, limit | 최근 판단 기록 |
| `get_backtest` | path, width, schedule | 백테스트 요약([모의]) |
| `propose_tx` | action, tokenId, policy? | 사용자가 서명할 거래 초안 |

시스템 지시 요점: 한국어로 짧게 답한다. 숫자마다 출처(블록, 거래 해시, [모의])를 붙인다. 수익을 약속하지 않는다. 모르는 것은 모른다고 말한다. 정책을 바꾸는 요청에는 `propose_tx`로 초안만 만든다.

## 4. 저장 자료 (SQLite)

| 표 | 열 |
| --- | --- |
| `positions` | tokenId, owner, pool, L0, policyJson, depositedTx, createdAt |
| `decisions` | id, tokenId, at, block, kind(`execute`/`hold`/`accelerate`/`bottom_keep`/`bottom_exit`/`chunk`), step, poolPrice, oraclePrice, signalsJson, sellAmount, reason(한국어), txHash, result(`ok`/`reverted`/`skipped`), error |
| `pool_snapshots` | pool, at, block, price, oraclePrice, liquidity, vol24h, netSell24h |
| `swaps_cache` | pool, block, logIndex, ts, amount0, amount1, sqrtPriceX96, liquidity |

판단 하나마다 `decisions`에 한 줄을 남긴다. 보류한 것도 남긴다. 채팅의 "왜?" 답은 이 표에서 나온다.

## 5. 우리가 부르는 외부 API

| 대상 | 호출 | 용도 |
| --- | --- | --- |
| HSK RPC | `eth_call`: 풀 `slot0()`, `liquidity()`, `observe()`; NPM `positions()`, `ownerOf()`, `balanceOf()`, `tokenOfOwnerByIndex()`; QuoterV2 `quoteExactInputSingle()`; APRO `latestRoundData()` | 상태 읽기 |
| HSK RPC | `eth_getLogs` (5,000블록 단위): 풀 `Swap`, 금고 이벤트 | 신호, 기록 |
| HSK RPC | `eth_estimateGas`, `eth_sendRawTransaction`, `eth_getTransactionReceipt` | 키퍼 실행 |
| Supra | `POST /get_proof {pair_indexes, chain_type:"evm"}` | 실행·수동 실행 직전 증명 |
| Blockscout | `/api/v2/smart-contracts/{addr}`, `/api/v2/transactions/{hash}` | ABI 확인, 거래 링크 |
| LLM | 함수 호출 API | 설명, 채팅 |

HSKSwap 계약 함수 형식(Blockscout 검증 소스 기준):

```solidity
// NonfungiblePositionManager
function positions(uint256 tokenId) view returns (uint96 nonce, address operator, address token0, address token1,
    uint24 fee, int24 tickLower, int24 tickUpper, uint128 liquidity, uint256 feeGrowthInside0LastX128,
    uint256 feeGrowthInside1LastX128, uint128 tokensOwed0, uint128 tokensOwed1);
function decreaseLiquidity((uint256 tokenId, uint128 liquidity, uint256 amount0Min, uint256 amount1Min, uint256 deadline))
    returns (uint256 amount0, uint256 amount1);
function collect((uint256 tokenId, address recipient, uint128 amount0Max, uint128 amount1Max))
    returns (uint256 amount0, uint256 amount1);
// SwapRouter02 (deadline 없음)
function exactInputSingle((address tokenIn, address tokenOut, uint24 fee, address recipient,
    uint256 amountIn, uint256 amountOutMinimum, uint160 sqrtPriceLimitX96)) payable returns (uint256 amountOut);
// QuoterV2
function quoteExactInputSingle((address tokenIn, address tokenOut, uint256 amountIn, uint24 fee, uint160 sqrtPriceLimitX96))
    returns (uint256 amountOut, uint160 sqrtPriceX96After, uint32 initializedTicksCrossed, uint256 gasEstimate);
// Supra Pull
function verifyOracleProofV2(bytes calldata _bytesProof) returns (PriceInfo memory);
struct PriceInfo { uint256[] pairs; uint256[] prices; uint256[] timestamp; uint256[] decimal; uint256[] round; }
```

Supra `timestamp`는 밀리초다(11-25 확인).
