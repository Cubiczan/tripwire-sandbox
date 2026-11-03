"""LLM client. All calls go through an OpenAI-compatible client pointed at Vultr Serverless Inference.

MOCK MODE: when VULTR_INFERENCE_API_KEY is unset (or TRIPWIRE_LLM_MODE=mock) a deterministic,
offline mock returns canned code. Mock output is labelled "mock" everywhere it is surfaced.
"""
from __future__ import annotations
import os

VULTR_BASE_URL = "https://api.vultrinference.com/v1"
DEFAULT_MODEL = os.getenv("VULTR_MODEL", "llama-3.3-70b-instruct-fp8")

SYSTEM = ("You are an accounts-payable reconciliation agent. Write a single Python 3 script. "
          "A global DATA = {'bills': [...], 'payments': [...]} is pre-defined. Use only the standard library. "
          "Print exactly one JSON object on the last line with keys: matched, mismatched, duplicates, "
          "unmatched_payments, unpaid_bills, proposed_payments (list of {bill_id, vendor_id, amount, country, reason}). "
          "Return only code, no markdown.")


def mode() -> str:
    if os.getenv("TRIPWIRE_LLM_MODE") == "mock" or not os.getenv("VULTR_INFERENCE_API_KEY"):
        return "mock"
    return "live"


class LLM:
    def __init__(self):
        self.mode = mode()
        self.calls: list[dict] = []
        self._client = None
        if self.mode == "live":
            from openai import OpenAI
            self._client = OpenAI(base_url=VULTR_BASE_URL, api_key=os.environ["VULTR_INFERENCE_API_KEY"])

    def write_code(self, task: str, scenario: str, attempt: int, last_error: str | None) -> str:
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]
        if last_error:
            msgs.append({"role": "user", "content": f"Previous attempt failed:\n{last_error[-1500:]}\nFix it."})
        self.calls.append({"mode": self.mode, "attempt": attempt, "base_url": VULTR_BASE_URL})
        if self.mode == "live":
            r = self._client.chat.completions.create(model=DEFAULT_MODEL, messages=msgs, temperature=0.1)
            return strip_fences(r.choices[0].message.content or "")
        from app import mock_llm
        return mock_llm.code_for(scenario, attempt)


def strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else ""
        s = s.rsplit("```", 1)[0]
    return s.strip()
