# Agent B 독립 검증 · 2026-11-27 KST

| 증거 | 실행한 검사 | 결과 |
|---|---|---|
| SYNTHETIC | 백엔드 pytest | 27개 통과. 의존 패키지 deprecation 경고 2건 |
| SYNTHETIC | 임시 PostgreSQL 마이그레이션 및 동시 등록 | upgrade → downgrade → upgrade 통과. 16개 동시 요청, 고유 주문 2건, 체결 1건, fill 2행 |
| SYNTHETIC | C 서명 벡터 2건과 B 샌드박스 예제 | Python eth-account와 프론트엔드 viem에서 digest·복구 주소 일치. 포크 주문 3건은 Solidity orderHash까지 일치 |
| BACKTEST | 기존 A Session1 및 B Session1 재실행 | A 라우팅 8개 통과. B 검증기는 보관 로그 656개, 610개 판단 × 3개 비용, 10개 대조군, 경제성 예제 7개, 직접 매칭 비교 50개와 수집기 오류 조건을 통과 |
| BACKTEST | Session2 quotes.py 재구성 | 세 견적의 출력 JSON이 보관 파일과 바이트 단위 일치 |
| OBSERVED_MAINNET | A v1 공급자로 역사적 블록 30,592,078을 재조회 | 1,000 WHSK 정확 입력 80.558131 USDT, 600 WHSK 정확 출력 48.641160 USDT, 400 WHSK 정확 입력 32.226965 USDT. 세 건의 블록 해시·원 단위가 보관 자료와 일치. [원응답](reference-quotes.json) |
| FORK_SIMULATION | FastAPI에 정책·정산 서명 3건 등록, 자동 worker → C Settlement → 영수증 대조 | 매도자 1명과 매수자 2명, 1,000 WHSK 복수 직접 매칭. 최종 실행 가스 추정 808,348, 사용 701,938. 수락 직후 전송 응답을 예외로 교체했고 동일 해시로 복구했다. 정산 방송은 정확히 1회, SQL 및 C 누적량 일치. [증거](fork-receipt.json) |
| UNVERIFIED | 실제 LLM 추론 품질·운영 수익·실현 순절감 | 로컬 도구 선택기는 주입한 응답으로 검사했다. Ollama 모델 서비스와 실제 서비스 운영비는 미측정 |

포크는 메인넷 같은 블록의 실제 WHSK·USDT·HSKSwap 코드와 로컬 배포 Settlement를 사용했다. 테스트 계정 잔액은 로컬 포크에서 설정했다. 주문·서명은 일회용 테스트 계정에서 생성했다. 사용자 비용 상한과 운영자 가스 예산은 합성 입력이다. 블록 해시는 `0x8e9ec7357cca666d04911b91bb3f5cf0292a7b4e5150a4e6febe30daa1280bda`다.

| 포크 사용자 | 체결 수량 | 독립 DEX 기준 USDT | 포크 정산 USDT | 추가 비용 차감 전 차이 USDT |
|---|---:|---:|---:|---:|
| 매도 | 1,000 WHSK | 수령 80.558131 | 수령 80.812643 | +0.254512 |
| 매수 | 600 WHSK | 지출 48.641160 | 지출 48.513806 | +0.127354 |
| 매수 | 400 WHSK | 지출 32.426191 | 지출 32.298837 | +0.127354 |

DEX 비교는 각 사용자의 고정 수량을 같은 시작 상태에 독립적으로 적용했다. 메인넷 거래 영수증과 실제 사용자 주문은 이번 검증에 없다. 기존 0.28893984 USDT 추정값을 성과로 이월하지 않았다.

## 통과 조건과 거절 조건

- 매도 EXACT_IN 및 매수 EXACT_OUT 양방향에 대해 단일·복수·혼합·부분 유지의 선정을 검사했다. 지급량과 잔량 합계를 보존해야 하며 부분 기준 DEX 견적은 실제 체결 수량에 대응해야 한다.
- 양측 가격 불일치, 한 사용자에게 과다한 비용, 최소 절감 미달, 0으로 반올림되는 작은 견적, 비용 상한 누락, 승인 없는 DEX 전환은 최적 후보에서 제외했다. 탐색 예산 축소 시 작은 문제의 최선 전량 결과와 탐색 중단 표시를 비교했다.
- 숫자형 JSON·오버플로·비정규 10진 표현을 거부했다. 매도 한도 올림, 매수 한도 내림을 대조했다. 정책 위조, 다른 소유자의 취소 서명, nonce 재사용을 거부했다. 서명 원문은 조회와 유효성 오류 응답에서 확인되지 않아야 한다.
- 주문 등록 이벤트로 자동 평가했다. 취소·만료, 중복 주문 및 로그, RPC 중단 후 outbox 재처리, 모니터 재시작 후 블록/로그 인덱스 재개, 활성 주문 없는 동안 시장 조회 0회를 검사했다.
- 잔액·승인 부족, 시뮬레이션 revert, 가스 예산 초과 때 실행 행이 없어야 한다. 미확정 영수증은 대기로 처리했다. FORK에서는 전송 응답 유실까지 실제 API 경로로 시험했다.
- 모의 계획자가 calldata 또는 공개 제출 도구를 지정하면 실행 요청을 폐기한다. 일반 주문 경로의 모델 호출은 0회다. 정상 도구 선택은 선택한 도구의 결과만 반환한다.

## 재현 명령

브랜치 루트, Python 3.12.3, Foundry Anvil 및 Agent C solc 0.8.26 빌드 산출물을 사용했다. `HSK_A_ROOT`와 `HSK_C_ROOT`에는 각 worktree 경로를 지정한다. 포크 명령은 직접 실행한 Anvil IPC와 임시 DB를 생성·종료한다.

```sh
python -m pip install -r backend/requirements.txt
python -m pytest -q -p no:cacheprovider backend/tests
python -m backend.tests.export_interfaces
python -m pip install pgserver==0.1.4
python -m backend.tests.postgres_check
python -B backend/tests/verify_reference.py --provider-root "$HSK_A_ROOT"
forge build --root "$HSK_C_ROOT/contracts"
python -B -m backend.tests.fork_settlement --compiled "$HSK_C_ROOT/contracts/out" --anvil "$(command -v anvil)"
```

기존 코드 재검증은 각 압축을 별도 임시 디렉터리에 풀고 실행했다. 보관 환경의 절대 경로나 과거 테스트 출력을 현재 결과로 가져오지 않았다.

```sh
# HSK_A_Session1.zip 내부 HSK_A_Session1에서
python -B -m unittest test_routes
# HSK_B_Session1_Verified.zip 루트에서
python -B verify.py
# HSK_Session2_Quotes.zip 루트에서
python -B quotes.py > recomputed.json
cmp quotes.json recomputed.json
```

첫 archive RPC 실행은 HTTP 403이었다. A의 User-Agent를 사용하는 읽기 전용 어댑터로 세 견적을 재조회해 검증했다. 최초 PostgreSQL initdb는 시스템 로케일을 거부해 임시 검증 프로세스에 LC_ALL=C를 지정한 뒤 재실행했다. 스타일 검사는 Ruff 0.11.13으로 수행했다. 실제 네트워크 견적과 테스트 가정을 함께 계산할 때는 각각의 증거 분류를 유지한다.
