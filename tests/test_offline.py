"""Offline tests. network / captcha_id は不要。"""
import io
import json


def _make_slide_images(x0=120, seed=7):
    """合成スライド画像を作ります (背景にピース相当をはめ込んだやつ)。"""
    try:
        import cv2
        import numpy as np
    except Exception:
        return None
    rng = np.random.RandomState(seed)
    bg = (rng.rand(150, 300, 3) * 255).astype("uint8")
    bg = cv2.GaussianBlur(bg, (5, 5), 0)
    # 40x40 piece with transparent padding
    sl = np.zeros((40, 40, 4), dtype="uint8")
    sl[4:-4, 4:-4, :3] = bg[50:82, x0:x0 + 32].copy()
    sl[4:-4, 4:-4, 3] = 255
    _, bg_b = cv2.imencode(".png", bg)
    _, sl_b = cv2.imencode(".png", sl)
    return bytes(bg_b), bytes(sl_b), x0


def test_pow_lot_crypto():
    """PoW / lotParser / 暗号の往復テストです。"""
    from geetest_solver.protocol_utils import generate_pow, parse_abo_pair
    from geetest_solver.crypto import build_w, encrypt_pt0, gen_td_sign
    lot = "abcdef0123456789" * 4
    r = generate_pow(lot, "test_id", hashfunc="md5", bits=8,
                     version="1", datetime="20240101")
    assert r["pow_msg"].startswith("1|8|md5|20240101|test_id|" + lot + "||")
    import hashlib
    assert hashlib.md5(r["pow_msg"].encode()).hexdigest() == r["pow_sign"]
    d = parse_abo_pair("(n[0:0])+.+(n[2:2])", "n[4:4]", lot)
    assert d == {"a": {"c": "e"}}, d
    import base64
    assert encrypt_pt0("hi") == base64.urlsafe_b64encode(b"hi").decode()
    w0 = build_w('{"a":1}', 0)
    assert base64.urlsafe_b64decode(w0 + "=").decode() == '{"a":1}'
    assert len(gen_td_sign("lot", "track")) == 64
    print("pow/lot/crypto OK")


def test_slide_hybrid():
    """ハイブリッドなスライド検出のテストです。"""
    imgs = _make_slide_images()
    if imgs is None:
        print("slide SKIP (cv2 なし)")
        return
    from geetest_solver.solvers import solve_slide, solve_slide_hybrid
    bg_b, sl_b, x0 = imgs
    x, conf, method = solve_slide_hybrid(bg_b, sl_b, 50)
    # slice has 4px transparent padding
    assert abs(x - (x0 - 4)) <= 3, f"got {x} want ~{x0-4} ({method} {conf:.3f})"
    assert solve_slide(bg_b, sl_b, 50) == x
    print(f"slide OK: x={x} (truth {x0}) conf={conf:.3f} method={method}")


def test_boards():
    """盤面ソルバー (gobang/match/winlinze) のテストです。"""
    from geetest_solver.solvers import solve_gobang, solve_match, solve_winlinze
    # gobang: 4 pieces + 1 empty
    b = [[0] * 5 for _ in range(5)]
    b[2] = [1, 1, 1, 1, 0]
    r = solve_gobang(b)
    assert r and r[1] == [2, 4], r
    # match may return None for this fixture
    q = [1, 2, 1, 2, 1, 2, 0, 0, 0]
    m = solve_match(q)
    assert m is None or len(m) == 2
    # nearly-complete line with a movable piece
    w = [1]*4 + [0] + [1] + [0]*19
    assert solve_winlinze(w) is not None
    print("boards OK")


def test_tracks():
    """全種の軌跡生成 + zip/unzip 往復テストです。"""
    from geetest_solver.tracks import (
        gen_click_track, gen_match_track, gen_nine_track,
        gen_slide_track, gen_winlinze_track, track_unzip, track_zip)
    for t, _ in (gen_slide_track(120), gen_nine_track([(1, 1), (2, 2), (3, 3)]),
                 gen_click_track([(0.3, 0.4)]),
                 gen_match_track(((0, 0), (0, 1))),
                 gen_winlinze_track(((0, 0), (4, 4)))):
        assert track_unzip(track_zip(t))["p"]
    print("tracks OK")


def test_generate_w_and_registry():
    """w 組み立て + ソルバーレジストリのテストです。"""
    from geetest_solver.client import GeetestSolver
    g = GeetestSolver.__new__(GeetestSolver)
    g.captcha_id = "cid"
    data = {"lot_number": "a" * 64, "captcha_id": "cid",
            "pow_detail": {"hashfunc": "md5", "version": "1", "bits": 8,
                           "datetime": "20240101"},
            "pt": 0, "guard": ""}
    w = g.generate_w(data, {"userresponse": 1, "passtime": 800})
    import base64
    blob = json.loads(base64.urlsafe_b64decode(w + "===" ).decode())
    assert blob["lot_number"] == "a" * 64 and blob["userresponse"] == 1

    @GeetestSolver.register_solver("demo_x")
    def _demo(data, solver):
        return {"userresponse": 1}
    assert GeetestSolver._solvers["demo_x"](None, None) == {"userresponse": 1}
    del GeetestSolver._solvers["demo_x"]
    print("generate_w/registry OK")


def test_icon_positions():
    """アイコン位置特定のテストです (合成円盤でチェック)。"""
    import io
    import numpy as np
    from PIL import Image
    from geetest_solver.solvers import find_prompt_in_grid, solve_icon_clicks
    rng = np.random.RandomState(3)
    grid = (rng.rand(200, 300) * 255).astype("uint8")
    # put a black disc at a known position
    yy, xx = np.ogrid[:200, :300]
    disc = (xx - 200) ** 2 + (yy - 100) ** 2 <= 15 ** 2
    grid[disc] = 0
    buf = io.BytesIO()
    Image.fromarray(grid).convert("RGB").save(buf, format="PNG")
    grid_b = buf.getvalue()
    # 48x48 RGBA prompt with a centered disc
    p = np.zeros((48, 48, 4), dtype="uint8")
    py, px = np.ogrid[:48, :48]
    m = (px - 24) ** 2 + (py - 24) ** 2 <= 15 ** 2
    p[m, :3] = 0
    p[m, 3] = 255
    p[~m, 3] = 0
    buf = io.BytesIO()
    Image.fromarray(p).save(buf, format="PNG")
    prompt_b = buf.getvalue()
    import cv2
    score, cx, cy = find_prompt_in_grid(grid, (m * 255).astype("uint8"))
    assert abs(cx * 300 - 200) < 12 and abs(cy * 200 - 100) < 12, (score, cx, cy)
    clicks = solve_icon_clicks(grid_b, [prompt_b])
    assert len(clicks) == 1
    assert abs(clicks[0][0] * 300 - 200) < 15 and abs(clicks[0][1] * 200 - 100) < 15, clicks
    print(f"icon OK: score={score:.3f} pos=({cx*300:.0f},{cy*200:.0f})")


if __name__ == "__main__":
    test_pow_lot_crypto()
    test_slide_hybrid()
    test_boards()
    test_tracks()
    test_generate_w_and_registry()
    test_icon_positions()
    print("ALL OFFLINE TESTS PASSED")
