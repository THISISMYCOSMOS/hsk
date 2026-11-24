# 3. 메인넷에서 KYC SBT는 실제로 쓰이고 있나 (2026-11-24 확인)

## 결론
**공식 문서의 KYC SBT는 메인넷에서 사실상 작동하지 않는다.** 그래서 KYC를 쓰는 주제는 "공식 SBT를 먼저 확인하고, 없으면 대체 인증을 쓰는" 두 단계로 설계해야 한다.

## 확인한 것
| 항목 | 값 | 조회 |
| --- | --- | --- |
| 공식 문서 | 함수(`isHuman`, `getKycInfo`, `requestKyc`)와 레벨 5단계를 설명한다. 예시 코드는 **테스트넷**용이고, 메인넷 주소는 없다 | docs.hskchain.net → Build on HashKey Chain → Tools → KYC |
| 메인넷 "KYC SBT" `0x0f362c05fb3Fadca687648F412abE2A6d6450D70` | 배포 주소는 `0xE4081d9B…599F`이다(HSKSwap 시험 LP를 넣은 주소와 같음). 소스는 공개되지 않았다 | Blockscout `/addresses/{addr}` |
| 이 계약의 거래 | 전부 50건, **2025-02-25 ~ 2025-07-03**. 그 뒤로는 없다 | `/addresses/{addr}/transactions` |
| 신청 | `requestKyc(string)`(셀렉터 `0x52aeb1ca`) 12건, 모두 한 주소(`0x80a9…1537`)가 보냈다 | 셀렉터는 RPC `web3_sha3`로 계산 |
| 승인·취소 | `approveKyc(address,uint8)` 6건, `revokeKyc` 4건 (관리자 주소 2개) | 같음 |
| `isHuman` 결과 | 위 거래에 나온 세 주소 모두 `(false, 0)` | `eth_call` 셀렉터 `0xf72c436f` |
| 다른 팀의 선례 | `KycGate` `0xA36E…Ee46`(2026-07, TEGATA Protocol): "공식 레지스트리가 없거나 대상을 다루지 않으면 데모 인증 목록으로 대체하고, 어느 방식인지 체인에 기록한다"고 소스에 적혀 있다 | `/smart-contracts/{addr}` |

## 의미
- KYC 주제는 HashKey Chain의 고유 기능이라 심사에서 유리하다. 하지만 **"실제 KYC 받은 사용자가 체인에 있다"는 주장은 할 수 없다.**
- 이미 다른 팀이 "공식 SBT + 데모 대체" 게이트를 만들었다. KYC 게이트 자체는 새롭지 않다. **KYC가 거래 결정을 어떻게 바꾸는지**를 보여 줘야 차별점이 생긴다.
