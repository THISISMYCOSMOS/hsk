// Run with Node 22+ and viem installed, from the repository root.
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import type { Hex, TypedDataDefinition } from "viem";
const require = createRequire(import.meta.url);
const { hashTypedData, recoverTypedDataAddress } = require(require.resolve("viem", {paths:[process.cwd(), ...(process.env.NODE_PATH ?? "").split(":")]})) as typeof import("viem");
const vectors = JSON.parse(readFileSync("data/fixtures/contract/order-vectors-v1.json", "utf8")).vectors;
for (const vector of vectors) {
    const payload = vector.typedData;
    for (const field of payload.types.Order) {
        if (field.type === "uint256") payload.message[field.name] = BigInt(payload.message[field.name]);
    }
    const typed = payload as TypedDataDefinition;
    assert.equal(hashTypedData(typed), vector.orderHash);
    const signer = await recoverTypedDataAddress({...typed, signature:vector.signature as Hex});
    assert.equal(signer, payload.message.owner);
}
console.log("PASS TypeScript exact-in/exact-out EIP-712 digests and recovery");
