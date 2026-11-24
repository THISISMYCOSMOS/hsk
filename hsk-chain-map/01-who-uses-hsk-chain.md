# 1. HashKey Chain은 누가, 무엇에 쓰고 있나

작성 2026-11-24 · 출처는 각 표 아래에 적었다 · 확인한 것 / 간접 근거 / 확인 못 한 것을 나눠 적는다

> **정정 (2026-11-24, 04·06 문서):** "주간 활동 계정 약 100개"는 직접 거래를 보낸 지갑만 센 숫자다. 플랫폼이 대신 처리하는 예측시장 참여자(하위 계정 64,291개, 실제 거래 43,313개)는 여기에 잡히지 않는다. 다만 그 예측시장의 돈은 이벤트용 자금이다.

## 한 장 요약

HashKey Chain은 **HashKey 그룹이 운영하는 이더리움 L2(OP Stack)**다. HSK는 이 체인의 가스 토큰이자, HashKey 거래소의 수수료 할인 등에 쓰는 플랫폼 토큰이다. 회사가 키우려는 방향은 **규제 안의 금융**이다. 토큰화 MMF·은 같은 RWA, 스테이블코인(RDUSD 시험), Base와의 협력, Morpho 기반 허가형 대출이 여기에 해당한다.

**지금 이 체인 위에 "많은 사람"은 없다.** 사람이 몰렸던 때는 2025년 초 캠페인 시기뿐이다. 지금 움직이는 것은 봇, 기관의 통합 계정, 운영 주체다. HSK 거래의 99% 이상은 체인 밖 거래소에서 일어난다.

| 사용자 유형 | 규모 | 지금 활동 | 체인 위 돈 |
| --- | --- | --- | --- |
| ① 캠페인·에어드랍 참여자 | 한 번이라도 거래한 계정 **297,194개**, 주소 242만 개 | **거의 없음** (주간 활동 계정 약 100개) | 작음 |
| ② 봇과 인프라 (예측시장, 가격 피드, 금고 자동화) | 주소 몇 개 | 사용자 거래의 **99.2%** | 작음 |
| ③ 기관 RWA 통합 계정 (토큰화 MMF) | 주소 2~3개 | **평일 매일** 청약·환매 | 펀드 단위 약 140만 개 이상 |
| ④ 유동성 운영 주체 | 주소 2개 | 가끔 (회수·재공급) | 약 100만 달러 |
| ⑤ HSK 보유자·트레이더 | 이더리움 HSK 보유 주소 4,287개 + 거래소 이용자 | **거래소에서** 활발 | 체인 위 거래는 전체의 1% 미만 |

---

## 1. 계정과 활동 (Blockscout 통계 서비스, 2026-11-23)

| 지표 | 값 | 조회 |
| --- | ---: | --- |
| 전체 주소 | 2,421,062 | `stats-service/api/v1/counters` → `totalAddresses` |
| 한 번이라도 거래를 보낸 계정 | 297,194 | 같은 곳 → `totalAccounts` |
| 계약 수 / 토큰 수 | 72,455 / 485 | 같은 곳 |
| **주간 활동 계정 정점** | **37,091** (2025-02-10 주) | `lines/activeAccounts?resolution=WEEK` |
| 주간 활동 계정 최근 | 89 · 181 · 100 · 125 · **106** (10/19 주 ~ 11/16 주) | 같은 곳 |
| 주간 새 계정 최근 | 20~30개 | `lines/newAccounts?resolution=WEEK` |

**표본 확인 (직접).** 블록 29,257,000~29,357,994(2026-10-24 16:58 ~ 10-27 02:52 UTC, 약 2.4일)의 시스템 거래(type 0x7e)를 뺀 거래 33,241건을 전수 조회했다.
- 보낸 주소는 **56개**뿐이었다.
- 거래 100건 이상을 보낸 주소 6개가 전체의 **99.2%**를 차지했다.
- 받는 쪽은 `PredictionMarket` `0xa0a6…49561`(21,962건), `Treasury` `0xa993…5646`(8,979건), `SubAccountFactory`, Chainlink 가격 피드(`AccessControlledOffchainAggregator`) 등이었다.

## 2. 보유자가 많은 토큰 = 지난 캠페인의 흔적

| 토큰 | 보유자 | 성격 | 마지막 움직임 |
| --- | ---: | --- | --- |
| AsteroidX Universe (ERC-1155) `0x5ABB…B556` | 156,829 | 캠페인 NFT | |
| BRAVO `0x6485…F3F8` | 112,888 | 배포형 토큰, 전송 357만 건 | **2025-10** 이후 사실상 멈춤 |
| AGI Open Network NFT | 23,059 | 캠페인 NFT | |
| Pizza Day NFT | 10,000 | 캠페인 NFT | |
| USDT `0xF1B5…9029` | 5,185 | 브리지 스테이블코인, 공급 117만 | 활동 중 |
| CELA, HDOG, HASHED, HASHOO | 650~1,860 | 체인 전용 토큰 | |
| veHSK / stHSK | 177 / 95 | HSK 잠금·스테이킹 | 활동 적음 |

출처: `hsk.blockscout.com/api/v2/tokens` (보유자 순), 토큰별 `/counters`, `/transfers`.

**해석.** 보유자 수는 2025년 캠페인 때 쌓인 숫자이고, 지금 쓰는 사람의 수가 아니다.

## 3. HSK는 어디서 거래되나

