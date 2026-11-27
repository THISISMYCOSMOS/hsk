"""Canonical engine projection. Fixed WHSK quantity, all cash limits in micro-USDT."""

from fractions import Fraction
from typing import Annotated, Literal
from eth_utils import to_checksum_address
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

WHSK = "0xb210d2120d57b758ee163cffb43e73728c471cf1"
USDT = "0xf1b50ed67a9e2cc94ad3c477779e2d4cbfff9029"
MAX = 2**256 - 1


def uint_string(value: str) -> str:
    if int(value) > MAX:
        raise ValueError("uint256 overflow")
    return value


Raw = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]*)$", max_length=78), AfterValidator(uint_string)]
Address = Annotated[str, Field(pattern=r"^0x[0-9a-fA-F]{40}$"), AfterValidator(to_checksum_address)]
Hash = Annotated[str, Field(pattern=r"^0x[0-9a-fA-F]{64}$")]
Signature = Annotated[str, Field(pattern=r"^0x[0-9a-fA-F]{130}$")]
Evidence = Literal[
    "OBSERVED_MAINNET", "EXECUTED_MAINNET", "FORK_SIMULATION", "BACKTEST", "SYNTHETIC", "UNVERIFIED"
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)


class Order(Model):
    maker: Address
    tokenIn: Address
    tokenOut: Address
    kind: Literal["EXACT_IN", "EXACT_OUT"]
    fixedAmount: Raw
    limitAmount: Raw
    nonce: Raw
    expiry: Raw
    timing: Literal["IMMEDIATE", "LIMIT"]
    allowPartial: bool
    allowDex: bool
    allowFallback: bool
    priority: Literal["SAVINGS", "SPEED"]
    maxCost: Raw
    minSaving: Raw

    @model_validator(mode="after")
    def check_order(self):
        pair = (WHSK, USDT) if self.selling else (USDT, WHSK)
        if (self.tokenIn.lower(), self.tokenOut.lower()) != pair:
            raise ValueError("unsupported pair or fixed side")
        if min(int(self.fixedAmount), int(self.limitAmount), int(self.expiry), int(self.maker, 16)) == 0:
            raise ValueError("zero maker, quantity, limit or expiry")
        if self.allowFallback and not self.allowDex:
            raise ValueError("fallback requires DEX permission")
        return self

    @property
    def selling(self):
        return self.kind == "EXACT_IN"

    @property
    def price(self):
        return Fraction(int(self.limitAmount), int(self.fixedAmount))

    def limit(self, quantity):
        n = int(self.limitAmount) * quantity
        d = int(self.fixedAmount)
        return -(-n // d) if self.selling else n // d


class SignedOrder(Model):
    order: Order
    signature: Signature


class Registration(SignedOrder):
    settlementSignature: Signature | None = None


class Cancel(Model):
    signature: Signature
