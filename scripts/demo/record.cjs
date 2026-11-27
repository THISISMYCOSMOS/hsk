// Capture an edited, three-minute walkthrough from a running disposable fork.
const { createRequire } = require("node:module");
const { resolve, join } = require("node:path");
const {
  mkdtempSync,
  writeFileSync,
  mkdirSync,
  existsSync,
} = require("node:fs");
const { tmpdir } = require("node:os");
const { execFileSync } = require("node:child_process");
const root = resolve(__dirname, "../.."),
  local = createRequire(join(root, "frontend/package.json"));
const { chromium } = local("playwright"),
  { expect } = local("@playwright/test");
const { createPublicClient, http, parseAbi, getAddress } = local("viem");
const base = "http://127.0.0.1:5189";
const rpc = "http://127.0.0.1:8754";
const client = createPublicClient({ transport: http(rpc) });
const tokenABI = parseAbi([
  "function balanceOf(address) view returns (uint256)",
]);
async function json(path) {
  const response = await fetch(base + "/engine" + path);
  if (!response.ok) throw Error("API unavailable " + response.status);
  return response.json();
}
async function main() {
  const manifest = await json("/integration/fork");
  if ((await client.getChainId()) !== 31337 || manifest.chainId !== 31337)
    throw Error("isolated Anvil fork required");
  const [seller, buyer] = manifest.wallets;
  const [w, u] = [
    "0xb210d2120d57b758ee163cffb43e73728c471cf1",
    "0xf1b50ed67a9e2cc94ad3c477779e2d4cbfff9029",
  ];
  const balance = (token, actor) =>
    client.readContract({
      address: token,
      abi: tokenABI,
      functionName: "balanceOf",
      args: [actor],
    });
  const amounts = () =>
    Promise.all([
      balance(w, seller),
      balance(u, seller),
      balance(w, buyer),
      balance(u, buyer),
    ]);
  const before = await amounts();
  const dir = mkdtempSync(join(tmpdir(), "hsk-film-"));
  const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  const browser = await chromium.launch({
    executablePath:
      process.env.CHROME_BIN || (existsSync(chrome) ? chrome : undefined),
  });
  const scenes = [];
  try {
    async function scene(page, seconds, caption) {
      await page.evaluate((text) => {
        const b = document.createElement("div");
        b.id = "film-caption";
        b.textContent = text;
        b.style.cssText =
          "position:fixed;bottom:0;left:0;right:0;z-index:9999;padding:15px 34px;background:#091521f5;color:white;font:600 18px/1.45 -apple-system,sans-serif;border-top:2px solid #6be1c5;pointer-events:none";
        document.body.append(b);
      }, caption);
      const filename = join(dir, String(scenes.length) + ".png");
      await page.screenshot({ path: filename });
      await page.locator("#film-caption").evaluate((e) => e.remove());
      scenes.push({ filename, seconds });
    }
    async function makePage(actor) {
      const page = await browser.newPage({
        viewport: { width: 1440, height: 960 },
        deviceScaleFactor: 1,
      });
      await page.exposeFunction(
        "localForkRPC",
        async ({ method, params = [] }) => {
          if (method === "eth_accounts" || method === "eth_requestAccounts")
            return [actor];
          if (method === "eth_sendTransaction") {
            const tx = params[0];
            if (
              tx.from.toLowerCase() !== actor.toLowerCase() ||
              ![w, u].includes(tx.to.toLowerCase()) ||
              tx.data.slice(0, 10) !== "0x095ea7b3" ||
              getAddress("0x" + tx.data.slice(34, 74)) !==
                getAddress(manifest.contract)
            )
              throw Error("only fixture token approvals for this contract");
          } else if (method === "eth_signTypedData_v4") {
            const t =
              typeof params[1] === "string" ? JSON.parse(params[1]) : params[1];
            if (
              params[0].toLowerCase() !== actor.toLowerCase() ||
              Number(t.domain.chainId) !== 31337 ||
              !["SandboxOrder", "Order", "Cancel"].includes(t.primaryType)
            )
              throw Error("bad local signature");
          } else if (
            ![
              "eth_chainId",
              "eth_call",
              "eth_getCode",
              "eth_getBlockByNumber",
              "eth_getTransactionReceipt",
              "eth_blockNumber",
              "eth_getBalance",
              "eth_getTransactionByHash",
              "eth_estimateGas",
              "eth_gasPrice",
              "eth_maxPriorityFeePerGas",
              "eth_feeHistory",
            ].includes(method)
          )
            throw Error("unsupported local method: " + method);
          if ((await client.getChainId()) !== 31337)
            throw Error("fork disconnected");
          return client.request({ method, params });
        },
      );
      await page.addInitScript(() => {
        window.ethereum = {
          request: (r) => window.localForkRPC(r),
          on: () => {},
          removeListener: () => {},
        };
      });
      await page.goto(base + "/#Demo%20Mode");
      await page.getByRole("button", { name: "지갑 연결" }).click();
      await expect(page.locator(".wallet")).toContainText("31337");
      return page;
    }
    const a = await makePage(seller),
      b = await makePage(buyer);
    await a.getByRole("link", { name: "Analytics & Verification" }).click();
    await expect(
      a.getByRole("heading", { name: "WHSK / USDT · 30일 거래대금" }),
    ).toBeVisible();
    await scene(
      a,
      16,
      "HSK Smart Execution  |  HSKSwap의 WHSK/USDT 단일 풀 · 실제 30일 관측과 가상 주문 시나리오",
    );
    await a.getByRole("link", { name: "Demo Mode" }).click();
    async function order(page, side, size, price, hybrid, record) {
      const form = page
        .locator("section")
        .filter({ has: page.getByRole("heading", { name: "로컬 서명 주문" }) });
      await form.getByLabel("로컬 주문 방향").selectOption(side);
      await form.getByLabel("WHSK 수량", { exact: true }).fill(size);
      await form.getByLabel("한도 가격").fill(price);
      await form
        .getByLabel("주문 시점")
        .selectOption(hybrid ? "IMMEDIATE" : "LIMIT");
      await form.getByLabel("잔량 DEX 허용").setChecked(hybrid);
      await form.getByLabel("부분 체결 허용").setChecked(false);
      await form.getByRole("button", { name: "서명 조건 검토" }).click();
      await expect(form.getByText("정산 계약 ", { exact: false })).toBeVisible({
        timeout: 20000,
      });
      if (record) await scene(page, 14, record);
      const approval = form.getByRole("button", { name: "제한된 토큰 승인" });
      if (await approval.count()) await approval.click();
      const submit = form.getByRole("button", { name: "EIP-712 서명 및 등록" });
      await expect(submit).toBeEnabled({ timeout: 30000 });
      if (hybrid)
        await scene(
          page,
          13,
          "체인 31337의 한정 승인 · 주문 정책과 Settlement v1 주문을 각각 검토하고 서명",
        );
      await submit.click();
      await expect(form.getByRole("status")).toContainText("등록됨", {
        timeout: 45000,
      });
      return (await form.getByRole("status").textContent()).match(
        /0x[0-9a-fA-F]{64}/,
      )[0];
    }
    const buyerId = await order(
      b,
      "BUY",
      "600",
      "0.084",
      false,
      "매수자 B · 600 WHSK EXACT_OUT · 테스트 지갑이 EIP-712 요청에 서명",
    );
    await b.getByRole("link", { name: "Orderbook" }).click();
    await expect(
      b.getByRole("cell", { name: "OPEN", exact: true }).first(),
    ).toBeVisible();
    await scene(
      b,
      12,
      "FastAPI에 저장한 사전 주문 · 원래 수량과 현재 잔량, 만료와 상태 확인",
    );
    const sellerId = await order(
      a,
      "SELL",
      "1000",
      "0.079",
      true,
      "매도자 A · 1,000 WHSK EXACT_IN · 직접 매칭 후 잔량 DEX를 명시적으로 허용",
    );
    await a.getByRole("link", { name: "Agent Activity" }).click();
    await expect(
      a.getByRole("heading", { name: "RECONCILIATION" }).first(),
    ).toBeVisible({ timeout: 50000 });
    await scene(
      a,
      16,
      "서버 이벤트 스트림 · 후보 생성, 사용자별 경제성, 시뮬레이션, 정산 및 DB 반영",
    );
    const executions = await json("/executions");
    const e = executions.find(
      (e) =>
        e.status === "FORK_CONFIRMED" &&
        e.receipt?.participants.some((p) => p.orderId === sellerId),
    );
    if (!e || !e.receipt.participants.some((p) => p.orderId === buyerId))
      throw Error("paired fork receipt missing");
    const comparison = (await json("/executions/" + e.id + "/comparison"))
      .comparison;
    if (
      comparison.selected.kind !== "HYBRID_MATCH" ||
      comparison.selected.dexFixed !== String(400n * 10n ** 18n)
    )
      throw Error("hybrid route mismatch");
    const chainReceipt = await client.getTransactionReceipt({
      hash: e.receipt.transactionHash,
    });
    const after = await amounts();
    if (
      chainReceipt.status !== "success" ||
      String(chainReceipt.gasUsed) !== e.receipt.gasUnits ||
      chainReceipt.to.toLowerCase() !== manifest.contract.toLowerCase() ||
      before[0] - after[0] !== 1000n * 10n ** 18n ||
      after[2] - before[2] !== 600n * 10n ** 18n
    )
      throw Error("on-chain reconciliation failed");
    await a.getByRole("link", { name: "Execution History" }).click();
    await expect(
      a.getByText(e.receipt.transactionHash, { exact: false }).first(),
    ).toBeVisible();
    await scene(
      a,
      20,
      "포크 영수증 · 직접 600 WHSK와 DEX 400 WHSK가 한 거래에서 정산됨 · 원장과 ERC-20 잔액 대조",
    );
    await a
      .getByRole("button", { name: "사용자별 비용 및 경로" })
      .first()
      .click();
    const chosen = a
      .locator("details")
      .filter({ has: a.locator("summary").filter({ hasText: "HYBRID_MATCH" }) })
      .first();
    await chosen.locator("summary").click();
    await chosen.scrollIntoViewIfNeeded();
    await scene(
      a,
      17,
      "동일 수량 기준 DEX 반사실적 견적과 사용자별 비용 상한 · 순절감액은 가정에 따라 달라짐",
    );
    const filter = a.getByLabel("정산 검증 경로");
    await filter.selectOption("no_trade");
    await filter.scrollIntoViewIfNeeded();
    await scene(
      a,
      15,
      "계약 검증 재생 · 경제성 미달 주문은 토큰 이동 0 · 포크에서 사용한 검증 가스는 별도",
    );
    await filter.selectOption("fallback");
    await scene(
      a,
      15,
      "계약 검증 재생 · 사용자 동의 범위 안에서 DEX fallback · 미측정 L1 비용과 실현 절감액은 공란",
    );
    await filter.selectOption("multi");
    await scene(
      a,
      14,
      "계약 검증 재생 · 복수 상대 주문별 WHSK와 USDT 변화량 · 포크 거래 해시",
    );
    await a.getByRole("link", { name: "Analytics & Verification" }).click();
    await scene(
      a,
      14,
      "HSK 단일 풀과 단일 집행 에이전트 · 복수 solver 성능 비교와 운영자 월간 이익은 미측정",
    );
    const evidence = {
      source: "FORK_SIMULATION",
      fixture: "ephemeral local test wallets",
      contract: manifest.contract,
      operator: manifest.operator,
      anchor: manifest.anchor,
      orderIds: [sellerId, buyerId],
      route: comparison.selected.kind,
      gasUsed: e.receipt.gasUnits,
      block: String(chainReceipt.blockNumber),
      blockHash: chainReceipt.blockHash,
      txHash: e.receipt.transactionHash,
      dexWHSK: comparison.selected.dexFixed,
      participants: e.receipt.participants,
      balancesRaw: {
        before: before.map(String),
        after: after.map(String),
        fields: ["sellerWHSK", "sellerUSDT", "buyerWHSK", "buyerUSDT"],
      },
      realizedSavings: null,
    };
    const output = join(root, "docs/agents/agent-d");
    writeFileSync(
      join(output, "browser-fork.json"),
      JSON.stringify(evidence, null, 2) + "\n",
    );
    const concat =
      scenes
        .map((s) => "file '" + s.filename + "'\nduration " + s.seconds)
        .join("\n") +
      "\nfile '" +
      scenes.at(-1).filename +
      "'\n";
    writeFileSync(join(dir, "shots.txt"), concat);
    const length = scenes.reduce((n, s) => n + s.seconds, 0);
    execFileSync("ffmpeg", [
      "-hide_banner",
      "-loglevel",
      "error",
      "-y",
      "-f",
      "concat",
      "-safe",
      "0",
      "-i",
      join(dir, "shots.txt"),
      "-vf",
      "fps=12,format=yuv420p",
      "-t",
      String(length),
      "-c:v",
      "libx264",
      "-preset",
      "fast",
      "-crf",
      "21",
      "-movflags",
      "+faststart",
      join(output, "fork-demo.mp4"),
    ]);
    console.log(
      "Browser → two signatures → Agent B → C Settlement → HSKSwap fork → reconciled UI; video seconds",
      length,
    );
  } finally {
    await browser.close();
  }
}
main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