| 거래처 | 24시간 거래액 (USD) | 출처 |
| --- | ---: | --- |
| CoinW | 78,813 (호가 차이 1.10%) | CoinGecko `coins/hashkey-ecopoints/tickers` |
| MEXC | 56,591 | 같은 곳 |
| LBank | 30,213 | 같은 곳 |
| Gate | 27,004 | 같은 곳 |
| HashKey Exchange (USD + USDT) | 34,773 | 같은 곳 |
| KuCoin | 11,959 | 같은 곳 |
| Kraken | 약 1,000 | 같은 곳 |
| **CoinGecko 합계** | **약 24.2만** | |
| HTX | 1분봉 합산 약 77만 (CoinGecko 목록에 없음, **미검증**) | `api.huobi.pro/market/history/kline` |
| **HSKSwap (체인 위)** | 11월 하루 평균 약 **1,400** | 풀 Swap 이벤트 전수 (lp-defense 문서) |

- 체인 위 거래는 HSK 거래 전체의 **1% 미만**이다.
- HSK 원래 토큰은 이더리움 ERC-20 `0xE7C6…C98a`이고, 보유 주소는 4,287개다. 상위 보유자는 브리지·멀티시그·거래소 주소다(eth.blockscout.com).
- 시가총액은 약 2,800만 달러다(가격 0.0813 × 유통량 약 3.45억, KuCoin 표기 기준).

## 4. 체인 위에서 실제로 돈이 반복해서 움직이는 곳: 토큰화 MMF

| 토큰 | 공급 | 보유 주소 | 이벤트 | 기간 |
| --- | ---: | ---: | --- | --- |
| Bosera HKD MMF (BHKD) `0xc716…b955` | 1,255,768 | 2 | 청약(발행) **340건**, 환매(소각) **342건** | 2025-04-02 ~ 2026-11-23 |
| Guotai Junan HKD MMF (GHKDT) `0x80De…7618` | 147,952 | 1 | 청약 87, 환매 55 | 2025-10-24 ~ 2026-11-18 |
| Guotai Junan USD MMF (GUSDT) `0x9609…F210` | 3,530 | 1 | 청약 55, 환매 43 | 2025-10-27 ~ 2026-11-13 |
| 은·금 토큰 (HKST, STHK, vSILVER, XAUM) | 60~23,228 | 0~3 | 1~8건 | 대부분 2026-04 이후 멈춤 |

**BHKD에서 관측한 행동 (직접 확인)**
- 청약·환매가 **평일에만** 있다(월~금 고르게, 주말 0건).
- 발행과 소각은 **UTC 07~10시(홍콩 15~18시)**에 몰린다.
- 환매는 보유 주소가 상환 주소 `0x8510…e84F`로 보내고(대부분 01:01 UTC = 홍콩 09:01), 같은 날 소각된다. 요청에서 소각까지 **중앙값 7.6시간**, 최대 56.9시간이 걸렸다(341건).
- 2025-04 이후 청약 합계 2,096만 단위, 환매 합계 1,970만 단위다. 한 건의 중앙값은 약 1.1만 단위다.
- 월별 이벤트는 2026-01에 76건, 2026-10에 29건, 11월에 21건(23일까지)으로 줄고 있다.

**해석 주의 (간접 근거).** 보유 주소 `0x5039…F264`는 BHKD 125만과 BUSD 132만을 함께 들고 있다. 매 영업일 순 청약·환매를 하는 모양새라, 개인 투자자가 아니라 **판매사·플랫폼의 통합 계정**으로 보인다. 개별 의사결정자가 누구인지는 체인에서 보이지 않는다.

## 5. 회사가 밝힌 방향 (보도·회사 발표, 숫자는 미검증)

- 체인 위 프로젝트 200개 이상, 체인 위 RWA 3억 달러 이상(회사 수치). **Blockscout에서 공개적으로 보이는 RWA 토큰의 합은 이보다 훨씬 작다.** 허가형이거나 다른 형태일 수 있어 확인하지 못했다.
- 2026-11-18 Base와 협력. 두 체인 모두 HashKey 토큰화 자산의 기본 발행 네트워크로 삼고, Morpho 기반 허가형 CeDeFi 대출을 검토한다.
- RD Technologies의 RDUSD 스테이블코인을 HSK Chain에서 시험한다. 쓰임새는 RWA 거래 정산, 무역금융, 기업 결제다.
- 2026-03 홍콩 첫 규제 은 RWA 토큰을 발행 지원했다(위 4절의 은 토큰은 지금 거의 움직이지 않는다).

출처: [Manila Times / PR Newswire, HSK Chain × Base](https://www.manilatimes.net/2026/11/18/tmt-newswire/pr-newswire/hsk-chain-and-base-collaborate-to-connect-asias-premier-onchain-asset-with-global-liquidity/2472839), [Fintech Hong Kong, RDUSD 시험](https://fintechnews.hk/41816/blockchain/hashkey-rdusd-hsk-chain-stablecoin-testing/), [HashKey Group, 은 RWA 토큰](https://group.hashkey.com/en/hashkey-chain-supports-the-on-chain-issuance-of-hong-kongs-first-regulated-silver-backed-rwa-tokens/), [CoinMarketCap, HSK 설명](https://coinmarketcap.com/cmc-ai/hashkey-platform-token/what-is/), [HashKey Exchange HSK 상장](https://www.prnewswire.com/apac/news-releases/hashkey-exchange-will-list-hsk-to-advance-the-regulated-circulation-of-the-groups-ecosystem-token-302696779.html)

## 6. 확인하지 못한 것

- MMF 통합 계정의 실제 주체(판매사인지, HashKey Exchange인지)
- 회사가 밝힌 3억 달러 RWA가 체인 어디에 있는지
- HTX 거래액의 신뢰도
- 2025-02 활동 정점을 만든 캠페인의 이름과 보상 구조
