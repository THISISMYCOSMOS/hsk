# app/ — LP 하락 방어 구현

팀이 새 공개 저장소를 정하기 전까지 두는 곳이다. `contracts/`와 `agent/`는 이 저장소의 다른 파일에 의존하지 않으므로 폴더째 옮기면 된다. 명세는 `../lp-defense/API-명세.md`, 일정과 시험 목록은 `../lp-defense/구현-계획.md`.

## 진행 (11-25~11-26 범위)

| 항목 | 상태 |
| --- | --- |
| 계약: HSKSwap(NPM·Factory·Pool·SwapRouter02·QuoterV2)·Supra Pull 인터페이스 | 완료. 소스 복사 없이 함수 형식만 다시 적음 |
| 계약: `LPGuardVault` `deposit`·`withdraw`·정책 검사·`getPosition` | 완료 |
| 계약: `executeStep`·`sellPending`·`updatePolicy`·`setPaused`·`priceStep` | 아직 안 함(11-27~) |
| 포크 시험 F1~F3 + 거부 경로 | 17개 통과 |
| 에이전트: 설정·RPC 클라이언트·풀 상태·NFT 읽기·Supra 증명 받기와 eth_call 검증 | 완료 |
| 에이전트: Swap 로그 캐시·신호·REST API | 아직 안 함(11-26 나머지) |

## 계약 (Foundry)

```bash
cd contracts
forge test -vv                                    # 기본: https://mainnet.hsk.xyz 블록 30,620,000 포크
forge test --fork-url https://mainnet.hsk.xyz     # 같은 결과(시험이 고정 블록으로 다시 포크함)
HSK_RPC=<다른 RPC> FORK_BLOCK=<블록> forge test   # 바꾸고 싶을 때
```

Foundry 1.5.1, solc 0.8.28, `evm_version = cancun`(HSK 메인넷에서 PUSH0·TLOAD·MCOPY가 동작하는 것을 eth_call로 확인). forge의 RPC 요청은 자체 User-Agent를 보내서 403이 나지 않았다. `lib/forge-std`(v1.17.0)는 그대로 넣어 두었다.

시험 결과(11-25, 17/17 통과):

| 시험 | 내용 |
| --- | --- |
| F1 | NPM·Router·Quoter `factory()`, `WETH9()`=WHSK, 두 풀 token0·token1·fee·tickSpacing·`getPool`, slot0, USDT 소수 6자리, 기존 NFT `positions()` 읽기 |
| F2 | `deal`로 WHSK·WETH·USDT를 받고 NPM `mint`로 범위 포지션 생성(WHSK/USDT, WETH/USDT 둘 다). 위험 목록의 "`deal`이 공식 토큰에 안 됨"은 일어나지 않았다 |
| F3 | `approve` 또는 `setApprovalForAll` → `deposit` → `getPosition` 값 확인 → `withdraw` → NFT가 원소유자에게, 유동성 그대로, 기록 삭제 |
| 거부 | 남의 NFT, 승인 없음, 다른 수수료 풀(WHSK/USDT 1%), USDT가 아닌 풀(WHSK/WETH), 유동성 0, 정책 오류 코드 1~7 전부와 경계값 통과, NFT 직접 전송, `onERC721Received` 직접 호출, 남의 인출, 두 번 인출, 만료 후 인출 허용, 생성자 주소 불일치 |

정책 오류 코드(`InvalidPolicy(code)`): 1 회수선(기준가 > 선1 > 선2 > 선3 > 선4 > 0 아님), 2 누적 비율(0 < … < 10000으로 끝나지 않음), 3 매도 손실 > 500bps, 4 오라클 차이 > 1000bps, 5 오라클 유효 시간 0 또는 600초 초과, 6 앞당기기 > 1, 7 만료가 지금 이전.

