"""End-to-end check of the HTTP API against a running `video-grounding serve`, and an example client.

  python scripts/api_smoke.py --base http://127.0.0.1:8800 --video /data/v.mp4 --prompt "A person opens a door"

Runs: job -> poll -> events -> clip -> review (accept first event with adjusted start, reject the rest)
-> dataset -> manifest. Prints API_SMOKE ok|FAIL.
"""
import argparse
import json
import time
import urllib.request


def call(base, method, path, body=None):
    req = urllib.request.Request(base + path, method=method, headers={"Content-Type": "application/json"},
                                 data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        return data if r.headers.get_content_type() == "video/mp4" else json.loads(data)


def wait(base, path, done=("completed", "failed"), timeout=3600):
    t0 = time.time()
    while True:
        s = call(base, "GET", path)
        print(f"  {time.time() - t0:6.0f}s {s['state']} {s.get('progress', '')}", flush=True)
        if s["state"] in done:
            return s
        if time.time() - t0 > timeout:
            raise TimeoutError(path)
        time.sleep(5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8800")
    ap.add_argument("--video", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--prompt")
    g.add_argument("--prompt-file", help="JSON list of {query_id, text}")
    a = ap.parse_args()
    b = a.base
    print("health", call(b, "GET", "/v1/health"))
    body = {"video": a.video}
    if a.prompt_file:
        body["prompts"] = json.load(open(a.prompt_file))
    else:
        body["prompt"] = a.prompt
    job = call(b, "POST", "/v1/jobs", body)["job_id"]
    print("job", job)
    s = wait(b, f"/v1/jobs/{job}")
    assert s["state"] == "completed", s
    events = call(b, "GET", f"/v1/jobs/{job}/events")["events"]
    for e in events:
        print(f"  {e['query_id']:10s} {e['event_start_sec']:7.2f}-{e['event_end_sec']:7.2f} "
              f"p={e['raw_score_max']:.2f} {e['complete']} {e['review_reasons']}")
    if not events:
        print("API_SMOKE ok (no events, review/dataset skipped)")
        return
    clip = call(b, "GET", f"/v1/jobs/{job}/clips/{events[0]['event_id']}")
    assert len(clip) > 1000, len(clip)
    e0 = events[0]
    reviews = [{"event_id": e0["event_id"], "accepted": True,
                "start_sec": e0["event_start_sec"] + 0.5, "end_sec": e0["event_end_sec"]}]
    reviews += [{"event_id": e["event_id"], "accepted": False} for e in events[1:]]
    print("review metrics", call(b, "POST", f"/v1/jobs/{job}/reviews", {"reviews": reviews}))
    ds = call(b, "POST", "/v1/datasets", {"name": "api-smoke", "job_ids": [job], "include_rejected": True})["dataset_id"]
    s = wait(b, f"/v1/datasets/{ds}")
    assert s["state"] == "completed", s
    m = call(b, "GET", f"/v1/datasets/{ds}/manifest")
    print("dataset stats", m["stats"])
    acc = [x for x in m["annotations"] if x["status"] == "accepted"]
    assert len(acc) == 1 and acc[0]["adjusted"] and abs(acc[0]["start_s"] - reviews[0]["start_sec"]) < 1e-6, acc
    name = acc[0]["clip"].rsplit("/", 1)[-1].removesuffix(".mp4")
    assert len(call(b, "GET", f"/v1/datasets/{ds}/clips/{name}")) > 1000
    print("API_SMOKE ok")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 - smoke script: one verdict line
        print("API_SMOKE FAIL", repr(e))
        raise SystemExit(1)
