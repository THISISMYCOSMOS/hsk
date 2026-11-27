"""Read-only user interface for exact-input WHSK/USDT execution previews."""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from zipfile import ZipFile

from .economics import quote


DECIMALS = {"WHSK": 18, "USDT": 6}
ROUTES = {"dex": "전량 DEX", "direct": "직접 매칭", "hybrid": "직접 매칭 + 잔량 DEX", "hold": "주문 유지"}
NUMBER = r"[0-9]+(?:\.[0-9]+)?"
ARCHIVE = Path(__file__).resolve().parents[1] / "backtests/HSK_Session2_Quotes.zip"


def raw(text, token):
    if not re.fullmatch(NUMBER, text):
        raise ValueError(f"금액을 양의 십진수로 입력하세요 ({text})")
    whole, _, fraction = text.partition(".")
    digits = DECIMALS[token]
    if len(fraction) > digits:
        raise ValueError(f"{token}은 소수점 {digits}자리까지 지원합니다")
    result = int(whole + fraction.ljust(digits, "0"))
    if not 0 < result < 2**256:
        raise ValueError("금액이 유효 범위를 벗어났습니다")
    return result


def amount(value, token):
    if value is None:
        return "미측정"
    scale = 10**DECIMALS[token]
    whole, tail = divmod(abs(value), scale)
    fraction = str(tail).zfill(DECIMALS[token]).rstrip("0")
    number = str(whole) + ("." + fraction if fraction else "")
    return ("-" if value < 0 else "") + number + " " + token


def intent(words):
    text = " ".join(words).strip()
    command = re.fullmatch(r"(sell|매도|buy|매수)\s+(" + NUMBER + r"(?:\s+" + NUMBER + r")*)", text, re.I)
    if command:
        token = "WHSK" if command[1].lower() in ("sell", "매도") else "USDT"
        sizes = command[2].split()
    else:
        natural = re.fullmatch(
            r"(" + NUMBER + r")\s*(WHSK(?:를)?\s*매도|USDT(?:로)?\s*(?:WHSK(?:를)?\s*)?매수)"
            r"(?:해\s*줘|하기)?", text, re.I
        )
        if natural is None:
            raise ValueError("예시: sell 10 100 또는 10 USDT로 WHSK 매수. buy 금액은 USDT 예산입니다")
        token = "WHSK" if natural[2].upper().startswith("WHSK") else "USDT"
        sizes = [natural[1]]
    if len(sizes) > 64:
        raise ValueError("한 번에 최대 64개 금액을 비교할 수 있습니다")
    return token, [raw(value, token) for value in sizes]


def load_scenario(path, token):
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    allowed = {"token_in", "orders", "costs", "min_out", "remainder", "operator"}
    if not isinstance(data, dict) or data.get("token_in") != token:
        raise ValueError(f"시나리오의 token_in은 {token}이어야 합니다")
    if set(data) - allowed:
        raise ValueError("시나리오에 지원하지 않는 필드가 있습니다")
    if not isinstance(data.get("orders", []), list):
        raise ValueError("orders는 가상 주문 배열이어야 합니다")
    for row in data.get("orders", []):
        if not isinstance(row, dict) or set(row) - {"id", "offer", "want", "min_fill", "cost"}:
            raise ValueError("가상 주문 필드를 확인하세요")
    for name, keys in (("costs", {"dex", "direct", "hybrid", "per_order"}),
                       ("operator", {"revenue_usdt", "cost_usdt"})):
        if name in data and (not isinstance(data[name], dict) or set(data[name]) != keys):
            raise ValueError(f"{name} 필드: {', '.join(sorted(keys))}")
    return {k: v for k, v in data.items() if k != "token_in"}


def evaluate(snapshot, token, sizes, scenario):
    rows = [quote(snapshot, token, n, **scenario) for n in sizes]
    lowest = None
    status = "costs_unmeasured"
    if "costs" in scenario and all("cost" in o for o in scenario.get("orders", [])):
        profitable = [r["amount_in"] for r in rows
                      if r["candidate"]["matched_in"] and r["candidate"]["net_saving"] > 0]
        lowest = min(profitable, default=None)
        status = "first_positive_tested_size" if lowest is not None else "no_positive_tested_size"
    metadata = {k: snapshot[k] for k in (
        "chain_id", "block_number", "block_hash", "block_time_utc", "observed_at_utc",
        "pools", "quoter", "factory", "decimals_whsk", "decimals_usdt"
    ) if k in snapshot}
    return {"mode": "mainnet_read_only", "market": metadata, "scenario": scenario,
            "minimum_tested_input": {"status": status, "amount_in": lowest, "token": token},
            "evidence": "pinned_dex_quotes_and_hypothetical_matching", "rows": rows}


