import { useState, useRef } from "react";
import {
  decimals,
  display,
  quote,
  token,
  units,
  network,
  type Kind,
  type Side,
  type Quote,
} from "./network";
import { Tag } from "./evidence";
import { message } from "./wallet";

export function Trade() {
  const [side, setSide] = useState<Side>("SELL"),
    [kind, setKind] = useState<Kind>("EXACT_IN");
  const [amount, setAmount] = useState("1000"),
    [price, setPrice] = useState("0.081");
  const [mode, setMode] = useState("사전 주문"),
    [priority, setPriority] = useState("비용 절감 우선");
  const [expiry, setExpiry] = useState("24"),
    [fee, setFee] = useState("0"),
    [saving, setSaving] = useState("0.01");
  const [partial, setPartial] = useState(true),
    [residual, setResidual] = useState(false),
    [fallback, setFallback] = useState(false);
  const [result, setResult] = useState<Quote | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [review, setReview] = useState(false);
  const generation = useRef(0);
  function invalidate() {
    generation.current++;
    setResult(null);
    setError("");
    setBusy(false);
    setReview(false);
  }
  const fixedToken =
    (side === "SELL") === (kind === "EXACT_IN") ? "WHSK" : "USDT";
  async function lookup() {
    invalidate();
    const id = generation.current;
    try {
      if (
        !units(price, 18) ||
        !/^[1-9]\d*$/.test(expiry) ||
        Number(expiry) > 8760
      )
        throw Error("가격은 양수, 유효기간은 1~8760시간이어야 합니다.");
      units(fee, 6);
      units(saving, 6);
      units(amount, fixedToken === "WHSK" ? 18 : 6);
      setBusy(true);
      const value = await quote(side, kind, amount);
      if (id === generation.current) setResult(value);
    } catch (e) {
      if (id === generation.current) setError(message(e));
    } finally {
      if (id === generation.current) setBusy(false);
    }
  }
  return (
    <div className="tradegrid">
      <section className="panel">
        <div className="section-head">
          <div>
            <small>ORDER ENTRY</small>
            <h2>주문 조건</h2>
          </div>
          <Tag>READ_ONLY</Tag>
        </div>
        <form
          onChange={invalidate}
          onSubmit={(e) => {
            e.preventDefault();
            void lookup();
          }}
        >
          <div className="seg">
            {(["SELL", "BUY"] as const).map((s) => (
              <button
                type="button"
                key={s}
                className={s === side ? "on" : ""}
                aria-pressed={s === side}
                onClick={() => {
                  invalidate();
                  setSide(s);
                }}
              >
                {s === "SELL" ? "매도" : "매수"} WHSK
              </button>
            ))}
          </div>
          <div className="fields">
            <label>
              접수 방식
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option>사전 주문</option>
                <option>즉시 주문</option>
              </select>
            </label>
            <label>
              고정 조건
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value as Kind)}
              >
                <option value="EXACT_IN">EXACT_IN · 지출 고정</option>
                <option value="EXACT_OUT">EXACT_OUT · 수령 고정</option>
              </select>
            </label>
            <label>
              고정 수량 ({fixedToken})
              <input
                value={amount}
                inputMode="decimal"
                onChange={(e) => setAmount(e.target.value)}
                required
              />
            </label>
            <label>
              {side === "SELL" ? "최소 매도가" : "최대 매수가"} (USDT/WHSK)
              <input
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                inputMode="decimal"
                required
              />
            </label>
            <label>
              유효기간 (시간)
              <input
                value={expiry}
                onChange={(e) => setExpiry(e.target.value)}
                required
              />
            </label>
            <label>
              우선순위
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
              >
                <option>비용 절감 우선</option>
                <option>빠른 체결 우선</option>
              </select>
            </label>
            <label>
              최대 수수료 (USDT)
              <input
                value={fee}
                onChange={(e) => setFee(e.target.value)}
                required
              />
            </label>
            <label>
              최소 절감액 (USDT)
              <input
                value={saving}
                onChange={(e) => setSaving(e.target.value)}
                required
              />
            </label>
          </div>
          <div className="checks">
            {[
              [partial, setPartial, "부분 체결"],
              [residual, setResidual, "잔량 DEX"],
              [fallback, setFallback, "DEX fallback"] as const,
            ].map((item) => {
              const [value, set, label] = item as [
                boolean,
                (value: boolean) => void,
                string,
              ];
              return (
                <label key={label}>
                  <input
                    type="checkbox"
                    checked={value}
                    onChange={(e) => set(e.target.checked)}
                  />
                  {label}
                </label>
              );
            })}
          </div>
          <button className="primary" disabled={busy}>
            {busy ? "블록 확인 중…" : "실시간 DEX 견적 조회"}
          </button>
        </form>
        {error && (
          <p role="alert" className="error">
            견적 조회 실패 · {error}
          </p>
        )}
      </section>
      <section className="panel">
        <div className="section-head">
          <div>
            <small>EXECUTION PREVIEW</small>
            <h2>집행 전 검토</h2>
          </div>
          <Tag>{result ? "OBSERVED_MAINNET" : "UNVERIFIED"}</Tag>
        </div>
        <dl>
          <dt>기준 경로</dt>
          <dd>HSKSwap V3 · 0.30%</dd>
          <dt>지출 수량</dt>
          <dd>
            {result
              ? display(result.amountIn, decimals(result.tokenIn)) +
                " " +
                token(result.tokenIn)
              : "조회 전"}
          </dd>
          <dt>수령 수량</dt>
          <dd>
            {result
              ? display(result.amountOut, decimals(result.tokenOut)) +
                " " +
                token(result.tokenOut)
              : "조회 전"}
          </dd>
          <dt>기준 블록</dt>
          <dd>
            {result ? (
              <a
                href={"https://hsk.blockscout.com/block/" + result.hash}
                target="_blank"
                rel="noreferrer"
              >
                {result.block} ↗
              </a>
            ) : (
              "조회 전"
            )}
          </dd>
          <dt>조회 시각</dt>
          <dd>{result?.at || "조회 전"}</dd>
          <dt>실제 가스비 / 순절감액</dt>
          <dd>미측정</dd>
        </dl>
        <p>
          풀 수수료와 가격 충격은 견적에 포함됩니다. 지갑 승인에는 가스비가 들
          수 있으며 오프체인 서명은 가스비가 없습니다.
        </p>
        <button disabled={!result} onClick={() => setReview(true)}>
          최종 조건 확인
        </button>
        {review && result && (
          <div className="review">
            <strong>
              {mode} · {side} · {kind}
            </strong>
            <p>
              {amount} {fixedToken} · {price} USDT/WHSK · {expiry}시간 ·{" "}
              {priority}
            </p>
            <p>
              부분 체결 {partial ? "허용" : "차단"} / 잔량 DEX{" "}
              {residual ? "허용" : "차단"} / fallback{" "}
              {fallback ? "허용" : "차단"}
            </p>
            <p>
              수수료 ≤ {fee} USDT · 절감액 ≥ {saving} USDT
            </p>
            <p>읽기 전용 메인넷 · 주문 미등록</p>
          </div>
        )}
        <div className="panel-foot">Chain {network.chain} · WHSK / USDT</div>
      </section>
    </div>
  );
}
