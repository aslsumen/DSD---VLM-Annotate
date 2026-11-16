"""Real-model smoke test of the videojev adapter over HTTP, on a GPU host.

Needs a running API and a worker started with VLM_VLM_ADAPTER=videojev (see
docs/INSTALLATION_MANUAL.md 5.1). Uploads the given videos, queues one action on all
of them with the batch endpoint, follows job progress, reviews one candidate and
exports. Unlike scripts/smoke_e2e.py nothing is mocked, so it takes minutes per video.

    python scripts/smoke_videojev.py --base-url http://127.0.0.1:8765 \
        --action "person opens a door" a.mp4 b.mp4
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import httpx

TERMINAL = {"succeeded", "failed", "cancelled"}
failures: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)
    if not ok:
        failures.append(name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--action", required=True)
    ap.add_argument("--timeout-min", type=float, default=180)
    ap.add_argument("videos", nargs="+", type=Path)
    a = ap.parse_args()
    c = httpx.Client(base_url=f"{a.base_url}/api/v1", timeout=120)

    project = c.post("/projects", json={"name": f"videojev smoke {int(time.time())}"}).json()
    action = c.post(f"/projects/{project['id']}/actions",
                    json={"name": a.action, "description": a.action}).json()
    for v in a.videos:
        with v.open("rb") as f:
            r = c.post(f"/projects/{project['id']}/videos", files={"file": (v.name, f, "video/mp4")})
        check(f"upload {v.name}", r.status_code == 201 and r.json()["status"] == "ready", r.text[:200])

    url = f"/projects/{project['id']}/actions/{action['id']}/jobs"
    body = {"adapter": "videojev"}
    jobs = c.post(url, json=body, headers={"Idempotency-Key": "smoke"})
    check("batch enqueue (202)", jobs.status_code == 202, jobs.text[:200])
    jobs = jobs.json()
    check("one job per video", len(jobs) == len(a.videos), len(jobs))
    again = c.post(url, json=body, headers={"Idempotency-Key": "smoke"}).json()
    check("idempotent replay returns the same jobs", [j["id"] for j in again] == [j["id"] for j in jobs])

    seen: dict[int, list[float]] = {j["id"]: [] for j in jobs}
    deadline = time.time() + a.timeout_min * 60
    while time.time() < deadline:
        cur = c.get("/jobs", params={"action_id": action["id"], "limit": 200}).json()
        for j in cur:
            if not seen[j["id"]] or seen[j["id"]][-1] != j["progress"]:
                seen[j["id"]].append(j["progress"])
        if all(j["status"] in TERMINAL for j in cur):
            break
        time.sleep(2)
    check("action_id filter returns exactly this batch", sorted(j["id"] for j in cur) == sorted(seen))

    summary = []
    for j in cur:
        cands = c.get(f"/jobs/{j['id']}/candidates").json()
        p = seen[j["id"]]
        check(f"job {j['id']} succeeded", j["status"] == "succeeded", j.get("error_message") or "")
        check(f"job {j['id']} progress moved and is monotonic", len(p) >= 3 and p == sorted(p), p[:3] + p[-2:])
        check(f"job {j['id']} clips ready", all(x["clip_status"] == "ready" for x in cands))
        check(f"job {j['id']} ranked by score", [x["score"] for x in cands] == sorted(
            (x["score"] for x in cands), reverse=True))
        wall = (time.mktime(time.strptime(j["finished_at"][:19], "%Y-%m-%dT%H:%M:%S"))
                - time.mktime(time.strptime(j["started_at"][:19], "%Y-%m-%dT%H:%M:%S"))) if j["finished_at"] else None
        summary.append({"job": j["id"], "video_id": j["video_id"], "status": j["status"], "wall_s": wall,
                        "adapter": [j["adapter_name"], j["adapter_version"]],
                        "candidates": [[x["start_seconds"], x["end_seconds"], round(x["score"], 3),
                                        x["model_notes"]] for x in cands]})
    print(json.dumps(summary, indent=1), flush=True)

    top = next((c.get(f"/jobs/{s['job']}/candidates").json()[0] for s in summary if s["candidates"]), None)
    if top is not None:
        r = c.put(f"/candidates/{top['id']}/annotation", json={"verdict": "true_positive", "reviewer": "smoke"})
        check("annotation stored", r.status_code == 200, r.text[:200])
        export = c.post(f"/projects/{project['id']}/exports", json={}).json()["export"]
        for _ in range(60):
            export = c.get(f"/exports/{export['id']}").json()
            if export["status"] in {"ready", "failed"}:
                break
            time.sleep(5)
        check("export ready with the reviewed item", export["status"] == "ready" and export["item_count"] == 1,
              export["status"])
        if export["status"] == "ready":
            z = zipfile.ZipFile(io.BytesIO(c.get(f"/exports/{export['id']}/download").content))
            check("archive has manifest and labels", {"manifest.json", "labels.csv"} <= set(z.namelist()))
    print("SMOKE", "FAILED: " + ", ".join(failures) if failures else "PASSED", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
