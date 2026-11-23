# 재현 스크립트

모두 HashKey Chain 메인넷 RPC(`https://mainnet.hsk.xyz`)와 Blockscout API v2만 쓴다. 기준 블록은 **30553002 (2026-11-23 16:58:59 UTC)**.

| 순서 | 명령 | 결과 |
| --- | --- | --- |
| 1 | `python3 getlogs.py 0x4ff515761864e7838B0AdB8b5b2B8B7A068905dC 17714162 30553002 whsk_logs.json` | WHSK/USDT 풀 이벤트 전체 (26,440건) |
| 2 | `python3 decode.py whsk_logs.json whsk.json` | Swap 26,368 · Mint 31 · Burn 21 · Collect 17 |
| 3 | `python3 getlogs_t.py 1 30553002 v3mint_all.json '["0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde"]'` | 체인 전체 Uniswap V3형 Mint 이벤트 (176건) |
| 4 | `python3 build_swaps.py` | `whsk_sw.pkl` (스왑 가격·규모 표) |
| 5 | `python3 bt.py 0.10` (또는 0.15, 0.30) | 집중 범위 LP 모의 실험 |
| 6 | `python3 fullrange_bt.py` | 전 구간 LP 모의 실험 |

- `eth_getLogs`는 이 RPC에서 한 번에 5,000블록까지만 된다. 스크립트가 5,000블록씩 나눠 12개 스레드로 받는다.
- WBTC/USDT(`0xd9EA…449A`), WETH/USDT(`0xb92b…4C16`) 풀도 1~2단계를 같은 방법으로 돌렸다.
| 7 | `python3 bt_rule.py` | 처분 규칙 비교(항상 보유, 항상 매도, 24시간 하락률 규칙). KuCoin `HSK-USDT` 1시간봉(`kucoin_hsk_1h.pkl`, `/api/v1/market/candles`, 2026-04-01부터)이 필요하다 |
