"""GeeTest v4 統合 (同期+非同期)。

全体の流れ (全リポジトリ共通):
  GET {base}/load  -> lot_number/payload/process_token/pow_detail/captcha_type/... を取得
  static.geetest.com から素材を落とす -> 解く -> userresponse+passtime+track を作る
  GET {base}/verify?w=...(&td=...) -> data.seccode を受け取る

改良点:
- curl_cffi (chrome124 指紋) + requests フォールバック
  (wulu は wreq 必須、Geeked は chrome124 固定)
- track はデフォルトON、td+td_sign を自動付与
- pt はサーバ指定に従い、失敗時は 1->0 に降格
- 全タイプ対応のソルバーレジストリ (wulu の発想を nine/icon まで拡張)
- 指数バックオフ付きリトライ (wulu は固定回数のみ)
"""
from __future__ import annotations

import json
import random
import time
import uuid

from . import config as _cfg
from .crypto import build_w, gen_td_sign
from .protocol_utils import generate_pow, parse_abo_pair
from .solvers import (
    solve_gobang, solve_match, solve_nine, solve_slide,
    solve_winlinze, userresponse_from_setleft,
)
from .solvers.nine_icon import solve_icon_clicks
from .tracks import (
    gen_click_track, gen_match_track, gen_nine_track,
    gen_slide_track, gen_winlinze_track, track_zip,
)

LOAD_PATH = "/load"
VERIFY_PATH = "/verify"


class VerifyError(RuntimeError):
    """リトライを使い切っても通らなかったときの例外。"""
    pass


def _callback() -> str:
    """JSONP コールバック名 (`geetest_<ミリ秒>`)。"""
    return f"geetest_{int(time.time() * 1000)}"


def _unwrap_jsonp(text: str) -> dict:
    """`geetest_123({...})` を剥がして辞書化する。"""
    t = text.strip()
    if "(" in t:
        t = t[t.index("(") + 1: t.rindex(")")]
    return json.loads(t)


def _make_session(proxy=None, headers=None, timeout=20):
    """HTTP セッションを作る。curl_cffi (TLS 指紋付き) を優先し、
    無ければ requests にフォールバックする。"""
    hdrs = {"Accept": "*/*", "Referer": "https://www.geetest.com/",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "sec-ch-ua-mobile": "?0"}
    if headers:
        hdrs.update(headers)
    try:
        from curl_cffi import requests as cr
        s = cr.Session(impersonate="chrome124")
        s.headers.update(hdrs)
        if proxy:
            s.proxies = {"http": proxy, "https": proxy}
        s._gt_timeout = timeout
        s._gt_is_curl = True
        return s
    except Exception:
        import requests as rq
        s = rq.Session()
        s.headers.update(hdrs)
        if proxy:
            s.proxies = {"http": proxy, "https": proxy}
        s._gt_timeout = timeout
        s._gt_is_curl = False
        return s


def _http_get(session, url, params):
    """GET してテキストを返す (curl_cffi / requests 両対応)。"""
    to = getattr(session, "_gt_timeout", 20)
    r = session.get(url, params=params, timeout=to)
    return r.text if hasattr(r, "text") else r.content.decode()


def _http_get_bytes(session, url):
    """GET してバイト列を返す (画像素材用)。"""
    to = getattr(session, "_gt_timeout", 20)
    r = session.get(url, timeout=to)
    return r.content if hasattr(r, "content") else bytes(r)


