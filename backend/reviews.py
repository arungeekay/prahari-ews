"""Maker-checker review log: every drafted document and every flag is acted on by a named officer.

Actions
    approve   the officer agrees with the flag / accepts the drafted memo for filing
    return    sent back for more evidence (with a note)
    clear     reviewed and found not to need action; the account is suppressed from the watch-list
              for a cooling period so it does not re-alert every month
    file      document filed to the credit file (audit trail)

Stored as JSON under DATA_DIR (append-only list plus a per-account state view). Timestamps are
wall-clock: this is audit data, not generated data, and determinism does not apply to it.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

ACTIONS = ("approve", "return", "clear", "file")
COOLING_MONTHS = 1


class ReviewStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.path.join(os.environ.get("DATA_DIR", "data"), "reviews.json"))
        self._lock = threading.Lock()
        self._log: list[dict] = []
        if self.path.exists():
            try:
                self._log = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._log = []

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._log, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            pass

    def add(self, account_id: str, action: str, reviewer: str, note: str = "", document_type: str = "",
            as_of_month: int | None = None) -> dict:
        if action not in ACTIONS:
            raise ValueError(f"unknown action {action}; expected one of {ACTIONS}")
        rec = dict(id=f"RV{len(self._log) + 1:06d}", account_id=account_id, action=action,
                   reviewer=reviewer.strip() or "officer", note=note.strip(), document_type=document_type,
                   as_of_month=as_of_month, timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        with self._lock:
            self._log.append(rec)
            self._save()
        return rec

    def for_account(self, account_id: str) -> list[dict]:
        return [r for r in self._log if r["account_id"] == account_id]

    def state(self, account_id: str, as_of_month: int | None = None) -> dict:
        """Latest review state; `suppressed` is true inside the cooling period after a 'clear'."""
        hist = self.for_account(account_id)
        if not hist:
            return dict(status="unreviewed", suppressed=False, last=None)
        last = hist[-1]
        suppressed = False
        if last["action"] == "clear" and as_of_month is not None and last.get("as_of_month") is not None:
            suppressed = as_of_month < int(last["as_of_month"]) + COOLING_MONTHS + 1
        status = {"approve": "approved", "return": "returned", "clear": "cleared", "file": "filed"}[last["action"]]
        return dict(status=status, suppressed=suppressed, last=last, n_reviews=len(hist))

    def all(self, limit: int = 200) -> list[dict]:
        return list(reversed(self._log[-limit:]))

    def suppressed_ids(self, as_of_month: int) -> set[str]:
        return {aid for aid in {r["account_id"] for r in self._log} if self.state(aid, as_of_month)["suppressed"]}
