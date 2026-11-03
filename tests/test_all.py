import os, pytest
os.environ.pop("VULTR_INFERENCE_API_KEY", None)
from fastapi.testclient import TestClient
from app import sandbox, llm, agent
from app.main import app

docker = pytest.mark.skipif(not sandbox.docker_available(), reason="docker not available")
c = TestClient(app)

def test_mock_mode_without_key():
    assert llm.mode() == "mock"

def test_live_mode_uses_vultr_base_url(monkeypatch):
    monkeypatch.setenv("VULTR_INFERENCE_API_KEY", "dummy-not-real")
    monkeypatch.delenv("TRIPWIRE_LLM_MODE", raising=False)
    l = llm.LLM()
    assert l.mode == "live" and str(l._client.base_url).rstrip("/") == llm.VULTR_BASE_URL

def test_strip_fences():
    assert llm.strip_fences("```python\nprint(1)\n```") == "print(1)"

def test_sandbox_argv_flags():
    a = sandbox.build_argv("x", sandbox.Limits())
    s = " ".join(a)
    for f in ["--rm", "--network none", "--read-only", "--tmpfs", "--memory 256m", "--cpus 0.5",
              "--pids-limit 64", "--cap-drop ALL", "no-new-privileges", "--env-file /dev/null", "--user 65534:65534"]:
        assert f in s
    assert "-e" not in a and "-v" not in a and "--volume" not in a

def test_policy_reused():
    from app.policy import Policy, PaymentRequest, evaluate, Decision
    from datetime import datetime
    r = PaymentRequest("a", "k", 7200, "USD", "V", "US", datetime(2026, 11, 3, 12))
    assert evaluate(r, Policy(), []).decision == Decision.DENY

@docker
def test_recon_correct():
    r = agent.run_task("recon")
    o = r["output"]
    assert o["matched"] == ["B-1001", "B-1003"]
    assert o["mismatched"][0]["bill_id"] == "B-1002" and o["mismatched"][0]["short_by"] == 90.0
    assert o["duplicates"][0]["payment_id"] == "P-504"
    assert o["unmatched_payments"] == ["P-505"]
    assert set(o["unpaid_bills"]) == {"B-1004", "B-1005", "B-1006"}
    assert all(a["destroyed"] for a in r["attempts"])

@docker
def test_retry_on_error():
    r = agent.run_task("retry")
    assert len(r["attempts"]) == 2 and r["attempts"][0]["exit_code"] != 0 and r["output"]

@docker
def test_containment_network_and_secrets(monkeypatch):
    monkeypatch.setenv("FAKE_SECRET_TOKEN", "should-never-reach-sandbox")
    r = agent.run_task("escape")
    probes = r["output"]["containment_probes"]
    assert all(p["blocked"] for p in probes.values()), probes
    kinds = [e for e in agent.LOG if e.get("task_id") == r["task_id"]]
    assert sum(e["kind"] == "containment_blocked" for e in kinds) == len(probes)
    assert not any(e["kind"] == "containment_FAILED" for e in kinds)

@docker
def test_forkbomb_capped():
    r = agent.run_task("forkbomb")
    assert r["output"]["containment_probes"]["fork_bomb"]["blocked"]

@docker
def test_timeout_kills_and_destroys():
    r = agent.run_task("hang", limits=sandbox.Limits(timeout_s=3))
    a = r["attempts"][0]
    assert a["timed_out"] and a["destroyed"] and r["output"] is None

@docker
def test_memory_cap():
    r = sandbox.run("x = bytearray(600*1024*1024)\nprint('allocated')", {})
    assert r.exit_code != 0 and "allocated" not in r.stdout

@docker
def test_human_approval_required():
    r = agent.run_task("recon")
    q = r["pending_approvals"]
    assert q and all(i["status"] in ("awaiting_human", "denied_by_policy") for i in q)
    big = [i for i in q if i["bill_id"] == "B-1005"][0]
    assert big["status"] == "denied_by_policy"
    small = [i for i in q if i["status"] == "awaiting_human"][0]
    res = c.post(f"/approvals/{small['approval_id']}", json={"approve": True, "approver": "CFO"}).json()
    assert res["status"] == "approved" and res["execution"] == "not_executed_no_rail_connected"
    assert c.post(f"/approvals/{small['approval_id']}", json={"approve": True, "approver": "CFO"}).status_code == 409
    assert c.post(f"/approvals/{big['approval_id']}", json={"approve": True, "approver": "CFO"}).status_code == 409

def test_status_endpoint():
    s = c.get("/status").json()
    assert s["llm_mode"] == "mock" and s["llm_base_url"] == "https://api.vultrinference.com/v1"

def test_unknown_scenario():
    assert c.post("/run", json={"scenario": "nope"}).status_code == 400
