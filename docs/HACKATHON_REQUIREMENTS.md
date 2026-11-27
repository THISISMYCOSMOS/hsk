# Track 1 제출 근거

공식 주최 행사 안내는 거래 트랙의 시장 모니터링·AI 분석·자동 실행·리스크 관리·대화형 인터페이스, 권장 제품 사용 가산점, 데모팀 메인넷 배포, 영상과 Git 링크 제출을 명시한다. HSP 의무 조건은 결제 트랙에 해당한다. 정확한 제품별 가산점 배점표는 미확인이다. [주최 측 행사 안내](https://luma.com/mwn8lt3q) · [공식 제출 페이지](https://dorahacks.io/hackathon/hskchainseoul/detail)

| 요건 | 구현 및 증거 |
|---|---|
| 현행 시장 조회 | Agent A의 단일 풀 고정 블록 견적, 30일 풀 관측, 가격·유동성 변경 포크 시험 |
| AI 및 대화 | 자연어 입력 → 구조화된 초안 → 검토. 기본 규칙 파서와 선택적 로컬 모델 도구 계획, 실제 도구 호출 수 표시 |
| 자율 거래 | FastAPI 주문 등록 → DB outbox → 워커 → 경제성·시뮬레이션 → C 정산 → 영수증 기록. 브라우저 포크 실행으로 검증 |
| 위험 관리 | 체인·지갑·서명 검증, 제한 승인, 부분 체결 한도, 만료·취소·중복 방지, 재견적·미체결·원자적 롤백 |
| 제출물 | 소스·README·재현 명령·3분 포크 영상 제공. 승인된 메인넷 배포와 실거래 영수증은 대기 |
| 범위 | 본 실험은 HSK 단일 풀 주문 집행과 비용 검증을 다룬다. 일반 차익거래·포지션 관리·손절 성과는 미측정 |

## 공식 자료 검토

- HashFans는 공식 개발자 포털이다. 행사 안내와 개발 문서의 연결을 확인했다. [HashFans](https://hashfans.io/)
- WHSK·USDT 주소와 HSK 네이티브 가스 토큰을 확인하고 프로젝트 설정 및 포크 시장과 대조했다. [HSK 토큰 문서](https://docs.hskchain.net/docs/Build-on-HashKey-Chain/Token-Contracts)
- CCIP Router의 용도는 체인 간 전송·메시징이다. 이번 단일 체인 거래 경로의 사용 실적에는 포함하지 않았다. [Chainlink Router](https://docs.chain.link/ccip/evm/api-reference/v2.0.0/router)
- HSP API와 Agentic Payment의 의도·정산·응답 확인 흐름을 검토했다. HSP 기능이나 가산점 획득을 주장하지 않는다. [HSP 개발 가이드](https://hsp-hackathon.hashkeymerchant.com/docs) · [HashFans HSP API](https://hashfans.io/assets/merchant-docs-all-in-one.pdf)
- 실제 사용 증거는 HSK RPC의 블록·견적 기록, HSKSwap Quoter/Router 포크 호출, 조회 블록의 Blockscout 연결이다. [Blockscout](https://hsk.blockscout.com/) · [브라우저 실행 자료](agents/agent-d/browser-fork.json)

기준 커밋 9ec804a에서 기존 자료는 README와 backtests ZIP 네 개였다. Agent D 신규 범위는 React/TS 프런트엔드, API·SSE·지갑 어댑터, 서비스 기동 및 검증 스크립트, 브라우저 E2E, 영상과 제출 문서다. 아카이브 검증·A 데이터·B 엔진·C 계약은 각 담당자 출처를 보존했다. [저장소](https://github.com/THISISMYCOSMOS/hsk)
