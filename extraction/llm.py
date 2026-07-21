"""Provider-agnostic LLM access. Swap providers with one env var.

  LLM_PROVIDER = gemini | anthropic | openai | mock   (default: gemini)
  GEMINI_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY
  LLM_MODEL overrides the per-provider default model.

Every provider implements: generate(prompt, images_b64=None, system=None) -> str
Raw REST via requests — no per-vendor SDKs, so this file IS the abstraction.
"""

import json
import os
import time

import requests

TIMEOUT = 120


class LLMError(RuntimeError):
    pass


def _retrying(fn):
    def wrapper(*a, **k):
        last = None
        for attempt in range(3):
            try:
                return fn(*a, **k)
            except (requests.RequestException, LLMError) as e:
                last = e
                time.sleep(2 * (attempt + 1))
        raise LLMError(f"LLM call failed after retries: {last}")
    return wrapper


class GeminiLLM:
    def __init__(self):
        self.key = os.environ.get("GEMINI_API_KEY")
        if not self.key:
            raise LLMError("GEMINI_API_KEY not set")
        self.model = os.environ.get("LLM_MODEL", "gemini-2.5-flash")

    @_retrying
    def generate(self, prompt, images_b64=None, system=None):
        parts = []
        for img in images_b64 or []:
            parts.append({"inline_data": {"mime_type": "image/png", "data": img}})
        parts.append({"text": prompt})
        body = {"contents": [{"parts": parts}],
                "generationConfig": {"temperature": 0.0, "response_mime_type": "application/json"}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            params={"key": self.key}, json=body, timeout=TIMEOUT)
        if r.status_code != 200:
            raise LLMError(f"Gemini {r.status_code}: {r.text[:300]}")
        data = r.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise LLMError(f"Gemini unexpected response: {json.dumps(data)[:300]}")


class AnthropicLLM:
    def __init__(self):
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.key:
            raise LLMError("ANTHROPIC_API_KEY not set")
        self.model = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")

    @_retrying
    def generate(self, prompt, images_b64=None, system=None):
        content = []
        for img in images_b64 or []:
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": "image/png", "data": img}})
        content.append({"type": "text", "text": prompt})
        body = {"model": self.model, "max_tokens": 8000, "temperature": 0,
                "messages": [{"role": "user", "content": content}]}
        if system:
            body["system"] = system
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                          json=body, timeout=TIMEOUT)
        if r.status_code != 200:
            raise LLMError(f"Anthropic {r.status_code}: {r.text[:300]}")
        return "".join(b.get("text", "") for b in r.json()["content"])


class OpenAILLM:
    def __init__(self):
        self.key = os.environ.get("OPENAI_API_KEY")
        if not self.key:
            raise LLMError("OPENAI_API_KEY not set")
        self.model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    @_retrying
    def generate(self, prompt, images_b64=None, system=None):
        content = [{"type": "text", "text": prompt}]
        for img in images_b64 or []:
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img}"}})
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": content}]
        r = requests.post("https://api.openai.com/v1/chat/completions",
                          headers={"Authorization": f"Bearer {self.key}"},
                          json={"model": self.model, "temperature": 0, "messages": messages},
                          timeout=TIMEOUT)
        if r.status_code != 200:
            raise LLMError(f"OpenAI {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]


class OracleMockLLM:
    """No-API test double. Answers extraction prompts using ground_truth.json,
    so the ENTIRE pipeline (documents -> extraction -> coding -> evaluation)
    can be wired and tested without any API key. Requires GT_PATH env var.
    Obviously scores ~100% — it exists to prove the plumbing, not the model."""

    def __init__(self):
        gt_path = os.environ.get("GT_PATH")
        if not gt_path or not os.path.exists(gt_path):
            raise LLMError("mock provider needs GT_PATH pointing to ground_truth.json")
        with open(gt_path) as f:
            self.gt = {g["patient_id"]: g["expected_extraction"] for g in json.load(f)}

    def generate(self, prompt, images_b64=None, system=None):
        # find which patient this prompt is about via UHID or Pxxx marker
        for pid, exp in self.gt.items():
            uhid = (exp.get("patient") or {}).get("uhid", "")
            if pid in prompt or (uhid and uhid in prompt):
                out = {
                    "patient": exp["patient"],
                    "encounter": exp["encounter"],
                    "diagnoses": [{"text": d["text"]} for d in exp["diagnoses"]],
                    "procedures": [{"text": p["text"]} for p in exp["procedures"]],
                    "medications_on_discharge": exp["medications_on_discharge"],
                    "labs": exp["labs"],
                    "billing": exp["billing"],
                    "coverage": exp["coverage"],
                }
                return json.dumps(out)
        # coding-selection prompts: pick the first candidate code
        if "CANDIDATES" in prompt:
            first = prompt.split("CANDIDATES")[1].strip().splitlines()
            for line in first:
                if "|" in line:
                    return json.dumps({"code": line.split("|")[0].strip()})
        return "{}"


def get_llm():
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    return {"gemini": GeminiLLM, "anthropic": AnthropicLLM,
            "openai": OpenAILLM, "mock": OracleMockLLM}[provider]()
