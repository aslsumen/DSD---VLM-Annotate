"""Long-video accuracy benchmark: YouCook2 (cooking) and ROAD (driving), videos of 5 to 30 minutes.

VideoJev was trained on Charades-STA, so these two sets are the main accuracy check. Every video is run
on its own (no concatenation). Intervals come from a bootstrap over source videos.

  select DIR YC_JSON ROAD_DIR   # build DIR/heldout_{youcook2,road}.json from the annotation files
  prep SEL_DIR OUT              # download + normalise videos into OUT/{yc,road}/<video>/
  score OUT [RUN]               # KPIs with 95% CIs, before and after Gemini verify

Cooking: validation-split videos in the pinned HF mirror, shuffled with SEED and taken until about TARGET
events; prompts are that video's steps plus 3 steps from other recipes (absent prompts). Driving: every ROAD
video (Oxford RobotCar) in the length range, 20 of 22; events are runs of the per-frame ego-vehicle action label (12 fps), same-label runs under 1 s
apart joined. ROAD_DIR holds road_{trainval,test}_v1.0.json and videos_*.txt ("name.mp4 drive_file_id").
"""

from __future__ import annotations

import itertools
import json
import random
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from composite_bench import _YC, _assemble, _merge  # noqa: E402

SEED, TARGET, MIN_SEC, MAX_SEC, ROAD_FPS = 0, 300, 300, 1800, 12
_HF_TREE = "https://huggingface.co/api/datasets/lccshunli/youcook2-videos-only/tree/" + _YC.rstrip("/").rsplit("/", 1)[-1]
_STOP = set("""a an and the of to in on into onto with for from over until then them it its some all more few up out off
add put cut mix place pour stir cook heat fry boil bake serve set aside remove make use top cover leave let take
bowl pan pot plate tray dish mixture pieces piece small large well together inside little each""".split())
# ROAD av_action_labels -> prompt. AV-Mov (plain driving) is the background, not an event.
_ROAD_LABELS = {"AV-Stop": "stop", "AV-TurLft": "turn_left", "AV-TurRht": "turn_right",
                "AV-MovLft": "move_left", "AV-MovRht": "move_right", "AV-Ovtak": "overtake"}
_ROAD_PROMPTS = {"stop": "the ego vehicle is stopped",
                 "turn_left": "the ego vehicle turns left",
                 "turn_right": "the ego vehicle turns right",
                 "move_left": "the ego vehicle moves over to the left, changing lanes",
                 "move_right": "the ego vehicle moves over to the right, changing lanes",
                 "overtake": "the ego vehicle overtakes another vehicle",
                 "absent_collision": "the ego vehicle collides with another vehicle"}


def _words(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]+", s.lower()) if t not in _STOP and len(t) > 2}


def road_events(frame_labels: list[int], names: list[str]) -> list[dict]:
    """Runs of one ego action label -> events in seconds; -1 (black / unannotated) and AV-Mov are skipped."""
    runs, i = [], 0
    for k, g in itertools.groupby(frame_labels):
        n = len(list(g))
        if 0 <= k < len(names) and names[k] in _ROAD_LABELS:
            runs.append((_ROAD_LABELS[names[k]], i / ROAD_FPS, (i + n) / ROAD_FPS))
        i += n
    return [{"query_id": q, "start_sec": s, "end_sec": e} for q, s, e in _merge(runs)]


