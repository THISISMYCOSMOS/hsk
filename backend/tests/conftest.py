import time
import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from backend.app.schemas.orders import Order, SignedOrder, USDT, WHSK
from backend.app.orderbook.signatures import typed_data
from backend.app.api.main import create_app

UNIT = 10**18


def terms(account, sell=True, size=1000, **change):
    values = dict(
        maker=account.address,
        tokenIn=WHSK if sell else USDT,
        tokenOut=USDT if sell else WHSK,
        kind="EXACT_IN" if sell else "EXACT_OUT",
        timing="LIMIT",
        expiry=str(int(time.time()) + 3600),
        fixedAmount=str(size * UNIT),
        limitAmount=str((79_000 if sell else 84_000) * size),
        nonce="1",
        allowPartial=True,
        allowDex=False,
        allowFallback=False,
        priority="SAVINGS",
        minSaving="1",
        maxCost="100000",
    )
    return Order(**(values | change))


def sign(account, o):
    sig = account.sign_message(encode_typed_data(full_message=typed_data(o)))
    return SignedOrder(order=o, signature="0x" + bytes(sig.signature).hex())


@pytest.fixture
def actors():
    return [Account.create() for _ in range(4)]


@pytest.fixture
def app(tmp_path):
    return create_app("sqlite:///" + str(tmp_path / "hsk.db"), "MOCK", run_worker=False)
