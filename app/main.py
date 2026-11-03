from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from app import agent, sandbox, llm

app = FastAPI(title="Tripwire Sandbox")
STATIC = Path(__file__).parent / "static"


class RunReq(BaseModel):
    scenario: str = "recon"


class Decision(BaseModel):
    approve: bool
    approver: str


@app.get("/")
def index(): return FileResponse(STATIC / "index.html")


@app.get("/status")
def status():
    return {"llm_mode": llm.mode(), "llm_base_url": llm.VULTR_BASE_URL, "model": llm.DEFAULT_MODEL,
            "docker": sandbox.docker_available(), "sandbox_mode": sandbox.mode(), "sandbox_image": sandbox.IMAGE,
            "note": "mock = offline canned model output, not Vultr inference" if llm.mode() == "mock" else "live Vultr inference"}


@app.post("/run")
def run(r: RunReq):
    if r.scenario not in {"recon", "retry", "escape", "forkbomb", "hang"}:
        raise HTTPException(400, "unknown scenario")
    return agent.run_task(r.scenario)


@app.get("/approvals")
def approvals(): return list(agent.APPROVALS.values())


@app.post("/approvals/{aid}")
def decide(aid: str, d: Decision):
    if aid not in agent.APPROVALS: raise HTTPException(404)
    try: return agent.decide(aid, d.approve, d.approver)
    except ValueError as e: raise HTTPException(409, str(e))


@app.get("/log")
def log(): return agent.LOG[-300:]
