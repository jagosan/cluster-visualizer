#!/usr/bin/env python3
import subprocess
import re

cmd = ["ssh", "chunkito", "docker logs --since '2h' llama-moe-rocm72 2>&1"]
res = subprocess.run(cmd, capture_output=True, text=True)

tasks = {}
for line in res.stdout.splitlines():
    # Prompt tokens
    m_p = re.search(r"task (\d+) \| prompt eval time =.*?/\s*(\d+) tokens", line)
    if m_p:
        t_id, toks = m_p.group(1), int(m_p.group(2))
        tasks.setdefault(t_id, {})["prompt_tokens"] = toks

    # Completion / eval tokens
    m_e = re.search(r"task (\d+) \|\s+eval time =.*?/\s*(\d+) tokens", line)
    if m_e:
        t_id, toks = m_e.group(1), int(m_e.group(2))
        tasks.setdefault(t_id, {})["completion_tokens"] = toks

    # Total time
    m_t = re.search(r"task (\d+) \|\s+total time =\s*([\d\.]+) ms", line)
    if m_t:
        t_id, ms = m_t.group(1), float(m_t.group(2))
        tasks.setdefault(t_id, {})["duration_ms"] = ms

print(f"Parsed {len(tasks)} distinct tasks from Chunkito:")
tot_p = 0
tot_c = 0
for tid, data in sorted(tasks.items()):
    p = data.get("prompt_tokens", 0)
    c = data.get("completion_tokens", 0)
    ms = data.get("duration_ms", 0.0)
    tot_p += p
    tot_c += c
    print(f"  Task {tid}: prompt={p} tokens, completion={c} tokens, duration={ms/1000:.2f}s")

print(f"\nTOTAL Prompt Tokens:     {tot_p:,}")
print(f"TOTAL Completion Tokens: {tot_c:,}")
print(f"GRAND TOTAL Tokens:      {tot_p + tot_c:,}")
