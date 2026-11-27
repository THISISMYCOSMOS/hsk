# HSK Smart Execution

WHSK/USDT 주문의 크기에 따라 HSKSwap 직접 풀의 견적과 가상 반대 주문을 이용한 집행 비용을 비교한다. 메인넷 검증 경로는 지갑 연결 없이 읽기 전용 RPC를 사용한다.

## 바로 실행

프로젝트 루트에서 Python 3.11 이상으로 실행한다. Python 패키지 설치는 필요하지 않다.

```sh
python3 -m hsk sell 10 100 1000
python3 -m hsk buy 1 10 100
python3 -m hsk.headroom WHSK 10 100 1000 --match-bps 6000
python3 -m hsk --archive
python3 -B -m unittest discover -s tests -v
```

첫 두 명령은 각각 WHSK 매도 수량과 USDT 매수 예산을 입력받는다. `--scenario`로 가상 지정가·수량·비용을 입력하고 `--watch 30`으로 갱신할 수 있다. 세 번째 명령은 상대가 입력량의 60%를 사고 싶어 한다고 가정하여 같은 시작 블록의 DEX 견적 세 개를 비교한다. 매칭 대금은 양측 사이에서 이동하므로 **반대 주문의 DEX 매수 비용 + 잔량 DEX 수령액 − 전량 DEX 수령액**이 양측에 배분할 수 있는 비용 전 차이다. 실제 반대 주문의 가용성, 사용자별 배분, 승인·정산·가스 비용에 따라 순절감액은 달라진다. `--archive`는 팀이 보관한 과거 블록 예시다.

## 개발 인계

| 담당 | 인계 자료 |
| --- | --- |
| 감독 | [프로젝트 원문](docs/project-brief.ko.md) · [네 에이전트의 업무 지시 및 인수 기준](docs/agent-briefs.ko.md) |
| 시장 데이터 | [HSKSwap V3의 동일 블록 조회](docs/market.md) |
| 매칭·경제성 | [비용 단위, 후보 선택 및 순차 거래 비교](docs/economics.md) |
| 정산·보호 조건 | [EIP-712 로컬 정산 및 테스트](docs/settlement.md) |
| 실행 에이전트·인터페이스 | [거래 조건 입력, 시나리오 및 갱신 방법](docs/agent.md) |

금액별 실제 조회값, 비용 가정별 해석, 포크 재현 명령과 미측정 항목은 [감독 검증 기록](docs/validation.ko.md)에 있다. `hsk.headroom`의 `--extra-cost 0.03`은 경로 간 추가비용을 출력 토큰 0.03개로 가정해 양측 합산 결과를 계산한다.

메인넷 읽기와 가상 주문 처리는 Python 경로에서 수행한다. Solidity 프로토타입은 별도 로컬 테스트에서 승인 조건과 원자적 정산을 검증한다. 현재 견적 CLI에서 가상 주문을 정산 컨트랙트로 제출하는 경로는 없다.
