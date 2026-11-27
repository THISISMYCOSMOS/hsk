# Agent B 인계 · 엔진 0.1 / Settlement v1

## 실행

브랜치 루트에서 Python 3.12 가상환경을 활성화한 뒤 실행한다. Python 3.11 이상을 대상으로 작성했고 검증에는 3.12.3을 사용했다.

```sh
python -m pip install -r backend/requirements.txt
HSK_EXECUTION_MODE=MOCK python -m uvicorn backend.app.api.main:create_app --factory --host 127.0.0.1
```

기본 모드는 READ_ONLY다. MOCK은 독립 실행한다. 메인넷 읽기는 Agent A의 `backend/app/{blockchain,market_data}`와 네트워크 설정이 동일한 Python 경로에 필요하다. 공급자 부재·RPC 실패 시 시장 API는 503을 반환한다. PostgreSQL은 `HSK_ENGINE_DB`에 `postgresql+psycopg://...`를 지정하고 `python -m alembic -c backend/migrations/alembic.ini upgrade head`를 선행한다. SQLite 기본 위치는 `backend/hsk-engine.db`다. 모드별 독립 DB와 포크별 nonce 저널을 사용한다.

## A · 견적과 경제성

`backend.app.optimizer.search.compare(primary, peers, snapshot, now, search)`가 단일 계산 진입점이다. `Entry`는 주문 해시·정규 주문·미체결 WHSK raw·도착 순서다. `read_market(MarketData())`는 Agent A v1의 정확 입력/출력 견적을 같은 블록 해시에 묶는다. `MarketSnapshot.costs(orderId, route, legCount)`는 해당 사용자의 USDT 비용 범위 혹은 미측정값 None을 반환한다. Quoter 반환값에 포함된 AMM 수수료와 가격 충격을 재차 빼지 않는다.

- 매도는 고정 WHSK 입력과 최소 USDT 순수령, 매수는 고정 WHSK 출력과 최대 USDT 총지출이다. 수량은 WHSK 18자리, USDT 6자리의 최소 단위다. JSON은 10진 문자열, 산술은 Python int다. 부분 한도는 매도 올림, 매수 내림이다. 비교에는 같은 수량·주문 종류·비용 부담자를 쓴다.
- 비용에는 L1·L2·정산·재검증·승인·서비스·기타 상한과 안전마진이 있다. 항목은 중복되지 않게 분해해야 한다. 비교 DEX 비용은 하한만 절감에 더한다. 모르는 비용이 하나라도 있으면 공급자는 None을 전달한다. 메인넷 공급자는 현재 합산 상한이 없어 최적화 후보를 보류한다. `/metrics`는 A RPC 메서드 호출 수와 AI 호출 수를 제공한다.
- 각 측의 서명 한도와 비용 후 최소 개선을 먼저 만족시키는 가격 범위를 구한다. 여유분은 설정 가능한 `taker_bps`로 배분한다. 기본값은 5000이다. 최소 순절감은 체결 건당 micro-USDT, 총 비용 한도는 주문 전체에 대해 체결 수량만큼 내림 배분한다. 사용자별 순절감이 양수인 최적화 후보만 남는다. DEX 전환은 즉시·속도 우선·DEX 및 fallback 허용·최소 절감 0일 때 비용·가격까지 검사한다.
- 주문 가격·시간 우선으로 최대 7개 반대 주문, 128회 조합·수량 평가, 기본 2초의 탐색 예산을 쓴다. 개별 동기 RPC 한 건은 이 예산을 넘길 수 있다. 동일 지갑을 중복 참여시키지 않는다. 전량과 부분 결과는 체결량별로 분리한다. 기본 정책은 전량 최적화 가능 시 우선하고, 대기 허용 시 가장 큰 경제적 부분 수량 안에서 사용자 절감을 비교한다. 가격 한도·비용 상한·허용된 부분 수량 내에서 후보를 평가한다. `smallestEconomicFillTested`는 확인한 수량 중 최소이며 미발견은 null이다. 탐색하지 않은 분할 또는 전역 최적성은 보장할 수 없다.
- 다중 풀은 공급자가 동일 블록에 대해 검증한 추가 경로만 전달한다. 현재 A 어댑터는 단일 풀을 제공한다. C v1도 단일 풀만 실행한다.

