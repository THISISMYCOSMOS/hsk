"""Extract literal terms only. Signing always requires a complete structured request."""

import re
from ..schemas.orders import Model
from pydantic import Field


class Intent(Model):
    text: str = Field(min_length=1, max_length=2000)


def parse_user_intent(request):
    text = request.text
    buy = bool(re.search(r"사고|매수|buy", text, re.I))
    sell = bool(re.search(r"팔고|매도|sell", text, re.I))
    amount = re.search(r"WHSK\s*([0-9][\d,]*(?:\.\d+)?)|([0-9][\d,]*(?:\.\d+)?)\s*WHSK", text, re.I)
    price = re.search(r"(\d+(?:\.\d+)?)\s*USDT\s*(이상|이하)", text, re.I)
    ttl = re.search(r"(\d+)\s*시간", text)
    return dict(
        side=("SELL" if sell else "BUY") if buy != sell else None,
        whskAmount=next((v.replace(",", "") for v in amount.groups() if v), None) if amount else None,
        price=price[1] if price else None,
        priceRelation=price[2] if price else None,
        hours=ttl[1] if ttl else None,
        allowPartial=False
        if re.search(r"부분\s*체결.{0,8}(?:불가|금지|않|안|불허)", text)
        else True
        if re.search(r"부분\s*체결(?:도|을)?\s*허용", text)
        else None,
        requiresConfirmation=True,
        llmCalls=0,
    )
