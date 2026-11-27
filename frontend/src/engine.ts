import { hashTypedData, type Address, type Hex } from "viem";
import { network, units, type Side } from "./network";
export async function api<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const r = await fetch("/engine" + path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!r.ok)
    throw Error(
      "Agent B API " + r.status + " · " + (await r.text()).slice(0, 220),
    );
  if (!r.headers.get("content-type")?.includes("application/json"))
    throw Error("Agent B API가 연결되지 않았습니다.");
  return r.json();
}
export const domain = {
  name: "HSK Smart Execution Sandbox",
  version: "0.1",
  chainId: 31337,
  verifyingContract: "0x0000000000000000000000000000000000000001",
} as const;
const fields = (pairs: readonly (readonly [string, string])[]) =>
  pairs.map(([name, type]) => ({ name, type }));
const domainFields = fields([
  ["name", "string"],
  ["version", "string"],
  ["chainId", "uint256"],
  ["verifyingContract", "address"],
]);
const orderFields = fields([
  ["maker", "address"],
  ["tokenIn", "address"],
  ["tokenOut", "address"],
  ["kind", "string"],
  ["fixedAmount", "uint256"],
  ["limitAmount", "uint256"],
  ["nonce", "uint256"],
  ["expiry", "uint256"],
  ["timing", "string"],
  ["allowPartial", "bool"],
  ["allowDex", "bool"],
  ["allowFallback", "bool"],
  ["priority", "string"],
  ["maxCost", "uint256"],
  ["minSaving", "uint256"],
]);
export interface Terms {
  side: Side;
  amount: string;
  price: string;
  hours: string;
  timing: "LIMIT" | "IMMEDIATE";
  allowPartial: boolean;
  allowDex: boolean;
  allowFallback: boolean;
  priority: "SAVINGS" | "SPEED";
  fee: string;
  saving: string;
}
export function composeOrder(t: Terms, maker: Address) {
  const fixed = units(t.amount, 18),
    rate = units(t.price, 18);
  const denominator = 10n ** 30n; // WHSK raw * USDT/WHSK with 18 decimals -> micro-USDT.
  const selling = t.side === "SELL";
  const limit = selling
    ? (fixed * rate + denominator - 1n) / denominator
    : (fixed * rate) / denominator;
  if (
    limit <= 0n ||
    limit >= 2n ** 256n ||
    fixed === 0n ||
    !/^\d+$/.test(t.hours) ||
    BigInt(t.hours) < 1n ||
    BigInt(t.hours) > 8760n
  )
    throw Error("수량, 가격 또는 만료 시간이 유효하지 않습니다.");
  if (t.allowFallback && !t.allowDex)
    throw Error("DEX fallback에는 DEX 거래 허용이 필요합니다.");
  const nonce = Array.from(crypto.getRandomValues(new Uint8Array(16)), (v) =>
    v.toString(16).padStart(2, "0"),
  ).join("");
  return {
    maker,
    tokenIn: selling ? network.whsk : network.usdt,
    tokenOut: selling ? network.usdt : network.whsk,
    kind: selling ? "EXACT_IN" : "EXACT_OUT",
    fixedAmount: fixed.toString(),
    limitAmount: limit.toString(),
    nonce: BigInt("0x" + nonce).toString(),
    expiry: (
      BigInt(Math.floor(Date.now() / 1000)) +
      BigInt(t.hours) * 3600n
    ).toString(),
    timing: t.timing,
    allowPartial: t.allowPartial,
    allowDex: t.allowDex,
    allowFallback: t.allowFallback,
    priority: t.priority,
    maxCost: units(t.fee, 6).toString(),
    minSaving: units(t.saving, 6).toString(),
  };
}
export type LocalOrder = ReturnType<typeof composeOrder>;
export async function signLocal(account: Address, orderOrId: LocalOrder | Hex) {
  const provider = window.ethereum;
  if (!provider) throw Error("지갑 연결 필요");
  async function verify() {
    const [chain, accounts] = await Promise.all([
      provider!.request({ method: "eth_chainId" }),
      provider!.request({ method: "eth_accounts" }),
    ]);
    if (
      BigInt(chain) !== 31337n ||
      accounts[0]?.toLowerCase() !== account.toLowerCase()
    )
      throw Error("계정 또는 네트워크 변경 · 로컬 체인 31337 필요");
  }
  await verify();
  const cancel = typeof orderOrId === "string";
  const primaryType = cancel ? "Cancel" : "SandboxOrder";
  const message = cancel ? { orderId: orderOrId } : orderOrId;
  const types = {
    [primaryType]: cancel ? fields([["orderId", "bytes32"]]) : orderFields,
    EIP712Domain: domainFields,
  };
  const payload = { domain, primaryType, message, types };
  const server = await api<typeof payload>(
    cancel
      ? "/orders/" + orderOrId + "/cancel-typed-data"
      : "/orders/typed-data",
    cancel ? undefined : orderOrId,
  );
  if (
    server.primaryType !== primaryType ||
    hashTypedData(server) !== hashTypedData(payload)
  )
    throw Error("서버 서명 도메인 또는 주문 의미 불일치");
  await verify();
  const signature = await provider.request({
    method: "eth_signTypedData_v4",
    params: [account, JSON.stringify(payload)],
  });
  await verify();
  return { signature, digest: hashTypedData(payload) };
}
