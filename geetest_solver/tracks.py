"""人間らしいポインタ軌跡 (wulu007/hshinosa の track/* を移植。MIT)。

参考元に対する改良点:
- デフォルトON (wulu はデフォルトOFF、Geeked には存在しない)。
  td 必須のサイトがあるため。
- 入口を統一:gen_slide_track / gen_click_track / gen_nine_track /
  gen_match_track / gen_winlinze_track + track_zip / track_unzip
- ベジェ制御点 + ease(3t^2-2t^3) + ジッタ + 17ms サンプリング (参考元と同じ流儀)
"""
from __future__ import annotations

import base64
import gzip
import json
import math
import random
import time
import zlib

# イベント種別 (JS と同じ番号)
START, MOVE, END, DOWN = 0, 1, 2, 3


def _rnd(a: float, b: float) -> float:
    return random.uniform(a, b)


def _round4(pt):
    """座標を小数4桁に丸める (JS の _percent_round 相当)。"""
    return (round(pt[0], 4), round(pt[1], 4))


def _timestamps(duration: int, base: int = 0):
    """base から base+duration まで、人間らしい間隔で時刻を刻む。

    17ms 前後のランダム間隔でサンプリングする (実測の癖を模倣)。
    """
    if duration <= 0:
        yield base
        return
    yield base
    cur = 0
    while duration - cur >= 17:
        iv = 17 + random.randint(0, 10)
        nxt = cur + iv
        if duration - nxt >= 17:
            yield nxt + base
            cur = nxt
        else:
            break
    yield duration + base


def _controls(p0, p1):
    """3次ベジェの制御点2つを始終点間にサンプリングする。

    区間の 30%-70% あたりに置き、ランダムな横ずれを加えて手書き感を出す。
    距離がほぼ0なら直線に潰す。
    """
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    base = min(0.2, max(0.05, dist * 0.3))
    if dist < 0.01:
        return (x0, y0), (x1, y1)
    a1, a2 = random.uniform(-math.pi, math.pi), random.uniform(-math.pi, math.pi)
    o1, o2 = base * random.uniform(0.5, 1.0), base * random.uniform(0.5, 1.0)
    return ((x0 + dx * _rnd(0.3, 0.7) + math.cos(a1) * o1,
             y0 + dy * _rnd(0.3, 0.7) + math.sin(a1) * o1),
            (x1 - dx * _rnd(0.3, 0.7) + math.cos(a2) * o2,
             y1 - dy * _rnd(0.3, 0.7) + math.sin(a2) * o2))


def _bez(t, p0, p1, c1, c2):
    """3次ベジェ曲線上の点を求める。"""
    m = 1 - t
    return (m**3 * p0[0] + 3 * m**2 * t * c1[0] + 3 * m * t**2 * c2[0] + t**3 * p1[0],
            m**3 * p0[1] + 3 * m**2 * t * c1[1] + 3 * m * t**2 * c2[1] + t**3 * p1[1])


def _segment(p0, p1, dur: int, base: int = 0):
    """p0 -> p1 へ dur ミリ秒かけて滑らかに移動するイベント列を作る。

    時刻は [0,1] 規格化後に ease (3t^2-2t^3) で緩急を付け、
    座標に微小ジッタを載せて [0,1] に収める。
    """
    times = list(_timestamps(dur, base))
    span = times[-1] - times[0]
    c1, c2 = _controls(p0, p1)
    ev = [(times[0], *_round4(p0), MOVE)]
    for t in times[1:-1]:
        e = 3 * ((t - times[0]) / span) ** 2 - 2 * ((t - times[0]) / span) ** 3
        x, y = _bez(e, p0, p1, c1, c2)
        x = max(0.0, min(1.0, x + _rnd(-0.002, 0.002)))
        y = max(0.0, min(1.0, y + _rnd(-0.002, 0.002)))
        ev.append((t, *_round4((x, y)), MOVE))
    ev.append((times[-1], *_round4(p1), MOVE))
    return ev


