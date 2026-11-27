import {
  createPublicClient,
  createWalletClient,
  custom,
  hashTypedData,
  isAddress,
  keccak256,
  parseAbi,
  type Address,
  type Hex,
  type TypedDataDomain,
} from "viem";
import { api, type LocalOrder } from "./engine";
export interface Manifest {
  chainId: number;
  anchor: Hex;
  contract: Address;
  operator: Address;
  codeHash: Hex;
  wallets: Address[];
}
type Payload = {
  domain: TypedDataDomain;
  types: Record<string, { name: string; type: string }[]>;
  primaryType: "Order";
  message: Record<string, string | number | boolean>;
};
const erc20 = parseAbi([
  "function balanceOf(address) view returns (uint256)",
  "function allowance(address,address) view returns (uint256)",
  "function approve(address,uint256) returns (bool)",
]);
const anchor =
  "0x8e9ec7357cca666d04911b91bb3f5cf0292a7b4e5150a4e6febe30daa1280bda";
const fields = [
  ["owner", "address"],
  ["recipient", "address"],
  ["tokenIn", "address"],
  ["tokenOut", "address"],
  ["orderKind", "uint8"],
  ["amountIn", "uint256"],
  ["amountOut", "uint256"],
  ["validAfter", "uint256"],
  ["deadline", "uint256"],
  ["nonce", "uint256"],
  ["partiallyFillable", "bool"],
  ["allowDexFallback", "bool"],
  ["executionPriority", "uint8"],
  ["maxFeeAmount", "uint256"],
  ["minImprovementAmount", "uint256"],
  ["allowedExecutor", "address"],
  ["allowDex", "bool"],
  ["immediate", "bool"],
] as const;
export async function forkReview(order: LocalOrder) {
  const provider = window.ethereum;
  if (!provider) throw Error("지갑 연결 필요");
  const client = createPublicClient({ transport: custom(provider) });
  const accounts = await provider.request({ method: "eth_accounts" });
  const [manifest, server] = await Promise.all([
    api<Manifest>("/integration/fork"),
    api<Payload>("/orders/settlement-typed-data", order),
  ]);
  if (
    (await client.getChainId()) !== 31337 ||
    accounts[0]?.toLowerCase() !== order.maker.toLowerCase() ||
    manifest.chainId !== 31337 ||
    manifest.anchor !== anchor ||
    !isAddress(manifest.contract) ||
    !isAddress(manifest.operator)
  )
    throw Error("로컬 포크 계정 또는 배포 설정 불일치");
  const code = await client.getCode({ address: manifest.contract });
  if (
    !code ||
    keccak256(code) !== manifest.codeHash ||
    (await client.getBlock({ blockNumber: 30592078n })).hash !== anchor
  )
    throw Error("포크 블록 또는 정산 코드 불일치");
  const sell = order.kind === "EXACT_IN";
  const msg = {
    owner: order.maker,
    recipient: order.maker,
    tokenIn: order.tokenIn,
    tokenOut: order.tokenOut,
    orderKind: sell ? 0 : 1,
    amountIn: sell ? order.fixedAmount : order.limitAmount,
    amountOut: sell ? order.limitAmount : order.fixedAmount,
    validAfter: "0",
    deadline: order.expiry,
    nonce: order.nonce,
    partiallyFillable: order.allowPartial,
    allowDexFallback: order.allowFallback,
    executionPriority: order.priority === "SPEED" ? 1 : 0,
    maxFeeAmount: order.maxCost,
    minImprovementAmount: order.minSaving,
    allowedExecutor: manifest.operator,
    allowDex: order.allowDex,
    immediate: order.timing === "IMMEDIATE",
  };
  const types: Payload["types"] = {
    Order: fields.map(([name, type]) => ({ name, type })),
  };
  const domain = {
    name: "HSK Smart Execution",
    version: "1",
    chainId: 31337,
    verifyingContract: manifest.contract,
  } as const;
  const digest = hashTypedData({
    domain,
    types,
    primaryType: "Order",
    message: msg,
  });
  if (server.primaryType !== "Order" || hashTypedData(server) !== digest)
    throw Error("서버와 검토한 계약 서명 조건 불일치");
  const [balance, allowance] = await Promise.all([
    client.readContract({
      address: order.tokenIn,
      abi: erc20,
      functionName: "balanceOf",
      args: [order.maker],
    }),
    client.readContract({
      address: order.tokenIn,
      abi: erc20,
      functionName: "allowance",
      args: [order.maker, manifest.contract],
    }),
  ]);
  return {
    digest,
    server,
    manifest,
    balance,
    allowance,
    required: BigInt(msg.amountIn),
  };
}
export type ForkReview = Awaited<ReturnType<typeof forkReview>>;
export async function approveFork(order: LocalOrder, old: ForkReview) {
  const current = await forkReview(order);
  if (current.digest !== old.digest || current.balance < current.required)
    throw Error("포크 자산 또는 서명 조건 변경");
  if (current.allowance >= current.required) return current;
  const provider = window.ethereum!;
  const wallet = createWalletClient({
    account: order.maker,
    transport: custom(provider),
  });
  const pub = createPublicClient({ transport: custom(provider) });
  const chain = {
    id: 31337,
    name: "Local HSK fork",
    nativeCurrency: { name: "HSK", symbol: "HSK", decimals: 18 },
    rpcUrls: { default: { http: ["http://127.0.0.1:8754"] } },
  } as const;
  const tx = await wallet.writeContract({
    chain,
    address: order.tokenIn,
    abi: erc20,
    functionName: "approve",
    args: [current.manifest.contract, current.required],
  });
  const receipt = await pub.waitForTransactionReceipt({
    hash: tx,
    timeout: 60000,
  });
  if (receipt.status !== "success") throw Error("토큰 승인 실패");
  return forkReview(order);
}
export async function signFork(order: LocalOrder, old: ForkReview) {
  const fresh = await forkReview(order);
  if (
    fresh.digest !== old.digest ||
    fresh.allowance < fresh.required ||
    fresh.balance < fresh.required
  )
    throw Error("잔액·승인·서명 조건 재검토 필요");
  const signature = await window.ethereum!.request({
    method: "eth_signTypedData_v4",
    params: [order.maker, JSON.stringify(fresh.server)],
  });
  if ((await forkReview(order)).digest !== fresh.digest)
    throw Error("서명 도중 배포 변경");
  return signature;
}
