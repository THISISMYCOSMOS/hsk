# 감독 검증 기록

## 판정 기준

승인 범위는 WHSK/USDT의 읽기 전용 메인넷 견적과 가상 주문에 대한 비교다. 온체인 관측값은 블록 번호·해시·주소로 찾을 수 있어야 하고, 두 경로는 같은 시작 상태와 같은 주문 수량에서 비교해야 한다. 참가자 주문이나 영수증이 없는 계산에서 실현 손익은 미측정이다.

## 메인넷 금액별 견적

2026-11-27 17:42:49 KST, HashKey Chain(177) 블록 30,710,916, 해시 `0xdb1a420b150464551801fb4d2696b5dec3a714e2426f5b1f16094b91a4a02da2`. 공식 RPC `https://mainnet.hsk.xyz`에 블록을 고정해 QuoterV2의 `quoteExactInputSingle` 여섯 번과 `quoteExactOutputSingle` 세 번을 호출했다. 호출 전후 블록 해시가 일치했다. 수수료 0.30% 직접 풀, Quoter와 토큰 주소는 아래 포크 호출과 같다. [블록 탐색기](https://hsk.blockscout.com/block/30710916)

| 매도량 WHSK | 가상 매칭 WHSK | 전량 DEX 수령 USDT | 상대방 DEX 매수 비용 USDT | 잔량 DEX 수령 USDT | 양측 비용 전 차이 USDT |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 6 | 0.791946 | 0.478035 | 0.316778 | 0.002867 |
| 100 | 60 | 7.919328 | 4.780382 | 3.167767 | 0.028821 |
| 1,000 | 600 | 79.179713 | 47.808742 | 31.675503 | 0.304532 |

이 표를 다시 계산하려면 과거 블록 상태를 제공하는 RPC에서 다음을 실행한다. 현행 시점으로 갱신할 때는 `--block 30710916`을 생략한다.

```sh
python3 -m hsk.headroom WHSK 10 100 1000 --match-bps 6000 --block 30710916 --extra-cost 0.03
```

전량 DEX 수령액, 상대방 DEX 매수 비용, 잔량 DEX 수령액은 실제 메인넷 Quoter의 반환값이다. 각 행은 입력량의 60%를 원하는 상대가 있다는 **가정**이다. 맨 오른쪽 값은 두 트레이더가 각자 같은 시작 상태의 DEX를 쓰는 경우와 비교한 합계이며, 참가자별 실현 절감액과 실제 가스비는 미측정이다. 예를 들어 100 WHSK에서 두 경로 사이의 양측 합산 추가비용을 0.03 USDT로 가정하면 차감 후 값은 −0.001179 USDT다.

17:47 KST에 제품 CLI에서 같은 블록의 9개 견적을 재조회했다. 세 수량에서 독립 검산값과 최소 단위까지 일치했다. [수량·풀 상태·비용 가정을 담은 원본 출력](evidence/headroom-30710916.json)

개인별 결과도 별도로 검산했다. 가상 매수자가 600 WHSK에 47.656476 USDT를 제시하고, 매도자 비용 차이를 0.03 USDT, 매수자 비용을 0.01 WHSK로 가정했다. 1,000 WHSK를 매도하면 600 WHSK 직접 매칭과 400 WHSK DEX 경로에서 79.331979 USDT가 견적된다. 전량 DEX 대비 매도자 예상 순절감액은 **0.122266 USDT**였다. 같은 예산을 전량 DEX에 쓰는 경우와 비교한 매수자의 예상 순절감액은 **1.900713335777149609 WHSK**였다. 두 개인별 개선액의 단위가 다르므로 그대로 더할 수 없다. [가상 주문 및 비용 입력](evidence/hypothetical-order-30710916.json)

```sh
python3 -m hsk sell 1000 --block 30710916 --scenario docs/evidence/hypothetical-order-30710916.json
```

## 보관 견적과 포크 대조

2026-11-27에 기존 팀 자료 `backtests/HSK_Session2_Quotes.zip`의 `quotes.py`를 실행해 보관된 `quotes.json`과 전 필드가 일치함을 확인했다. HashKey Chain 블록 30,592,078의 상태(해시 `0x8e9ec7357cca666d04911b91bb3f5cf0292a7b4e5150a4e6febe30daa1280bda`)를 공식 RPC에서 읽어 Foundry 1.10.0의 로컬 포크에서도 매도 견적 한 건을 재실행했다.

```sh
cast call --trace --block 30592078 --rpc-url https://mainnet.hsk.xyz \
  0x603f70466fddbe3f238220b9a74fff419a2bbfdd \
  'quoteExactInputSingle((address,address,uint256,uint24,uint160))(uint256,uint160,uint32,uint256)' \
  '(0xb210d2120d57b758ee163cffb43e73728c471cf1,0xf1b50ed67a9e2cc94ad3c477779e2d4cbfff9029,1000000000000000000000,3000,0)'
```

직접 풀 `0x4ff515761864e7838b0adb8b5b2b8b7a068905dc`에서 1,000 WHSK 입력의 반환값은 80,558,131 USDT 최소 단위(80.558131 USDT)였다. 포크 반환값의 첫 ABI 워드는 `0x4cd3833`이다. 포크의 Quoter 호출은 정산 프로토타입 전체의 통합 시험과 범위가 다르다. 출력된 실행 gas는 사용자 실거래 비용 계산에서 제외했다.

같은 자료의 1,000 WHSK 매도·600 WHSK 반대 매수 시나리오에서 독립 견적 세 개로 계산한 양측 합산 여유분은 0.309994 USDT였다. 두 거래자가 차례로 같은 풀을 사용해 앞 거래가 다음 가격을 바꾸는 비교에서는 순서에 따라 0.291315 또는 0.291372 USDT였다. 세 결과 모두 추가비용 차감 전의 시뮬레이션이다. [순차 거래 산식·재현](economics.md)

## 해커톤 제출 전 남은 증거

이 빌드에서 Python 3.14.7의 `python3 -B -m unittest discover -s tests -v`는 22개, Foundry 1.10.0의 `forge test --offline --root contracts`는 14개 테스트를 통과했다. 후자는 신규 직접 정산 계약에 대한 로컬 EVM 결과다. [계약 시험 항목](settlement.md)

| 항목 | 현재 확인 범위와 인수 조건 |
| --- | --- |
| 시장과 주문 수요 | 메인넷 DEX 견적과 기존 스왑 보관 자료. 만료별 실제 서명 주문 수·양방향 불균형·실제 매칭률은 참가자 주문 표본이 필요하다. |
| 사용자 경제성 | 명시한 금액·가상 반대 주문·비용 가정별 비교 가능. 최적 멀티홉, 사용자별 실제 승인 비용, L1/L2 정산비·재시도 비용과 실제 순절감액은 미측정이다. |
| 운영 경제성 | 가정한 운영 수입·지출을 입력할 수 있다. 월간 실현 순절감액, 실제 서버/RPC/AI 비용과 사업 손익분기점은 미측정이다. |
| 자동화와 AI | CLI가 방향·금액을 규칙으로 파싱하고 블록·주문 조건이 바뀌면 견적을 다시 평가한다. 모델 기반 의도 해석 및 규칙 대비 개선율은 미검증이다. |
| 계약·시연 | 로컬 두 주문 직접 정산과 원자적 실패 처리를 시험했다. 다중 주문과 잔여 DEX를 묶는 실정산, 외부 보안 검토, 제출용 데모 영상은 후속 항목이다. 배포 주소와 제품 체결 해시는 없다. |

## 기존 시스템과 비교하는 기준

- **CoW Protocol**의 solver는 주문 의도에 대한 일괄 정산안을 찾는다. 이 빌드는 단일 에이전트가 제한된 크기의 주문 집합만 탐색한다. [CoW Protocol의 solver](https://docs.cow.fi/cow-protocol/concepts/introduction/solvers)
- **UniswapX**는 서명 주문을 filler가 경쟁해 체결한다. 여기서는 HSKSwap 직접 풀의 같은 블록 견적을 비교 기준으로 쓴다. [UniswapX 개요](https://developers.uniswap.org/docs/liquidity/uniswapx/overview)
- **1inch Fusion**은 경매 조건을 충족하는 resolver가 체결 비용을 부담할 수 있다. 이 빌드는 비용 부담자를 분리해 사용자별 결과를 계산하며 상대 주문이 있는 경우만 비교한다. [1inch Fusion의 주문 처리](https://business.1inch.com/portal/documentation/apis/swap/intent-swap/aqua/swapvm/patterns/dutch-auction.md)

기존 서비스 대비 가격 우위를 주장하려면 같은 시각·체인·거래 조건에서 해당 서비스가 반환한 가용 견적과 모든 비용을 저장해 비교해야 한다. 이번 검증에는 이 비교 표본이 없다. 네트워크 및 자산 식별에 HSK 공식 문서를 사용했다. HSP·CCIP 사용 또는 행사 가점 충족을 실적으로 산입하지 않았다. [네트워크 정보](https://docs.hskchain.net/docs/Build-on-HashKey-Chain/network-info) · [토큰 컨트랙트](https://docs.hskchain.net/docs/Build-on-HashKey-Chain/Token-Contracts)
