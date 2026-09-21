"""nine/icon/word ソルバー:ヒューリスティック + ONNX フック。

hshinosa は非公開の SigLIP ONNX モデル (~9MB、同梱不可) を使う。
Geeked は外部の ddddocr サーバが要る。改良点:依存なしで動く
ヒューリスティック (プロンプトとのセル別テンプレマッチ) を内蔵しつつ、
任意の ONNX/自作モデルを差せるフックを付ける (hshinosa 式の
マージン判定リトライ付き:上位3件のマージン、しきい値 2.2、低信頼度でもベスト)。
"""
from __future__ import annotations

_ONNX_MATCHER = None  # register_onnx_matcher() で設定する。未設定ならヒューリスティック


def register_onnx_matcher(fn):
    """``fn(prompt_bytes, grid_bytes) -> list[float] (9 logits)`` を登録する。"""
    global _ONNX_MATCHER
    _ONNX_MATCHER = fn
    return fn


def _load_images(imgs_bytes: bytes, ques_bytes_list: list[bytes]):
    """グリッド画像とプロンプト画像群を PIL で開く。"""
    from PIL import Image
    import io
    grid = Image.open(io.BytesIO(imgs_bytes)).convert("RGB")
    prompts = [Image.open(io.BytesIO(q)).convert("RGB") for q in ques_bytes_list]
    return grid, prompts


