"""VideoJev adapter (fake engine), exhaustive pipeline semantics, batch endpoint, job filter."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import ClassVar

import pytest
from app.adapters import AdapterError, AdapterUnavailable, ProposalRequest, ProposedInterval
from app.adapters import videojev as vj
from tests.conftest import create_action, create_project, upload_video

# --------------------------------------------------------------------------- #
# Fake `video_grounding` engine (torch is never imported)
# --------------------------------------------------------------------------- #


class _Section:
    def __init__(self, **kw) -> None:
        self.__dict__.update(kw)

    def model_copy(self, update=None):
        return _Section(**{**self.__dict__, **(update or {})})


class FakeEngine:
    """Records calls; behaviour is steered through the class attributes."""

    events: ClassVar[list[dict]] = []
    scan_complete = True
    fail: Exception | None = None
    resume_mismatch = False
    calls: ClassVar[list[tuple]] = []
    backends = 0
    unloaded = 0


@pytest.fixture()
def engine(monkeypatch):
    FakeEngine.events, FakeEngine.scan_complete, FakeEngine.fail = [], True, None
    FakeEngine.resume_mismatch, FakeEngine.calls = False, []
    FakeEngine.backends = FakeEngine.unloaded = 0
    vj._BACKENDS.clear()

    class Backend:
        def unload(self) -> None:
            FakeEngine.unloaded += 1

    def make_backend(settings):
        FakeEngine.backends += 1
        return Backend()

    def _result():
        if FakeEngine.fail:
            raise FakeEngine.fail
        return {"events": FakeEngine.events, "scan_complete": FakeEngine.scan_complete}

    class ResumeMismatch(ValueError):
        pass

    def run_scan(video, queries, settings, out_dir, **kw):
        FakeEngine.calls.append(("scan", video, queries, settings, Path(out_dir), kw))
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "job.sqlite").write_text("x")
        if kw.get("progress"):
            kw["progress"](0.5)
        return _result()

    def resume(out_dir, **kw):
        FakeEngine.calls.append(("resume", Path(out_dir), kw))
        if FakeEngine.resume_mismatch:
            raise ResumeMismatch("config changed")
        return _result()

    mods = {
        "video_grounding": types.ModuleType("video_grounding"),
        "video_grounding.adapters": types.ModuleType("video_grounding.adapters"),
        "video_grounding.adapters.base": types.SimpleNamespace(make_backend=make_backend),
        "video_grounding.models": types.SimpleNamespace(Query=lambda id_, text: (id_, text)),
        "video_grounding.scheduler": types.SimpleNamespace(
            ResumeMismatch=ResumeMismatch, resume=resume, run_scan=run_scan
        ),
        "video_grounding.settings": types.SimpleNamespace(
            Settings=lambda: _Section(
                export=_Section(cut_clips=True), verify=_Section(enabled=True)
            ),
            load_settings=lambda path: _Section(
                export=_Section(cut_clips=True), verify=_Section(enabled=True), path=path
            ),
        ),
    }
    for name, mod in mods.items():
        monkeypatch.setitem(sys.modules, name, mod)
    yield FakeEngine
    vj._BACKENDS.clear()


def _event(start: float, end: float, score: float, reasons=()) -> dict:
    return {
        "event_start_sec": start,
        "event_end_sec": end,
        "raw_score_max": score,
        "review_reasons": list(reasons),
    }


def _request(tmp_path: Path, progress=None) -> ProposalRequest:
    return ProposalRequest(
        video_path=tmp_path / "v.mp4",
        duration_seconds=100.0,
        action_text="a person waves",
        max_candidates=12,
        min_duration_seconds=1.5,
        max_duration_seconds=40.0,
        work_dir=tmp_path / "work",
        progress=progress,
    )


# --------------------------------------------------------------------------- #
# Adapter
# --------------------------------------------------------------------------- #


def test_propose_maps_events_and_disables_engine_clips_and_verify(engine, tmp_path) -> None:
    engine.events = [_event(1, 5, 0.9, ["boundary uncertain"]), _event(20, 25, 0.6)]
    seen: list[float] = []
    out = vj.VideoJevAdapter().propose(_request(tmp_path, progress=seen.append))
    assert out == [
        ProposedInterval(1.0, 5.0, 0.9, "boundary uncertain"),
        ProposedInterval(20.0, 25.0, 0.6, ""),
    ]
    kind, _video, queries, settings, work_dir, kw = engine.calls[0]
    assert (kind, queries, work_dir) == ("scan", [("q1", "a person waves")], tmp_path / "work")
    assert settings.export.cut_clips is False
    assert settings.verify.enabled is False
    assert kw["keep_loaded"] is True
    assert seen == [0.5]


def test_zero_events_is_not_an_error_and_incomplete_scan_is_flagged(engine, tmp_path) -> None:
    assert vj.VideoJevAdapter().propose(_request(tmp_path)) == []
    engine.events, engine.scan_complete = [_event(1, 5, 0.9)], False
    (tmp_path / "work" / "job.sqlite").unlink()
    assert "scan incomplete" in vj.VideoJevAdapter().propose(_request(tmp_path))[0].notes


def test_existing_work_dir_resumes_and_mismatch_restarts(engine, tmp_path) -> None:
    adapter = vj.VideoJevAdapter()
    adapter.propose(_request(tmp_path))
    adapter.propose(_request(tmp_path))
    assert [c[0] for c in engine.calls] == ["scan", "resume"]
    assert engine.backends == 1  # model loaded once per process

    engine.resume_mismatch = True
    adapter.propose(_request(tmp_path))
    assert [c[0] for c in engine.calls] == ["scan", "resume", "resume", "scan"]


def test_engine_failure_is_retryable_and_evicts_backend(engine, tmp_path) -> None:
    engine.fail = RuntimeError("CUDA out of memory")
    with pytest.raises(AdapterError, match="CUDA out of memory") as info:
        vj.VideoJevAdapter().propose(_request(tmp_path))
    assert info.value.retryable is True
    assert engine.unloaded == 1
    assert vj._BACKENDS == {}


def test_missing_engine_is_unavailable(monkeypatch, tmp_path) -> None:
    monkeypatch.setitem(sys.modules, "video_grounding.adapters.base", None)  # forces ImportError
    monkeypatch.setitem(sys.modules, "video_grounding", types.ModuleType("video_grounding"))
    with pytest.raises(AdapterUnavailable):
        vj.VideoJevAdapter().propose(_request(tmp_path))


def test_registry_lists_videojev_without_engine(client, settings, tmp_path) -> None:
    # The API process has no engine installed; the adapter must still be selectable there.
    adapters = {a["name"]: a for a in client.get("/api/v1/adapters").json()["adapters"]}
    assert adapters["videojev"]["available"] is True
    assert adapters["videojev"]["requires_gpu"] is True
    assert vj.VideoJevAdapter(str(tmp_path / "missing.yaml")).is_available() is False


# --------------------------------------------------------------------------- #
# Pipeline: exhaustive semantics
# --------------------------------------------------------------------------- #


class StubAdapter:
    name = "videojev"
    version = "stub"
    requires_gpu = False
    exhaustive = True

    def __init__(self, proposals) -> None:
        self.proposals = proposals
        self.request: ProposalRequest | None = None

    def is_available(self) -> bool:
        return True

    def propose(self, request):
        self.request = request
        request.progress(1.0)
        return self.proposals


def _queue(client, adapter="mock"):
    project = create_project(client)
    action = create_action(client, project["id"])
    video = upload_video(client, project["id"])
    job = client.post(
        f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"], "adapter": adapter}
    ).json()
    return project, action, video, job


def _run(client, worker, monkeypatch, adapter):
    monkeypatch.setattr("app.worker.get_adapter", lambda name, cfg: adapter)
    assert worker.run_once() is True


def test_exhaustive_adapter_keeps_all_events_ranked_by_score(client, worker, monkeypatch) -> None:
    _, _, _, job = _queue(client)
    proposals = [ProposedInterval(i * 20.0, i * 20.0 + 5, i / 100) for i in range(1, 21)]
    stub = StubAdapter(proposals)
    _run(client, worker, monkeypatch, stub)

    done = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert done["status"] == "succeeded"
    assert done["adapter_version"] == stub.version  # provenance carried into exports
    cands = client.get(f"/api/v1/jobs/{job['id']}/candidates").json()
    assert len(cands) == 20  # not truncated to max_candidates_per_job
    assert cands[0]["score"] == 0.2 and cands[0]["rank"] == 1  # highest score first
    assert stub.request.work_dir.name == f"job-{job['id']}"
    assert stub.request.work_dir.parent.name == "engine"


def test_exhaustive_adapter_zero_events_succeeds(client, worker, monkeypatch) -> None:
    _, _, _, job = _queue(client)
    _run(client, worker, monkeypatch, StubAdapter([]))
    done = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert done["status"] == "succeeded" and done["error_code"] is None
    assert client.get(f"/api/v1/jobs/{job['id']}/candidates").json() == []


def test_non_exhaustive_adapter_zero_still_fails(client, worker, monkeypatch) -> None:
    _, _, _, job = _queue(client)
    stub = StubAdapter([])
    stub.exhaustive = False
    _run(client, worker, monkeypatch, stub)
    assert client.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "queued"  # retry scheduled


# --------------------------------------------------------------------------- #
# Batch endpoint + job filter
# --------------------------------------------------------------------------- #


def test_batch_enqueues_one_job_per_ready_video(client) -> None:
    project = create_project(client)
    action = create_action(client, project["id"])
    v1, v2 = upload_video(client, project["id"]), upload_video(client, project["id"], "b.mp4")
    url = f"/api/v1/projects/{project['id']}/actions/{action['id']}/jobs"

    response = client.post(url, json={})
    assert response.status_code == 202
    jobs = response.json()
    assert [j["video_id"] for j in jobs] == [v1["id"], v2["id"]]
    assert {j["action_id"] for j in jobs} == {action["id"]}

    only_second = client.post(url, json={"video_ids": [v2["id"], v2["id"]]}).json()
    assert [j["video_id"] for j in only_second] == [v2["id"]]


def test_batch_validates_scope_and_is_idempotent(client) -> None:
    project, other = create_project(client), create_project(client, "other")
    action = create_action(client, project["id"])
    foreign = upload_video(client, other["id"])
    own = upload_video(client, project["id"])
    url = f"/api/v1/projects/{project['id']}/actions/{action['id']}/jobs"

    bad = client.post(url, json={"video_ids": [foreign["id"]]})
    assert (bad.status_code, bad.json()["code"]) == (409, "PROJECT_MISMATCH")
    assert client.post(url, json={"video_ids": [9999]}).status_code == 404
    assert (
        client.post(
            f"/api/v1/projects/{other['id']}/actions/{action['id']}/jobs", json={}
        ).status_code
        == 409
    )
    assert (
        client.post(f"/api/v1/projects/{project['id']}/actions/9999/jobs", json={}).status_code
        == 404
    )

    headers = {"Idempotency-Key": "batch-1"}
    first = client.post(url, json={}, headers=headers).json()
    again = client.post(url, json={}, headers=headers).json()
    assert [j["id"] for j in first] == [j["id"] for j in again] == [first[0]["id"]]
    assert first[0]["video_id"] == own["id"]


def test_jobs_filter_by_action(client) -> None:
    project = create_project(client)
    a1, a2 = create_action(client, project["id"], "a"), create_action(client, project["id"], "b")
    video = upload_video(client, project["id"])
    for action in (a1, a2):
        client.post(f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"]})
    jobs = client.get("/api/v1/jobs", params={"action_id": a2["id"]}).json()
    assert [j["action_id"] for j in jobs] == [a2["id"]]


def test_idempotency_key_longer_than_100_is_rejected(client):
    r = client.post(
        "/api/v1/projects/1/actions/1/jobs", json={}, headers={"Idempotency-Key": "k" * 101}
    )
    assert r.status_code == 422