class TrackBuilder:
    """軌跡セグメントを継ぎ足していく流暢ビルダー (wulu の TrackBuilder を簡略化)。"""

    def __init__(self, start):
        self.cur = start
        self.dur = 0
        self.end_point = None
        self.events = [(0, *_round4(start), START)]

    def move_to(self, x, y, duration: int):
        """(x, y) へ duration ミリ秒で移動する区間を追加する。

        継ぎ目は前区間の終点と重複するので落とす。
        """
        seg = _segment(self.cur, (x, y), duration, self.events[-1][0])
        self.events.extend(seg[1:])
        self.cur = (x, y)
        self.dur += duration
        return self

    def down(self):
        """現在位置を押下 (DOWN) マークする。"""
        e = self.events[-1]
        self.events[-1] = (e[0], e[1], e[2], DOWN)
        return self

    def end(self):
        """現在位置を最終 END マークする。"""
        e = self.events[-1]
        self.events[-1] = (e[0], e[1], e[2], END)
        self.end_point = self.cur
        return self

    def click(self, delay: int | None = None):
        """押下 (DOWN) して delay ミリ秒後に自動解放 (END) する。

        自動送信クリックの末尾パターン:同位置の DOWN 直後に END、
        間に移動なし。
        """
        delay = random.randint(80, 120) if delay is None else delay
        self.down()
        self.events.append((self.events[-1][0] + delay, *_round4(self.cur), END))
        self.end_point = self.cur
        self.dur += delay
        return self

    def build(self, max_points: int = 150):
        """イベント列を確定する。多すぎたら間引く (直近優先)。"""
        if self.end_point is None or self.dur <= 0:
            raise ValueError("build 前に start/end/duration を決めること")
        if len(self.events) <= max_points:
            return self.events
        # MOVE 以外 (クリック等の重要点) は残し、MOVE だけ間引く。
        # 終盤の点を優先して、クリック前後の粒度を保つ。
        moves = [p for p in self.events if p[3] == MOVE]
        rest = [p for p in self.events if p[3] != MOVE]
        need = max_points - len(rest) - 1
        end_t = self.events[-1][0]
        near = [p for p in moves if end_t - p[0] <= 150][-need:] if need > 0 else []
        if len(near) < need:
            older = [p for p in moves if p not in near]
            for p in reversed(older):
                if len(near) >= need:
                    break
                near.insert(0, p)
        return [(0, *self.events[0][1:3], START), *near, *rest]


def _payload(events, w: float, h: float):
    """イベント列を送信用ペイロード (m/w/h/s/e/p) で包む。"""
    s = int(time.time() * 1000)
    return {"m": 1, "w": w, "h": h, "s": s, "e": s + events[-1][0], "p": events}


def _jitter(pt, j: float):
    """目標座標に ±j の揺らぎを載せて [0,1] に収める。"""
    return (max(0.0, min(1.0, pt[0] + _rnd(-j, j))),
            max(0.0, min(1.0, pt[1] + _rnd(-j, j))))


def gen_slide_track(set_left: int, w: float = 300.015625,
                    h: float = 261.5234375):
    """スライド用ドラッグ軌跡を作る。戻り値は (ペイロード, passtime)。"""
    tb = TrackBuilder((_rnd(0.3, 0.8), _rnd(0.85, 0.99)))
    passtime = random.randint(600, 1400)
    sx = _rnd(0.1, 0.15)
    tb.move_to(sx, _rnd(0.88, 0.90), random.randint(800, 1400)).down()
    tb.move_to(sx + set_left / w, _rnd(0.88, 0.90), passtime).end()
    ev = tb.build()
    return _payload(ev, w, h), passtime


def _two_click(cells, center, w=300.015625, h=259.6015625, jitter=0.045):
    """2クリック系 (winlinze/match) 共通の骨格。

    ``center(r, c)`` で 0 始まりのセルを行き先の規格化座標に変換する。
    1セル目へ移動→クリック→2セル目へ移動→クリック。戻り値は (ペイロード, 所要時間)。
    """
    (a, b), (c, d) = cells
    t1, t2 = _jitter(center(a, b), jitter), _jitter(center(c, d), jitter)
    total = random.randint(4500, 9000)
    d1, d2 = random.randint(80, 120), random.randint(80, 120)
    m1 = int(total * _rnd(0.35, 0.55))
    m2 = max(total - m1 - d1 - d2, 1)
    tb = TrackBuilder((_rnd(0.4, 0.6), _rnd(0.9, 1.0)))
    tb.move_to(*t1, m1).click(d1)
    tb.move_to(*t2, m2).click(d2)
    ev = tb.build()
    return _payload(ev, w, h), total


def gen_match_track(cells):
    """match (3x3 入れ替え) 用の2クリック軌跡。

    ``cells`` は隣接2マスの 0 始まり座標。3x3 グリッドは画面いっぱい
    (1マス 33.4% 刻み、前提は ``left: 33.4*first%`` 形式)。
    """
    def center(i, j):
        return ((33.4 * i + 16.7) / 100, (33.4 * j + 16.7) / 100)
    return _two_click(cells, center, jitter=0.05)


def gen_winlinze_track(cells, w=300.015625, h=259.6015625):
    """winlinze (五目) 用の2クリック軌跡。

    ``cells`` は 0 始まりの (移動元, 移動先)。5x5 盤面の絶対配置
    (``left: 20*col+3%`` 等、1マス41px) からセル中心を求めてジッタを載せる。
    """
    def center(r, c):
        return ((20 * c + 3) / 100 + 20.5 / w, (19 * r + 4) / 100 + 20.5 / h)
    return _two_click(cells, center, jitter=0.04)


