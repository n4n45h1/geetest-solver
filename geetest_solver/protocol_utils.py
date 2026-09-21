"""lotParser + PoW (5 リポジトリ共通の線路ロジックをここに統一)。"""
from __future__ import annotations

import hashlib
import uuid

# PoW 難易度の余りビットに対する16進しきい値 (JS と同じ対応表)
_THRESHOLDS = {0: "f", 1: "7", 2: "3", 3: "1"}
_HASH_FN = {"md5": hashlib.md5, "sha1": hashlib.sha1, "sha256": hashlib.sha256}


# ---------- lotParser (Geeked の LotParser.get_dict / wulu の parse_abo_pair) ----------
def _parse_lot_string(pattern: str) -> list:
    """`n[5:7]+n[7:9]` 形式のパターンをインデックス範囲のリストに分解する。"""
    result = []
    for part in pattern.split("+.+"):
        group = []
        for single in part.split("+"):
            inner = single[single.index("[") + 1: single.index("]")]
            bounds = [int(n) for n in inner.split(":")]
            group.append(bounds)
        result.append(group)
    return result


def _get_string_by_indexes(indexes: list, s: str) -> str:
    """lot_number 文字列から指定範囲を切り出して `.` 連結する。"""
    parts = []
    for group in indexes:
        gs = ""
        for r in group:
            start = r[0]
            end = r[1] + 1 if len(r) > 1 else start + 1
            gs += s[start:end]
        parts.append(gs)
    return ".".join(parts)


def parse_abo_pair(key: str, value: str, lot_number: str) -> dict:
    """`a.b.c` 形式のドット付きキー文字列からネスト辞書を作る。

    例:キー `pow.msg` + 値 `xxxx` -> `{'pow': {'msg': 'xxxx'}}`
    """
    key_str = _get_string_by_indexes(_parse_lot_string(key), lot_number)
    val_str = _get_string_by_indexes(_parse_lot_string(value), lot_number)
    parts = key_str.split(".")
    obj: dict = {}
    cur = obj
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    if parts:
        cur[parts[-1]] = val_str
    return obj


# ---------- PoW (Proof of Work) ----------
def generate_pow(lot_number: str, captcha_id: str, *,
                 hashfunc: str = "md5", version: str = "1",
                 bits: int = 10, datetime: str = "",
                 extra: str = "") -> dict:
    """指定難易度を満たすハッシュが出るまでランダム値を回す。

    判定条件 (JS と同一):先頭 `bits//4` 桁が `0` で、次の1桁がしきい値以下。
    """
    if hashfunc not in _HASH_FN:
        raise ValueError(f"未対応の PoW ハッシュ: {hashfunc}")
    fn = _HASH_FN[hashfunc]
    rem, zeros = bits % 4, bits // 4
    prefix, threshold = "0" * zeros, _THRESHOLDS[rem]
    header = f"{version}|{bits}|{hashfunc}|{datetime}|{captcha_id}|{lot_number}|{extra}|"
    while True:
        rand = uuid.uuid4().hex
        msg = header + rand
        h = fn(msg.encode()).hexdigest()
        if h.startswith(prefix) and h[zeros] <= threshold:
            return {"pow_msg": msg, "pow_sign": h}
