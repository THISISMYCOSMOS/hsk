# Agent C 개발 상태 · 2026-11-27 KST

HSKSwap 단일 WHSK/USDT 풀의 정산 계약, 서명 규격, 로컬 배포 도구를 구현하고 블록 30,592,078의 실제 풀·라우터 코드에서 검증했다. 전량 직접 매칭도 사용자별 실시간 비교 견적을 얻는 데 가스가 든다. 포크 가스와 메인넷 조회 결과는 TEST_REPORT에 구분했다. 운영자 손익, 실제 주문 도착 빈도 및 사용자별 실현 순절감은 UNVERIFIED다.

## 시작점과 신규 개발 범위

- 기준 커밋은 `9ec804a`, 브랜치는 `agent-c-contract`다. 기준 커밋에 루트 AGENTS.md가 없어 사용자가 제공한 지침과 Agent C 역할서, 기존 작업 트리의 `docs/project-brief.ko.md`를 적용했다. 과거 LP 방어 브랜치의 AGENTS.md는 별도 주제의 파일이었다.
- B 세션 보관본 `verify.py`를 분리된 디렉터리에서 다시 실행했다. 656개 로그, 재생 결과, 7개 경제성 fixture와 50개 직접 매칭 비교가 통과했다. A 세션의 SessionSettlement는 자금이 들어 있는 로컬 모의 호가창을 사용했다. 기존 미커밋 DirectSettlement는 양측 exact-input 주문, 서명·취소·부분 체결·전송 전후 잔액 검사와 외부 견적을 제공하지만 HSKSwap 라우터 호출 및 exact-output 인터페이스가 없다. 과거 코드의 EIP-712 도메인 및 실제 잔액 차 검증 방식을 재사용했다.
- 이번 해커톤에서 주문 검증 및 원자적 직접·복수·혼합 정산, 실시간 비교, 부분 체결 및 수수료 산술, 배포 스크립트, 교차 언어 벡터, 포크 실험을 새로 작성했다. FullMath와 연구용 TickMath는 Blockscout의 HSKSwap 검증 소스에서 가져와 라이선스와 출처를 유지하고 Solidity 0.8.26에 맞췄다. TickMath 연구 코드는 테스트에만 포함된다.
- 변경 위치는 `contracts/src`, `contracts/interfaces`, `contracts/test`, `contracts/script`, `contracts/foundry.toml`, `shared/abi`, `shared/typed-data`, `data/fixtures/contract`, `reports/gas`, `docs/agents/agent-c`다. ABI와 컴파일 산출물은 버전 1이다.

## 구현 상태

| 단계 | 결과 |
|---|---|
| C0–C2 | A 작업 트리의 6개 주소와 실제 조회 결과 일치. 라우터·Quoter 사용 함수의 ABI 원소도 A 보관본과 일치. 서명·유효기간·nonce·취소·누적 체결 및 서명 재사용 방지 구현 |
| C3–C6 | 주 주문과 최대 7개 반대 주문. 동일 사용자 중복 금지. WHSK 매도 exact-in과 WHSK 매수 exact-out. 직접 체결, 잔량 대기 또는 주 주문 잔량 DEX 처리. 고정 Router·Quoter·fee 3000 |
| C7–C9 | 개별 사용자별 원래 수량의 실시간 단일 풀 Quoter 호출. 고정 비용 상한, 실제 결과 재검증, 전체 묶음 원자성, 동의한 주 주문의 무료 DEX 전환, NO_TRADE |
| C10–C12 | 로컬 단위·퍼즈·상태 기반 invariant, 가격·유동성 변화 포크 테스트. 3개 연구 비교군 및 기존 DEX, 실패, fallback의 가스 원시 결과 제공 |
| C13 | MOCK 로컬 배포 예행연습과 포크 배포·바이트코드 검증 수행. 테스트넷 도구는 검증된 해당 네트워크 설정과 가스 예산이 필요하다. 메인넷 주소와 배포 영수증은 미발급 |

## 공식 자료 및 사용 근거

행사 공지는 HSK Chain 기반 거래 트랙과 HSP가 필요한 결제 트랙을 구분하며, 데모팀의 메인넷 배포와 권장 제품 가점 가능성을 명시한다. 제품별 가점 배점표는 확인하지 못했다. [서울 행사 공지](https://luma.com/mwn8lt3q)

HashFans 개발 포털과 토큰·네트워크 문서를 검토했다. 공식 토큰 주소, 177/133 네트워크 구분을 적용했고 실제 Router와 Quoter는 Blockscout 검증 ABI와 고정 블록 RPC로 대조했다. [HashFans](https://hashfans.io/) · [토큰 계약](https://docs.hskchain.net/docs/Build-on-HashKey-Chain/Token-Contracts) · [네트워크](https://docs.hskchain.net/docs/Build-on-HashKey-Chain/network-info) · [Router](https://hsk.blockscout.com/api/v2/smart-contracts/0x2c16f75b95cf1390c328ab70e2cee7f4b80bd8f3) · [Quoter](https://hsk.blockscout.com/api/v2/smart-contracts/0x603f70466fddbe3f238220b9a74fff419a2bbfdd)

CCIP는 체인 간 메시지용이며 이 주문은 같은 체인에서 종료된다. HSP의 공개 결제 API 및 agentic payment 자료를 검토했다. 이 정산의 지급 권한은 양측 ERC-20 승인과 EIP-712 서명으로 제한된다. CCIP·HSP 연동 증거나 가점은 청구하지 않는다. [CCIP Router 개요](https://docs.chain.link/ccip/concepts/architecture/offchain/overview) · [HSP API](https://hashfans.io/assets/merchant-docs-all-in-one.pdf) · [HSP 개발 가이드](https://hsp-hackathon.hashkeymerchant.com/docs)

## 남은 결정

팀장이 배포 계정·긴급 정지 관리자·운영자·서비스 수수료 및 가스 예산을 확정해야 한다. 수수료 수취인을 0으로 두면 유료 계획을 거부한다. B·D의 공식 ABI 채택, 주문 수명주기 통합, A의 동시점 가스·운영비 검증, 테스트넷 주소·계정, 외부 보안 감사, 실제 메인넷 승인·배포는 남아 있다. 상세 명령은 TEST_REPORT, 통합 요청은 HANDOFF에 있다.
