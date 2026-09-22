"""Slide image matcher.

gradient と Canny の両方を試して、スコアが高い方を使います。
"""

from __future__ import annotations

try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False


def _decode(bg_bytes: bytes, slice_bytes: bytes):
    """背景・ピースのバイト列を OpenCV 画像にデコードします。"""
    import numpy as _np
    import cv2 as _cv2
    bg = _cv2.imdecode(_np.frombuffer(bg_bytes, _np.uint8), _cv2.IMREAD_COLOR)
    sl = _cv2.imdecode(_np.frombuffer(slice_bytes, _np.uint8), _cv2.IMREAD_UNCHANGED)
    if bg is None or sl is None:
        raise ValueError("背景/ピース画像のデコードに失敗しました")
    return bg, sl


def _slice_gray(sl) -> object:
    """ピースを grayscale 化して、透過部分は 0 にします。

    
    """
    import cv2 as _cv2
    if len(sl.shape) == 3 and sl.shape[2] == 4:
        alpha = sl[:, :, 3]
        g = _cv2.cvtColor(sl, _cv2.COLOR_BGR2GRAY)
        g[alpha == 0] = 0  # 透明部分は黒に固定
        return g
    if len(sl.shape) == 3:
        return _cv2.cvtColor(sl, _cv2.COLOR_BGR2GRAY)
    return sl


def _match_gradient(bg_gray, sl_gray, ypos: int):
    """MORPH_GRADIENT で template matching。"""
    import cv2 as _cv2
    kernel = _cv2.getStructuringElement(_cv2.MORPH_RECT, (3, 3))
    mg_bg = _cv2.morphologyEx(bg_gray, _cv2.MORPH_GRADIENT, kernel)
    mg_sl = _cv2.morphologyEx(sl_gray, _cv2.MORPH_GRADIENT, kernel)
    h = mg_sl.shape[0]
    if ypos > 0 and ypos + h <= mg_bg.shape[0]:
        # ypos が取れるならその帯を優先
        search = mg_bg[ypos:ypos + h, :]
        y_off = ypos
    else:
        search = mg_bg
        y_off = 0
    res = _cv2.matchTemplate(search, mg_sl, _cv2.TM_CCOEFF_NORMED)
    _, mx, _, ml = _cv2.minMaxLoc(res)
    return ml[0], ml[1] + y_off, float(mx)


def _match_canny(bg_gray, sl_gray, ypos: int):
    """Canny edge で template matching。"""
    import cv2 as _cv2
    h = sl_gray.shape[0]
    margin = 10
    if ypos > 0:
        ys = max(0, ypos - margin)
        ye = min(bg_gray.shape[0], ypos + h + margin)
        crop = bg_gray[ys:ye]
        y_off = ys
    else:
        crop, y_off = bg_gray, 0
    e_bg = _cv2.Canny(crop, 100, 200)
    e_sl = _cv2.Canny(sl_gray, 100, 200)
    e_bg = _cv2.cvtColor(e_bg, _cv2.COLOR_GRAY2RGB)
    e_sl = _cv2.cvtColor(e_sl, _cv2.COLOR_GRAY2RGB)
    res = _cv2.matchTemplate(e_bg, e_sl, _cv2.TM_CCOEFF_NORMED)
    _, mx, _, ml = _cv2.minMaxLoc(res)
    return ml[0], ml[1] + y_off, float(mx)


def solve_slide_hybrid(bg_bytes: bytes, slice_bytes: bytes,
                       ypos: int = 0) -> tuple[int, float, str]:
    """(set_left, 信頼度, 採用方式名) を返します。"""
    if not _HAS_CV2:
        raise RuntimeError("opencv が要ります: pip install opencv-python")
    import cv2 as _cv2
    bg, sl = _decode(bg_bytes, slice_bytes)
    bg_gray = _cv2.cvtColor(bg, _cv2.COLOR_BGR2GRAY)
    sl_gray = _slice_gray(sl)
    ax, _, ac = _match_gradient(bg_gray, sl_gray, ypos)
    try:
        bx, _, bc = _match_canny(bg_gray, sl_gray, ypos)
    except Exception:
        bx, bc = ax, -1.0
    # gradient が弱いときだけ全体検索でもう一度
    if ac < 0.15:
        try:
            res = _cv2.matchTemplate(
                _cv2.morphologyEx(bg_gray, _cv2.MORPH_GRADIENT,
                                  _cv2.getStructuringElement(_cv2.MORPH_RECT, (3, 3))),
                _cv2.morphologyEx(sl_gray, _cv2.MORPH_GRADIENT,
                                  _cv2.getStructuringElement(_cv2.MORPH_RECT, (3, 3))),
                _cv2.TM_CCOEFF_NORMED)
            _, ac2, _, ml2 = _cv2.minMaxLoc(res)
            if ac2 > ac:
                ax, ac = ml2[0], float(ac2)
        except Exception:
            pass
    if ac >= bc:
        return int(ax), float(ac), "gradient"
    return int(bx), float(bc), "canny"


def solve_slide(bg_bytes: bytes, slice_bytes: bytes, ypos: int = 0) -> int:
    """setLeft (px) を返す public API。"""
    x, _, _ = solve_slide_hybrid(bg_bytes, slice_bytes, ypos)
    return x


def userresponse_from_setleft(set_left: int) -> float:
    """setLeft -> userresponse 変換です。全フォーク共通の係数: left/1.0059466...+2。"""
    return set_left / 1.0059466666666665 + 2
