"""Conservative local receipt reconciliation. No network calls; no secrets are read.

Legacy concurrent JSON writers lost some attempts. Recover response receipts and retain
extra liabilities for missing evidence rather than pretending the ledger equals billing.
Media receipts without a provider request ID are charged independently, even if this may
double-count an old ledger entry. The additional legacy hold remains until manual billing
reconciliation; it is NOT reported as exact provider spend.
"""

from __future__ import annotations

import json
import shutil
import time

from app.services.achievements.generation import BACKEND_ROOT, BudgetLedger, token_cost
from app.services.achievements.media import load_manifest


def reconcile() -> None:
    with BudgetLedger().job_lock():
        ledger = BudgetLedger()
        backup = ledger.path.with_name("ledger.before-sequential-reconciliation.json")
        if ledger.path.is_file() and not backup.exists():
            shutil.copy2(ledger.path, backup)
        before = ledger.summary()
        recovered = []
        for path in sorted((BACKEND_ROOT / "achievement_generation" / "responses").glob("*.json")):
            receipt = json.loads(path.read_text(encoding="utf-8"))
            request_id = receipt["id"]
            if any(row.get("requestId") == request_id for row in ledger.attempts()):
                continue
            cost = token_cost(receipt["model"], receipt["usage"])
            key = f"reconciled:response:{request_id}"
            if ledger.reserve(key, "openai", "text", receipt["model"], cost):
                ledger.sent(key)
                ledger.settle(key, cost, request_id=request_id, usage=receipt["usage"])
                recovered.append(key)

        # Correct older underestimates that dropped input-image token usage.
        for row in ledger.attempts("openai"):
            if row.get("usage") and row["status"] == "settled":
                row["costMicros"] = max(row.get("costMicros") or 0, token_cost(row["model"], row["usage"]))
        ledger._save()

        for asset in load_manifest().get("assets", {}).values():
            metadata = asset.get("imageMetadata", {})
            if metadata.get("usage") and metadata.get("sha256"):
                key = f"reconciled:image-receipt:{metadata['sha256']}"
                cost = token_cost(metadata["model"], metadata["usage"])
                if ledger.reserve(key, "openai", "image", metadata["model"], cost):
                    ledger.sent(key)
                    ledger.settle(key, cost, usage=metadata["usage"])
                    recovered.append(key)

        # Known missing evidence includes overwritten/rejected image pilots, failed
        # reference attempts, Fish retries and one Fish diagnostic. These intentionally
        # generous holds are in ADDITION to recovered receipts and unresolved reserves.
        for provider, amount in (("openai", 5_000_000), ("fish", 1_000_000)):
            key = f"reconciled:legacy-unobserved-hold-v1:{provider}"
            if ledger.find(key) is None:
                ledger.reserve(key, provider, "legacy_hold", "unknown-historical", amount)
                ledger.sent(key)
                ledger.unsettled(key)

        report = {
            "createdAt": time.time(), "exactProviderBilling": False,
            "reason": "Recoverable receipts plus conservative extra liabilities for lost legacy writes; possible double counting.",
            "before": before, "after": ledger.summary(), "recovered": recovered,
            "legacyHoldUsd": {"openai": 5, "fish": 1},
        }
        path = ledger.path.with_name("reconciliation-report.json")
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    reconcile()