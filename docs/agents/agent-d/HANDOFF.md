# Agent D 인계 · 2026-11-27

기준 커밋 9ec804a에는 루트 AGENTS.md와 현행 A/B/C 산출물이 없었다. 사용자의 공통 지침, 첨부한 D0–D15 역할 지시서 및 원 작업공간의 docs/project-brief.ko.md를 읽고 agent-d-integration worktree에서 시작했다.

| 요청 상대 | D0 요청과 실제 연결 | 남은 변경 요청 |
|---|---|---|
| A | 네트워크·주소·decimals, 고정 블록 MarketData, 30일 시장·경제성 보고서를 받았다. 브라우저의 읽기 요청과 원자료 집계에 연결 | 두 단계 이상 경로의 최적 견적, 실제 비용 상한의 유효기간과 실시간 운영자 단가 |
| B | OpenAPI, shared/engine-0.1, 주문·취소·상태·SSE·비교·영수증·자연어 API 사용. 실제 서명과 DB·워커 실행으로 대조 | 주문 목록의 등록 UTC 시각 및 영수증의 확인 시각·블록 번호·L1 실제 수수료·부담자 필드 명시. 외부 API의 장애·재연결·장기 고가용성 검증 |
| C | Settlement-v1 ABI, EIP-712 v1 typed data와 벡터, 취소·nonce 무효화·OrderFilled 이벤트 확인. 한정 승인과 Solidity/viem digest 일치 검증 | 승인 후 실제 배포 manifest, 바이트코드와 탐색기 소스 검증, 운영 예산·권한 정책 |

B의 SandboxOrder와 C의 Order는 구분되는 서명이다. 차이점에는 domain, recipient, allowedExecutor, 가격·비용 한도 표현이 있다. 포크 제출 시 두 서명을 받아 명시된 projection과 검증 계약을 확인한다. C 서명만으로 모든 운영 비용이 보전된다고 간주할 수 없다. 실제 합의가 필요한 변경은 A의 제안과 B/C 버전 원본을 유지한다. D가 별도의 정식 공통 스키마 버전을 발행하지 않았다.

Worktree 자동 탐색, 환경변수, 명령은 [통합 명세](../../INTEGRATION.md), 제출 항목별 근거는 [해커톤 요건](../../HACKATHON_REQUIREMENTS.md)에 있다. [포크 영수증](browser-fork.json) · [메인넷 읽기](observed-quote.json) · [3분 영상](fork-demo.mp4)

공개 배포 전 남은 사항은 팀장 승인, 실제 비용·경제성 확인, 메인넷 계약과 거래 영수증, 공식 제출 URL이다. 일반 UI의 오프체인 취소와 계약 상태를 동기화하는 온체인 취소는 서로 다른 작업이다. 주문 생성 전에 서명을 요구하며, 서명 원문이나 키는 공개 주문장에서 제공하지 않는다.
