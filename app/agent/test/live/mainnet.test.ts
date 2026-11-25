// HSK 메인넷 읽기 시험. 네트워크가 필요하다. 서명·전송은 하지 않는다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { assertChain, createHskClient } from "../../src/chain.ts";
import { loadEnv, POOLS } from "../../src/config.ts";
import { readNftPosition, readPoolState, verifyPoolConfig } from "../../src/pools.ts";
import { deviationBps } from "../../src/price.ts";
import { fetchSupraProof, verifySupraProof } from "../../src/supra.ts";

const env = loadEnv();
const client = createHskClient(env);

test("체인 177, 풀 설정이 체인과 같다", async () => {
  await assertChain(client);
  for (const cfg of POOLS) await verifyPoolConfig(client, cfg);
});

test("풀 상태 읽기(같은 블록 고정)", async () => {
  const block = await client.getBlockNumber();
  for (const cfg of POOLS) {
    const s = await readPoolState(client, cfg.pool, block);
    assert.equal(s.block, block);
    assert.ok(s.sqrtPriceX96 > 0n);
    assert.ok(s.liquidity > 0n, `${cfg.pair} liquidity`);
    assert.ok(s.price > 0);
    // tick과 가격이 서로 맞는지: 1.0001^tick × 10^(18−6)
    const fromTick = 1.0001 ** s.tick * 1e12;
    assert.ok(Math.abs(fromTick - s.price) / s.price < 2e-4, `${cfg.pair} tick/price`);
  }
});

test("과거 블록 읽기", async () => {
  const s = await readPoolState(client, POOLS[1]!.pool, 30_620_000n);
  assert.equal(s.block, 30_620_000n);
  assert.ok(s.price > 0);
});

test("기존 NFT #14 읽기(WHSK/USDT 범위 LP)", async () => {
  const p = await readNftPosition(client, 14n);
  assert.equal(p.supportedPool, POOLS[1]!.pool);
  assert.ok(p.tickLower < p.tickUpper);
});

test("Supra 증명 받기 → verifyOracleProofV2 eth_call → 풀과 비교", async () => {
  const pairs = POOLS.map((p) => p.supraPair);
  const proof = await fetchSupraProof(pairs, env);
  const prices = await verifySupraProof(client, proof.proofBytes);
  const now = Math.floor(Date.now() / 1000);
  for (const cfg of POOLS) {
    const o = prices.find((x) => x.pair === cfg.supraPair);
    assert.ok(o, `pair ${cfg.supraPair} in proof`);
    assert.ok(o.price > 0);
    assert.ok(Math.abs(now - o.timestamp) < 600, `oracle age ${now - o.timestamp}s`);
    const s = await readPoolState(client, cfg.pool);
    const dev = deviationBps(s.priceE18, o.priceE18);
    console.log(`${cfg.pair} pool=${s.price} oracle=${o.price} dev=${dev}bps ts=${o.timestamp}`);
    // 정상성 확인만 한다(10% 안). 실제 거부 기준(기본 3%)은 계약이 강제한다.
    assert.ok(Math.abs(dev) < 1000, `${cfg.pair} deviation ${dev}bps`);
  }
});
