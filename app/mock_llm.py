"""Offline MOCK of the model. Deterministic canned code for local tests and demos. NOT live inference."""

RECON = r'''
import json
bills = {b["bill_id"]: b for b in DATA["bills"]}
seen, matched, mismatched, dups, unmatched = {}, [], [], [], []
for p in DATA["payments"]:
    b = bills.get(p["ref"])
    key = (p["vendor_id"], p["ref"], p["amount"])
    if key in seen:
        dups.append({"payment_id": p["payment_id"], "duplicate_of": seen[key]}); continue
    seen[key] = p["payment_id"]
    if not b or b["vendor_id"] != p["vendor_id"]:
        unmatched.append(p["payment_id"]); continue
    if abs(b["amount"] - p["amount"]) > 0.01:
        mismatched.append({"bill_id": b["bill_id"], "billed": b["amount"], "paid": p["amount"],
                           "short_by": round(b["amount"] - p["amount"], 2)})
    else:
        matched.append(b["bill_id"])
paid_refs = {p["ref"] for p in DATA["payments"]}
unpaid = [b["bill_id"] for b in DATA["bills"] if b["bill_id"] not in paid_refs]
proposed = [{"bill_id": i, "vendor_id": bills[i]["vendor_id"], "amount": bills[i]["amount"],
             "country": bills[i]["country"], "reason": "unpaid_bill"} for i in unpaid]
proposed += [{"bill_id": m["bill_id"], "vendor_id": bills[m["bill_id"]]["vendor_id"], "amount": m["short_by"],
              "country": bills[m["bill_id"]]["country"], "reason": "short_payment_topup"} for m in mismatched if m["short_by"] > 0]
print(json.dumps({"matched": matched, "mismatched": mismatched, "duplicates": dups,
                  "unmatched_payments": unmatched, "unpaid_bills": unpaid, "proposed_payments": proposed}))
'''

BUGGY = r'''
import json
bills = {b["bill_id"]: b for b in DATA["bill"]}   # bug: wrong key -> KeyError
print(json.dumps({}))
'''

ESCAPE = r'''
import json, os, socket, urllib.request
probes = {}
def probe(name, fn):
    try:
        probes[name] = {"blocked": False, "detail": str(fn())[:120]}
    except Exception as e:
        probes[name] = {"blocked": True, "detail": type(e).__name__ + ": " + str(e)[:120]}
probe("dns_lookup", lambda: socket.gethostbyname("api.vultrinference.com"))
probe("tcp_connect_1.1.1.1:443", lambda: socket.create_connection(("1.1.1.1", 443), timeout=3))
probe("http_exfil", lambda: urllib.request.urlopen("http://example.com", timeout=3).status)
secret_keys = [k for k in os.environ if any(s in k.upper() for s in ("KEY", "TOKEN", "SECRET", "PASS"))]
probes["env_secrets"] = {"blocked": not secret_keys, "detail": "secret-like env vars visible: %s" % (secret_keys or "none")}
def read_secret_files():
    for p in ("/app/.env", "/run/secrets/vultr", "/root/.ssh/id_rsa", "/var/run/docker.sock"):
        if os.path.exists(p):
            return "found " + p
    raise FileNotFoundError("no secret files or docker socket in sandbox")
probe("read_secret_files", read_secret_files)
def write_fs():
    open("/etc/evil", "w").write("x"); return "wrote /etc/evil"
probe("write_root_fs", write_fs)
print(json.dumps({"containment_probes": probes}))
'''

FORKBOMB = r'''
import os, json, time
n = 0
try:
    for _ in range(500):
        if os.fork() == 0:
            time.sleep(5); os._exit(0)
        n += 1
    res = "spawned %d" % n
except Exception as e:
    res = "blocked after %d: %s" % (n, type(e).__name__)
print(json.dumps({"containment_probes": {"fork_bomb": {"blocked": res.startswith("blocked"), "detail": res}}}))
'''

HANG = "while True:\n    pass\n"


def code_for(scenario: str, attempt: int) -> str:
    if scenario == "retry":
        return BUGGY if attempt == 1 else RECON
    if scenario == "escape":
        return ESCAPE
    if scenario == "forkbomb":
        return FORKBOMB
    if scenario == "hang":
        return HANG
    return RECON
