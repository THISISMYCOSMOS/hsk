// RPC 클라이언트: 체인 177 정의, User-Agent 헤더, 429·5xx 재시도(viem http 기본 동작: 408/413/429/5xx).
import { createPublicClient, defineChain, http, type PublicClient, type Transport, type Chain } from "viem";
import { CHAIN_ID, type AgentEnv } from "./config.ts";

export function hskChain(rpcUrl: string): Chain {
  return defineChain({
    id: CHAIN_ID,
    name: "HashKey Chain",
    nativeCurrency: { name: "HSK", symbol: "HSK", decimals: 18 },
    rpcUrls: { default: { http: [rpcUrl] } },
    blockExplorers: { default: { name: "Blockscout", url: "https://hsk.blockscout.com" } },
  });
}

export interface ClientOptions {
  retryCount?: number;
  retryDelayMs?: number;
  timeoutMs?: number;
}

export function hskTransport(env: Pick<AgentEnv, "rpcUrl" | "userAgent">, opts: ClientOptions = {}): Transport {
  return http(env.rpcUrl, {
    fetchOptions: { headers: { "User-Agent": env.userAgent } },
    retryCount: opts.retryCount ?? 4,
    retryDelay: opts.retryDelayMs ?? 500, // viem은 지수 백오프(delay × 2^n)를 쓴다
    timeout: opts.timeoutMs ?? 15_000,
  });
}

export function createHskClient(
  env: Pick<AgentEnv, "rpcUrl" | "userAgent">,
  opts: ClientOptions = {},
): PublicClient {
  return createPublicClient({ chain: hskChain(env.rpcUrl), transport: hskTransport(env, opts) }) as PublicClient;
}

/** 연결 확인: 체인 번호가 177인지 본다. */
export async function assertChain(client: PublicClient): Promise<void> {
  const id = await client.getChainId();
  if (id !== CHAIN_ID) throw new Error(`체인 번호가 ${id}다. 177이어야 한다.`);
}
