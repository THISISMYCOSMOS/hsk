// Supra Pull 오라클 증명 받기. 실행 직전에만 부른다(구현-계획.md 5절). 실패하면 호출한 쪽이 보류한다.
import { getAddress, isHex, type Hex, type PublicClient } from "viem";
import { supraPullAbi } from "./abis.ts";
import { ADDR, type AgentEnv } from "./config.ts";
import { fromFixed, scaleToE18 } from "./price.ts";

export interface SupraProof {
  pairIndexes: number[];
  proofBytes: Hex;
  fetchedAt: number; // ms
}

export class SupraError extends Error {
  constructor(
    message: string,
    readonly kind: "http" | "timeout" | "format" | "network",
  ) {
    super(message);
    this.name = "SupraError";
  }
}

/** POST /get_proof {pair_indexes, chain_type:"evm"} → proof_bytes(16진수, 0x 없음) */
export async function fetchSupraProof(
  pairIndexes: number[],
  env: Pick<AgentEnv, "supraUrl" | "supraTimeoutMs">,
  fetchImpl: typeof fetch = fetch,
): Promise<SupraProof> {
  if (pairIndexes.length === 0) throw new SupraError("pair_indexes가 비었다", "format");
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), env.supraTimeoutMs);
  let res: Response;
  try {
    res = await fetchImpl(env.supraUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ pair_indexes: pairIndexes, chain_type: "evm" }),
      signal: ctrl.signal,
    });
  } catch (e) {
    if (ctrl.signal.aborted) throw new SupraError(`Supra 응답 없음(${env.supraTimeoutMs}ms)`, "timeout");
    throw new SupraError(`Supra 요청 실패: ${(e as Error).message}`, "network");
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) throw new SupraError(`Supra HTTP ${res.status}`, "http");

  let body: unknown;
  try {
    body = await res.json();
  } catch {
    throw new SupraError("Supra 응답이 JSON이 아니다", "format");
  }
  const raw = (body as { proof_bytes?: unknown }).proof_bytes;
  if (typeof raw !== "string" || raw.length === 0) throw new SupraError("proof_bytes 없음", "format");
  const proofBytes = (raw.startsWith("0x") ? raw : `0x${raw}`) as Hex;
  if (!isHex(proofBytes) || proofBytes.length % 2 !== 0) throw new SupraError("proof_bytes가 16진수가 아니다", "format");
  return { pairIndexes: [...pairIndexes], proofBytes, fetchedAt: Date.now() };
}

export interface SupraPrice {
  pair: number;
  priceE18: bigint;
  price: number;
  decimals: number;
  /** 초 단위(Supra는 밀리초로 준다) */
  timestamp: number;
  round: bigint;
}

/**
 * 증명을 Supra Pull 계약의 verifyOracleProofV2로 eth_call 해서 검증·해석한다.
 * 상태를 바꾸지 않는 모의 호출이다. 금고가 실행 때 하는 검증과 같은 함수다.
 */
export async function verifySupraProof(client: PublicClient, proof: Hex, blockNumber?: bigint): Promise<SupraPrice[]> {
  const { result } = await client.simulateContract({
    address: getAddress(ADDR.supraPull),
    abi: supraPullAbi,
    functionName: "verifyOracleProofV2",
    args: [proof],
    ...(blockNumber !== undefined ? { blockNumber } : {}),
  });
  const out: SupraPrice[] = [];
  for (let i = 0; i < result.pairs.length; i++) {
    const decimals = Number(result.decimal[i]);
    const priceE18 = scaleToE18(result.prices[i]!, decimals);
    out.push({
      pair: Number(result.pairs[i]),
      priceE18,
      price: fromFixed(priceE18, 18),
      decimals,
      timestamp: Math.floor(Number(result.timestamp[i]) / 1000),
      round: result.round[i]!,
    });
  }
  return out;
}
