// 읽기 전용 점검: 두 풀 상태, Supra 증명 검증(eth_call), 풀·오라클 차이. 서명·전송은 하지 않는다.
// 실행: npm run read            (NFT 하나를 보려면: npm run read -- 14)
import { assertChain, createHskClient } from "./chain.ts";
import { loadEnv, POOLS } from "./config.ts";
import { readNftPosition, readPoolState, verifyPoolConfig } from "./pools.ts";
import { deviationBps } from "./price.ts";
import { fetchSupraProof, verifySupraProof } from "./supra.ts";

const env = loadEnv();
const client = createHskClient(env);
await assertChain(client);
const block = await client.getBlockNumber();
const blockTs = (await client.getBlock({ blockNumber: block })).timestamp;
console.log(`block ${block} (ts ${blockTs})`);

for (const cfg of POOLS) await verifyPoolConfig(client, cfg);
const states = await Promise.all(POOLS.map((p) => readPoolState(client, p.pool, block)));

const proof = await fetchSupraProof(POOLS.map((p) => p.supraPair), env);
const prices = await verifySupraProof(client, proof.proofBytes);

for (const s of states) {
  const cfg = POOLS.find((p) => p.pool === s.pool)!;
  const o = prices.find((x) => x.pair === cfg.supraPair);
  console.log(
    JSON.stringify(
      {
        pair: s.pair,
        pool: s.pool,
        price: s.price,
        tick: s.tick,
        liquidity: s.liquidity.toString(),
        oraclePrice: o?.price ?? null,
        oracleAgeSec: o ? Number(blockTs) - o.timestamp : null,
        deviationPct: o ? deviationBps(s.priceE18, o.priceE18) / 100 : null,
      },
      null,
      0,
    ),
  );
}

const arg = process.argv[2];
if (arg) {
  const pos = await readNftPosition(client, BigInt(arg), block);
  console.log(JSON.stringify(pos, (_, v) => (typeof v === "bigint" ? v.toString() : v)));
}
