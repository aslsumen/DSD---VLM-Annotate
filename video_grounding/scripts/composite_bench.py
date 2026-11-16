"""YouCook2 and BDD-X composite benchmarks: the main accuracy check.

VideoJev was trained on Charades-STA, so charades_sta.py is only a reference; these two sets are held out.
Each benchmark joins several long source videos into one composite (854x480, 30 fps) and every prompt
searches the whole composite, so a prompt can match several times and other videos act as distractors.
Some prompts never happen in the composite ("absent" prompts); every event they get is a false positive.

  python scripts/composite_bench.py prep  NAME DIR    # NAME: youcook2_a | youcook2_b | bddx; needs curl and ffmpeg
  video-grounding scan --video DIR/video.mp4 --prompt-file DIR/prompts.json --config CONFIG --out DIR/RUN
  python scripts/composite_bench.py score DIR [RUN]   # KPIs as JSON; RUN defaults to "run"
bddx downloads from the BDD100K video zip and needs remotezip (uv run --with remotezip ...).
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
from pathlib import Path

_YC = "https://huggingface.co/datasets/lccshunli/youcook2-videos-only/resolve/c6953ae7bcae24704957def5c1b1c4c879644ab2/"
_BDD_ZIP = "http://dl.yf.io/bdd100k/bdd100k_videos.zip"

# YouCook2 val steps: (query_id, step text, start, end in the source video). One labelled step per prompt.
_YOUCOOK2 = {
    "youcook2_a": {
        "DpuofwnCI8A": [("DpuofwnCI8A_0", "mash a bowl of chickpeas using a fork", 150, 196),
                        ("DpuofwnCI8A_2", "add garam masala cloves cinnamon sticks bay leaf and cardamom to the pan", 245, 290),
                        ("DpuofwnCI8A_5", "add turmeric to the pan and stir", 379, 405),
                        ("DpuofwnCI8A_7", "garnish with cilantro leaves and stir", 549, 560)],
        "2iWUUcW08ac": [("2iWUUcW08ac_0", "sift flour sugar baking powder baking soda and salt into a bowl", 120, 175),
                        ("2iWUUcW08ac_4", "mix the egg yolks with sugar", 259, 278),
                        ("2iWUUcW08ac_8", "cut up the banana", 341, 347),
                        ("2iWUUcW08ac_12", "pour maple syrup on top", 412, 417)],
        "HBUz55JRRm8": [("HBUz55JRRm8_0", "add oil and onions to a pan", 40, 55),
                        ("HBUz55JRRm8_4", "stir in beef stock and vegetables", 213, 254),
                        ("HBUz55JRRm8_8", "mash the boiled potatos with butter salt and pepper", 405, 449),
                        ("HBUz55JRRm8_12", "sprinkle parsley on the top", 640, 655)],
    },
    "youcook2_b": {
        "LQDP3xm8aRk": [("LQDP3xm8aRk_0", "put potatoes and salt into a pot of water and boil", 40, 53),
                        ("LQDP3xm8aRk_5", "add dry italian herbs", 166, 173),
                        ("LQDP3xm8aRk_9", "add splash of worchestire sauce and beef stock", 231, 248),
                        ("LQDP3xm8aRk_14", "add potatoes sausage onions and peas to plate", 456, 480)],
        "9guuyTr8EUg": [("9guuyTr8EUg_0", "cook the rice noodles in boiling water", 86, 110),
                        ("9guuyTr8EUg_4", "add the rice noodles and bean sprouts to the wok and stir", 203, 212),
                        ("9guuyTr8EUg_9", "roll the wrapper half way up", 314, 325),
                        ("9guuyTr8EUg_13", "cook the spring rolls until golden brown", 372, 394)],
        "6seOEuK0ojg": [("6seOEuK0ojg_0", "add onion paste", 114, 120),
                        ("6seOEuK0ojg_4", "add tumeric and chili powder", 139, 148),
                        ("6seOEuK0ojg_9", "add cardamom cinnamon sticks and cloves", 247, 255),
                        ("6seOEuK0ojg_13", "stir the food", 405, 415)],
    },
}
# Cooking steps from other YouCook2 recipes; "easy" ones look unlike anything in the composites, "hard" ones look close.
_YC_ABSENT = {
    "youcook2_a": {"absent_e1": "place basil leaves on top of the pizza", "absent_e2": "grill the burgers",
                   "absent_e3": "chop lettuce and place it in a bowl", "absent_h1": "knead the dough",
                   "absent_h2": "rinse the shrimp with water and finely chop",
                   "absent_h3": "boil a pot of salted water and cook pasta in it"},
    "youcook2_b": {"absent_e4": "cut the avocado and place in a bowl",
                   "absent_e5": "place the salmon and cucumber on the seaweed", "absent_e6": "cut the tofu into squares",
                   "absent_h4": "place the cheese and bacon on top of the patties", "absent_h5": "stir pasta into the sauce",
                   "absent_h6": "add fish balls to the wok and stir"},
}

_BDDX_PROMPTS = {
    "turn_left": "the ego vehicle turns left",
    "turn_right": "the ego vehicle turns right",
    "lane_change": "the ego vehicle changes lanes or merges into another lane",
    "stop_red": "the ego vehicle slows down or stops for a red traffic light",
    "stop_lead": "the ego vehicle slows down or stops because the vehicle in front of it slows or stops",
    "stop_ped": "the ego vehicle slows down or stops for a pedestrian",
    "go_green": "the ego vehicle starts moving or accelerates after the traffic light turns green",
    "absent_collision": "the ego vehicle collides with another vehicle",
}
# BDD-X action annotations (integer seconds) on 40 s BDD100K train clips, mapped to the prompts above.
_BDDX = {
    "2aa96687-30998843": [("lane_change", 5, 8), ("stop_red", 18, 20), ("stop_lead", 18, 20), ("lane_change", 21, 23), ("stop_red", 24, 26), ("stop_red", 27, 40)],
    "29589b34-48b14982": [("stop_lead", 0, 9), ("stop_ped", 0, 9), ("stop_ped", 17, 18), ("stop_lead", 23, 25), ("stop_lead", 29, 31), ("go_green", 32, 40)],
    "2a554470-c314a903": [("stop_red", 0, 3), ("lane_change", 4, 17), ("turn_right", 18, 22), ("lane_change", 35, 40)],
    "2938b429-79354be6": [("go_green", 0, 10), ("turn_left", 11, 18), ("stop_red", 27, 36), ("stop_lead", 27, 36), ("go_green", 37, 40)],
    "1f225b07-91132e43": [("lane_change", 14, 19), ("turn_right", 19, 22), ("stop_ped", 22, 24), ("turn_right", 24, 28)],
    "2c3171e6-4217ab81": [("turn_left", 9, 15), ("turn_right", 22, 26)],
    "2bce70c2-a034e870": [("stop_red", 21, 24), ("turn_left", 25, 32), ("go_green", 25, 32)],
    "2740c139-838de60f": [("turn_left", 11, 18), ("stop_ped", 18, 22), ("stop_red", 22, 31)],
    "2bbe0227-63906001": [("stop_red", 0, 16), ("stop_red", 20, 21), ("go_green", 22, 25), ("stop_lead", 26, 27), ("stop_ped", 26, 27)],
    "2a051b12-cca63af9": [("stop_red", 0, 9), ("turn_left", 10, 18), ("go_green", 10, 18), ("stop_red", 19, 22), ("stop_red", 23, 40)],
    "2bba8054-8894be38": [("turn_right", 0, 5), ("lane_change", 19, 21), ("stop_red", 22, 25), ("stop_red", 26, 40)],
    "2afddd2b-e46076b1": [("lane_change", 18, 21), ("stop_red", 21, 24), ("stop_red", 24, 40), ("stop_ped", 24, 40)],
    "2ae714ac-5e710c05": [("lane_change", 4, 8), ("stop_red", 20, 23), ("stop_red", 24, 40), ("stop_ped", 24, 40)],
    "2ad035f4-cd94277d": [("stop_lead", 8, 18), ("go_green", 19, 20), ("stop_red", 21, 29), ("stop_red", 30, 40)],
    "2a02db81-581e1c04": [("stop_red", 0, 2), ("go_green", 3, 9), ("stop_red", 22, 27), ("stop_red", 28, 40)],
    "29f27e14-60a87a96": [("stop_lead", 11, 18), ("stop_lead", 26, 32), ("stop_red", 33, 38), ("stop_red", 39, 40)],
    "29da0a66-4ee959c4": [("go_green", 0, 8), ("stop_red", 23, 25), ("stop_lead", 23, 25), ("stop_red", 26, 40)],
    "29a6a14c-6ab8e4c7": [("stop_red", 0, 5), ("go_green", 5, 12), ("stop_red", 19, 22), ("stop_red", 22, 40)],
    "28dbc980-a186da44": [("lane_change", 0, 4), ("lane_change", 10, 12), ("turn_right", 17, 20), ("turn_right", 23, 32)],
    "289af74b-f2c8a214": [("stop_red", 0, 7), ("go_green", 13, 19), ("stop_red", 28, 33), ("stop_red", 34, 40)],
}


def _normalise(src: Path, dst: Path) -> float:
    if not dst.exists():
        vf = "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-vf", vf, "-an", "-c:v", "libx264",
                        "-crf", "23", "-preset", "veryfast", str(dst) + ".tmp.mp4"], check=True)
        Path(str(dst) + ".tmp.mp4").rename(dst)
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dst)],
                         check=True, capture_output=True, text=True)
    return float(out.stdout)


def _merge(segs: list[tuple[str, float, float]], gap: float = 1.0) -> list[tuple[str, float, float]]:
    """BDD-X labels are whole seconds and often split one action at a second boundary: join same-prompt
    segments less than `gap` apart."""
    out: list[list] = []
    for q, s, e in sorted(segs):
        if out and out[-1][0] == q and s - out[-1][2] <= gap:
            out[-1][2] = max(out[-1][2], e)
        else:
            out.append([q, s, e])
    return [tuple(x) for x in out]


def prep(name: str, d: Path) -> None:
    (d / "src").mkdir(parents=True, exist_ok=True)
    if name in _YOUCOOK2:
        sel = _YOUCOOK2[name]
        prompts = {q: t for rows in sel.values() for q, t, _, _ in rows} | _YC_ABSENT[name]
        for v in sel:
            raw = d / "src" / f"{v}.mp4"
            if not raw.exists():
                subprocess.run(["curl", "-fsSL", "--retry", "5", "-o", str(raw), _YC + f"{v}.mp4"], check=True)
        labels = {v: [(q, s, e) for q, _, s, e in rows] for v, rows in sel.items()}
    elif name == "bddx":
        import remotezip

        prompts, labels = _BDDX_PROMPTS, {v: _merge(segs) for v, segs in _BDDX.items()}
        with remotezip.RemoteZip(_BDD_ZIP) as z:
            for v in _BDDX:
                raw = d / "src" / f"{v}.mov"
                if not raw.exists():
                    raw.write_bytes(z.read(f"bdd100k/videos/100k/train/{v}.mov"))
    else:
        raise SystemExit(f"unknown benchmark {name!r}")
    events, offsets, parts, t = [], {}, [], 0.0
    for v, segs in labels.items():
        raw = next((d / "src").glob(f"{v}.*"))
        dur = _normalise(raw, d / "src" / f"{v}.norm.mp4")
        offsets[v] = t
        parts.append(f"file '{(d / 'src' / f'{v}.norm.mp4').resolve()}'")
        events += [{"query_id": q, "start_sec": t + s, "end_sec": t + min(e, dur), "video": v} for q, s, e in segs]
        t += dur
    (d / "concat.txt").write_text("\n".join(parts) + "\n")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(d / "concat.txt"),
                    "-c", "copy", str(d / "video.mp4")], check=True)
    (d / "prompts.json").write_text(json.dumps([{"query_id": q, "text": txt} for q, txt in prompts.items()], indent=1))
    (d / "gt.json").write_text(json.dumps({"events": events, "offsets": offsets}, indent=1))
    print(json.dumps({"benchmark": name, "video_sec": round(t, 1), "gt": len(events), "prompts": len(prompts)}))


def score(d: Path, run: str = "run") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    from charades_sta import _kpis
    from video_grounding.evaluation import _iou, _match

    gts = json.loads((d / "gt.json").read_text())["events"]
    prompts = [p["query_id"] for p in json.loads((d / "prompts.json").read_text())]
    doc = json.loads((d / run / "events.json").read_text())
    kept = doc["events"]
    allev = kept + doc.get("rejected_events", [])
    present = {g["query_id"] for g in gts}
    absent = [q for q in prompts if q not in present]
    p_of = lambda e: (e.get("verdict") or {}).get("p_present")  # noqa: E731

    def kpis(evs: list[dict]) -> dict:
        pos = [e for e in evs if e["query_id"] in present]
        out = {k: v for k, v in _kpis(pos, gts).items() if not k.startswith("R1")}  # R1 assumes one GT per prompt
        del out["preds_per_query"]
        out["preds_per_prompt"] = round(len(pos) / len(present), 2)
        out["absent_prompt_events"] = sum(e["query_id"] in absent for e in evs)
        per = {}
        for q in sorted(present):
            pq, gq = [e for e in pos if e["query_id"] == q], [g for g in gts if g["query_id"] == q]
            per[q] = {"gt": len(gq), "hit": sum(iou >= 0.3 for iou, _, _ in _match(pq, gq)), "events": len(pq)}
        out["per_prompt"] = per
        return out

    res = {"video_sec": round(doc["video_duration_sec"], 1), "n_gt": len(gts), "prompts": len(present),
           "absent_prompts": len(absent), "before_verify": kpis(allev), "after_verify": kpis(kept)}
    # Gemini as a classifier: positive = an event overlapping a GT span of its prompt at IoU >= 0.3
    hit = lambda e: any(g["query_id"] == e["query_id"] and  # noqa: E731
                        _iou((e["event_start_sec"], e["event_end_sec"]), (g["start_sec"], g["end_sec"])) >= 0.3
                        for g in gts)
    ver = [e for e in allev if p_of(e) is not None]
    res["gemini"] = {"verdicts": len(ver), "not_verified": len(allev) - len(ver),
                     "true_events_kept": sum(hit(e) and p_of(e) >= 0.5 for e in ver),
                     "true_events": sum(hit(e) for e in ver),
                     "false_events_removed": sum(not hit(e) and p_of(e) < 0.5 for e in ver),
                     "false_events": sum(not hit(e) for e in ver),
                     "absent_events_removed": sum(e["query_id"] in absent and p_of(e) < 0.5 for e in ver),
                     "absent_events": sum(e["query_id"] in absent for e in ver)}
    res["timing_s"] = json.loads((d / run / "manifest.json").read_text()).get("timings", {})
    return res


def _selfcheck() -> None:
    assert _merge([("a", 24, 26), ("a", 27, 40), ("b", 26, 27), ("a", 0, 2)]) == [("a", 0, 2), ("a", 24, 40), ("b", 26, 27)]
    assert _merge([("a", 0, 2), ("a", 3.5, 4)]) == [("a", 0, 2), ("a", 3.5, 4)]


if __name__ == "__main__":
    _selfcheck()
    if sys.argv[1] == "prep":
        prep(sys.argv[2], Path(sys.argv[3]))
    else:
        print(json.dumps(score(Path(sys.argv[2]), *sys.argv[3:4]), indent=1))
