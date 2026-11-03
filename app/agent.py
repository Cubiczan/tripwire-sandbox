"""Agent loop: LLM writes code -> sandbox runs it -> retry on error -> policy gate -> human approval queue."""
from __future__ import annotations
import json, time, uuid
from datetime import datetime
from pathlib import Path
from app import sandbox
from app.llm import LLM
from app.policy import Policy, PaymentRequest, evaluate, Decision

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TASK = "Reconcile these vendor bills against payments. Flag mismatches, duplicates, unmatched payments and unpaid bills, and propose payments."
SUSPICIOUS = ("socket", "urllib", "requests", "os.environ", "subprocess", "/etc/", ".env", "fork", "docker.sock")

LOG: list[dict] = []          # audit log (in-memory; append-only)
APPROVALS: dict[str, dict] = {}


def log(kind: str, **kw):
    e = {"ts": datetime.now().isoformat(timespec="seconds"), "kind": kind, **kw}
    LOG.append(e); return e


def load_data() -> dict:
    return {"bills": json.loads((DATA_DIR / "bills.json").read_text()),
            "payments": json.loads((DATA_DIR / "payments.json").read_text())}


def last_json(stdout: str):
    for line in reversed(stdout.strip().splitlines()):
        try: return json.loads(line)
        except Exception: continue
    return None


def run_task(scenario: str = "recon", max_attempts: int = 3, limits: sandbox.Limits | None = None) -> dict:
    llm, data, task_id = LLM(), load_data(), uuid.uuid4().hex[:8]
    log("task_start", task_id=task_id, scenario=scenario, llm_mode=llm.mode)
    attempts, err, out = [], None, None
    for n in range(1, max_attempts + 1):
        code = llm.write_code(TASK, scenario, n, err)
        flags = [s for s in SUSPICIOUS if s in code]
        if flags: log("static_flags", task_id=task_id, attempt=n, patterns=flags)
        r = sandbox.run(code, data, limits)
        out = last_json(r.stdout) if r.exit_code == 0 else None
        a = {"attempt": n, "container": r.container, "exit_code": r.exit_code, "timed_out": r.timed_out,
             "destroyed": r.destroyed, "stderr_tail": r.stderr[-600:], "code": code}
        attempts.append(a)
        log("sandbox_run", task_id=task_id, attempt=n, container=r.container, exit_code=r.exit_code,
            timed_out=r.timed_out, destroyed=r.destroyed)
        if out is not None: break
        err = r.stderr or f"exit {r.exit_code}, no JSON output"
        log("retry" if n < max_attempts else "gave_up", task_id=task_id, attempt=n, error=err[-300:])
        if r.timed_out and scenario == "hang": break
        time.sleep(0.2 * n)
    result = {"task_id": task_id, "scenario": scenario, "llm_mode": llm.mode, "attempts": attempts,
              "output": out, "pending_approvals": []}
    if out and "containment_probes" in out:
        for name, p in out["containment_probes"].items():
            log("containment_blocked" if p["blocked"] else "containment_FAILED", task_id=task_id, probe=name, detail=p["detail"])
    if any(a["timed_out"] for a in attempts):
        log("containment_blocked", task_id=task_id, probe="runaway_cpu_timeout", detail="killed at timeout, container removed")
    if out and "proposed_payments" in out:
        result["pending_approvals"] = queue_payments(task_id, out["proposed_payments"], data)
    log("task_end", task_id=task_id, ok=out is not None)
    return result


def queue_payments(task_id: str, proposals: list[dict], data: dict) -> list[dict]:
    pol = Policy(allowed_payees={b["vendor_id"] for b in data["bills"]})
    queued = []
    for p in proposals:
        req = PaymentRequest(agent_id="recon-agent", kind="vendor_payment", amount=float(p["amount"]), currency="USD",
                             payee_id=p["vendor_id"], payee_country=p.get("country", "US"),
                             at=datetime.now().replace(hour=12))
        v = evaluate(req, pol, [])
        aid = uuid.uuid4().hex[:8]
        item = {"approval_id": aid, "task_id": task_id, **p, "policy": v.decision.value, "policy_reasons": v.reasons,
                "status": "denied_by_policy" if v.decision == Decision.DENY else "awaiting_human"}
        APPROVALS[aid] = item; queued.append(item)
        log("payment_proposed", approval_id=aid, bill_id=p["bill_id"], amount=p["amount"], policy=v.decision.value)
    return queued


def decide(approval_id: str, approve: bool, approver: str) -> dict:
    item = APPROVALS[approval_id]
    if item["status"] != "awaiting_human":
        raise ValueError(f"not awaiting approval: {item['status']}")
    item["status"] = "approved" if approve else "rejected"
    item["approver"] = approver
    # No payment rail is connected in this project: approval records intent only.
    item["execution"] = "not_executed_no_rail_connected" if approve else None
    log("human_decision", approval_id=approval_id, approved=approve, approver=approver)
    return item