def show(report, as_json):
    if as_json:
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return
    market = report["market"]
    print(f"HSK 메인넷 · 블록 {market['block_number']} · {market['block_hash']}")
    if market.get("observed_at_utc"):
        print(f"조회 시각 {market['observed_at_utc']}")
    print("동일 블록 DEX 견적 / 가상 반대 주문 시뮬레이션 · 실현 절감액 미측정")
    for row in report["rows"]:
        src, dst = row["token_in"], row["token_out"]
        chosen = row["candidate"]
        print(f"\n입력 {amount(row['amount_in'], src)}  →  {ROUTES[chosen['route']]}")
        print(f"전량 DEX {amount(row['baseline_out'], dst)} · 선택 경로 수령 {amount(chosen['out'], dst)}")
        print(f"직접 매칭 {amount(chosen['matched_in'], src)} · DEX 투입 {amount(chosen['dex_in'], src)}"
              f" · 유지 {amount(chosen['held_in'], src)}")
        print(f"체결량 기준 DEX {amount(chosen['benchmark_out'], dst)}"
              f" · 비용 전 차이 {amount(chosen['gross_saving'], dst)}"
              f" · 가정 비용 반영 후 예상 절감액 {amount(chosen['net_saving'], dst)}")
        for fill in chosen["fills"]:
            print(f"가상 상대 {fill['id']} · 비용 전 차이 {amount(fill['maker_gross_saving'], src)}"
                  f" · 비용 반영 후 예상 절감액 {amount(fill['maker_net_saving'], src)}")
        exclusions = sorted({c["exclusion"] for c in row["candidates"] if c.get("exclusion")})
        if exclusions:
            print("후보 제외 사유 " + ", ".join(exclusions))
        elif not report["scenario"].get("orders"):
            print("등록한 가상 반대 주문 0건")
    threshold = report["minimum_tested_input"]
    if threshold["amount_in"] is not None:
        print("\n입력한 금액 중 양측 예상 순절감이 양수인 최소 금액 "
              + amount(threshold["amount_in"], threshold["token"]))
    sys.stdout.flush()


def archive_example(as_json):
    with ZipFile(ARCHIVE) as archive:
        data = json.loads(archive.read("quotes.json"))
    if as_json:
        print(json.dumps(data, ensure_ascii=False))
        return
    print(f"팀 보관 상태 재구성 · 블록 {data['block']} · {data['timestamp_utc']}\n{data['block_hash']}")
    for row in data["quotes"]:
        src, dst = ("USDT", "WHSK") if row["kind"] == "exact_output" else ("WHSK", "USDT")
        print(f"{row['kind']}  {amount(int(row['amount_in_raw']), src)} → {amount(int(row['amount_out_raw']), dst)}")
    print("팀이 정한 가상 수량 · 실현 절감액 미측정")


def get_snapshot(block_number=None):
    from .market import get_snapshot as fetch
    return fetch() if block_number is None else fetch(block_number=block_number)


def run(args):
    if args.archive:
        if args.request or args.scenario or args.watch is not None or args.block is not None:
            raise ValueError("--archive는 팀이 보관한 고정 예시 세 건을 표시합니다")
        archive_example(args.json)
        return
    if args.block is not None and args.block < 0:
        raise ValueError("--block은 0 이상의 블록 번호여야 합니다")
    if args.watch is not None and not 1 <= args.watch <= 86400:
        raise ValueError("--watch 주기는 1~86400초여야 합니다")
    words = args.request
    if not words:
        if sys.stdin.isatty():
            print("주문 조건 (예: 10 WHSK 매도 또는 buy 1 10 100)", file=sys.stderr)
        words = [sys.stdin.readline().strip()]
    token, sizes = intent(words)
    previous = None
    while True:
        try:
            scenario = load_scenario(args.scenario, token)
            snapshot = get_snapshot(args.block)
            key = (snapshot["block_hash"], scenario)
            if key != previous:
                show(evaluate(snapshot, token, sizes, scenario), args.json)
                previous = key
        except (OSError, ValueError, KeyError, RuntimeError, TypeError) as exc:
            if args.watch is None:
                raise
            previous = None
            print(f"견적 미측정 · {exc}", file=sys.stderr, flush=True)
        if args.watch is None:
            break
        time.sleep(args.watch)


def main(argv=None):
    parser = argparse.ArgumentParser(description="WHSK/USDT 메인넷 읽기 전용 금액별 비교")
    parser.add_argument("request", nargs="*", help="sell 10 100 (WHSK) / buy 1 10 (USDT)")
    parser.add_argument("--scenario", type=Path, help="가상 주문·비용 조건 JSON 파일")
    parser.add_argument("--block", type=int, metavar="NUMBER", help="지정한 메인넷 블록의 종료 상태로 재현")
    parser.add_argument("--watch", type=float, metavar="SECONDS", help="블록/시나리오 변경 시 다시 평가")
    parser.add_argument("--archive", action="store_true", help="팀이 보관한 고정 블록 예시")
    parser.add_argument("--json", action="store_true", help="기계 판독 결과 (토큰 최소 단위)")
    try:
        run(parser.parse_args(argv))
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, RuntimeError, TypeError, EOFError) as exc:
        print(f"견적 미측정 · {exc}", file=sys.stderr)
        return 1
    return 0
