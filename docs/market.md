# WHSK/USDT 메인넷 시장 조회

`hsk.market`는 Chain ID 177의 공개 RPC에서 같은 블록의 WHSK/USDT 직접 풀을 조회한다. 사용자 지갑과 키가 필요하지 않다. [공식 체인 연결 정보](https://docs.hskchain.net/docs/Build-on-HashKey-Chain/network-info) · [공식 토큰 주소](https://docs.hskchain.net/docs/Build-on-HashKey-Chain/Token-Contracts)

| 구성 | 주소 또는 근거 |
| --- | --- |
| WHSK, 18자리 | `0xb210d2120d57b758ee163cffb43e73728c471cf1` |
| USDT, 6자리 | `0xf1b50ed67a9e2cc94ad3c477779e2d4cbfff9029` |
| V3 Factory | `0x972ca9d1662f5e029cd18327d29026532e84c742` |
| QuoterV2 | `0x603f70466fddbe3f238220b9a74fff419a2bbfdd` |
| 수수료 0.30% 직접 풀 | `0x4ff515761864e7838b0adb8b5b2b8b7a068905dc` |

DEX 배포 주소는 팀의 메인넷 자료에서 가져왔다. 블록 30,709,982에서 주소별 코드와 읽기 응답이 기록되어 있다. Quoter와 풀 ABI의 출처 및 해시는 계약 검증 기록에 있다. [검증 기록](../config/verified_contracts.json) · [Quoter 계약](https://hsk.blockscout.com/address/0x603f70466fddbe3f238220b9a74fff419a2bbfdd) · [풀 계약](https://hsk.blockscout.com/address/0x4ff515761864e7838b0adb8b5b2b8b7a068905dc)

1. `get_head()`는 최신 블록 번호, 해시, Unix 시각을 반환한다. `get_snapshot(block_number=None)`은 해당 블록의 주소, 소수 자릿수, 풀의 활성 유동성·가격·틱·수수료, 조회 시각과 출처를 기록한다.
2. Factory의 `getPool`을 수수료 0.01%, 0.05%, 0.30%, 1.00%에 대해 호출한다. 응답이 있는 풀마다 토큰 순서, Factory와 수수료를 검증한다. Quoter의 Factory도 검증한다.
3. `quote_exact_input(snapshot, side, amount_in)`은 같은 블록에서 각 풀의 수령량 중 최댓값을 반환한다. `quote_exact_output(snapshot, side, amount_out)`은 지출량 중 최솟값을 반환한다. `buy`는 USDT 지출, `sell`은 WHSK 지출이다. 금액은 해당 토큰 최소 단위의 양의 정수다.
4. 후보별 RPC 호출 실패, 불완전 ABI 응답, 체인·토큰·블록 해시 불일치, 가격 한계 도달은 오류로 표시한다. 다중 홉 및 분할 경로는 이 기준 견적의 범위 밖이다. DEX 견적에는 풀 수수료와 가격 충격이 포함된다. L1·L2 정산비와 사용자별 실현 손익은 별도 측정 항목이다.

과거 블록 조회를 지원하는 메인넷 RPC에서 10 WHSK 매도 견적을 재현할 수 있다.

```sh
python3 -c 'from hsk.market import get_snapshot, quote_exact_input; s=get_snapshot(30710916); print(s, quote_exact_input(s, "sell", 10*10**18))'
python3 -m unittest discover -s tests -p test_market.py -v
```

감독의 같은 블록 독립 호출에서 수령 견적은 791,946 USDT 최소 단위였다. 예측 절감액에 필요한 반대 주문 수량·추가 운영비의 가정 및 실제 조회 시각은 금액별 검증 표에 있다. [메인넷 검증 표](validation.ko.md)
