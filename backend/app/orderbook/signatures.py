"""A local sandbox authorization for the complete engine policy; never a chain settlement signature."""

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from ..schemas.orders import Order

DOMAIN = {
    "name": "HSK Smart Execution Sandbox",
    "version": "0.1",
    "chainId": 31337,
    "verifyingContract": "0x0000000000000000000000000000000000000001",
}
ORDER_FIELDS = {
    "maker": "address",
    "tokenIn": "address",
    "tokenOut": "address",
    "kind": "string",
    "fixedAmount": "uint256",
    "limitAmount": "uint256",
    "nonce": "uint256",
    "expiry": "uint256",
    "timing": "string",
    "allowPartial": "bool",
    "allowDex": "bool",
    "allowFallback": "bool",
    "priority": "string",
    "maxCost": "uint256",
    "minSaving": "uint256",
}
DOMAIN_FIELDS = {"name": "string", "version": "string", "chainId": "uint256", "verifyingContract": "address"}


def fields(spec):
    return [{"name": k, "type": v} for k, v in spec.items()]


def typed_data(order: Order = None, *, cancel=None):
    if (cancel is None) == (order is None):
        raise ValueError("select one message")
    kind = "Cancel" if cancel is not None else "SandboxOrder"
    spec = {"orderId": "bytes32"} if cancel is not None else ORDER_FIELDS
    msg = {"orderId": cancel} if cancel is not None else order.model_dump()
    return dict(
        domain=DOMAIN.copy(),
        primaryType=kind,
        message=msg,
        types={"EIP712Domain": fields(DOMAIN_FIELDS), kind: fields(spec)},
    )


def recover(payload, signature, owner):
    msg = encode_typed_data(full_message=payload)
    try:
        signer = Account.recover_message(msg, signature=signature)
    except Exception as exc:
        raise ValueError("INVALID_SIGNATURE") from exc
    if signer.lower() != owner.lower():
        raise ValueError("INVALID_SIGNATURE")
    return "0x" + keccak(b"\x19" + msg.version + msg.header + msg.body).hex()
