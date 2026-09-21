"""定数更新 (GeekedTest/deobfuscate.py の発想を自動化)。

使い方:
    python -m geetest_solver.deobfuscate
    python -m geetest_solver.deobfuscate --base-url https://gcaptcha4.geetest.com
"""
from __future__ import annotations

import argparse
import json


def main() -> int:
    ap = argparse.ArgumentParser(description="GeeTest v4 の abo/lib 定数を更新する")
    ap.add_argument("--base-url", default="https://gcaptcha4.geetest.com")
    ap.add_argument("--json", action="store_true", help="JSON のみ出力")
    a = ap.parse_args()
    from . import config as cfg
    before = cfg.as_dict()
    after = cfg.refresh(a.base_url)
    keys = ("lib_key", "lib_val", "abo_key", "abo_val")
    if a.json:
        print(json.dumps(after, indent=2, ensure_ascii=False))
    else:
        print("before:", json.dumps({k: before[k] for k in keys}, indent=2))
        print("after: ", json.dumps({k: after[k] for k in keys}, indent=2))
        print("cache: geetest_solver/.config_cache.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
