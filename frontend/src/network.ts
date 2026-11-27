import {
  createPublicClient,
  http,
  parseAbi,
  formatUnits,
  parseUnits,
  isAddress,
  type Address,
} from "viem";

export const network = {
  chain: 177,
  whsk: "0xb210d2120d57b758ee163cffb43e73728c471cf1",
  usdt: "0xf1b50ed67a9e2cc94ad3c477779e2d4cbfff9029",
  pool: "0x4ff515761864e7838b0adb8b5b2b8b7a068905dc",
  quoter: "0x603f70466fddbe3f238220b9a74fff419a2bbfdd",
  factory: "0x972ca9d1662f5e029cd18327d29026532e84c742",
} as const;
export const rpc = createPublicClient({
  transport: http(import.meta.env.VITE_HSK_RPC || "https://mainnet.hsk.xyz", {
    timeout: 12000,
    retryCount: 0,
  }),
});
const erc20 = parseAbi([
  "function decimals() view returns (uint8)",
  "function balanceOf(address) view returns (uint256)",
  "function allowance(address,address) view returns (uint256)",
]);
const quoter = parseAbi([
  "function quoteExactInputSingle((address tokenIn,address tokenOut,uint256 amountIn,uint24 fee,uint160 sqrtPriceLimitX96) p) returns (uint256,uint160,uint32,uint256)",
  "function quoteExactOutputSingle((address tokenIn,address tokenOut,uint256 amount,uint24 fee,uint160 sqrtPriceLimitX96) p) returns (uint256,uint160,uint32,uint256)",
  "function factory() view returns (address)",
]);
export type Side = "SELL" | "BUY";
export type Kind = "EXACT_IN" | "EXACT_OUT";
export function units(value: string, decimals: number) {
  if (
    !/^\d+(\.\d+)?$/.test(value) ||
    (value.split(".")[1]?.length || 0) > decimals ||
    value.length > 90
  )
    throw Error("토큰 단위에 맞는 수량을 입력하세요.");
  const raw = parseUnits(value, decimals);
  if (raw >= 2n ** 256n) throw Error("uint256 범위를 초과했습니다.");
  return raw;
}
export const display = (value: string | null, decimals = 6) =>
  value === null ? "미측정" : formatUnits(BigInt(value), decimals);
export function pair(side: Side) {
  return side === "SELL"
    ? ([network.whsk, network.usdt] as const)
    : ([network.usdt, network.whsk] as const);
}
export function token(address: string) {
  return address.toLowerCase() === network.whsk ? "WHSK" : "USDT";
}
export const decimals = (address: string) =>
  address.toLowerCase() === network.whsk ? 18 : 6;
export async function quote(side: Side, kind: Kind, input: string) {
  if (import.meta.env.VITE_AGENT_A_PROVIDER === "1") {
    const [a, b] = pair(side);
    const raw = units(input, decimals(kind === "EXACT_IN" ? a : b));
    if (!raw) throw Error("수량은 0보다 커야 합니다.");
    const res = await fetch(
      "/market/quote?" +
        new URLSearchParams({ side, kind, amount: raw.toString() }),
    );
    const q = await res.json();
    if (!res.ok || q.error) throw Error(q.error || "Agent A 견적 요청 실패");
    if (
      q.source !== "OBSERVED_MAINNET" ||
      q.side !== side ||
      q.kind !== kind ||
      q.tokenIn !== a ||
      q.tokenOut !== b ||
      !/^0x[0-9a-f]{64}$/i.test(q.hash) ||
      !/^\d+$/.test(q.block) ||
      BigInt(q.amountIn) <= 0n ||
      BigInt(q.amountOut) <= 0n ||
      BigInt(kind === "EXACT_IN" ? q.amountIn : q.amountOut) !== raw
    )
      throw Error("Agent A 시장 응답 불일치");
    return {
      source: "OBSERVED_MAINNET",
      side,
      kind,
      tokenIn: a,
      tokenOut: b,
      amountIn: String(q.amountIn),
      amountOut: String(q.amountOut),
      block: String(q.block),
      hash: q.hash as Address,
      at: String(q.at),
    };
  }
  if ((await rpc.getChainId()) !== network.chain)
    throw Error("RPC 체인 ID 불일치");
  const block = await rpc.getBlock({ blockTag: "latest" });
  const blockNumber = block.number;
  const [tokenIn, tokenOut] = pair(side);
  const [wi, ui, factory, pool] = await Promise.all([
    ...[network.whsk, network.usdt].map((address) =>
      rpc.readContract({
        blockNumber,
        address,
        abi: erc20,
        functionName: "decimals",
      }),
    ),
    rpc.readContract({
      blockNumber,
      address: network.quoter,
      abi: quoter,
      functionName: "factory",
    }),
    rpc.readContract({
      blockNumber,
      address: network.factory,
      abi: parseAbi([
        "function getPool(address,address,uint24) view returns (address)",
      ]),
      functionName: "getPool",
      args: [tokenIn, tokenOut, 3000],
    }),
  ]);
  if (
    wi !== 18 ||
    ui !== 6 ||
    String(factory).toLowerCase() !== network.factory ||
    String(pool).toLowerCase() !== network.pool
  )
    throw Error("토큰 또는 DEX 설정 검증 실패");
  const exactIn = kind === "EXACT_IN";
  const amount = units(input, decimals(exactIn ? tokenIn : tokenOut));
  if (amount === 0n) throw Error("수량은 0보다 커야 합니다.");
  const args = { tokenIn, tokenOut, fee: 3000, sqrtPriceLimitX96: 0n };
  const request = { blockNumber, address: network.quoter, abi: quoter };
  const {
    result: [variable],
  } = exactIn
    ? await rpc.simulateContract({
        ...request,
        functionName: "quoteExactInputSingle",
        args: [{ ...args, amountIn: amount }],
      })
    : await rpc.simulateContract({
        ...request,
        functionName: "quoteExactOutputSingle",
        args: [{ ...args, amount }],
      });
  if (
    variable === 0n ||
    (await rpc.getBlock({ blockNumber })).hash !== block.hash
  )
    throw Error("견적 0 또는 블록 교체 · 다시 조회하세요.");
  return {
    source: "OBSERVED_MAINNET",
    side,
    kind,
    tokenIn,
    tokenOut,
    amountIn: (exactIn ? amount : variable).toString(),
    amountOut: (exactIn ? variable : amount).toString(),
    block: blockNumber.toString(),
    hash: block.hash,
    at: new Date().toISOString(),
  };
}
export type Quote = Awaited<ReturnType<typeof quote>>;
export async function balances(account: Address) {
  if (!isAddress(account) || (await rpc.getChainId()) !== 177)
    throw Error("계정 또는 체인 검증 실패");
  const blockNumber = await rpc.getBlockNumber();
  const [h, w, u] = await Promise.all([
    rpc.getBalance({ address: account, blockNumber }),
    ...[network.whsk, network.usdt].map((address) =>
      rpc.readContract({
        address,
        blockNumber,
        abi: erc20,
        functionName: "balanceOf",
        args: [account],
      }),
    ),
  ]);
  return [formatUnits(h, 18), formatUnits(w, 18), formatUnits(u, 6)];
}
