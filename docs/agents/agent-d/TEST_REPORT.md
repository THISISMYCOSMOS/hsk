# 독립 검증 · Agent D · 2026-11-27 KST

| 실행한 명령 | 확인한 결과 |
|---|---|
| make setup / make dev | 의존성 설치, 브라우저 빌드, 로컬 서버 기동. 실제 UI 경유 1 WHSK → 0.079197 USDT, 블록 30,711,527 |
| make backtest / make demo-local / make export-report | 기존 라우팅 8개 통과. 656개 로그 대조, 610개 결정 × 비용 3개, 7개 경제성 fixture, 50개 계정 비교. 고비용·반대 주문 없음·한도 미달 시나리오 재생 |
| make interfaces | Agent B 실제 모델 11개와 서명 fixture 검증. Solidity/viem Settlement v1 벡터 2개 대조 |
| make market-report | A의 관측 범위 만료점 30,709,982. 전체 로그 2,792개, 대상 풀 2,421개, 47,473.168591 USDT. 원자료에서 중복·방향·수량·풀 집계 대조 |
| make test | TypeScript 및 Vite 빌드. Playwright 정상 등록·취소, 네트워크 변경, 직접·부분+DEX·복수 매칭, 중복·비경제적 거래, 모바일·RPC 실패 7개 통과. 임시 DB와 실제 FastAPI/워커를 사용 |
| python3 scripts/integration/contract_test.py | 보관 SessionSettlement 로컬 Solidity 테스트 30개 통과 |
| python3 scripts/integration/role_tests.py | C의 현행 로컬 Solidity 20개·B의 Python 27개 통과한 실행 확인. 이 수치는 해당 시점 복사본의 결과 |
| make test-fork | Anvil 포크에서 보관 QuoterV2 응답 3개 대조. 새로 빌드한 C 계약으로 직접·부분+DEX·복수·미체결·fallback·취소·만료 7경로 확인. Foundry 가격 재조회·유동성 변화 2개 통과 |
| make dev-fork / node scripts/demo/record.cjs | 브라우저 EIP-1193 요청, 정책·정산 각 서명, 제한 승인, DB·worker·실제 정산·영수증 대조. 포크 체인 31337, 원본 177/30,592,078 |
| docker compose up -d --wait / node scripts/integration/check-compose.cjs | PostgreSQL 마이그레이션, Nginx·FastAPI·워커·Anvil 기동. 일반 UI 프록시에서 합성 주문 서명·등록·DB 조회·소유자 취소 확인 |
| ffprobe | 재생 가능한 H.264 MP4, 180초. 실제 화면 캡처를 자막과 편집한 영상 |

### 포크에서 실제로 측정한 값

원본 블록 30,592,078의 HSKSwap 풀을 사용했다. 사용자별 포크 변화량은 다음과 같다.

| 지갑 | WHSK | USDT |
|---|---:|---:|
| 매도자 | −1,000 | +80.713128 |
| 매수자 | +600 | −48.486163 |

로컬 영수증 가스 686,104. 양측 서비스 수수료 0은 이번 포크 주문에서 측정했다. 실현 L1 비용, 운영 이익과 메인넷 실현 순절감액은 미측정이다. [원본 실행 증거](browser-fork.json)

### 확인 범위와 문제

- 실행 중 발생한 환경 문제로 샌드박스의 로컬 포트 바인딩과 레지스트리 접근이 차단됐다. 승인된 실행에서 재시도해 검증했다. Compose의 초기 UI는 컨테이너 시작 시 npm 다운로드에서 ECONNRESET이 발생했다. 빌드된 자산을 Nginx에서 제공하도록 수정했다.
- Foundry가 캐시 경로 및 Solidity lint 경고를 출력했다. 테스트 성공을 외부 계약 보안 감사 결과로 사용할 수 없다.
- 실제 브라우저 및 EIP-712 서명을 사용했다. 지갑 확장 UI의 승인 팝업이나 하드웨어 지갑 상호운용은 미검증이다. 시연 전용 provider는 로컬 Anvil에만 연결했다.
- 포크에 발행한 거래 해시와 테스트용 잔액은 메인넷 탐색기의 거래가 아니다. 관측 블록만 Blockscout에 연결한다. 현행 메인넷 계약 배포와 지출은 팀장 승인 전이다.
- 기본 파서는 모델 호출 0건. 실제 LLM 품질·비용 및 사용자의 자연 수요는 미측정이다. 최적화는 탐색한 후보에 한정된다.