class GeetestSolver:
    """改良ソルバーの本体。``Geeked(captcha_id, risk_type).solve()`` と互換。"""

    BASE_URL = "https://gcaptcha4.geetest.com"
    IMG_BASE = "https://static.geetest.com"

    _solvers: dict = {}

    def __init__(self, captcha_id: str, risk_type: str = "slide",
                 client_type: str = "web", lang: str = "zh",
                 proxy: str | None = None, headers: dict | None = None,
                 timeout: int = 20, track_enable: bool = True,
                 base_url: str | None = None, session=None):
        self.captcha_id = captcha_id
        self.risk_type = risk_type
        self.client_type = client_type
        self.lang = lang
        self.timeout = timeout
        self.track_enable = track_enable
        if base_url:
            self.BASE_URL = base_url
        self.session = session or _make_session(proxy, headers, timeout)

    # ---- ソルバーレジストリ (wulu の register_solver を拡張) ----
    @classmethod
    def register_solver(cls, risk, fn=None):
        """指定タイプ用の自作ソルバーを登録する。

        直接呼び出し::

            GeetestSolver.register_solver('slide', my_slide_func)

        デコレータ::

            @GeetestSolver.register_solver('slide')
            def my_slide_func(bg, slice, ypos): ...
        """
        def deco(f):
            cls._solvers[risk] = f
            return f
        return deco(fn) if fn else deco

    # ---- プロトコル ----
    def load(self) -> dict:
        """`/load` を叩いてチャレンジ情報 (lot_number 等) を取得する。"""
        params = {"callback": _callback(), "captcha_id": self.captcha_id,
                  "challenge": str(uuid.uuid4()), "client_type": self.client_type,
                  "risk_type": self.risk_type, "lang": self.lang}
        try:
            data = _unwrap_jsonp(_http_get(self.session, self.BASE_URL + LOAD_PATH, params))
        except Exception as e:
            raise RuntimeError(f"load に失敗: {e}") from e
        d = data.get("data")
        if not isinstance(d, dict):
            raise RuntimeError(f"load の応答が不正: {str(data)[:200]}")
        return d

    async def aload(self) -> dict:
        """load の非同期版 (中身は同じ同期処理)。"""
        return self.load()

    def _resource(self, path: str) -> bytes:
        """static.geetest.com から画像素材を落とす。"""
        sep = "" if path.startswith("/") else "/"
        return _http_get_bytes(self.session, self.IMG_BASE + sep + path)

    def generate_w(self, data: dict, ans: dict) -> str:
        """verify 用の `w` パラメータを組み立てる (PoW + abo + 解答 + 暗号化)。"""
        lot = data["lot_number"]
        payload = {**generate_pow(lot, data.get("captcha_id", self.captcha_id),
                                  **data["pow_detail"]),
                   **parse_abo_pair(_cfg.ABO_KEY, _cfg.ABO_VAL, lot),
                   _cfg.LIB_KEY: _cfg.LIB_VAL,
                   "biht": _cfg.BIHT, "device_id": "", "em": _cfg.EM,
                   "ep": "123", "geetest": "captcha", "lang": "zh",
                   "lot_number": lot,
                   **{k: v for k, v in ans.items() if k != "track"}}
        if ans.get("track") is not None:
            payload["td_sign"] = gen_td_sign(lot, ans["track"])
        if data.get("guard"):
            payload.update(_cfg.GEE_GUARD)
        pt = int(data.get("pt", 1))
        blob = json.dumps(payload, separators=(",", ":"))
        try:
            return build_w(blob, pt)
        except RuntimeError:
            if pt == 2:  # smcryptopy が無い -> pt=1 に降格
                return build_w(blob, 1)
            raise
        except Exception:
            if pt != 0:
                return build_w(blob, 0)
            raise

    # ---- 求解 ----
    def auto_solve(self, data: dict) -> dict:
        """captcha_type に応じて解き、userresponse/passtime/track を返す。"""
        ct = data.get("captcha_type", self.risk_type)
        if ct in self._solvers:
            return self._solvers[ct](data, self)
        ans: dict = {}
        if ct == "ai":
            pass  # ai は無音検証。解答不要
        elif ct == "slide":
            data["bg"] = self._resource(data["bg"]) if isinstance(data.get("bg"), str) else data["bg"]
            data["slice"] = self._resource(data["slice"]) if isinstance(data.get("slice"), str) else data["slice"]
            sl = solve_slide(data["bg"], data["slice"], int(data.get("ypos", 0)))
            ans["setLeft"] = sl
            ans["userresponse"] = userresponse_from_setleft(sl)
            if self.track_enable:
                ans["track"], ans["passtime"] = gen_slide_track(sl)
            else:
                ans["passtime"] = random.randint(600, 1200)
        elif ct in ("icon", "word"):
            data["imgs"] = self._resource(data["imgs"]) if isinstance(data.get("imgs"), str) else data["imgs"]
            data["ques"] = [self._resource(u) if isinstance(u, str) else u for u in data["ques"]]
            clicks = solve_icon_clicks(data["imgs"], data["ques"])
            # icon の線路形式 (GeekedTest + syncrain。live 検証済み):
            # 画像ピクセル座標 x*33 / y*49 (wulu 想定の percent*10000 ではない)
            try:
                from PIL import Image
                import io as _io
                _gw, _gh = Image.open(_io.BytesIO(data["imgs"])).size
            except Exception:
                _gw, _gh = 300, 200
            ans["userresponse"] = [[int(x * _gw * 33), int(y * _gh * 49)]
                                   for x, y in clicks]
            if self.track_enable:
                ans["track"], ans["passtime"] = gen_click_track(clicks)
            else:
                ans["passtime"] = random.randint(2500, 4000)
        elif ct == "nine":
            data["imgs"] = self._resource(data["imgs"]) if isinstance(data.get("imgs"), str) else data["imgs"]
            data["ques"] = [self._resource(u) if isinstance(u, str) else u for u in data["ques"]]
            cells = solve_nine(data["imgs"], data["ques"], int(data.get("nine_nums", 3)))
            ans["userresponse"] = [list(c) for c in cells]
            if self.track_enable:
                ans["track"], ans["passtime"] = gen_nine_track(cells)
            else:
                ans["passtime"] = random.randint(2500, 4000)
        elif ct == "match":
            cells = solve_match(data["ques"])
            if cells is None:
                raise NotImplementedError("match: 交換手が見つからない")
            ans["userresponse"] = [list(c) for c in cells]
            if self.track_enable:
                ans["track"], ans["passtime"] = gen_match_track(cells)
            else:
                ans["passtime"] = random.randint(4500, 9000)
        elif ct in ("winlinze", "gobang"):
            cells = solve_winlinze(data["ques"])
            if cells is None:
                cells = solve_gobang(data["ques"])
            if cells is None:
                raise NotImplementedError("winlinze: 勝ち手が見つからない")
            ans["userresponse"] = [list(c) for c in cells]
            if self.track_enable:
                ans["track"], ans["passtime"] = gen_winlinze_track(cells)
            else:
                ans["passtime"] = random.randint(4500, 9000)
        elif ct == "phrase":
            ans["userresponse"] = []
            ans["passtime"] = random.randint(1000, 2000)
        else:
            raise NotImplementedError(f"captcha_type {ct!r} は未対応 "
                                      f"(register_solver で自作を差し込めます)")
        return ans

    def verify(self, data: dict) -> dict:
        """解答を作って `/verify` に投げる。応答 JSON をそのまま返す。"""
        data.setdefault("captcha_id", self.captcha_id)
        ans = self.auto_solve(data)
        track_b64 = track_zip(ans["track"]) if ans.get("track") else None
        if not self.track_enable:
            ans.pop("track", None)
        else:
            ans["track"] = track_b64
        q = {"callback": _callback(), "captcha_id": self.captcha_id,
             "client_type": self.client_type, "risk_type": self.risk_type,
             "lot_number": data["lot_number"], "payload": data["payload"],
             "process_token": data["process_token"],
             "payload_protocol": data["payload_protocol"], "pt": data.get("pt", 1),
             "w": self.generate_w(data, ans)}
        if track_b64 is not None and self.track_enable:
            q["td"] = track_b64
        try:
            return _unwrap_jsonp(_http_get(self.session, self.BASE_URL + VERIFY_PATH, q))
        except Exception as e:
            raise RuntimeError(f"verify に失敗: {e}") from e

    async def averify(self, data: dict) -> dict:
        """verify の非同期版 (中身は同じ同期処理)。"""
        return self.verify(data)

    def solve(self, retry: int = 3, backoff: float = 1.5) -> dict:
        """load->verify をリトライ付きで一気通貫。成功時は seccode 辞書を返す。

        Geeked 互換の戻り値: {lot_number, pass_token, gen_time, captcha_output}
        """
        last = None
        for attempt in range(retry):
            data = self.load()
            resp = self.verify(data)
            d = resp.get("data", {})
            if d.get("result") == "success":
                return d.get("seccode", d)
            last = resp
            if attempt < retry - 1:
                # 指数バックオフ + ジッタで少し待ってから次へ
                time.sleep(backoff * (attempt + 1) * random.uniform(0.7, 1.3))
        raise VerifyError(f"{retry} 回試して通らなかった: {str(last)[:300]}")

    async def asolve(self, retry: int = 3, backoff: float = 1.5) -> dict:
        """solve の非同期版 (中身は同じ同期処理)。"""
        return self.solve(retry, backoff)

    # wulu 流の呼び名
    resolve = solve


# Geeked 流の呼び名
Geeked = GeetestSolver
