const { createRequire } = require("node:module");
const { resolve } = require("node:path");
const local = createRequire(resolve(__dirname, "../../frontend/package.json"));
const { generatePrivateKey, privateKeyToAccount } = local("viem/accounts");
const user = privateKeyToAccount(generatePrivateKey());
const url =
  "http://127.0.0.1:" + (process.env.HSK_WEB_PORT || "5173") + "/engine";
async function call(path, body) {
  const response = await fetch(
    url + path,
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {},
  );
  if (!response.ok) throw Error(path + " " + response.status);
  return response.json();
}
async function main() {
  if ((await call("/health")).mode !== "MOCK")
    throw Error("test requires MOCK");
  const order = {
    maker: user.address,
    tokenIn: "0xb210d2120d57b758ee163cffb43e73728c471cf1",
    tokenOut: "0xf1b50ed67a9e2cc94ad3c477779e2d4cbfff9029",
    kind: "EXACT_IN",
    fixedAmount: "1000000000000000000",
    limitAmount: "1000000",
    expiry: String(Math.floor(Date.now() / 1000) + 60),
    nonce: "1",
    allowPartial: false,
    allowDex: false,
    allowFallback: false,
    priority: "SAVINGS",
    timing: "LIMIT",
    minSaving: "1",
    maxCost: "2",
  };
  const signature = await user.signTypedData(
    await call("/orders/typed-data", order),
  );
  const { orderId } = await call("/orders", { order, signature });
  const response = await call("/orders/" + orderId);
  if (
    response.order.maker !== user.address ||
    response.remaining !== order.fixedAmount
  )
    throw Error("database round-trip mismatch");
  const cancel = await user.signTypedData(
    await call("/orders/" + orderId + "/cancel-typed-data"),
  );
  if (
    (await call("/orders/" + orderId + "/cancel", { signature: cancel }))
      .status !== "CANCELLED"
  )
    throw Error("cancel failed");
  console.log(
    "Compose API registration, read-back and signed cancellation passed",
  );
}
main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
