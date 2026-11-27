"""Requires eth-account. Run from the repository root."""

import json
from pathlib import Path
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

spec = json.loads(Path("shared/typed-data/order-v1.json").read_text())
for row in json.loads(Path("data/fixtures/contract/order-vectors-v1.json").read_text())[
    "vectors"
]:
    typed = row["typedData"]
    assert typed["types"] == spec["types"]
    message = encode_typed_data(full_message=typed)
    assert (
        "0x" + keccak(b"\x19" + message.version + message.header + message.body).hex()
        == row["orderHash"]
    )
    assert (
        Account.recover_message(message, signature=row["signature"])
        == typed["message"]["owner"]
    )
print("PASS Python exact-in/exact-out EIP-712 digests and recovery")
