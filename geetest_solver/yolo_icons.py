"""Optional YOLO backend for icon detection.

モデルは同梱せず、必要になったときだけ取得して cache します。
クレジットは THIRD_PARTY_NOTICES.md にまとめています。
"""

from __future__ import annotations

import os

# optional model source
MODEL_URL = ("https://raw.githubusercontent.com/syncrain/geetest-solver"
             "/main/geetest_solver/best.pt")
CACHE_PATH = os.path.join(os.path.expanduser("~"), ".cache",
                          "geetest_solver", "best.pt")

_model = None
_model_tried = False


def model_path() -> str | None:
    """モデルを用意して path を返します。失敗したら None。"""
    if os.path.exists(CACHE_PATH):
        return CACHE_PATH
    try:
        import requests
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with requests.get(MODEL_URL, timeout=120, stream=True) as r:
            r.raise_for_status()
            tmp = CACHE_PATH + ".part"
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        os.replace(tmp, CACHE_PATH)
        return CACHE_PATH
    except Exception:
        return None


def get_model():
    """YOLO backend を lazy-load します。"""
    global _model, _model_tried
    if _model_tried:
        return _model
    _model_tried = True
    try:
        os.environ.setdefault("YOLO_VERBOSE", "False")
        from ultralytics import YOLO
        # dev override
        for cand in (os.environ.get("GEETEST_YOLO_PATH", ""),
                     "/tmp/geetest_ref2/syncrain/geetest_solver/best.pt"):
            if cand and os.path.exists(cand):
                _model = YOLO(cand)
                return _model
        path = model_path()
        if path:
            _model = YOLO(path)
    except Exception:
        _model = None
    return _model


def detect_icons(grid_bytes: bytes, conf: float = 0.35,
                 imgsz: int = 640) -> list:
    """グリッド画像から ``icon`` クラスの箱 ``[(x1, y1, x2, y2), ...]`` を返します (ピクセル座標)。"""
    model = get_model()
    if model is None:
        return []
    try:
        import cv2
        import numpy as np
        # predict 前に image として decode する
        
        img = cv2.imdecode(np.frombuffer(grid_bytes, dtype="uint8"),
                           cv2.IMREAD_COLOR)
        if img is None:
            return []
        r = model.predict(img, verbose=False, imgsz=imgsz, conf=0.05)[0]
        names = getattr(model, "names", {})
        out = []
        for b in r.boxes or []:
            cls = int(b.cls[0])
            if isinstance(names, dict) and names.get(cls) not in ("icon", 0):
                if names.get(cls) != "icon":
                    continue
            if float(b.conf[0]) < conf:
                continue
            x1, y1, x2, y2 = (int(v) for v in b.xyxy[0])
            if x2 - x1 >= 10 and y2 - y1 >= 10:
                out.append((x1, y1, x2, y2))
        return out
    except Exception:
        return []
