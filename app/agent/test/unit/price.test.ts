import { test } from "node:test";
import assert from "node:assert/strict";
import { deviationBps, fromFixed, scaleToE18, sqrtPriceX96ToPriceE18 } from "../../src/price.ts";

const Q96 = 1n << 96n;

test("sqrtPriceX96 → 가격: 같은 소수 자리, sqrt=1이면 1", () => {
  assert.equal(sqrtPriceX96ToPriceE18(Q96, 18, 18), 10n ** 18n);
  assert.equal(sqrtPriceX96ToPriceE18(2n * Q96, 18, 18), 4n * 10n ** 18n);
});

test("sqrtPriceX96 → 가격: 18/6 자리(WETH/USDT 형식)", () => {
  // 가격 2000 USDT/WETH → raw = 2000e6/1e18 = 2e-9, sqrt = sqrt(2e-9) × 2^96
  const sqrt = BigInt(Math.round(Math.sqrt(2e-9) * 2 ** 48)) * (1n << 48n);
  const p = fromFixed(sqrtPriceX96ToPriceE18(sqrt, 18, 6), 18);
  assert.ok(Math.abs(p - 2000) / 2000 < 1e-9, `got ${p}`);
});

test("sqrtPriceX96 → 가격: 실제 WHSK/USDT slot0 값(11-25 블록)", () => {
  // slot0.sqrtPriceX96 = 22519988702454218083783, tick -301484 → 약 0.0808 USDT
  const p = fromFixed(sqrtPriceX96ToPriceE18(22519988702454218083783n, 18, 6), 18);
  assert.ok(Math.abs(p - 1.0001 ** -301484 * 1e12) / p < 1e-4, `got ${p}`);
});

test("sqrtPriceX96 0은 거부", () => {
  assert.throws(() => sqrtPriceX96ToPriceE18(0n, 18, 6));
});

test("scaleToE18", () => {
  assert.equal(scaleToE18(165938n, 2), 1659380000000000000000n);
  assert.equal(scaleToE18(5n, 18), 5n);
  assert.equal(scaleToE18(123456789n * 10n ** 20n, 28), 1234567890000000000n);
});

test("deviationBps: 풀이 1% 비싸면 +100, 3% 싸면 -300", () => {
  assert.equal(deviationBps(101n, 100n), 100);
  assert.equal(deviationBps(97n * 10n ** 18n, 100n * 10n ** 18n), -300);
  assert.throws(() => deviationBps(1n, 0n));
});

test("fromFixed", () => {
  assert.equal(fromFixed(1_500_000n, 6), 1.5);
  assert.equal(fromFixed(-2_500_000n, 6), -2.5);
});