## C · 서명과 포크 실행

C가 제안한 주 주문 1개와 반대 주문 배열, WHSK·USDT 직접 수량, 주 주문 잔량 DEX, 사용자별 수수료, 비례 반올림을 채택했다. Python은 C ABI의 `orderHash` tuple에서 필드 이름·타입·순서를 읽고 같은 ABI로 `settle`을 인코딩한다. 확인한 `Settlement-v1.json` SHA-256은 `548c994864b0d1a59518e99eb5e473508d09f4fc06be2879d4e065690cbaa263`이다. 권위 있는 계약 서명·ABI는 C 브랜치의 `shared/typed-data`와 `shared/abi`에 있다.

B의 `SandboxOrder`는 총비용 등 주문장 정책을 승인한다. FORK에서 자산 정산 권한은 별도 C v1 `Order`에 대한 지갑 서명이다. C의 `maxFeeAmount`는 USDT 서비스 수수료 한도이고 B의 `maxCost`는 더 넓은 총비용 한도다. 현재 지갑 수취인은 maker, executor는 배포된 포크 운영자다. 두 문서 원문은 각각 `POST /orders/typed-data`, `POST /orders/settlement-typed-data`로 확인한다. FORK 등록은 `{order, signature, settlementSignature}`, MOCK은 `{order, signature}`를 받는다.

실행 서비스는 동일한 sender·to·value·calldata로 eth_call과 가스 추정을 하고, 블록 해시·gas 예산·누적 체결을 재확인한다. 제출 전 실행 계획·주문 잠금과 nonce·예상 해시를 남긴다. 응답 유실 시 같은 해시를 조회한다. 제출 여부를 알 수 없는 동안 예약을 유지하며 장기 미확인 건은 운영자 조사가 필요하다. 포크 방송은 로컬 IPC·Anvil·chain ID 31337·계약 운영자 일치로 제한한다. TESTNET/MAINNET 모드에는 방송 어댑터가 연결되지 않는다. API 취소는 주문장 취소다. 이미 제공한 C 서명을 온체인에서 무효화하려면 소유자가 C의 cancelOrder 또는 invalidateNonce를 사용한다.

## D · API와 증거

- [OpenAPI](openapi.json), [JSON Schema 11종](../../../shared/engine-0.1/schemas.json), [만료된 서명 주문 2건 및 API 예제](../../../shared/engine-0.1/fixtures.json), [포크 영수증 발췌](fork-receipt.json)를 사용한다. 원본 서명은 주문 조회와 SSE로 반환하지 않는다.
- `POST /orders` 직후 worker가 페어를 평가한다. 주문 해시가 같은 재등록은 멱등이다. owner/nonce 재사용은 409, 잘못된 형식은 422, 없는 자원은 404다. 취소 서명 원문은 `GET /orders/{id}/cancel-typed-data`에 있다. 비교·영수증은 `/executions/{id}/comparison`, `/executions/{id}/receipt`로 조회한다. 미확정 영수증은 409다.
- 이벤트 목록 `GET /agent/events?after=N`, SSE `GET /agent/events/stream`의 Last-Event-ID로 재개한다. 실행 ID, 견적 ID 또는 주문 ID로 연관 이벤트를 찾는다. 포크 영수증의 cumulativeWHSK는 계약 누적 체결량이다.
- `POST /agent/intent`는 원문에서 명시된 값을 추출한다. `POST /agent/ask`는 선택한 도구를 실행한다. `HSK_LOCAL_PLANNER_MODEL`을 지정하면 loopback Ollama에 도구 선택을 요청한다. 모델의 인자는 비워 두며 수량·서명 수정과 제출 도구의 공개 호출을 거부한다. 일반 주문 처리와 서명 후 자동 실행은 모델 없이 진행한다. 공급자 장애·부적절한 호출은 결정론적 해석으로 돌아간다.
- A/B/C/D 공통 버전 승격 시 이 엔진 스키마와 D의 소비자 스냅샷, C의 EIP-712 벡터를 함께 비교해야 한다. A에는 payer별 실측 비용 상한 공급, C에는 실제 배포 manifest, D에는 지갑 정책·정산 이중 서명과 근거 표시를 인계한다.