def gen_click_track(clicks, w=300.015625, h=259.6015625,
                    img_w=300.0, img_h=200.0, with_submit=True):
    """画像クリック系 (icon/word/phrase) 用の複数クリック軌跡。

    ``clicks`` は検証画像基準の規格化 [(x, y)] ([0,1])。内部で要素座標に
    換算するので、自作ソルバーは画像基準で返せばよい。各クリック後に
    自動送信の DOWN+END を付け、最後に送信ボタンを押す
    (``with_submit`` で省略可)。戻り値は (ペイロード, 所要時間)。
    """
    if not clicks:
        raise ValueError("clicks が空")
    targets = [_jitter((x * img_w / w, y * img_h / h), 0.02) for x, y in clicks]
    if with_submit:
        targets = targets + [_jitter((0.5, 0.92), 0.01)]
    n = len(targets)
    delays = [random.randint(80, 120) for _ in range(n)]
    total = max(random.randint(2500, 4000) - sum(delays), 1)
    ws = [random.random() for _ in range(n)]
    tot = sum(ws)
    moves = [max(int(total * x / tot), 1) for x in ws]
    moves[-1] = max(total - sum(moves[:-1]), 1)
    tb = TrackBuilder((_rnd(0.4, 0.6), _rnd(0.9, 1.0)))
    for t, dl, mv in zip(targets, delays, moves):
        tb.move_to(*t, mv).click(dl)
    ev = tb.build()
    return _payload(ev, w, h), ev[-1][0]


def gen_nine_track(cells, cols: int = 3,
                   w=300.015625, h=259.6015625):
    """nine (3x3 グリッド) 用の複数クリック軌跡。

    ``cells`` は 1 始まり [(row, col)]。グリッドが画面いっぱいで
    送信ボタンが無い (nine_nums 到達で自動送信) ため、送信クリックは付けない。
    セル中心は ``((col-0.5)/cols, (row-0.5)/cols)``。
    """
    if not cells:
        raise ValueError("cells が空")
    targets = [_jitter(((c - 0.5) / cols, (r - 0.5) / cols), 0.05)
               for r, c in cells]
    n = len(targets)
    delays = [random.randint(80, 120) for _ in range(n)]
    total = max(random.randint(2500, 4000) - sum(delays), 1)
    ws = [random.random() for _ in range(n)]
    tot = sum(ws)
    moves = [max(int(total * x / tot), 1) for x in ws]
    moves[-1] = max(total - sum(moves[:-1]), 1)
    tb = TrackBuilder((_rnd(0.4, 0.6), _rnd(0.9, 1.0)))
    for t, dl, mv in zip(targets, delays, moves):
        tb.move_to(*t, mv).click(dl)
    ev = tb.build()
    return _payload(ev, w, h), ev[-1][0]


# ---------- fflate 互換 gzip (wulu の track/compress.py) ----------
def track_zip(track, mtime: int | None = None) -> str:
    """軌跡を gg4.js と同じ方式で圧縮する:fflate の gzipSync + URL セーフ base64。

    gzip ヘッダは fflate とバイト一致するよう手組みする (fflate は OS=3 (Unix)
    固定で mtime に ``Date.now()/1000`` を書くが、:mod:`gzip` は OS=255 を出す)。
    deflate ストリーム自体は zlib と fflate で実装が別なので完全一致はしない。

    :param track: 圧縮する軌跡データ。
    :param mtime: gzip ヘッダの更新時刻。省略時は現在時刻。
    :return: パディングなし URL セーフ base64 の gzip ブロブ。
    """
    raw = json.dumps(track, separators=(",", ":"), ensure_ascii=False).encode()
    comp = zlib.compressobj(6, zlib.DEFLATED, -zlib.MAX_WBITS)
    df = comp.compress(raw) + comp.flush()
    blob = (b"\x1f\x8b\x08\x00"
            + (int(time.time()) if mtime is None else mtime).to_bytes(4, "little")
            + b"\x00\x03" + df
            + (zlib.crc32(raw) & 0xFFFFFFFF).to_bytes(4, "little")
            + (len(raw) & 0xFFFFFFFF).to_bytes(4, "little"))
    return base64.urlsafe_b64encode(blob).decode().rstrip("=")


def track_unzip(s: str):
    """track_zip の逆変換 (デバッグ用)。パディングを補って展開する。"""
    s += "=" * (-len(s) % 4)
    return json.loads(gzip.decompress(base64.urlsafe_b64decode(s)).decode())
