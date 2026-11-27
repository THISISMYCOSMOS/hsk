import { useState, useRef, useEffect } from "react";
import type { Address } from "viem";
import {
  api,
  composeOrder,
  signLocal,
  type LocalOrder as Order,
  type Terms,
} from "./engine";
import { approveFork, forkReview, signFork, type ForkReview } from "./fork";
import { display } from "./network";
import { message } from "./wallet";
import { Tag } from "./evidence";
const initial: Terms = {
  side: "SELL",
  amount: "1000",
  price: "0.080",
  hours: "24",
  timing: "LIMIT",
  allowPartial: true,
  allowDex: false,
  allowFallback: false,
  priority: "SAVINGS",
  fee: "0.02",
  saving: "0.01",
};
interface Intent {
  side: Terms["side"] | null;
  whskAmount: string | null;
  price: string | null;
  priceRelation: string | null;
  hours: string | null;
  allowPartial: boolean | null;
  requiresConfirmation: boolean;
  llmCalls: number;
}
export function LocalOrderForm({
  account,
  chain,
}: {
  account: Address | null;
  chain: number | null;
}) {
  const [terms, setTerms] = useState<Terms>(initial),
    [text, setText] = useState(""),
    [intent, setIntent] = useState<Intent | null>(null);
  const [draft, setDraft] = useState<Order | null>(null),
    [status, setStatus] = useState(""),
    [error, setError] = useState("");
  const [fork, setFork] = useState<ForkReview | null>(null),
    [mode, setMode] = useState("UNVERIFIED");
  useEffect(() => {
    let active = true;
    api<{ mode: string }>("/agent/status")
      .then((v) => {
        if (active) setMode(v.mode);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  const [working, setWorking] = useState(false),
    lock = useRef(false);
  function update<K extends keyof Terms>(key: K, value: Terms[K]) {
    setTerms((prev) => ({ ...prev, [key]: value }));
    setDraft(null);
    setStatus("");
    setError("");
  }
  async function request(action: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true;
    setWorking(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(message(e));
    } finally {
      lock.current = false;
      setWorking(false);
    }
  }
  async function preview() {
    if (!account || chain !== 31337)
      throw Error("로컬 체인 31337 지갑을 연결하세요.");
    const service = await api<{ mode: string; broadcastEnabled: boolean }>(
      "/agent/status",
    );
    if (
      !(
        (service.mode === "MOCK" && !service.broadcastEnabled) ||
        (service.mode === "FORK" && service.broadcastEnabled)
      )
    )
      throw Error("로컬 MOCK 또는 FORK 백엔드 필요");
    const order = composeOrder(terms, account);
    setFork(service.mode === "FORK" ? await forkReview(order) : null);
    setMode(service.mode);
    setDraft(order);
    setStatus("");
  }
  async function submit() {
    if (
      !draft ||
      !account ||
      chain !== 31337 ||
      draft.maker !== account ||
      BigInt(draft.expiry) <= BigInt(Math.floor(Date.now() / 1000))
    )
      throw Error("계정·체인·만료를 다시 확인하세요.");
    const { signature, digest } = await signLocal(account, draft);
    const settlementSignature = fork ? await signFork(draft, fork) : undefined;
    const result = await api<{ orderId: string; status: string }>("/orders", {
      order: draft,
      signature,
      settlementSignature,
    });
    if (result.orderId !== digest)
      throw Error("주문 ID 불일치 · 주문장 확인 필요");
    setStatus("등록됨 · " + result.orderId);
    setDraft(null);
  }
  const number = (
    key: "amount" | "price" | "hours" | "fee" | "saving",
    label: string,
  ) => (
    <label>
      {label}
      <input
        inputMode="decimal"
        value={terms[key]}
        onChange={(e) => update(key, e.target.value)}
      />
    </label>
  );
  return (
    <section className="panel">
      <div className="section-head">
        <h2>로컬 서명 주문</h2>
        <Tag>
          {mode === "FORK"
            ? "FORK_SIMULATION"
            : mode === "MOCK"
              ? "SYNTHETIC"
              : mode}{" "}
          · 31337
        </Tag>
      </div>
      <p>
        샌드박스 주문은 지갑 서명 후 Agent B 주문장에 저장됩니다.{" "}
        {mode === "FORK"
          ? "포크에서는 정책과 정산 주문에 각각 서명하며, 실제 HSKSwap 포크와 모의 비용 상한을 사용합니다."
          : "MOCK 모드는 모의 잔액을 사용합니다."}
      </p>
      <fieldset disabled={working} style={{ border: 0, padding: 0, margin: 0 }}>
        <label>
          자연어 주문 초안
          <textarea
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setIntent(null);
            }}
            placeholder="WHSK 1,000개를 0.081 USDT 이상에 팔고 싶어."
          />
        </label>
        <button
          disabled={!text.trim()}
          onClick={() =>
            void request(async () => {
              setIntent(await api<Intent>("/agent/intent", { text }));
            })
          }
        >
          조건 추출
        </button>
        {intent && (
          <div className="review">
            <p>
              {[
                intent.side,
                intent.whskAmount && intent.whskAmount + " WHSK",
                intent.price && intent.price + " USDT " + intent.priceRelation,
                intent.hours && intent.hours + "시간",
                intent.allowPartial && "부분 체결 허용",
              ]
                .filter(Boolean)
                .join(" · ") || "인식된 조건 없음"}{" "}
              · 규칙 파서 · LLM 호출 {intent.llmCalls}건
            </p>
            <button
              onClick={() => {
                const side = intent.side || terms.side;
                if (
                  intent.price &&
                  ((side === "SELL" && intent.priceRelation !== "이상") ||
                    (side === "BUY" && intent.priceRelation !== "이하"))
                ) {
                  setError("가격 한도 방향과 주문 방향이 일치하지 않습니다.");
                  return;
                }
                setTerms({
                  ...terms,
                  side,
                  amount: intent.whskAmount || terms.amount,
                  price: intent.price || terms.price,
                  hours: intent.hours || terms.hours,
                  allowPartial: intent.allowPartial ?? terms.allowPartial,
                });
                setDraft(null);
                setIntent(null);
                setStatus("");
              }}
            >
              인식된 조건 적용
            </button>
          </div>
        )}
        <div className="fields" style={{ marginTop: 15 }}>
          <label>
            로컬 주문 방향
            <select
              value={terms.side}
              onChange={(e) => update("side", e.target.value as Terms["side"])}
            >
              <option value="SELL">매도 · EXACT_IN</option>
              <option value="BUY">매수 · EXACT_OUT</option>
            </select>
          </label>
          <label>
            주문 시점
            <select
              value={terms.timing}
              onChange={(e) =>
                update("timing", e.target.value as Terms["timing"])
              }
            >
              <option value="LIMIT">사전 주문</option>
              <option value="IMMEDIATE">즉시 주문</option>
            </select>
          </label>
          {number("amount", "WHSK 수량")}
          {number("price", "한도 가격 (USDT/WHSK)")}
          {number("hours", "유효 시간")}
          {number("fee", "최대 비용 (USDT)")}
          {number("saving", "최소 절감액 (USDT)")}
          <label>
            체결 우선순위
            <select
              value={terms.priority}
              onChange={(e) =>
                update("priority", e.target.value as Terms["priority"])
              }
            >
              <option value="SAVINGS">비용 절감</option>
              <option value="SPEED">빠른 체결</option>
            </select>
          </label>
        </div>
        <div className="checks">
          {(
            [
              ["allowPartial", "부분 체결 허용"],
              ["allowDex", "잔량 DEX 허용"],
              ["allowFallback", "DEX fallback 허용"],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={terms[key]}
                onChange={(e) => update(key, e.target.checked)}
              />
              {label}
            </label>
          ))}
        </div>
        <button onClick={() => void request(preview)}>서명 조건 검토</button>
        {draft && (
          <div className="review">
            <strong>
              {display(draft.fixedAmount, 18)} WHSK · {draft.kind} ·{" "}
              {draft.kind === "EXACT_IN" ? "최소 수령" : "최대 지출"}{" "}
              {display(draft.limitAmount)} USDT
            </strong>
            <p>
              만료 {new Date(Number(draft.expiry) * 1000).toISOString()} ·{" "}
              {draft.priority} · {draft.timing}
            </p>
            <details>
              <summary>전체 서명 필드</summary>
              <pre>{JSON.stringify(draft, null, 2)}</pre>
            </details>
            {fork && (
              <>
                <p>
                  정산 계약 {fork.manifest.contract} · 서명한 지출 한도로 승인
                </p>
                <p>
                  잔액{" "}
                  {display(
                    fork.balance.toString(),
                    draft.kind === "EXACT_IN" ? 18 : 6,
                  )}{" "}
                  / 승인{" "}
                  {display(
                    fork.allowance.toString(),
                    draft.kind === "EXACT_IN" ? 18 : 6,
                  )}{" "}
                  {draft.kind === "EXACT_IN" ? "WHSK" : "USDT"}
                </p>
                <details>
                  <summary>포크 정산 서명 전체 조건</summary>
                  <pre>{JSON.stringify(fork.server, null, 2)}</pre>
                </details>
                {fork.allowance < fork.required && (
                  <button
                    onClick={() =>
                      void request(async () =>
                        setFork(await approveFork(draft, fork)),
                      )
                    }
                  >
                    제한된 토큰 승인
                  </button>
                )}
              </>
            )}
            <button
              className="primary"
              disabled={
                !!fork &&
                (fork.allowance < fork.required || fork.balance < fork.required)
              }
              onClick={() => void request(submit)}
            >
              EIP-712 서명 및 등록
            </button>
          </div>
        )}
      </fieldset>
      {status && <p role="status">{status}</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
