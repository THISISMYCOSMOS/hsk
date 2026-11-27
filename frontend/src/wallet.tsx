import { useEffect, useState } from "react";
import { isAddress, type Address, type EIP1193Provider } from "viem";
import { balances } from "./network";
type Provider = EIP1193Provider & {
  on?: (event: string, fn: () => void) => void;
  removeListener?: (event: string, fn: () => void) => void;
};
declare global {
  interface Window {
    ethereum?: Provider;
  }
}
export function useWallet() {
  const [account, setAccount] = useState<Address | null>(null);
  const [chain, setChain] = useState<number | null>(null);
  const [holdings, setHoldings] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    const provider = window.ethereum;
    if (!connected || !provider) return;
    let generation = 0;
    const sync = async () => {
      const id = ++generation;
      setAccount(null);
      setChain(null);
      setHoldings([]);
      setError("");
      try {
        const [accounts, network] = await Promise.all([
          provider.request({ method: "eth_accounts" }),
          provider.request({ method: "eth_chainId" }),
        ]);
        if (id !== generation) return;
        if (!accounts[0] || !isAddress(accounts[0])) {
          setConnected(false);
          return;
        }
        const chainId = Number(BigInt(network));
        setAccount(accounts[0]);
        setChain(chainId);
        if (chainId === 177) {
          const values = await balances(accounts[0]);
          if (id === generation) setHoldings(values);
        }
      } catch (e) {
        if (id === generation) setError(message(e));
      }
    };
    const disconnect = () => setConnected(false);
    void sync();
    provider.on?.("accountsChanged", sync);
    provider.on?.("chainChanged", sync);
    provider.on?.("disconnect", disconnect);
    return () => {
      generation++;
      provider.removeListener?.("accountsChanged", sync);
      provider.removeListener?.("chainChanged", sync);
      provider.removeListener?.("disconnect", disconnect);
    };
  }, [connected]);
  async function toggle() {
    setError("");
    if (connected) {
      setConnected(false);
      setAccount(null);
      setChain(null);
      setHoldings([]);
      return;
    }
    try {
      if (!window.ethereum)
        throw Error("EVM 지갑 확장을 열고 다시 연결하세요.");
      await window.ethereum.request({ method: "eth_requestAccounts" });
      setConnected(true);
    } catch (e) {
      setError(message(e));
    }
  }
  async function switchChain() {
    try {
      await window.ethereum?.request({
        method: "wallet_switchEthereumChain",
        params: [{ chainId: "0xb1" }],
      });
    } catch (e) {
      setError(message(e));
    }
  }
  return {
    account: connected ? account : null,
    chain: connected ? chain : null,
    holdings: connected ? holdings : [],
    error,
    toggle,
    switchChain,
  };
}
export const message = (e: unknown) =>
  e instanceof Error ? e.message : "요청 실패";