명세와 다르게 하거나 더한 것:
- `EmptyPosition()`, `UnexpectedNFT()`, `NotDeposited()`, `Reentrancy()`, `TransferFailed()`, `BadConfig(code)` 오류를 더했다. 명세의 "유동성 > 0", "직접 전송 거부"를 오류 이름으로 구분하려는 것이다.
- 생성자에서 주소 묶음(NPM·Router의 factory, 풀의 token1=USDT, `getPool` 일치)을 확인하고 틀리면 배포가 되돌아간다.
- `line[3]`이 NFT 범위 하단과 같은지는 계약에서 확인하지 않는다. TickMath(GPL)를 들이지 않으려는 것이고, 회수선은 소유자가 정하는 값이라 자금 안전과는 관계가 없다. 화면·에이전트가 채운다.

## 에이전트 (Node 22 + TypeScript)

```bash
cd agent
npm install
npm run typecheck
npm test            # 단위 시험(네트워크 없음)
npm run test:live   # HSK 메인넷 읽기 + Supra 증명(읽기 전용)
npm run read -- 14  # 두 풀 상태, 오라클 가격, 차이, NFT #14
```

`NODE_USE_ENV_PROXY=1`은 프록시 환경에서 Node 기본 fetch가 `HTTPS_PROXY`를 따르게 한다. 프록시가 없으면 아무 영향이 없다. 환경변수: `HSK_RPC`, `HSK_USER_AGENT`, `SUPRA_PROOF_URL`, `SUPRA_TIMEOUT_MS`.

| 파일 | 하는 일 |
| --- | --- |
| `src/config.ts` | 주소를 `@hskswap/sdk-core`에서 가져와 개발-가이드 3절 값과 대조(다르면 시작 중단). 풀 두 개와 Supra 쌍 번호 |
| `src/chain.ts` | viem 클라이언트, 체인 177, User-Agent 헤더, 408/413/429/5xx 재시도(지수 백오프). 403은 재시도하지 않음 |
| `src/pools.ts` | 같은 블록에 고정한 `slot0`·`liquidity` 읽기, 풀 설정 체인 대조, NFT `positions`·`ownerOf`, 지갑 NFT 목록 |
| `src/supra.ts` | `get_proof` 받기(시간 초과·HTTP·형식 오류 구분), `verifyOracleProofV2`를 eth_call로 검증·해석(밀리초 → 초) |
| `src/price.ts` | sqrtPriceX96 → 가격, 소수 자리 맞추기, 풀·오라클 차이(bps) |

시험 결과(11-25): 단위 13/13, 메인넷 5/5 통과. 단위 시험 하나(`scaleToE18`)는 처음에 시험 쪽 기대값을 잘못 적어 실패했고, 기대값을 고쳐 통과했다(코드 변경 없음).

메인넷에서 읽은 값(블록 30,620,320 부근): WETH/USDT 풀 1679.69 / Supra 1659.38(풀이 +1.22%), WHSK/USDT 풀 0.08079 / Supra 0.08131(풀이 −0.63%). 둘 다 기본 거부 기준(풀이 3% 넘게 낮음) 안이다.

## 다음 단계에 반영할 것

- **Supra 시각이 블록 시각보다 앞설 수 있다.** 읽기에서 `블록 시각 − 오라클 시각`이 −1초로 나왔다. 명세 1-4의 `block.timestamp − ts/1000`을 그대로 쓰면 0.8의 언더플로 검사로 되돌아간다. `executeStep`에서는 미래 시각을 나이 0으로 보거나 허용 오차를 두어야 한다. 어느 쪽인지는 11-27 구현 때 정하고 시험(F8)에 넣는다.
- 위의 차이처럼 WETH/USDT 풀은 오라클보다 1% 넘게 비싸게 거래되고 있다. 풀이 더 비싼 쪽은 계약이 거부하지 않는다(명세대로). 매도 최소 수령액을 오라클 가치로 잡으므로 이 경우 손실 한도는 오히려 느슨해진다는 점을 기억해 둔다.
