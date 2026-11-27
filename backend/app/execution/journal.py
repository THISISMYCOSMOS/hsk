"""Durable local submission intent. Ambiguous transmission stays pending across restarts."""

import sqlite3
from web3 import Web3
from web3.exceptions import TransactionNotFound


class Journal:
    def __init__(self, path):
        self.path = path
        with self.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS submissions(
              plan TEXT UNIQUE, chain TEXT, sender TEXT, nonce TEXT, txhash TEXT UNIQUE, status TEXT,
              UNIQUE(chain,sender,nonce))""")

    def connect(self):
        return sqlite3.connect(self.path, timeout=15)

    def submit_local(self, w3, plan, tx, signer):
        from web3 import IPCProvider

        if (
            not isinstance(w3.provider, IPCProvider)
            or w3.eth.chain_id != 31337
            or "anvil" not in w3.client_version.lower()
        ):
            raise ValueError("LOCAL_FORK_REQUIRED")
        if any(tx.get(k) != v for k, v in plan.transaction.items()) or signer.address != tx["from"]:
            raise ValueError("TRANSACTION_MISMATCH")
        id_ = Web3.to_hex(plan.plan_id)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT txhash FROM submissions WHERE plan=?", (id_,)).fetchone()
            if row:
                return row[0]
            if w3.to_hex(w3.eth.get_block("latest").hash) != plan.block_hash:
                raise ValueError("STALE_SNAPSHOT")
            nonce = w3.eth.get_transaction_count(signer.address, "pending")
            signed = signer.sign_transaction(dict(tx, nonce=nonce, chainId=w3.eth.chain_id))
            digest = Web3.to_hex(signed.hash)
            conn.execute(
                "INSERT INTO submissions VALUES(?,?,?,?,?,?)",
                (id_, str(w3.eth.chain_id), signer.address, str(nonce), digest, "PENDING_CONFIRMATION"),
            )
        # Crash or timeout here leaves both the expected hash and reserved operator nonce.
        w3.eth.send_raw_transaction(signed.raw_transaction)
        return digest

    def lookup(self, w3, digest):
        try:
            receipt = w3.eth.get_transaction_receipt(digest)
        except (TransactionNotFound, OSError, TimeoutError):
            return None
        return receipt

    def confirm(self, digest, status):
        if status not in ("CONFIRMED", "FAILED"):
            raise ValueError("invalid final state")
        with self.connect() as conn:
            conn.execute("UPDATE submissions SET status=? WHERE txhash=?", (status, digest))
