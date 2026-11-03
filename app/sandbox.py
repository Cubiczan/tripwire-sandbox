"""Throwaway Docker sandbox for agent-generated code.

Every task runs in a NEW container that is destroyed afterwards (--rm + explicit `docker rm -f`).
Code and data go in over stdin; nothing from the host env, filesystem or network is shared.
"""
from __future__ import annotations
import json, os, shutil, subprocess, uuid
from dataclasses import dataclass, asdict

IMAGE = os.getenv("SANDBOX_IMAGE", "python:3.12-slim")
DOCKER = os.getenv("DOCKER_BIN", "docker")
# The base image bakes in ENV vars (e.g. GPG_KEY, a public signing-key fingerprint). The runner wipes the
# environment down to PATH before agent code runs, so nothing secret-looking is visible inside.
RUNNER = ("import os,sys,json;_p=os.environ.get('PATH');os.environ.clear();os.environ['PATH']=_p;"
          "p=json.load(sys.stdin);"
          "exec(compile(p['code'],'agent_code.py','exec'),{'DATA':p['data'],'__name__':'__main__'})")


@dataclass
class Limits:
    memory: str = "256m"; cpus: str = "0.5"; pids: int = 64; timeout_s: int = 15; tmpfs_size: str = "16m"


@dataclass
class Result:
    container: str; exit_code: int; stdout: str; stderr: str; timed_out: bool; destroyed: bool; argv: list[str]
    def to_dict(self): return asdict(self)


def build_argv(name: str, lim: Limits) -> list[str]:
    return [DOCKER, "run", "--rm", "-i", "--name", name,
            "--network", "none",
            "--read-only", "--tmpfs", f"/tmp:rw,nosuid,nodev,size={lim.tmpfs_size}",
            "--memory", lim.memory, "--memory-swap", lim.memory, "--cpus", lim.cpus,
            "--pids-limit", str(lim.pids),
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--user", "65534:65534", "--workdir", "/tmp",
            "--env-file", "/dev/null",  # explicit: no env passed in
            IMAGE, "python", "-I", "-c", RUNNER]


def docker_available() -> bool:
    if not shutil.which(DOCKER):
        return False
    return subprocess.run([DOCKER, "info"], capture_output=True).returncode == 0


def run(code: str, data: dict, lim: Limits | None = None) -> Result:
    lim = lim or Limits()
    name = f"tw-sbx-{uuid.uuid4().hex[:12]}"
    argv = build_argv(name, lim)
    payload = json.dumps({"code": code, "data": data})
    timed_out = False
    try:
        # clean env for the docker CLI itself so nothing can leak via argv/env expansion
        p = subprocess.run(argv, input=payload, capture_output=True, text=True, timeout=lim.timeout_s,
                           env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                                **({"DOCKER_HOST": os.environ["DOCKER_HOST"]} if "DOCKER_HOST" in os.environ else {})})
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        timed_out, rc = True, 124
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = f"sandbox timeout after {lim.timeout_s}s"
    subprocess.run([DOCKER, "rm", "-f", name], capture_output=True)
    gone = subprocess.run([DOCKER, "inspect", name], capture_output=True).returncode != 0
    return Result(name, rc, out[-20000:], err[-5000:], timed_out, gone, argv[:-1] + ["<runner>"])