def select(out: Path, yc_json: Path, road_dir: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    db = json.loads(yc_json.read_text())["database"]
    mirror = {f["path"].rsplit(".", 1)[0] for f in json.load(urllib.request.urlopen(_HF_TREE + "?recursive=1"))}
    pool = sorted(k for k, x in db.items() if k in mirror and x["subset"] == "validation"
                  and MIN_SEC <= x["duration"] <= MAX_SEC)
    rng.shuffle(pool)
    vids = []
    for v in pool:
        if sum(len(x["events"]) for x in vids) >= TARGET:
            break
        steps: dict[str, list] = {}
        for a in db[v]["annotations"]:
            steps.setdefault(a["sentence"].strip().lower(), []).append(a["segment"])
        mine = set().union(*(_words(s) for s in steps))
        others = sorted({a["sentence"].strip().lower() for k in db if db[k]["recipe_type"] != db[v]["recipe_type"]
                         for a in db[k]["annotations"]})
        # ponytail: word-overlap filter for absent prompts; an unlisted action can still happen on screen.
        absent = rng.sample([s for s in others if not (_words(s) & mine)], 3)
        prompts = [{"query_id": f"s{i}", "text": s} for i, s in enumerate(steps)]
        prompts += [{"query_id": f"absent{i}", "text": s} for i, s in enumerate(absent)]
        gt = [{"query_id": q, "start_sec": float(s), "end_sec": float(e)}
              for q, s, e in _merge([(f"s{i}", *seg) for i, segs in enumerate(steps.values()) for seg in segs])]
        vids.append({"id": v, "subset": db[v]["subset"], "recipe_type": db[v]["recipe_type"],
                     "duration": db[v]["duration"], "prompts": prompts, "events": gt})
    (out / "heldout_youcook2.json").write_text(json.dumps({"seed": SEED, "min_sec": MIN_SEC, "max_sec": MAX_SEC, "videos": vids}, indent=1))
    print(f"youcook2: {len(vids)} videos, {sum(len(v['events']) for v in vids)} events, "
          f"{sum(v['duration'] for v in vids) / 3600:.2f} h")

    ids = dict(l.split()[:2] for f in road_dir.glob("videos_*.txt") for l in f.read_text().splitlines() if l.strip())
    road = []
    for fn in ("road_trainval_v1.0.json", "road_test_v1.0.json"):
        d = json.loads((road_dir / fn).read_text())
        for v, a in sorted(d["db"].items()):
            if not MIN_SEC <= a["numf"] / ROAD_FPS <= MAX_SEC:
                continue
            road.append({"id": v, "drive_id": ids[v + ".mp4"], "split": fn.split("_")[1], "duration": a["numf"] / ROAD_FPS,
                         "events": road_events(a["frame_labels"], d["av_action_labels"])})
    (out / "heldout_road.json").write_text(json.dumps({"fps": ROAD_FPS, "prompts": _ROAD_PROMPTS, "videos": road}, indent=1))
    print(f"road: {len(road)} videos, {sum(len(v['events']) for v in road)} events, "
          f"{sum(v['duration'] for v in road) / 3600:.2f} h")


def prep(sel: Path, out: Path) -> None:
    """One unit dir per video; each holds video.mp4 (854x480, 30 fps), prompts.json, gt.json."""
    import gdown

    units = [("yc", v, _YC + f"{v['id']}.mp4", {p["query_id"]: p["text"] for p in v["prompts"]})
             for v in json.loads((sel / "heldout_youcook2.json").read_text())["videos"]]
    r = json.loads((sel / "heldout_road.json").read_text())
    units += [("road", v, v["drive_id"], r["prompts"]) for v in r["videos"]]
    for dom, v, src, prompts in units:
        d = out / dom / v["id"]
        if (d / "gt.json").exists():
            continue
        (d / "src").mkdir(parents=True, exist_ok=True)
        raw = d / "src" / f"{v['id']}.mp4"
        try:  # one failed download must not stop the rest; score() lists units without results
            if not raw.exists():
                if dom == "yc":
                    subprocess.run(["curl", "-fsSL", "--retry", "5", "-o", f"{raw}.part", src], check=True)
                elif not gdown.download(id=src, output=f"{raw}.part", quiet=True):
                    raise RuntimeError("gdown failed")
                Path(f"{raw}.part").rename(raw)
            labels = {v["id"]: [(g["query_id"], g["start_sec"], g["end_sec"]) for g in v["events"]]}
            _assemble(d, labels, prompts, f"{dom}/{v['id']}")
        except Exception as e:  # noqa: BLE001
            print(f"PREP FAIL {dom}/{v['id']}: {e!r}"[:300], flush=True)


def _outcomes(d: Path, evs: list[dict]) -> list[dict]:
    """Per source video: GT hits (IoU >= 0.3, one-to-one), complete clips, boundary offsets, candidate counts."""
    from video_grounding.evaluation import _match

    gt = json.loads((d / "gt.json").read_text())
    offsets = gt.get("offsets") or {next(iter({g["video"] for g in gt["events"]}), d.name): 0.0}
    starts = sorted(offsets.items(), key=lambda x: x[1])
    present = {g["query_id"] for g in gt["events"]}
    n_absent = len([p for p in json.loads((d / "prompts.json").read_text()) if p["query_id"] not in present])
    per = {v: {"video": f"{d.name}/{v}", "gt": 0, "hit": 0, "complete": 0, "adjust": 0.0, "present_events": 0,
               "absent_events": 0, "by_query": {}} for v in offsets}

    def video_of(t: float) -> str:
        return next(v for v, o in reversed(starts) if t >= o) if t >= starts[0][1] else starts[0][0]

    for e in evs:
        per[video_of(e["event_start_sec"])]["present_events" if e["query_id"] in present else "absent_events"] += 1
    for q in present:
        gq = [g for g in gt["events"] if g["query_id"] == q]
        for g in gq:
            per[g["video"]]["gt"] += 1
            per[g["video"]]["by_query"].setdefault(q, [0, 0])[0] += 1
        for iou, e, g in _match([e for e in evs if e["query_id"] == q], gq):
            if iou < 0.3:
                continue
            r = per[g["video"]]
            r["hit"] += 1
            r["by_query"][q][1] += 1
            r["complete"] += e["clip_start_sec"] - 2.0 - 1e-6 <= g["start_sec"] and g["end_sec"] <= e["clip_end_sec"] + 2.0 + 1e-6
            r["adjust"] += abs(g["start_sec"] - e["event_start_sec"]) + abs(g["end_sec"] - e["event_end_sec"])
    for r in per.values():  # a unit's prompts are shared by its videos, so each video carries a share
        r["present_prompts"], r["absent_prompts"] = len(present) / len(per), n_absent / len(per)
    return list(per.values())


def _kpis(rows: list[dict]) -> dict:
    s = {k: sum(r[k] for r in rows) for k in ("gt", "hit", "complete", "adjust", "present_events", "absent_events",
                                              "present_prompts", "absent_prompts")}
    pp, ap = s["present_prompts"], s["absent_prompts"]
    return {"recall": s["hit"] / s["gt"] if s["gt"] else None,
            "complete_clip_rate": s["complete"] / s["hit"] if s["hit"] else None,
            "boundary_adjust_mean": s["adjust"] / (2 * s["hit"]) if s["hit"] else None,
            "candidates_per_present_prompt": s["present_events"] / pp if pp else None,
            "candidates_per_absent_prompt": s["absent_events"] / ap if ap else None,
            "absent_events": s["absent_events"], "gt": s["gt"], "hits": s["hit"]}


def _ci(rows: list[dict], n: int = 2000) -> dict:
    """95% percentile bootstrap over source videos."""
    rng, point = random.Random(SEED), _kpis(rows)
    draws = [_kpis([rng.choice(rows) for _ in rows]) for _ in range(n)]
    out = {}
    for k, v in point.items():
        xs = sorted(x[k] for x in draws if x[k] is not None)
        out[k] = v if k in ("absent_events", "gt", "hits") or not xs else [v, xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs)) - 1]]
    return out


