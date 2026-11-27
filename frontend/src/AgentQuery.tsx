import { useState } from "react";
import { api } from "./engine";
import { message } from "./wallet";
interface Answer {
  llmCalls: number;
  latencyMs: number;
  plannerError: string | null;
  tools: { name: string; data: Record<string, unknown> }[];
}
export function AgentQuery() {
  const [text, setText] = useState(""),
    [order, setOrder] = useState(""),
    [answer, setAnswer] = useState<Answer | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function ask() {
    setBusy(true);
    setError("");
    setAnswer(null);
    try {
      setAnswer(
        await api<Answer>("/agent/ask", { text, orderId: order || null }),
      );
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <h3>주문에 대해 질문</h3>
      <label>
        주문 ID (선택)
        <input
          value={order}
          onChange={(e) => setOrder(e.target.value)}
          placeholder="0x…"
        />
      </label>
      <label>
        질문
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="왜 직접 매칭하지 않았나요?"
        />
      </label>
      <button disabled={busy || !text.trim()} onClick={() => void ask()}>
        판단 근거 조회
      </button>
      {error && <p role="alert">{error}</p>}
      {answer && (
        <div className="review">
          <p>
            모델 호출 {answer.llmCalls}회 · {answer.latencyMs} ms{" "}
            {answer.plannerError && "· " + answer.plannerError}
          </p>
          {answer.tools.map((tool, i) => (
            <details key={i} open>
              <summary>{tool.name}</summary>
              <pre>{JSON.stringify(tool.data, null, 2)}</pre>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
