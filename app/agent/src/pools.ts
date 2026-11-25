// 풀 상태와 NFT 포지션 읽기. 한 번의 읽기는 같은 블록에 고정해 값이 섞이지 않게 한다.
import type { Address, PublicClient } from "viem";
import { getAddress } from "viem";
import { npmAbi, poolAbi, factoryAbi } from "./abis.ts";
import { ADDR, POOLS, poolConfig, type PoolConfig } from "./config.ts";
import { fromFixed, sqrtPriceX96ToPriceE18 } from "./price.ts";

export interface PoolState {
  pool: Address;
  pair: string;
  block: bigint;
  sqrtPriceX96: bigint;
  tick: number;
  liquidity: bigint;
  /** token0 1개당 USDT, 10^18 배 */
  priceE18: bigint;
  price: number;
}

export async function readPoolState(client: PublicClient, pool: Address, blockNumber?: bigint): Promise<PoolState> {
  const cfg: PoolConfig = poolConfig(pool);
  const block = blockNumber ?? (await client.getBlockNumber());
  const [slot0, liquidity] = await Promise.all([
    client.readContract({ address: cfg.pool, abi: poolAbi, functionName: "slot0", blockNumber: block }),
    client.readContract({ address: cfg.pool, abi: poolAbi, functionName: "liquidity", blockNumber: block }),
  ]);
  const [sqrtPriceX96, tick] = slot0;
  const priceE18 = sqrtPriceX96ToPriceE18(sqrtPriceX96, cfg.decimals0, cfg.decimals1);
  return {
    pool: cfg.pool,
    pair: cfg.pair,
    block,
    sqrtPriceX96,
    tick,
    liquidity,
    priceE18,
    price: fromFixed(priceE18, 18),
  };
}

/** 풀의 token0·token1·fee가 설정과 같은지 체인에서 확인한다. */
export async function verifyPoolConfig(client: PublicClient, cfg: PoolConfig): Promise<void> {
  const [t0, t1, fee, fromFactory] = await Promise.all([
    client.readContract({ address: cfg.pool, abi: poolAbi, functionName: "token0" }),
    client.readContract({ address: cfg.pool, abi: poolAbi, functionName: "token1" }),
    client.readContract({ address: cfg.pool, abi: poolAbi, functionName: "fee" }),
    client.readContract({
      address: ADDR.factory,
      abi: factoryAbi,
      functionName: "getPool",
      args: [cfg.token0, cfg.token1, cfg.fee],
    }),
  ]);
  const bad: string[] = [];
  if (getAddress(t0) !== cfg.token0) bad.push(`token0 ${t0}`);
  if (getAddress(t1) !== cfg.token1) bad.push(`token1 ${t1}`);
  if (fee !== cfg.fee) bad.push(`fee ${fee}`);
  if (getAddress(fromFactory) !== cfg.pool) bad.push(`factory.getPool ${fromFactory}`);
  if (bad.length) throw new Error(`${cfg.pair} 설정 불일치: ${bad.join(", ")}`);
}

export interface NftPosition {
  tokenId: bigint;
  owner: Address;
  token0: Address;
  token1: Address;
  fee: number;
  tickLower: number;
  tickUpper: number;
  liquidity: bigint;
  tokensOwed0: bigint;
  tokensOwed1: bigint;
  /** 등록된 두 풀 중 하나면 그 주소, 아니면 null */
  supportedPool: Address | null;
}

export async function readNftPosition(client: PublicClient, tokenId: bigint, blockNumber?: bigint): Promise<NftPosition> {
  const block = blockNumber ?? (await client.getBlockNumber());
  const [owner, p] = await Promise.all([
    client.readContract({ address: ADDR.npm, abi: npmAbi, functionName: "ownerOf", args: [tokenId], blockNumber: block }),
    client.readContract({ address: ADDR.npm, abi: npmAbi, functionName: "positions", args: [tokenId], blockNumber: block }),
  ]);
  const [, , token0, token1, fee, tickLower, tickUpper, liquidity, , , tokensOwed0, tokensOwed1] = p;
  const cfg = POOLS.find(
    (c) => c.token0 === getAddress(token0) && c.token1 === getAddress(token1) && c.fee === fee,
  );
  const supportedPool = cfg?.pool ?? null;
  return {
    tokenId,
    owner: getAddress(owner),
    token0: getAddress(token0),
    token1: getAddress(token1),
    fee,
    tickLower,
    tickUpper,
    liquidity,
    tokensOwed0,
    tokensOwed1,
    supportedPool,
  };
}

/** 지갑이 가진 HSKSwap NFT 번호 목록 */
export async function listWalletTokenIds(client: PublicClient, owner: Address): Promise<bigint[]> {
  const n = await client.readContract({ address: ADDR.npm, abi: npmAbi, functionName: "balanceOf", args: [owner] });
  const ids: bigint[] = [];
  for (let i = 0n; i < n; i++) {
    ids.push(
      await client.readContract({ address: ADDR.npm, abi: npmAbi, functionName: "tokenOfOwnerByIndex", args: [owner, i] }),
    );
  }
  return ids;
}
