// 주소, 체인, 외부 API 설정. 주소는 @hskswap/sdk-core(HashKey 배포)에서 가져오고,
// 개발-가이드.md 3절(11-25 확인)의 값과 다르면 시작할 때 멈춘다.
import { CHAIN_TO_ADDRESSES_MAP, WETH9 } from "@hskswap/sdk-core";
import { getAddress, type Address } from "viem";

export const CHAIN_ID = 177;

const sdk = (CHAIN_TO_ADDRESSES_MAP as Record<number, Record<string, string | undefined>>)[CHAIN_ID];
const sdkWeth9 = (WETH9 as Record<number, { address: string } | undefined>)[CHAIN_ID];
if (!sdk || !sdkWeth9) throw new Error("@hskswap/sdk-core에 체인 177 주소가 없다");

/** 개발-가이드.md 3절에 적은 값. sdk 값과 대조한다. */
const DOC = {
  factory: "0x972cA9D1662F5e029cD18327D29026532E84c742",
  npm: "0xDF0A9b833Db0E4CeEa103A4408f3B68e7FC0cad5",
  router: "0x2c16f75b95Cf1390c328aB70e2CEE7f4b80bD8F3",
  quoter: "0x603f70466fDdbE3F238220B9a74FFF419a2BbFDD",
  whsk: "0xB210D2120d57b758EE163cFfb43e73728c471Cf1",
} as const;

function fromSdk(name: string, value: string | undefined, expected: string): Address {
  if (!value || getAddress(value) !== getAddress(expected)) {
    throw new Error(`주소 불일치 ${name}: sdk=${value} 문서=${expected}`);
  }
  return getAddress(value);
}

export const ADDR = {
  factory: fromSdk("factory", sdk.v3CoreFactoryAddress, DOC.factory),
  npm: fromSdk("npm", sdk.nonfungiblePositionManagerAddress, DOC.npm),
  router: fromSdk("router", sdk.swapRouter02Address, DOC.router),
  quoter: fromSdk("quoter", sdk.quoterAddress, DOC.quoter),
  whsk: fromSdk("WHSK", sdkWeth9.address, DOC.whsk),
  // 아래는 sdk에 없다. 공식 문서 Token Contracts·Supra 네트워크 표에서 확인한 값.
  weth: getAddress("0xefd4bC9afD210517803f293ABABd701CaeeCdfd0"),
  usdt: getAddress("0xf1b50ed67a9e2cc94ad3c477779e2d4cbfff9029"),
  supraPull: getAddress("0x16f70cAD28dd621b0072B5A8a8c392970E87C3dD"),
} as const;

export interface PoolConfig {
  pool: Address;
  pair: string;
  token0: Address;
  token1: Address;
  decimals0: number;
  decimals1: number;
  fee: number;
  /** Supra 쌍 번호 */
  supraPair: number;
}

export const POOLS: readonly PoolConfig[] = [
  {
    pool: getAddress("0xb92b79ed6b370d5cfee2e14b1d0983c258304c16"),
    pair: "WETH/USDT",
    token0: ADDR.weth,
    token1: ADDR.usdt,
    decimals0: 18,
    decimals1: 6,
    fee: 3000,
    supraPair: 1, // ETH/USDT
  },
  {
    pool: getAddress("0x4ff515761864e7838b0adb8b5b2b8b7a068905dc"),
    pair: "WHSK/USDT",
    token0: ADDR.whsk,
    token1: ADDR.usdt,
    decimals0: 18,
    decimals1: 6,
    fee: 3000,
    supraPair: 517, // HSK/USDT
  },
];

export function poolConfig(pool: Address): PoolConfig {
  const p = POOLS.find((x) => x.pool === getAddress(pool));
  if (!p) throw new Error(`지원하지 않는 풀: ${pool}`);
  return p;
}

export interface AgentEnv {
  rpcUrl: string;
  /** HSK RPC는 User-Agent가 없으면 403을 준다(11-25 확인). */
  userAgent: string;
  supraUrl: string;
  supraTimeoutMs: number;
}

export function loadEnv(env: NodeJS.ProcessEnv = process.env): AgentEnv {
  return {
    rpcUrl: env.HSK_RPC ?? "https://mainnet.hsk.xyz",
    userAgent: env.HSK_USER_AGENT ?? "lp-guard-agent/0.1",
    supraUrl: env.SUPRA_PROOF_URL ?? "https://rpc-mainnet-dora-2.supra.com/get_proof",
    supraTimeoutMs: Number(env.SUPRA_TIMEOUT_MS ?? 10_000),
  };
}
