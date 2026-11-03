# Submission: Vultr Agent Rush, Blast Radius Zero

**Title:** Tripwire Sandbox: an AP agent whose code can't hurt you

**Short description (≤200 chars):**
A finance agent writes and runs AP reconciliation code in a throwaway, network-less Docker sandbox on Vultr. It retries on errors, and a person approves every payment.

**Long description:**
Finance teams want agents that write code to reconcile vendor bills against payments, but model-written code is untrusted. Tripwire Sandbox runs every piece of agent-generated code in a fresh Docker container with no network, no secrets or env, a read-only filesystem plus a small tmpfs, and memory, CPU, PID and time caps. The container is destroyed after each task. When the code fails, the agent feeds the error back to the model and retries. The reconciliation output (matches, short payments, duplicates, unknown-vendor payments and unpaid bills) becomes proposed payments. Those pass a deterministic policy gate reused from our Tripwire project, then wait for a CFO's approval. Payments the policy denies can't be approved, and no payment rail is connected, so approvals record intent only.

The containment demo has the agent's code try DNS, TCP and HTTP exfiltration, read env secrets and secret files, write to the root filesystem, fork-bomb and spin forever. Every attempt is blocked and logged. While building it, the test caught a baked-in image ENV var (a public GPG key fingerprint), and we now wipe the env before agent code runs.

All LLM calls go through an OpenAI-compatible client pointed at Vultr Serverless Inference (`https://api.vultrinference.com/v1`). The app deploys to a Vultr Cloud Compute Ubuntu VM with Docker Compose. *Status at time of writing: the demo and screenshots use a clearly labelled offline mock model, because the Vultr credit and key were not yet issued, and the VM deploy has not run yet.* [Update this line once live.]

**Tags:** Vultr, Serverless Inference, AI Agents, Sandboxing, Docker, FastAPI, Fintech, Accounts Payable, Human-in-the-loop, Security

**Repo:** https://github.com/Cubiczan/tripwire-sandbox
**Demo video:** TODO
**Live app:** TODO (Vultr VM)

## Slide deck outline
1. **Title:** Tripwire Sandbox, Blast Radius Zero for finance agents
2. **Problem:** agents writing code against AP data, where a wrong, injected or runaway script means money or data leaving
3. **Use case:** weekly bill-vs-payment reconciliation for a CFO (sample retail/distribution vendors)
4. **Architecture:** UI → FastAPI → agent loop → Vultr Serverless Inference; code → per-task sandbox → policy → human approval
5. **The sandbox:** the flags table (`--network none`, read-only + tmpfs, mem/cpu/pids caps, cap-drop, non-root, no env, timeout, destroyed)
6. **Live demo 1:** reconciliation finds a short payment, a duplicate, an unknown vendor and unpaid bills
7. **Live demo 2:** retry, where a buggy first script fails and the agent fixes it on attempt 2
8. **Live demo 3:** containment, with 8 probes blocked and logged (network, secrets, fs write, fork bomb, timeout)
9. **Human in the loop:** policy denies $7,200 over the cap; the CFO approves the rest; no rail = intent only
10. **Vultr services:** Serverless Inference (OpenAI-compatible), Cloud Compute VM + Docker Compose
11. **What we learned:** the image ENV leak caught by our own test; the trust boundary of the Docker socket
12. **Next:** gVisor/rootless runtime, persistent audit log, connect a payment rail behind the approval gate
