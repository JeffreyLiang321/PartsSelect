"""
Wait for the Hugging Face Space to finish rebuilding, then health-check it.
Exits non-zero on a build/runtime error, a timeout, or a failed health check,
so a broken deploy fails the GitHub Action instead of failing silently.

Usage: python deploy/hf-space/wait_for_space.py [space_id] [api_base_url]
"""

import sys
import time
import urllib.request

from huggingface_hub import HfApi

SPACE = sys.argv[1] if len(sys.argv) > 1 else "jeffjeff20120112/partselect-agent"
API = sys.argv[2] if len(sys.argv) > 2 else "https://jeffjeff20120112-partselect-agent.hf.space"
TIMEOUT = 600

api = HfApi()
start = time.time()
seen_build = False
last = None

time.sleep(10)  # give the Hub a moment to register the new commit
while time.time() - start < TIMEOUT:
    stage = api.get_space_runtime(SPACE).stage
    if stage != last:
        print(f"{int(time.time() - start):>4}s  {stage}", flush=True)
        last = stage
    if "BUILDING" in stage or "STARTING" in stage:
        seen_build = True
    if stage in ("BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR"):
        sys.exit(f"Space failed: {stage}. Check the Space's logs on huggingface.co.")
    if stage == "RUNNING" and seen_build:
        break
    if stage == "RUNNING" and time.time() - start > 90:
        # hf upload skips the commit when no files changed, so no rebuild happens
        print("No rebuild detected (nothing changed); checking the running app.")
        break
    time.sleep(10)
else:
    sys.exit("Timed out waiting for the Space to rebuild.")

with urllib.request.urlopen(f"{API}/api/health", timeout=30) as r:
    body = r.read().decode()
    if r.status != 200 or '"ok"' not in body:
        sys.exit(f"Health check failed: {r.status} {body}")
print("Health check passed:", body)
