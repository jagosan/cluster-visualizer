#!/usr/bin/env python3
"""
Jagular Swarm Delegator:
Dispatches coding and synthesis tasks directly to Jagular (177B Big Iron on Chunkito)
at http://100.71.183.123:11434/v1, extracts generated code, and applies it cleanly.
"""

import sys
import os
import json
import urllib.request
import urllib.error

CHUNKITO_URL = "http://100.71.183.123:11434/v1/chat/completions"

def call_jagular(system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 4096) -> str:
    payload = {
        "model": "flash-next",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
        "stream": True
    }
    req = urllib.request.Request(
        CHUNKITO_URL,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8")
    )
    full_content = []
    with urllib.request.urlopen(req, timeout=600) as resp:
        for line in resp:
            line = line.decode("utf-8").strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0]["delta"]
                content = delta.get("content", "")
                if content:
                    full_content.append(content)
                    sys.stdout.write(content)
                    sys.stdout.flush()
            except Exception:
                pass
    sys.stdout.write("\n")
    sys.stdout.flush()
    return "".join(full_content)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: jagular_agent.py <prompt>")
        sys.exit(1)
    prompt = sys.argv[1]
    ans = call_jagular("You are Jagular, the deep synthesizer and code generator on Chunkito.", prompt)
    print(ans)
