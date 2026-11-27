const { createRequire } = require("node:module");
const { resolve } = require("node:path");
const fromFrontend = createRequire(
  resolve(__dirname, "../../frontend/package.json"),
);
const { test, expect } = fromFrontend("@playwright/test");
const { privateKeyToAccount, generatePrivateKey } =
  fromFrontend("viem/accounts");
const { hashTypedData } = fromFrontend("viem");
const localAccount = () => privateKeyToAccount(generatePrivateKey());

async function wallet(page, user) {
  // In-memory test signer accepts only sandbox typed data. No transaction RPC.
  await page.exposeFunction("signFixture", async (serialized) => {
    const t = JSON.parse(serialized);
    if (
      t.domain.chainId !== 31337 ||
      t.domain.name !== "HSK Smart Execution Sandbox"
    )
      throw Error("unexpected domain");
    return user.signTypedData(t);
  });
  await page.addInitScript(
    ({ address }) => {
      const handlers = {};
      window.fixtureChain = "0x7a69";
      window.changeChain = (id) => {
        window.fixtureChain = id;
        handlers.chainChanged?.();
      };
      window.ethereum = {
        on: (name, fn) => {
          handlers[name] = fn;
        },
        removeListener: (name) => {
          delete handlers[name];
        },
        request: async ({ method, params }) => {
          if (method === "eth_accounts" || method === "eth_requestAccounts")
            return [address];
          if (method === "eth_chainId") return window.fixtureChain;
          if (method === "eth_signTypedData_v4")
            return window.signFixture(params[1]);
          throw Error("Unexpected method " + method);
        },
      };
    },
    { address: user.address },
  );
}
async function register(request, who, overrides = {}) {
  const sell = overrides.kind !== "EXACT_OUT";
  const whsk = "0xb210d2120d57b758ee163cffb43e73728c471cf1",
    usdt = "0xf1b50ed67a9e2cc94ad3c477779e2d4cbfff9029";
  const order = {
    maker: who.address,
    tokenIn: sell ? whsk : usdt,
    tokenOut: sell ? usdt : whsk,
    kind: "EXACT_IN",
    fixedAmount: (1000n * 10n ** 18n).toString(),
    limitAmount: sell ? "79000000" : "83000000",
    nonce: crypto.getRandomValues(new Uint32Array(1))[0].toString(),
    expiry: String(Math.floor(Date.now() / 1000) + 300),
    timing: "LIMIT",
    allowPartial: true,
    allowDex: false,
    allowFallback: false,
    priority: "SAVINGS",
    maxCost: "20000",
    minSaving: "1000",
    ...overrides,
  };
  const typed = await (
    await request.post("/engine/orders/typed-data", { data: order })
  ).json();
  const body = { order, signature: await who.signTypedData(typed) };
  const post = () => request.post("/engine/orders", { data: body });
  const res = await post();
  expect(res.ok(), await res.text()).toBeTruthy();
  const view = await res.json();
  expect(view.orderId).toBe(hashTypedData(typed));
  return { view, post };
}
test("wallet → reviewed typed data → database → own off-chain cancellation", async ({
  page,
  request,
}) => {
  const user = localAccount();
  await wallet(page, user);
  await page.goto("/#Demo%20Mode");
  await page.getByRole("button", { name: "지갑 연결" }).click();
  await page
    .getByLabel("자연어 주문 초안")
    .fill("WHSK 77개를 0.089 USDT 이상에 팔고 싶어.");
  await page.getByRole("button", { name: "조건 추출" }).click();
  await page.getByRole("button", { name: "인식된 조건 적용" }).click();
  await expect(page.getByLabel("WHSK 수량", { exact: true })).toHaveValue("77");
  await page.getByRole("button", { name: "서명 조건 검토" }).click();
  await page.getByRole("button", { name: "EIP-712 서명 및 등록" }).click();
  await expect(page.getByRole("status")).toContainText("등록됨");
  await page.getByRole("link", { name: "Orderbook" }).click();
  await expect(
    page.getByRole("cell", { name: "OPEN", exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "오프체인 취소" }).click();
  await expect(page.getByRole("cell", { name: "CANCELLED" })).toBeVisible();
  const all = await (await request.get("/engine/orders")).json();
  expect(all.find((o) => o.order.maker === user.address).status).toBe(
    "CANCELLED",
  );
  expect(JSON.stringify(all)).not.toContain("signature");
});
test("chain change invalidates signature review", async ({ page }) => {
  await wallet(page, localAccount());
  await page.goto("/#Demo%20Mode");
  await page.getByRole("button", { name: "지갑 연결" }).click();
  await page.getByRole("button", { name: "서명 조건 검토" }).click();
  await expect(
    page.getByRole("button", { name: "EIP-712 서명 및 등록" }),
  ).toBeVisible();
  await page.evaluate(() => window.changeChain("0x1"));
  await expect(
    page.getByRole("button", { name: "EIP-712 서명 및 등록" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "서명 조건 검토" }).click();
  await expect(page.getByRole("alert")).toContainText("31337");
});
for (const [route, makers] of [
  ["DIRECT_MATCH", [1000]],
  ["HYBRID_MATCH", [600]],
  ["MULTI_ORDER_MATCH", [400, 600]],
]) {
  test(
    "event worker and reconciled mock receipt · " + route,
    async ({ request, page }) => {
      for (const qty of makers) {
        await register(request, localAccount(), {
          kind: "EXACT_OUT",
          fixedAmount: (BigInt(qty) * 10n ** 18n).toString(),
          limitAmount: String(qty * 83000),
          allowPartial: false,
        });
      }
      const taker = await register(request, localAccount(), {
        timing: "IMMEDIATE",
        allowDex: true,
        allowPartial: false,
      });
      await expect
        .poll(
          async () =>
            (
              await (
                await request.get("/engine/orders/" + taker.view.orderId)
              ).json()
            ).status,
        )
        .toBe("FILLED");
      const receipts = await (await request.get("/engine/executions")).json();
      const match = receipts.find((r) =>
        r.receipt.participants.some((p) => p.orderId === taker.view.orderId),
      );
      expect(match.receipt.transactionHash).toBeNull();
      const plan = await (
        await request.get("/engine/executions/" + match.id + "/comparison")
      ).json();
      expect(plan.comparison.selected.kind).toBe(route);
      expect(plan.comparison.selected.savings).toHaveLength(makers.length + 1);
      expect(plan.comparison.selected.dexFixed).toBe(
        route === "HYBRID_MATCH" ? String(400n * 10n ** 18n) : "0",
      );
      await page.goto("/#Execution%20History");
      await expect(
        page.getByText("#" + match.id + " · MOCK_CONFIRMED", { exact: true }),
      ).toBeVisible();
      await page.goto("/#Agent%20Activity");
      await expect(
        page.getByRole("heading", { name: "RECONCILIATION" }).first(),
      ).toBeVisible();
    },
  );
}
test("uneconomic immediate order and idempotent duplicate create no execution", async ({
  request,
}) => {
  const count = async () =>
    (await (await request.get("/engine/executions")).json()).length;
  const before = await count();
  const taker = await register(request, localAccount(), {
    timing: "IMMEDIATE",
    minSaving: "999000000",
  });
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get("/engine/orders/" + taker.view.orderId)
          ).json()
        ).status,
    )
    .toBe("UNFILLED");
  const duplicate = await taker.post();
  expect((await duplicate.json()).orderId).toBe(taker.view.orderId);
  expect(await count()).toBe(before);
});
test("mobile archive review and unavailable market never show a transaction receipt", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#Demo%20Mode");
  await page.getByLabel("검증 시나리오").selectOption("too_costly");
  await expect(page.getByText("추가 비용이 절감 가능액을 초과")).toBeVisible();
  await page.getByRole("link", { name: "Trade", exact: false }).click();
  await page.route("**/market/quote?**", (r) =>
    r.fulfill({ status: 503, json: { error: "RPC_UNAVAILABLE" } }),
  );
  await page.route("https://mainnet.hsk.xyz/**", (r) => r.abort());
  await page.getByRole("button", { name: "실시간 DEX 견적 조회" }).click();
  await expect(page.getByRole("alert")).toContainText("견적 조회 실패");
  await expect(
    page.getByRole("button", { name: "최종 조건 확인" }),
  ).toBeDisabled();
  expect(
    await page.evaluate(() => document.body.scrollWidth <= innerWidth),
  ).toBeTruthy();
});
