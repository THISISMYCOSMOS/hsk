def operator_summary(executions, *, chain_mode, ai_calls):
    charged = 0
    failed_l2 = 0
    success_l2 = 0
    receipts = 0
    for row in executions:
        receipt = row["receipt"]
        if not receipt or receipt.get("mode") != "FORK":
            continue
        receipts += 1
        l2 = int(receipt["gasUnits"]) * int(receipt["effectiveGasPriceWei"])
        if row["status"] == "TRANSACTION_FAILED":
            failed_l2 += l2
        else:
            success_l2 += l2
            charged += sum(int(p.get("feeUSDT", 0)) for p in receipt["participants"])
    return dict(
        receiptsCounted=receipts,
        serviceRevenueUSDT=str(charged) if receipts else None,
        failedL2Wei=str(failed_l2) if receipts else None,
        successfulL2Wei=str(success_l2) if receipts else None,
        l1DataWei=None,
        failedGasWei=None,
        rpcUSDT=None,
        aiUSDT=None if ai_calls else "0",
        serverUSDT=None,
        netProfitUSDT=None,
        evidence="FORK_SIMULATION" if receipts else "UNVERIFIED",
    )
