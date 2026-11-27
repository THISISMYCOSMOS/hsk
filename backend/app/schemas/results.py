from typing import Literal
from pydantic import Field
from .orders import Model, Order, Raw, Hash, Evidence


class MarketSnapshot(Model):
    blockHash: Hash
    blockNumber: Raw
    evidence: Evidence


class DexQuote(MarketSnapshot):
    tokenIn: str
    tokenOut: str
    amountIn: Raw
    amountOut: Raw


class CostBreakdown(Model):
    dex_lower: Raw
    l1: Raw
    l2: Raw
    settlement: Raw
    verification: Raw
    approval: Raw
    service: Raw
    other: Raw
    margin: Raw


class UserSavings(Model):
    orderId: str
    token: Literal["USDT"]
    gross: Raw
    dexGross: Raw
    conservativeSaving: str = Field(pattern=r"^-?(0|[1-9][0-9]*)$")
    costs: CostBreakdown


class Fill(Model):
    orderId: str
    fixed: Raw
    cash: Raw


class ExecutionCandidate(Model):
    kind: Literal[
        "DEX_ONLY", "DIRECT_MATCH", "MULTI_ORDER_MATCH", "HYBRID_MATCH", "PARTIAL_AND_KEEP", "VALID_DEX_ROUTE"
    ]
    fixedFilled: Raw
    remaining: Raw
    dexFixed: Raw
    eligible: bool
    reason: str | None
    fills: list[Fill]
    savings: list[UserSavings]
    totalConservativeSavingUSDT: str | None = None
    gross: Raw | None = None
    routeId: str | None = None


class Comparison(MarketSnapshot):
    candidates: list[ExecutionCandidate]
    selected: ExecutionCandidate | None
    combinationsChecked: int
    truncated: bool
    globalOptimum: bool
    smallestEconomicFillTested: Raw | None
    marketEvidence: Evidence


class ExecutionPlan(Model):
    orderId: Hash
    blockHash: Hash
    candidate: ExecutionCandidate


class OrderView(Model):
    orderId: Hash
    order: Order
    remaining: Raw
    status: str


class AgentEvent(Model):
    id: int
    kind: str
    payload: dict
    at: int


class SimulationResult(Model):
    mode: str
    evidence: Evidence
    success: bool
    reason: str | None
    receipt: dict | None


class ExecutionReceipt(Model):
    mode: str
    evidence: Evidence
    transactionHash: Hash | None
    blockHash: Hash
    gasUnits: Raw
    effectiveGasPriceWei: Raw | None = None
    walletDeltas: list[dict]
    participants: list[dict]


class QuoteRequest(Model):
    orderId: Hash


class QuoteView(Model):
    quoteId: str
    orderId: Hash
    comparison: Comparison
