#!/usr/bin/env python
"""Print VideoJev config summary; with --load also parameter counts, dtypes and hf_device_map."""
from __future__ import annotations

import argparse
import collections
import json


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-path", required=True)
    ap.add_argument("--load", action="store_true", help="load weights (otherwise config only)")
    ap.add_argument("--device-map", default="auto")
    ap.add_argument("--attn", default="flash_attention_2")
    args = ap.parse_args()

    from transformers import AutoConfig
    cfg = AutoConfig.from_pretrained(args.model_path, trust_remote_code=True)
    print("config:", json.dumps(cfg.to_dict(), indent=1, default=str)[:4000])
    if not args.load:
        return
    import torch
    from transformers import AutoModel
    model = AutoModel.from_pretrained(args.model_path, trust_remote_code=True, dtype=torch.bfloat16,
                                      device_map=args.device_map, attn_implementation=args.attn)
    for name, child in model.named_children():
        n = sum(p.numel() for p in child.parameters())
        dt = collections.Counter(str(p.dtype) for p in child.parameters())
        print(f"{name:20s} {n / 1e6:10.1f}M params  dtypes={dict(dt)}")
    print("total params:", sum(p.numel() for p in model.parameters()))
    print("hf_device_map:", json.dumps(getattr(model, "hf_device_map", None), indent=1, default=str))


if __name__ == "__main__":
    main()
