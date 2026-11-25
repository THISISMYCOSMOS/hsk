import { test } from "node:test";
import assert from "node:assert/strict";
import { fetchSupraProof, SupraError } from "../../src/supra.ts";

const env = { supraUrl: "https://example.invalid/get_proof", supraTimeoutMs: 200 };

function fakeFetch(handler: (body: unknown) => Response | Promise<Response>): typeof fetch {
  return (async (_url: string | URL | Request, init?: RequestInit) => {
    return handler(JSON.parse(String(init?.body)));
  }) as typeof fetch;
}

test("요청 본문 형식과 0x 붙이기", async () => {
  let seen: unknown;
  const proof = await fetchSupraProof(
    [517, 1],
    env,
    fakeFetch((b) => {
      seen = b;
      return Response.json({ pair_indexes: [517, 1], proof_bytes: "00ab" });
    }),
  );
  assert.deepEqual(seen, { pair_indexes: [517, 1], chain_type: "evm" });
  assert.equal(proof.proofBytes, "0x00ab");
  assert.deepEqual(proof.pairIndexes, [517, 1]);
});

test("HTTP 오류·형식 오류·빈 목록", async () => {
  await assert.rejects(
    fetchSupraProof([1], env, fakeFetch(() => new Response("x", { status: 500 }))),
    (e: SupraError) => e.kind === "http",
  );
  await assert.rejects(
    fetchSupraProof([1], env, fakeFetch(() => Response.json({}))),
    (e: SupraError) => e.kind === "format",
  );
  await assert.rejects(
    fetchSupraProof([1], env, fakeFetch(() => Response.json({ proof_bytes: "zz" }))),
    (e: SupraError) => e.kind === "format",
  );
  await assert.rejects(
    fetchSupraProof([1], env, fakeFetch(() => new Response("not json"))),
    (e: SupraError) => e.kind === "format",
  );
  await assert.rejects(fetchSupraProof([], env), (e: SupraError) => e.kind === "format");
});

test("시간 초과", async () => {
  const slow = ((_u: unknown, init?: RequestInit) =>
    new Promise<Response>((_, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new Error("aborted")));
    })) as typeof fetch;
  await assert.rejects(fetchSupraProof([1], env, slow), (e: SupraError) => e.kind === "timeout");
});
