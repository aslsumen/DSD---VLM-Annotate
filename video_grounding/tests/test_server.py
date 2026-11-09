import json
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from _media import make_video, needs_ffmpeg
from conftest import make_settings
from video_grounding.adapters.base import SyntheticBackend
from video_grounding.server import create_app

pytestmark = needs_ffmpeg


def _app(root, media=None):
    return create_app(make_settings(export={"cut_clips": True}), root, media_root=media,
                      backend=SyntheticBackend({"q_event": [(12, 18)]}))


def _wait(c, url, key="state", done="completed"):
    for _ in range(600):
        j = c.get(url).json()
        assert j[key] != "failed", j
        if j[key] == done:
            return j
        time.sleep(0.1)
    raise AssertionError(f"timeout: {j}")


def _job(c, video, **kw):
    r = c.post("/v1/jobs", json={"video": video, **kw})
    assert r.status_code == 202, r.text
    return r.json()["job_id"]


PROMPTS = [{"query_id": "q_event", "text": "x"}, {"query_id": "q_none", "text": "y"}]


def test_full_flow(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    video = make_video(media / "v.mp4", dur=40)
    with TestClient(_app(tmp_path / "root", media)) as c:
        assert c.get("/v1/health").json()["status"] == "ok"
        # input validation
        outside = make_video(tmp_path / "outside.mp4", dur=2)
        assert c.post("/v1/jobs", json={"video": outside, "prompt": "x"}).status_code == 400
        assert c.post("/v1/jobs", json={"video": "file:///etc/passwd", "prompt": "x"}).status_code == 400
        assert c.post("/v1/jobs", json={"video": video}).status_code == 400
        assert c.post("/v1/jobs", json={"video": video, "prompt": "x", "prompts": PROMPTS}).status_code == 400
        dup = [PROMPTS[0], PROMPTS[0]]
        assert c.post("/v1/jobs", json={"video": video, "prompts": dup}).status_code == 400

        jid = _job(c, video, prompts=PROMPTS)
        job = _wait(c, f"/v1/jobs/{jid}")
        assert job["scan_complete"] and job["progress"]
        assert [j["job_id"] for j in c.get("/v1/jobs").json()] == [jid]
        assert c.get("/v1/jobs/job_nope/events").status_code == 404
        doc = c.get(f"/v1/jobs/{jid}/events").json()
        evs = [e for e in doc["events"] if e["query_id"] == "q_event"]
        assert len(evs) >= 1 and not [e for e in doc["events"] if e["query_id"] == "q_none"]
        ev = evs[0]
        clip = c.get(f"/v1/jobs/{jid}/clips/{ev['event_id']}")
        assert clip.status_code == 200 and len(clip.content) > 0
        assert c.get(f"/v1/jobs/{jid}/clips/..%2Fjob.sqlite").status_code == 404

        s, e = ev["event_start_sec"] + 1, ev["event_end_sec"] - 1
        r = c.post(f"/v1/jobs/{jid}/reviews", json={"reviews": [
            {"event_id": ev["event_id"], "accepted": True, "start_sec": s, "end_sec": e}]})
        assert r.status_code == 200 and r.json()["n_accepted"] == 1, r.text
        assert c.post(f"/v1/jobs/{jid}/reviews", json={"reviews": [
            {"event_id": "evt_unknown", "accepted": True}]}).status_code == 400
        assert c.post(f"/v1/jobs/{jid}/reviews", json={"reviews": [
            {"event_id": ev["event_id"], "accepted": True, "start_sec": e, "end_sec": s}]}).status_code == 400
        assert c.get(f"/v1/jobs/{jid}/reviews").json()["reviews"][0]["start_sec"] == s
        assert c.post(f"/v1/jobs/{jid}/retry").status_code == 409  # completed

        assert c.post("/v1/datasets", json={"name": "d", "job_ids": ["job_nope"]}).status_code == 404
        ds = c.post("/v1/datasets", json={"name": "d1", "job_ids": [jid]}).json()["dataset_id"]
        _wait(c, f"/v1/datasets/{ds}")
        man = c.get(f"/v1/datasets/{ds}/manifest").json()
        assert man["stats"] == {"n_annotations": 1, "n_accepted": 1, "n_rejected": 0,
                                "n_unreviewed": len(doc["events"]) - 1}
        a = man["annotations"][0]
        assert a["adjusted"] and a["status"] == "accepted" and (a["start_s"], a["end_s"]) == (s, e)
        assert (tmp_path / "root" / "datasets" / ds / a["clip"]).stat().st_size > 0
        assert c.get(f"/v1/datasets/{ds}/clips/{a['clip'][6:-4]}").status_code == 200


def test_url_download_and_restart_recovery(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    video = make_video(media / "v.mp4", dur=40)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(media)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    root = tmp_path / "root"
    try:
        with TestClient(_app(root)) as c:
            jid = _job(c, f"http://127.0.0.1:{srv.server_port}/v.mp4", prompts=PROMPTS)
            _wait(c, f"/v1/jobs/{jid}")
            assert (root / "jobs" / jid / "source.mp4").stat().st_size > 0
            bad = _job(c, f"http://127.0.0.1:{srv.server_port}/missing.mp4", prompt="x")
            for _ in range(100):
                if c.get(f"/v1/jobs/{bad}").json()["state"] == "failed":
                    break
                time.sleep(0.1)
            j = c.get(f"/v1/jobs/{bad}").json()
            assert j["state"] == "failed" and "404" in j["error"]
            assert c.post(f"/v1/jobs/{bad}/retry").status_code == 202  # worker survived, retry re-enqueues
    finally:
        srv.shutdown()
    # restart: a queued job (request.json only) is picked up by a new app
    d = root / "jobs" / "job_aaaaaaaaaaaa"
    d.mkdir()
    (d / "request.json").write_text(json.dumps({"video": video, "queries": [{"query_id": "q_event", "text": "x"}]}))
    with TestClient(_app(root)) as c:
        _wait(c, "/v1/jobs/job_aaaaaaaaaaaa")
        assert c.get("/v1/jobs/job_aaaaaaaaaaaa/events").json()["events"]
