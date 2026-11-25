import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer, type IncomingHttpHeaders } from "node:http";
import type { AddressInfo } from "node:net";
import { createHskClient } from "../../src/chain.ts";

// 로컬 RPC 흉내: User-Agent가 없으면 403(HSK RPC와 같게), 처음 몇 번은 429.
async function withServer(fail429: number, fn: (url: string, seen: IncomingHttpHeaders[]) => Promise<void>) {
  const seen: IncomingHttpHeaders[] = [];
  let left = fail429;
  const srv = createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      seen.push(req.headers);
      if (!req.headers["user-agent"] || req.headers["user-agent"] === "node") {
        res.writeHead(403).end("forbidden");
        return;
      }
      if (left-- > 0) {
        res.writeHead(429).end("slow down");
        return;
      }
      const { id } = JSON.parse(body);
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ jsonrpc: "2.0", id, result: "0xb1" }));
    });
  });
  await new Promise<void>((r) => srv.listen(0, "127.0.0.1", r));
  const url = `http://127.0.0.1:${(srv.address() as AddressInfo).port}`;
  try {
    await fn(url, seen);
  } finally {
    srv.close();
  }
}

test("User-Agent 헤더를 보낸다", async () => {
  await withServer(0, async (url, seen) => {
    const c = createHskClient({ rpcUrl: url, userAgent: "lp-guard-test/1" }, { retryDelayMs: 1 });
    assert.equal(await c.getChainId(), 177);
    assert.equal(seen[0]?.["user-agent"], "lp-guard-test/1");
  });
});

test("429는 재시도해서 성공한다", async () => {
  await withServer(2, async (url, seen) => {
    const c = createHskClient({ rpcUrl: url, userAgent: "lp-guard-test/1" }, { retryDelayMs: 1, retryCount: 4 });
    assert.equal(await c.getChainId(), 177);
    assert.equal(seen.length, 3);
  });
});

test("429가 재시도 횟수를 넘으면 실패한다", async () => {
  await withServer(10, async (url, seen) => {
    const c = createHskClient({ rpcUrl: url, userAgent: "lp-guard-test/1" }, { retryDelayMs: 1, retryCount: 2 });
    await assert.rejects(c.getChainId());
    assert.equal(seen.length, 3);
  });
});
