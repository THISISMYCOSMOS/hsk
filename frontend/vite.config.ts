import { defineConfig } from "vite";
import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
const backend = new URL(process.env.AGENT_B_API || "http://127.0.0.1:8765");
if (
  !["127.0.0.1", "localhost", "backend"].includes(backend.hostname) ||
  backend.protocol !== "http:"
)
  throw Error("Agent B endpoint must be a local integration service");
const provider = process.env.AGENT_A_ROOT;
const script = fileURLToPath(
  new URL("../scripts/integration/market.py", import.meta.url),
);
export default defineConfig({
  cacheDir: "node_modules/.vite",
  plugins: [
    {
      name: "agent-a-read-only",
      configureServer(server) {
        if (!provider) return;
        let active = 0;
        server.middlewares.use("/market/quote", (req, res) => {
          res.setHeader("Content-Type", "application/json");
          const p = new URL(req.url || "/", "http://localhost").searchParams;
          const side = p.get("side") || "",
            kind = p.get("kind") || "",
            amount = p.get("amount") || "";
          if (
            req.method !== "GET" ||
            !["SELL", "BUY"].includes(side) ||
            !["EXACT_IN", "EXACT_OUT"].includes(kind) ||
            !/^([1-9][0-9]{0,77})$/.test(amount)
          ) {
            res.statusCode = 400;
            res.end('{"error":"invalid quote terms"}');
            return;
          }
          if (active >= 4) {
            res.statusCode = 429;
            res.end('{"error":"quote capacity reached"}');
            return;
          }
          active++;
          execFile(
            "python3",
            [script, provider, side, kind, amount],
            {
              timeout: 90000,
              env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
            },
            (error, out, stderr) => {
              active--;
              if (error) {
                res.statusCode = 503;
                res.end(
                  JSON.stringify({
                    error: (
                      stderr.trim().split("\n").at(-1) ||
                      "Agent A provider unavailable"
                    ).slice(0, 240),
                  }),
                );
                return;
              }
              res.end(out);
            },
          );
        });
      },
    },
  ],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/engine": {
        target: backend.origin,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/engine/, ""),
      },
    },
  },
});
