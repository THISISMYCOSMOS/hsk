const { resolve } = require("node:path");
const { createRequire } = require("node:module");
const root = resolve(__dirname, "../..");
const { hashTypedData, recoverTypedDataAddress } = createRequire(
  resolve(root, "frontend/package.json"),
)("viem");
const { vectors } = require(process.argv[2]);
(async () => {
  for (const v of vectors) {
    if (
      hashTypedData(v.typedData) !== v.orderHash ||
      (
        await recoverTypedDataAddress({
          ...v.typedData,
          signature: v.signature,
        })
      ).toLowerCase() !== v.typedData.message.owner.toLowerCase()
    )
      throw Error("viem order digest or signer mismatch");
  }
  const engine = require(process.argv[3]);
  const signer = await recoverTypedDataAddress({
    ...engine.typedData,
    signature: engine.examples.SignedOrder.signature,
  });
  if (signer.toLowerCase() !== engine.typedData.message.maker.toLowerCase())
    throw Error("B sandbox signer mismatch");
  console.log(vectors.length, "Settlement v1 vectors verified with viem");
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
