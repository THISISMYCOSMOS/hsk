// 가격 계산(순수 함수). 금액은 bigint로 계산하고, 사람이 읽는 값만 number로 바꾼다.

const Q192 = 1n << 192n;

/**
 * sqrtPriceX96 → token0 1개당 token1 가격을 10^18 배 한 정수.
 * price = (sqrtP / 2^96)^2 × 10^(dec0 − dec1)
 */
export function sqrtPriceX96ToPriceE18(sqrtPriceX96: bigint, decimals0: number, decimals1: number): bigint {
  if (sqrtPriceX96 <= 0n) throw new Error("sqrtPriceX96 must be > 0");
  const num = sqrtPriceX96 * sqrtPriceX96 * 10n ** BigInt(decimals0) * 10n ** 18n;
  const den = Q192 * 10n ** BigInt(decimals1);
  return num / den;
}

/** 10^decimals 배 정수를 number로. 표시·비교용이다. */
export function fromFixed(x: bigint, decimals: number): number {
  const neg = x < 0n;
  const abs = neg ? -x : x;
  const base = 10n ** BigInt(decimals);
  const v = Number(abs / base) + Number(abs % base) / Number(base);
  return neg ? -v : v;
}

/** Supra 가격(정수, decimal 자리) → 10^18 배 정수 */
export function scaleToE18(value: bigint, decimals: number): bigint {
  if (decimals === 18) return value;
  if (decimals < 18) return value * 10n ** BigInt(18 - decimals);
  return value / 10n ** BigInt(decimals - 18);
}

/** (풀 − 오라클) / 오라클, bps. 음수면 풀이 더 싸다. */
export function deviationBps(poolE18: bigint, oracleE18: bigint): number {
  if (oracleE18 <= 0n) throw new Error("oracle price must be > 0");
  return Number(((poolE18 - oracleE18) * 10_000_00n) / oracleE18) / 100;
}