def solve_nine_heuristic(imgs_bytes: bytes, ques_bytes_list: list[bytes],
                         nine_nums: int = 3) -> list[tuple[int, int]]:
    """3x3 各セルをプロンプトとの照合スコアで順位付けする。

    戻り値は 1 始まり [(row, col)] (hshinosa の線路形式)。
    OpenCV があればそれで、無ければ純 PIL の SAD フォールバック。
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image
        import io
        grid = np.array(Image.open(io.BytesIO(imgs_bytes)).convert("RGB"))
        gh, gw = grid.shape[:2]
        ch, cw = gh // 3, gw // 3
        prompt = np.array(Image.open(io.BytesIO(ques_bytes_list[0])).convert("RGB"))
        scores = []
        for i in range(3):
            for j in range(3):
                cell = grid[i * ch:(i + 1) * ch, j * cw:(j + 1) * cw]
                tmpl = cv2.resize(prompt, (cell.shape[1], cell.shape[0]))
                res = cv2.matchTemplate(cell, tmpl, cv2.TM_CCOEFF_NORMED)
                scores.append((float(res.max()), (i + 1, j + 1)))
        # 縮退ケース (ベタ塗りで NCC が全同点) -> SAD 順位付けにフォールスルー
        vals = [s for s, _ in scores]
        if max(vals) - min(vals) < 1e-6:
            raise ValueError("tie")
        scores.sort(reverse=True)
        return [pos for _, pos in scores[:nine_nums]]
    except Exception:
        pass
    # PIL フォールバック:差分絶対値和 (SAD) で順位付け
    from PIL import Image
    import io
    grid, prompts = _load_images(imgs_bytes, ques_bytes_list)
    gw, gh = grid.size
    cw, ch = gw // 3, gh // 3
    prompt = prompts[0].resize((cw, ch))
    pl = list(prompt.getdata())
    scored = []
    for i in range(3):
        for j in range(3):
            cell = grid.crop((j * cw, i * ch, (j + 1) * cw, (i + 1) * ch))
            cl = list(cell.getdata())
            sad = sum(abs(a - b) for px1, px2 in zip(cl, pl) for a, b in zip(px1, px2))
            scored.append((sad, (i + 1, j + 1)))
    scored.sort()
    return [pos for _, pos in scored[:nine_nums]]


def solve_nine(imgs_bytes: bytes, ques_bytes_list: list[bytes],
               nine_nums: int = 3, margin_threshold: float = 2.2) -> list[tuple[int, int]]:
    """ONNX 優先 (hshinosa 式)、ダメならヒューリスティック。

    ONNX マッチャー登録済みで信頼度十分 (マージン >= しきい値) なら採用。
    低信頼度でもベストゲスを返す (呼び出し側が新 lot でリトライできる)。
    """
    if _ONNX_MATCHER is not None:
        try:
            logits = list(_ONNX_MATCHER(ques_bytes_list[0], imgs_bytes))
            order = sorted(range(len(logits)), key=lambda i: -logits[i])
            top = order[:nine_nums]
            margin = logits[order[nine_nums - 1]] - logits[order[nine_nums]] \
                if len(order) > nine_nums else 99.0
            cells = [((i // 3) + 1, (i % 3) + 1) for i in sorted(top)]
            if margin >= margin_threshold:
                return cells
            # 低信頼度:それでもベストゲスを返す
            return cells
        except Exception:
            pass
    return solve_nine_heuristic(imgs_bytes, ques_bytes_list, nine_nums)


def segment_icon_boxes(grid_bgr, min_area: int = 150,
                       max_area: int = 6000) -> list:
    """写真背景から貼り付けアイコンを切り出す (学習モデル不要)。

    マスク = 背景との色相差 (カラーアイコン用) と無彩色の極値
    (黒白シルエット用) の OR。背景色相は彩度上位画素の中央値。
    戻り値は ``[(x1, y1, x2, y2), ...]``。
    """
    import cv2
    import numpy as np
    hsv = cv2.cvtColor(grid_bgr, cv2.COLOR_BGR2HSV)
    H = hsv[:, :, 0].astype(float)
    S = hsv[:, :, 1].astype(float)
    V = hsv[:, :, 2].astype(float)
    bg = float(np.median(H[S > 50])) if (S > 50).any() else 90.0
    colored = (np.abs(H - bg) > 25) & (S > 60)
    extreme = (S < 50) & ((V < 60) | (V > 200))
    mask = (colored | extreme).astype("uint8")
    # オープニングでアイコンと背景の細いテクスチャ橋を切る
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                            np.ones((5, 5), "uint8"))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    boxes = []
    for k in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[k])
        if not (min_area < area < max_area and w > 8 and h > 8):
            continue
        # アイコン箱はそこそこ埋まっているはず。スカスカ=テクスチャノイズ、
        # べったり=背景領域 として除外する
        fill = area / max(w * h, 1)
        if 0.15 > fill or fill > 0.95:
            continue
        boxes.append([x, y, x + w, y + h])
    # 明らかな破片だけ結合:小さい方の 30% 超が重なったら同一アイコンとみなす
    merged = []
    for b in boxes:
        for m in merged:
            ix1, iy1 = max(b[0], m[0]), max(b[1], m[1])
            ix2, iy2 = min(b[2], m[2]), min(b[3], m[3])
            inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
            small = min((b[2] - b[0]) * (b[3] - b[1]),
                        (m[2] - m[0]) * (m[3] - m[1]))
            if small > 0 and inter / small > 0.3:
                m[0], m[1] = min(m[0], b[0]), min(m[1], b[1])
                m[2], m[3] = max(m[2], b[2]), max(m[3], b[3])
                break
        else:
            merged.append(b)
    # アイコンを収容できない小箱は捨て、テクスチャ橋で合体した巨大箱は
    # 分割する (アイコンは ~30-60px 想定)
    final = []
    for x1, y1, x2, y2 in merged:
        w, h = x2 - x1, y2 - y1
        if w < 24 or h < 24:
            continue
        if w > 90 or h > 90:
            nx, ny = max(1, round(w / 55)), max(1, round(h / 55))
            for i in range(nx):
                for j in range(ny):
                    ax1 = x1 + (w * i) // nx
                    ax2 = x1 + (w * (i + 1)) // nx
                    ay1 = y1 + (h * j) // ny
                    ay2 = y1 + (h * (j + 1)) // ny
                    if ax2 - ax1 >= 24 and ay2 - ay1 >= 24:
                        final.append([ax1, ay1, ax2, ay2])
        else:
            final.append([x1, y1, x2, y2])
    return final


def segment_mask(grid_bgr) -> object:
    """アイコンマスク (segment_icon_boxes と同じ規則の2値画像)。"""
    import cv2
    import numpy as np
    hsv = cv2.cvtColor(grid_bgr, cv2.COLOR_BGR2HSV)
    H = hsv[:, :, 0].astype(float)
    S = hsv[:, :, 1].astype(float)
    V = hsv[:, :, 2].astype(float)
    bg = float(np.median(H[S > 50])) if (S > 50).any() else 90.0
    return ((np.abs(H - bg) > 25) & (S > 60)) | ((S < 50) & ((V < 60) | (V > 200)))


def _silhouette_crop(prompt_rgba):
    """プロンプトの透過マスクを bbox で切り出す。uint8 マスクか None を返す。"""
    import numpy as np
    a = (prompt_rgba[:, :, 3] > 0).astype("uint8") if prompt_rgba.shape[2] == 4 \
        else (prompt_rgba.mean(axis=2) < 128).astype("uint8")
    ys, xs = np.where(a > 0)
    if len(xs) == 0:
        return None
    return (a[ys.min():ys.max() + 1, xs.min():xs.max() + 1] * 255).astype("uint8")


def find_prompt_in_grid(grid_gray, sil_mask,
                        scales=(0.6, 0.8, 1.0, 1.2),
                        dark_thr: int = 80, bright_thr: int = 200):
    """散布アイコングリッド内でプロンプトのシルエットを探す。

    明暗2種の2値マップ (グリッド側アイコンはどちらにも化ける) × 複数スケールで
    照合し、最良ピークの ``(スコア, cx_norm, cy_norm)`` を返す。スコアは NCC
    ([-1, 1])。busy な写真背景では学習モデルなしだと ~0.5 が天井というのが
    正直な限界 (参考リポジトリ共通)。
    """
    import cv2
    import numpy as np
    H, W = grid_gray.shape
    maps = [((grid_gray < dark_thr).astype("uint8") * 255),
            ((grid_gray > bright_thr).astype("uint8") * 255)]
    best = (-2.0, 0.5, 0.5)
    for bg in maps:
        for sc in scales:
            r = cv2.resize(sil_mask, None, fx=sc, fy=sc)
            h, w = r.shape
            if h >= H or w >= W or h < 6 or w < 6:
                continue
            res = cv2.matchTemplate(bg, r, cv2.TM_CCOEFF_NORMED)
            res = np.nan_to_num(res, nan=-1.0)
            _, mx, _, ml = cv2.minMaxLoc(res)
            if mx > best[0]:
                best = (float(mx), (ml[0] + w / 2) / W, (ml[1] + h / 2) / H)
    return best


def _fit_mask(p, h: int, w: int, scale: float = 0.9):
    """2値シルエットを縦横比維持で (h, w) に収めて中央配置する。"""
    import cv2
    import numpy as np
    p = (np.asarray(p) > 0).astype("uint8")
    ph, pw = p.shape
    sc = min(h / ph, w / pw) * scale
    nh, nw = max(1, int(ph * sc)), max(1, int(pw * sc))
    r = cv2.resize((p * 255).astype("uint8"), (nw, nh)) > 127
    out = np.zeros((h, w), dtype=bool)
    y0, x0 = (h - nh) // 2, (w - nw) // 2
    out[y0:y0 + nh, x0:x0 + nw] = r
    return out


def score_prompt_box(crop_gray, sil_mask) -> float:
    """(プロンプトシルエット, YOLO 箱クロップ) の複合キュースコア。

    手がかり (いずれも縦横比維持マスク + 拡張リングで計算):
    - 内外の明度差 (両極性。グリッド側は黒地にも白地にも化ける)
    - 明/暗2値マップとの IoU
    公式デモの実測では単一の手がかりは busy 背景で分離せず、合計が最良だった。
    """
    import cv2
    import numpy as np
    h, w = crop_gray.shape
    m = _fit_mask(sil_mask, h, w)
    if m.sum() == 0:
        return 0.0
    dil = cv2.dilate(m.astype("uint8"), np.ones((7, 7), "uint8")) > 0
    ring = dil & (~m)
    c = crop_gray
    pin_b = float((c[m] > 180).mean())
    pin_d = float((c[m] < 80).mean())
    pout_b = float((c[ring] > 180).mean()) if ring.sum() else 0.0
    pout_d = float((c[ring] < 80).mean()) if ring.sum() else 0.0
    diff = max(pin_b - pout_b, pin_d - pout_d, 0.0)
    inter_b = np.logical_and(m, c > 180).sum()
    inter_d = np.logical_and(m, c < 80).sum()
    union = m.sum() + ((c > 180) | (c < 80)).sum() - max(inter_b, inter_d)
    iou = max(inter_b, inter_d) / max(union, 1)
    return float(diff + 0.5 * iou)


def solve_icon_yolo(imgs_bytes: bytes, ques_bytes_list: list[bytes]):
    """YOLO 検出 + キュースコア + ハンガリアン法で割り付ける。

    ques 順の規格化 [(x, y)] を返す。バックエンド
    (torch/ultralytics/モデル) が無い・箱ゼロなら None。
    """
    from PIL import Image
    import io
    try:
        import cv2
        import numpy as np
        from ..yolo_icons import detect_icons
    except Exception:
        return None
    try:
        grid = np.array(Image.open(io.BytesIO(imgs_bytes)).convert("RGB"))
        gray = cv2.cvtColor(grid, cv2.COLOR_RGB2GRAY)
        H, W = gray.shape
        boxes = detect_icons(imgs_bytes)
        if not boxes:
            return None
        sils = []
        for q in ques_bytes_list:
            t = np.array(Image.open(io.BytesIO(q)).convert("RGBA"))
            s = _silhouette_crop(t)
            if s is None:
                return None
            sils.append(s)
        n, m = len(sils), len(boxes)
        mat = np.zeros((n, m))
        for i, s_ in enumerate(sils):
            for j, (x1, y1, x2, y2) in enumerate(boxes):
                crop = gray[max(0, y1 - 2):y2 + 2, max(0, x1 - 2):x2 + 2]
                if crop.size == 0:
                    continue
                mat[i, j] = score_prompt_box(crop, s_)
        try:
            from scipy.optimize import linear_sum_assignment
            ri, ci = linear_sum_assignment(mat, maximize=True)
        except Exception:  # 貪欲フォールバック
            ri, ci = zip(*sorted(
                ((i, max(range(m), key=lambda j: mat[i, j])) for i in range(n)),
                key=lambda t: -mat[t[0], t[1]]))
        order = {int(i): int(j) for i, j in zip(ri, ci)}
        out = []
        for i in range(n):
            x1, y1, x2, y2 = boxes[order[i]]
            out.append ((((x1 + x2) / 2 / W), ((y1 + y2) / 2 / H)))
        return [(round(min(1.0, max(0.0, x)), 4),
                 round(min(1.0, max(0.0, y)), 4)) for x, y in out]
    except Exception:
        return None


def match_score_native(blob_mask, sil, scales=(0.85, 1.0, 1.15),
                       max_shift: int = 8) -> float:
    """シルエットとブロブマスクの最良 IoU をスケール/シフト探索で求める。

    アイコンはプロンプトとほぼ原寸で描かれるため、箱いっぱいに引き伸ばす
    IoU と違って原寸近傍に重ねて ±ピクセルずらすだけ。
    (best_iou, dy, dx, scale) を返す。適合位置はクリック位置の精密化に使う。
    """
    import cv2
    import numpy as np
    bh, bw = blob_mask.shape
    ph, pw = sil.shape
    best = (0.0, 0, 0, 1.0)
    B = blob_mask > 0
    for sc in scales:
        nh, nw = max(1, int(ph * sc)), max(1, int(pw * sc))
        if nh > bh + max_shift or nw > bw + max_shift:
            continue
        r = cv2.resize((sil > 0).astype("uint8"), (nw, nh)) > 0
        y0 = (bh - nh) // 2
        x0 = (bw - nw) // 2
        for dy in range(-max_shift, max_shift + 1, 2):
            for dx in range(-max_shift, max_shift + 1, 2):
                yy, xx = y0 + dy, x0 + dx
                if yy < 0 or xx < 0 or yy + nh > bh or xx + nw > bw:
                    continue
                sub = B[yy:yy + nh, xx:xx + nw]
                inter = np.logical_and(r, sub).sum()
                union = r.sum() + sub.sum() - inter
                iou = inter / max(union, 1)
                if iou > best[0]:
                    best = (float(iou), dy, dx, sc)
    return best


def solve_icon_segment(imgs_bytes: bytes, ques_bytes_list: list[bytes]):
    """セグメンテーション + 原寸探索 + ハンガリアン法で割り付ける。

    依存なし (torch/onnx 不要)。ques 順の規格化 [(x, y)] を返す。
    セグメントが使い物にならなければ None。
    """
    from PIL import Image
    import io
    try:
        import cv2
        import numpy as np
    except Exception:
        return None
    try:
        grid = np.array(Image.open(io.BytesIO(imgs_bytes)).convert("RGB"))
        H, W = grid.shape[:2]
        bgr = cv2.cvtColor(grid, cv2.COLOR_RGB2BGR)
        boxes = segment_icon_boxes(bgr)
        # YOLO 箱があれば合流する (破片の結合ルールは共通)
        try:
            from ..yolo_icons import detect_icons
            for b in detect_icons(imgs_bytes):
                for m in boxes:
                    ix1, iy1 = max(b[0], m[0]), max(b[1], m[1])
                    ix2, iy2 = min(b[2], m[2]), min(b[3], m[3])
                    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                    small = min((b[2] - b[0]) * (b[3] - b[1]),
                                (m[2] - m[0]) * (m[3] - m[1]))
                    if small > 0 and inter / small > 0.3:
                        m[0], m[1] = min(m[0], b[0]), min(m[1], b[1])
                        m[2], m[3] = max(m[2], b[2]), max(m[3], b[3])
                        break
                else:
                    boxes.append([b[0], b[1], b[2], b[3]])
        except Exception:
            pass
        if not boxes:
            return None
        # 割り付け問題を絞る。アイコンは大きいブロブ側にあるはず
        if len(boxes) > 8:
            boxes = sorted(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]),
                           reverse=True)[:8]
        full = segment_mask(bgr) > 0
        sils = []
        for q in ques_bytes_list:
            t = np.array(Image.open(io.BytesIO(q)).convert("RGBA"))
            s = _silhouette_crop(t)
            if s is None:
                return None
            sils.append((s > 0).astype("uint8"))
        n, m = len(sils), len(boxes)
        mat = np.zeros((n, m))
        fits = {}
        for i, s_ in enumerate(sils):
            for j, (x1, y1, x2, y2) in enumerate(boxes):
                sub = full[max(0, y1 - 2):y2 + 2, max(0, x1 - 2):x2 + 2]
                if sub.size == 0:
                    continue
                iou, dy, dx, sc = match_score_native(sub, s_)
                mat[i, j] = iou
                fits[(i, j)] = (dy, dx, sc)
        try:
            from scipy.optimize import linear_sum_assignment
            ri, ci = linear_sum_assignment(mat, maximize=True)
        except Exception:
            ri, ci = zip(*sorted(
                ((i, max(range(m), key=lambda j: mat[i, j])) for i in range(n)),
                key=lambda t: -mat[t[0], t[1]]))
        # 品質ゲート:縮退行列 (全ゼロ列など) は後段のバックエンドに譲る
        if float(mat[ri, ci].sum()) <= 0:
            return None
        out = []
        for i, j in zip(ri, ci):
            i, j = int(i), int(j)
            x1, y1, x2, y2 = boxes[j]
            crop = full[max(0, y1 - 2):y2 + 2, max(0, x1 - 2):x2 + 2]
            # クリック位置 = 箱中心ではなく best-fit シルエットの中心
            s_ = sils[i]
            dy, dx, sc = fits[(i, j)]
            nh = max(1, int(s_.shape[0] * sc))
            nw = max(1, int(s_.shape[1] * sc))
            bh, bw = crop.shape
            cx = (max(0, x1 - 2) + (bw - nw) // 2 + dx + nw / 2) / W
            cy = (max(0, y1 - 2) + (bh - nh) // 2 + dy + nh / 2) / H
            out.append((cx, cy))
        return [(round(min(1.0, max(0.0, x)), 4),
                 round(min(1.0, max(0.0, y)), 4)) for x, y in out]
    except Exception:
        return None


def solve_icon_clicks(imgs_bytes: bytes, ques_bytes_list: list[bytes]):
    """散布アイコンソルバー -> 規格化 [(x, y)] ([0,1], wulu レジストリ形式)。

    バックエンド鎖 (成功した時点で確定):
    1. セグメンテーション + 原寸探索 + ハンガリアン法
       (依存なし。torch があれば YOLO 箱も合流)
    2. YOLO 検出 + キュースコア + ハンガリアン法
    3. 全グリッドのマルチスケール・シルエット探索 (最終手段)
    ``ques`` の順序は保持する (v4 icon のクリックは順序付き)。
    """
    from PIL import Image
    import io
    try:
        res = solve_icon_segment(imgs_bytes, ques_bytes_list)
        if res:
            return res
    except Exception:
        pass
    try:
        res = solve_icon_yolo(imgs_bytes, ques_bytes_list)
        if res:
            return res
    except Exception:
        pass
    try:
        import cv2
        import numpy as np
        grid = np.array(Image.open(io.BytesIO(imgs_bytes)).convert("RGB"))
        gray = cv2.cvtColor(grid, cv2.COLOR_RGB2GRAY)
        out = []
        for q in ques_bytes_list:
            t = np.array(Image.open(io.BytesIO(q)).convert("RGBA"))
            sil = _silhouette_crop(t)
            if sil is None:
                continue
            _, cx, cy = find_prompt_in_grid(gray, sil)
            pt = (round(min(1.0, max(0.0, cx)), 4),
                  round(min(1.0, max(0.0, cy)), 4))
            out.append(pt)
        # 近傍重複は順序保持で除去
        uniq = []
        for p in out:
            if not any(abs(p[0] - u[0]) < 0.03 and abs(p[1] - u[1]) < 0.03
                       for u in uniq):
                uniq.append(p)
        if uniq:
            return uniq
    except Exception:
        pass
    # フォールバック:旧 nine セル近似 (API の体裁は保つ)
    out = []
    for q in ques_bytes_list:
        r, c = solve_nine_heuristic(imgs_bytes, [q], 1)[0]
        out.append(((c - 0.5) / 3, (r - 0.5) / 3))
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    return uniq
