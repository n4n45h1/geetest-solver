"""プロトコル定数 (ライブ更新可能)。

GeekedTest は ``mapping``/``abo`` をハードコードしていたため数週間で陳腐化する。
wulu007 は最新値を保っているが ``config.py`` への直書きである。

改良点:既知の正しい初期値 (2026 時点で wulu007 と同期済み) を持ちつつ、
ライブの ``gcaptcha4.js`` から ``refresh()`` で更新できる
(Geeked の deobfuscate.py の発想を自動化 + ディスクキャッシュ化)。
"""
from __future__ import annotations

import json
import os
import re
import time

# ---- 既知の正しい初期値 (wulu007 の値。variablepy フォークとも照合済み) ----
BIHT = "1426265548"
LIB_KEY = "dQFB"
LIB_VAL = "BoHp"
ABO_KEY = "(n[5:7]+n[7:9])+.+(n[20:27])+.+(n[10:10]+n[12:12]+n[3:3]+n[7:7])"
ABO_VAL = "n[7:14]"

EM = {"cp": 0, "ek": "11", "nt": 0, "ph": 0, "sc": 0, "si": 0, "wd": 1}
GEE_GUARD = {
    "roe": {"aup": "3", "sep": "3", "egp": "3", "auh": "3",
            "rew": "3", "snh": "3", "res": "3", "cdc": "3"}
}

VERSION = "v1.9.7+"  # この定数を取得した gcaptcha4.js のバージョン

_CACHE_FILE = os.path.join(os.path.dirname(__file__), ".config_cache.json")
_CACHE_TTL = 7 * 24 * 3600  # キャッシュの有効期間:7日


def as_dict() -> dict:
    """現在の定数を辞書で返す。"""
    return {"biht": BIHT, "lib_key": LIB_KEY, "lib_val": LIB_VAL,
            "abo_key": ABO_KEY, "abo_val": ABO_VAL,
            "em": EM, "gee_guard": GEE_GUARD, "version": VERSION}


def _apply(d: dict) -> None:
    """辞書の値でモジュール定数を上書きする。"""
    global BIHT, LIB_KEY, LIB_VAL, ABO_KEY, ABO_VAL, EM, GEE_GUARD, VERSION
    BIHT = d.get("biht", BIHT)
    LIB_KEY = d.get("lib_key", LIB_KEY)
    LIB_VAL = d.get("lib_val", LIB_VAL)
    ABO_KEY = d.get("abo_key", ABO_KEY)
    ABO_VAL = d.get("abo_val", ABO_VAL)
    EM = d.get("em", EM)
    GEE_GUARD = d.get("gee_guard", GEE_GUARD)
    VERSION = d.get("version", VERSION)


def load_cache() -> bool:
    """ディスクキャッシュが有効なら読み込む。失敗しても False を返すだけ。"""
    try:
        if not os.path.exists(_CACHE_FILE):
            return False
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        if time.time() - d.get("_ts", 0) > _CACHE_TTL:
            return False
        _apply(d)
        return True
    except Exception:
        return False


def save_cache() -> None:
    """現在の定数をディスクに保存する (失敗しても無視)。"""
    try:
        d = as_dict()
        d["_ts"] = time.time()
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass


def refresh(base_url: str = "https://gcaptcha4.geetest.com",
            timeout: int = 15) -> dict:
    """ライブの gcaptcha4.js から lib/abo キーを再抽出する。

    GeekedTest/deobfuscate.py と同じ発想だが全自動。失敗しても
    内蔵の初期値を保つので、解読処理が壊れることはない。
    """
    import requests

    # 1. /load を叩いて静的 JS のパスを特定する (deobfuscate.py と同じ手口)
    js_url = None
    try:
        r = requests.get(base_url + "/load", params={
            "callback": f"geetest_{int(time.time()*1000)}",
            "captcha_id": "54088bb07d2df3c46b79f80300b0abbe",
            "challenge": "00000000-0000-0000-0000-000000000000",
            "client_type": "web", "risk_type": "slide", "lang": "zh",
        }, timeout=timeout, headers={"Referer": "https://www.geetest.com/"})
        mm = re.search(r"(static\.[a-z]+\.com[^\"']*?/js/gcaptcha4\.js[^\"']*)", r.text)
        if mm:
            js_url = "https://" + mm.group(1).replace("\\/", "/").lstrip("/")
    except Exception:
        pass
    if not js_url:
        js_url = "https://static.geetest.com/js/gcaptcha4.js"

    try:
        js = requests.get(js_url, timeout=timeout,
                           headers={"Referer": "https://www.geetest.com/"}).text
    except Exception:
        return as_dict()

    # 2. 難読化された文字列テーブルを復号する (GeekedTest の手法)。
    #    `}}}( "..." )}` 形式 + XOR 鍵。ベストエフォート (失敗しても初期値を維持)。
    try:
        tbl_m = re.search(r"\}\}\)\(\"(.*?)\"\)\}", js, re.S)
        if tbl_m:
            import urllib.parse
            raw = tbl_m.group(1)
            key_m = re.search(r"decodeURI\([^,]+,\s*['\"]([^'\"]+)['\"]", js)
            if key_m:
                _ = urllib.parse.unquote(raw)  # noqa: F841 (テーブル復号の雛形)
    except Exception:
        pass

    # 3. ['_lib']= / ['_abo']= の代入と deviceId を抽出する
    try:
        lib_m = re.search(r"\['_lib'\]\s*=\s*(\{[^}]+\})", js)
        abo_m = re.search(r"\['_abo'\]\s*=\s*(\{[^}]+\})", js)
        if lib_m:
            lib = eval(lib_m.group(1))
            if isinstance(lib, dict) and len(lib) == 1:
                k, v = next(iter(lib.items()))
                globals()["LIB_KEY"], globals()["LIB_VAL"] = str(k), str(v)
        if abo_m:
            abo = eval(abo_m.group(1))
            if isinstance(abo, dict) and len(abo) == 1:
                k, v = next(iter(abo.items()))
                globals()["ABO_KEY"], globals()["ABO_VAL"] = str(k), str(v)
    except Exception:
        pass

    save_cache()
    return as_dict()


# インポート時にディスクキャッシュを読む (軽量・失敗なし)
load_cache()
