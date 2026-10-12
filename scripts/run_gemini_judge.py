#!/usr/bin/env python3
"""
Invoke Gemini 3.1 Pro to judge and score the Heffalump vs Hermes Cluster Visualizer reviews.
"""

import json
import os
import sys
import time
import urllib.request

REPO_ROOT = "/home/jagosan/repos/cluster-vis"

# Read both reviews
with open(os.path.join(REPO_ROOT, "docs/heffalump_review.md"), "r", encoding="utf-8") as f:
    heffalump_text = f.read()

with open(os.path.join(REPO_ROOT, "docs/hermes_refined_review.md"), "r", encoding="utf-8") as f:
    hermes_text = f.read()

# Load GOOGLE_API_KEY from ~/.hermes/.env
api_key = None
with open("/home/jagosan/.hermes/.env", "r") as f:
    for line in f:
        if line.startswith("GOOGLE_API_KEY="):
            api_key = line.strip().split("=", 1)[1]
            break

if not api_key:
    print("Error: GOOGLE_API_KEY not found in ~/.hermes/.env", file=sys.stderr)
    sys.exit(1)

eval_prompt = f"""You are an elite Principal Distributed Systems Architect, Staff Graphics Engineer, and Chief Information Security Officer acting as an impartial, rigorous judge.

### PROJECT CONTEXT & OBJECTIVE
The objective of the Cluster Visualizer (`cluster-vis`) project is:
"To give humans a way to understand cluster topology in a more physical way, by representing complex distributed systems in 3D space."
The system includes:
- 3D WebGL client (Three.js): Skyscraper elevation (Ingress -> Gateways -> Supervisors -> Workers -> Subterranean Vaults), dynamic Bezier conduits with traffic particles, Latency Force Field mode, Dual/Quad viewports, proportional pod capsules, VPA morphing, HPA conveyor replication, exterior staging yards, Kueue gang pallets, and M/M/c/K discrete-event queuing traffic simulation.
- In-Cluster Python Operator: SSE streaming server, Kubernetes watch informers, in-memory graph, secret scrubbing (sha256 fingerprints), TokenReview/SubjectAccessReview auth.
- Network Probe DaemonSet: Round-robin TCP SYN ping probe measuring inter-node latency.
- Client-side ingestion and CLI dump tools.

### REVIEW ASSIGNMENT
Two independent AI reviewers were tasked with conducting a complete review of Cluster Visualizer focusing on:
1. Performance & Scalability (WebGL draw calls, memory, operator SSE fan-out, probe overhead, etc.)
2. Security & Threat Modeling (RBAC least privilege, secret scrubbing leaks, auth & browser session hygiene, CORS, probe scanning)
3. Usability & Ability to Meet Objective (Physical 3D space vs 2D flat dashboards, cognitive load, operational actionability during outages)
4. Trade-off Analysis & Nuance (Examining real-world compromises rather than naive dismissals)
5. Technical Specification & Roadmap (Actionable next-generation architecture)

Below are the two candidate submissions:

========================================
CANDIDATE A: HEFFALUMP (DeepSeek-V4 284B)
========================================
{heffalump_text}

========================================
CANDIDATE B: HERMES (Hermes Refinement Pass)
========================================
{hermes_text}

========================================
JUDGING INSTRUCTIONS:
Conduct an exhaustive, impartial, and highly technical evaluation of Candidate A and Candidate B.
Score each candidate on a scale of 1 to 20 across the following 5 criteria (Total 100 points):
1. Performance & Scalability Rigor (/20)
2. Security & Threat Modeling Depth (/20)
3. Usability & Fidelity to the Core Objective (/20)
4. Quality and Depth of Trade-Off Surfacing (/20)
5. Technical Specification Precision & Viability (/20)

Structure your judgment as:
1. CRITERION-BY-CRITERION COMPARATIVE ANALYSIS
2. DETAILED SCORING TABLE & BREAKDOWN (Points per criterion, Total /100)
3. KEY STRENGTHS & SHORTCOMINGS OF EACH CANDIDATE
4. FINAL VERDICT & RECOMMENDATIONS FOR THE PROJECT
"""

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent?key={api_key}"

payload = {
    "contents": [
        {
            "parts": [
                {"text": eval_prompt}
            ]
        }
    ],
    "generationConfig": {
        "temperature": 0.2,
        "maxOutputTokens": 4096
    }
}

req_data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})

print("Submitting evaluation to Gemini 3.1 Pro (gemini-3.1-pro-preview)...")
start_time = time.time()

try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - start_time
        print(f"Gemini 3.1 Pro evaluation completed in {elapsed:.2f}s!")
        
        candidates = res.get("candidates", [])
        if not candidates:
            print("Error: No candidates returned from Gemini API", file=sys.stderr)
            sys.exit(1)
            
        content_text = candidates[0]["content"]["parts"][0]["text"]
        usage_metadata = res.get("usageMetadata", {})
        
        out_file = os.path.join(REPO_ROOT, "docs/gemini_3.1_pro_judgment.md")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(content_text)
            
        meta_file = os.path.join(REPO_ROOT, "docs/gemini_3.1_pro_judgment_meta.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump({
                "elapsed_seconds": elapsed,
                "usageMetadata": usage_metadata,
                "model": "gemini-3.1-pro-preview"
            }, f, indent=2)
            
        print(f"Saved Gemini 3.1 Pro judgment to {out_file}")
        print("Usage Metadata:", usage_metadata)
except Exception as e:
    print(f"Error during Gemini 3.1 Pro evaluation: {e}", file=sys.stderr)
    sys.exit(1)
