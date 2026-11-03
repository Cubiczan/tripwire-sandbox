"""Run all scenarios locally and print the audit log. Mock LLM unless VULTR_INFERENCE_API_KEY is set."""
import json, sys
sys.path.insert(0, ".")
from app import agent, llm
print("LLM mode:", llm.mode())
for s in ["recon", "retry", "escape", "forkbomb", "hang"]:
    r = agent.run_task(s)
    print(f"\n== {s}: attempts={len(r['attempts'])} ok={r['output'] is not None}")
    print(json.dumps(r["output"], indent=1)[:1500])
print("\n== audit log")
for e in agent.LOG: print(json.dumps(e))
