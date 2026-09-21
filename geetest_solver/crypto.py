"""w パラメータの暗号化まわり:pt0 (base64) + pt1 (AES-CBC + RSA) + pt2 (SM4/SM2、おまけ)。

RSA 公開鍵は全リポジトリ共通です (N=00C1E393...BAB81, e=0x10001)。
wulu007 は pt2 (SM4/SM2) にも対応してますが、うちはベストエフォートで
(smcryptopy がなければ分かりやすいエラーで pt1 に落とします)。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

# 全リポジトリ共通の RSA 公開鍵です (N だけ。e は 0x10001)
RSA_N_HEX = (
    "00C1E3934D1614465B33053E7F48EE4EC87B14B95EF88947713D25EECBFF7E74"
    "C7977D02DC1D9451F79DD5D1C10C29ACB6A9B4D6FB7D0A0279B6719E1772565F"
    "09AF627715919221AEF91899CAE08C0D686D748B20A3603BE2318CA6BC2B5970"
    "6592A9219D0BF05C9F65023A21D2330807252AE0066D59CEEFA5F2748EA80BAB81"
)

# pt2 用の SM2 公開鍵 (wulu007 と同じ値です)
SM2_PUBKEY_X = "9a4ea935b2576f37516d9b29cd8d8cc9bffe548ba6853253ba20f4ba44fba8c9"
SM2_PUBKEY_Y = "e97a398882769aa0dd1e3e1b5601429287303880ca17bd244ed73bf702a68fc7"


def guid() -> str:
    """16 桁のランダムな鍵種です (AES/SM4 の共通鍵に使います)。"""
    return os.urandom(8).hex()


def encrypt_pt0(plaintext: str) -> str:
    """pt=0:平文を URL セーフ base64 にするだけです。"""
    return base64.urlsafe_b64encode(plaintext.encode()).decode()


def _rsa_encrypt(key_bytes: bytes) -> bytes:
    # 生の RSA PKCS#1 v1.5 暗号化です。
    # まず pycryptodome を試して、なければ純 Python のべき乗剰余に落とします。
    try:
        from Crypto.Cipher import PKCS1_v1_5
        from Crypto.PublicKey import RSA
        key = RSA.construct((int(RSA_N_HEX, 16), 0x10001))
        return PKCS1_v1_5.new(key).encrypt(key_bytes)
    except Exception:
        # 手動で PKCS#1 v1.5 パディング + pow() 暗号化
        n = int(RSA_N_HEX, 16)
        k = (n.bit_length() + 7) // 8
        assert len(key_bytes) <= k - 11
        ps = os.urandom(k - len(key_bytes) - 3)
        ps = bytes(b if b else 1 for b in ps)  # 0 バイトは避けます
        em = b"\x00\x02" + ps + b"\x00" + key_bytes
        m = int.from_bytes(em, "big")
        c = pow(m, 0x10001, n)
        return c.to_bytes(k, "big")


def _aes_cbc_encrypt(plaintext: bytes, key: bytes) -> bytes:
    """AES-CBC 暗号化です (IV は '0'*16、PKCS7 パディング。JS と同じ仕様)。"""
    iv = b"0" * 16
    pad = 16 - len(plaintext) % 16
    plaintext = plaintext + bytes([pad]) * pad
    try:
        from Crypto.Cipher import AES
        return AES.new(key, AES.MODE_CBC, iv).encrypt(plaintext)
    except Exception:
        # `cryptography` パッケージがあればそっちで代用します
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        c = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        e = c.encryptor()
        return e.update(plaintext) + e.finalize()


def encrypt_pt1(plaintext: str) -> str:
    """pt=1:AES-CBC 暗号文(16進) + RSA 暗号化した鍵(16進) をくっつけます。"""
    key_bytes = guid().encode()
    cipher = _aes_cbc_encrypt(plaintext.encode(), key_bytes)
    enc_key = _rsa_encrypt(key_bytes)
    return cipher.hex() + enc_key.hex()


def encrypt_pt2(plaintext: str) -> str:
    """pt=2:SM4-CBC + SM2 暗号化です。smcryptopy が要ります。"""
    try:
        from smcryptopy import sm2, sm4
    except ImportError as e:
        raise RuntimeError("pt=2 には `smcryptopy` が要ります (pip install smcryptopy)") from e
    key_bytes = guid().encode()
    cipher = sm4.encrypt_cbc(plaintext.encode(), key_bytes, b"0" * 16)
    enc_key = sm2.encrypt_c1c2c3(key_bytes, SM2_PUBKEY_X + SM2_PUBKEY_Y).hex()
    return cipher.hex() + enc_key


def build_w(plaintext: str, pt: int) -> str:
    """サーバ指定の pt に応じて w を組み立てます。"""
    if pt == 0:
        return encrypt_pt0(plaintext)
    if pt == 1:
        return encrypt_pt1(plaintext)
    if pt == 2:
        return encrypt_pt2(plaintext)
    raise ValueError(f"unknown pt: {pt}")


def gen_td_sign(lot_number: str, track_data: str) -> str:
    """軌跡データの署名です (lot_number を鍵にした HMAC-SHA256)。"""
    return hmac.new(lot_number.encode(), track_data.encode(),
                    hashlib.sha256).hexdigest()