def score(out: Path, run: str = "run") -> dict:
    res = {}
    for dom in ("yc", "road"):
        before, after, tim, sec, missing = [], [], {}, 0.0, []
        for d in sorted((out / dom).glob("*/")):
            ev = d / run / "events.json"
            if not ev.exists():
                missing.append(d.name)
                continue
            e = json.loads(ev.read_text())
            before += _outcomes(d, e["events"] + e.get("rejected_events", []))
            after += _outcomes(d, e["events"])
            sec += e["video_duration_sec"]
            for k, v in json.loads((d / run / "manifest.json").read_text()).get("timings", {}).items():
                tim[k] = tim.get(k, 0.0) + v
        if not before:
            continue
        byq = {}
        for r in before:
            for q, (g, h) in r["by_query"].items():
                byq.setdefault(q, [0, 0])
                byq[q][0] += g
                byq[q][1] += h
        res[dom] = {"videos": len(before), "missing_units": missing, "video_hours": round(sec / 3600, 2),
                    "before_verify": _ci(before), "after_verify": _ci(after),
                    "recall_by_prompt_before_verify": {q: f"{h}/{g}" for q, (g, h) in sorted(byq.items())},
                    "timing_s": {k: round(v, 1) for k, v in tim.items()},
                    "rtf_no_verify": round(sum(tim.get(k, 0.0) for k in ("scan_s", "refine_s", "export_s")) / sec, 2),
                    "verify_ratio": round(tim.get("verify_s", 0.0) / sec, 2)}
    return res


def _selfcheck() -> None:
    names = ["AV-Stop", "AV-Mov", "AV-TurRht", "AV-TurLft"]
    ev = road_events([-1] * 12 + [0] * 24 + [1] * 6 + [0] * 12 + [3] * 36, names)  # Stop, 0.5 s of Mov, Stop, TurLft
    assert [(e["query_id"], e["start_sec"], e["end_sec"]) for e in ev] == [("stop", 1.0, 4.5), ("turn_left", 4.5, 7.5)], ev
    rows = [{"video": "u/a", "gt": 2, "hit": 1, "complete": 1, "adjust": 2.0, "present_events": 4, "absent_events": 1,
             "present_prompts": 2, "absent_prompts": 1}]
    k = _kpis(rows)
    assert (k["recall"], k["boundary_adjust_mean"], k["candidates_per_present_prompt"]) == (0.5, 1.0, 2.0), k


if __name__ == "__main__":
    _selfcheck()
    cmd, *a = sys.argv[1:]
    if cmd == "select":
        select(Path(a[0]), Path(a[1]), Path(a[2]))
    elif cmd == "prep":
        prep(Path(a[0]), Path(a[1]))
    elif cmd == "score":
        print(json.dumps(score(Path(a[0]), *a[1:]), indent=1))
    else:
        sys.exit(__doc__)
