# Agent A 개발 상태 · 2026-11-27 KST

**PARTIAL.** 지정한 30일 실데이터 수집, 시장 공급자, 양방향 순차 포크 비교, Agent C 정산 비용 검증과 Agent B 워커 재생을 수행했다. 제품 메인넷 배포·실사용자 등록·실제 서비스 순수익은 UNVERIFIED다. 담당 브랜치는 `agent-a-data`, 시작 커밋은 `origin/main@9ec804a`다.

| 단계 | 상태 | 근거 |
|---|---|---|
| A0 기존 자료 | PASS | ZIP 4개 조사, 기존 Python·Foundry 실행, 보관 금액과 원자료 대조. 종전 순액 차감 상세 명세 미발견 |
| A1 네트워크·주소 | PARTIAL | 공식 RPC 177, 최근 1,000개 블록 간격 평균 2초, 코드와 ABI 7건. 0·1·1,000,000·30,592,078·30,709,982 블록 표본 접근. 모든 중간 블록에 대한 archive SLA는 미검증. 공개 WSS 후보 구독 실패 |
| A2–A3 풀·시장 | PASS | Factory 인덱스와 풀별 getPool 재확인, 18개 풀 전 구간 로그·영수증 대조. 화폐가치 공통 환산이 불가능한 풀은 원 자산별 수량 보존 |
| A4 공급자 | PASS | 공개 메서드 11개를 실 RPC로 호출, 오류 전달·블록별 캐시·재조직 회귀 검사. finalized HTTP 이벤트 처리는 지연이 있음 |
| A5–A6 순차 실행·비용 | PARTIAL | A/B/C/D/E 로컬 포크, 사용자별 잔고 변화·쿼터 하위 호출·승인·취소·revert. C 고정 빌드와 연구용 검증 방식 비교. 메인넷 서비스 L1 영수증 미측정 |
| A7 사전 주문 | PARTIAL | 유효기간 5종과 8개 변수의 민감도. 희망가·참여율·가입 주문·지연·비용은 가정 |
| A8 운영비 | PARTIAL | B 워커의 4가지 실행 방식과 로컬 DB·CPU·메모리·지연 계측. 클라우드 청구 및 전체 이벤트 수집 운영비는 미측정 |
| A9 최종 평가 | PARTIAL | 순차 검증, 사례별 순편익, 실패 조건과 월간 적자 사례를 보고 |

## 해커톤 기간 변경 범위

2026-11-27에 Agent A가 새로 작성한 파일은 아래 경로에 있다. 재사용한 이전 Python·Foundry 소스는 기존 ZIP에서 임시 디렉터리로 풀어 실행했다. 구버전의 RFQ·시장조성 로직을 제품에 추가하지 않았다.

- `backend/app/blockchain/rpc.py`, `backend/app/market_data/provider.py`에 읽기 전용 전송과 시장 공급자를 구현했다.
- `config/network/`, `config/verified_contracts.json`에 공식 네트워크, 직접 검증한 주소·ABI·함수·조회 블록을 기록했다.
- `backtest/`에 기존 자료 재실행, 30일 수집, 견적 조회, 포크·운영비 실험, 검증 테스트를 구현했다.
- `data/raw/30709982/`와 `data/processed/`에 실제 로그·영수증·정제 레코드를 보관했다. `data/fixtures/market/`에는 공급자 예제와 C 검증용 빌드를 보관했다.
- `shared/proposals/agent-a-v1/`의 스키마와 fixture는 A의 버전 제안이다. B의 엔진 투영과 C의 온체인 서명 규격은 각 소유 브랜치에서 관리한다.
- `reports/economics/`와 `docs/agents/agent-a/`에 실행 결과, 해석, 재현 및 인계 요건을 기록했다.

## 기준 지침과 공식 자료

시작 시 로컬 폴더는 비어 있었다. 원격 main에도 마스터 AGENTS.md가 없었다. Git 이력의 `2ae8955:AGENTS.md`는 이전 LP 방어 주제를 위한 지침이다. 이번 작업은 사용자 본문과 Agent A 첨부를 기준으로 했다. 작업 중 생긴 감독자의 `docs/project-brief.ko.md`도 확인했다. 공통 파일 또는 타 에이전트 작업을 덮어쓰지 않았다.

서울 트랙의 개발 방향, 제출 시각(12월 3일 13시 KST), 메인넷 배포 및 Git 링크·영상 요구를 주최 공지로 확인했다. 공지는 권장 제품·프레임워크 추가점수 가능성을 명시한다. 전체 인정 대상 명단과 제품별 배점은 확인되지 않았다. [서울 주최 공지](https://luma.com/mwn8lt3q)

실제 활용한 공식 자료는 RPC·체인 ID·탐색기와 WHSK/USDT 토큰 문서다. 주소는 실 호출과 ABI로 대조했다. 가스는 L2 실행과 L1 데이터 비용으로 구분했다. 공식 Flashblocks 자료에서 공개 WebSocket은 테스트넷 제공으로 안내한다. [네트워크](https://docs.hskchain.net/docs/Build-on-HashKey-Chain/network-info) · [토큰](https://docs.hskchain.net/docs/Build-on-HashKey-Chain/Token-Contracts) · [수수료](https://docs.hskchain.net/docs/Build-on-HashKey-Chain/Fee) · [Flashblocks](https://docs.hskchain.net/docs/Build-on-HashKey-Chain/Flashblocks)

HashFans는 개발 자료 탐색 경로로 확인했다. Chainlink CCIP Router의 메시지 전송과 HSP 가이드의 mandate·지갑 서명·결제 검증은 현재 단일 체인 주문 집행의 실행 경로에 포함되지 않는다. 서울 행사에서 열거한 제목과 동일한 HSP Setup & Execution Guide의 원본 링크는 별도 확인이 필요하다. 추가점수 인정 또는 제품 호출 실적으로 산정한 항목은 없다. [HashFans](https://hashfans.io/) · [CCIP Router](https://docs.chain.link/ccip/evm/api-reference/v2.0.0/router) · [HSP 개발 가이드](https://hsp-hackathon.hashkeymerchant.com/docs)

## 인계 및 남은 일

실서비스 체결과 장기 이용자 수요, 실제 인프라 원가, 등록 시점 즉시 거래 대비 대기 기회비용, 혼합 경로의 최적 라우팅 우위는 미검증이다. 실제 WSS 또는 저비용 이벤트 공급원의 운영 측정이 필요하다. 배포·토큰 승인·자금 이동·가스 지출에 해당하는 메인넷 작업은 팀장 승인 단계다. 이 브랜치의 코드는 공개 읽기 전용 또는 분리된 로컬 포크로 검증했다. [판정표](../../../reports/economics/ASSESSMENT.ko.md) · [공급자·서명 인터페이스 인계](HANDOFF.md) · [실행 기록](TEST_REPORT.md)
