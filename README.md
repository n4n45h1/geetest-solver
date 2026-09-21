# geetest-solver-improved

GeeTest v4 のソルバーです。公開リポジトリを5つ読み比べて、
いいとこ取り＋自分なりの改良を入れた。(ただパクっただけだけど)
ブラウザなしで動く純 Python 実装です。
参考にさせてもらったリポジトリの開発者に感謝します。

| 参考リポジトリ | もらってきたもの |
|---|---|
| [xKiian/GeekedTest](https://github.com/xKiian/GeekedTest) | 基本プロトコル (`load`/`verify`/`w`)、五目ソルバー、`userresponse = left/1.0059466+2` の係数、**deobfuscate のアイデア** (自動化＋キャッシュ化しました) |
| [wulu007/geetest-bypass](https://github.com/wulu007/geetest-bypass) | 最新の `abo`/`lib` キー、`pt0/1/2`、ベジェ `TrackBuilder` + `track_zip` + `td_sign`、ソルバーレジストリ、タイプ別 passtime |
| [aster-go/Datadome-GeeTest-Captcha-Solver](https://github.com/aster-go/Datadome-GeeTest-Captcha-Solver) | Canny(100,200)＋テンプレートの画像処理、bbox/透過の扱い |
| [hshinosa/geetest-solver-nine](https://github.com/hshinosa/geetest-solver-nine) | ONNX マッチャーのIF＋マージン判定リトライ、`BrowserVT` (おまけ)、nine の `userresponse`/軌跡形式 |
| [variablepy/GeeTest-Solver](https://github.com/variablepy/GeeTest-Solver) | すっきりした分割構成 (challenge/crypto/client) |
| [syncrain/geetest-solver](https://github.com/syncrain/geetest-solver) (MIT) | icon 座標スケール `x*33/y*49` (live で検証済み)、YOLO `best.pt` の入手先 |
| [Evil-Bane/Geetest-Solver](https://github.com/Evil-Bane/Geetest-Solver) | ORB＋CLAHE＋極性反転マッチの発想 (試した結果、見送った経緯は後述) |

## 元リポジトリたちからの改良ポイント

1. **スライド検出** — `MORPH_GRADIENT` (wulu 式) **+** `Canny` (Geeked/aster 式) を信頼度でいい方採用。ypos 帯＋全画像フォールバック付き。どっちかだけだと外すケースがあるので両方走らせます。
2. **track はデフォルトON** — Geeked には無くて、wulu はデフォルトOFF。`td`+`td_sign` 必須のサイトがあるので、ベジェ＋`ease(3t²-2t³)`＋ジッタ＋17ms サンプリングの fflate 互換 gzip を自動で付けます。
3. **定数は自動更新** — Geeked の定数は数週間で腐って、手動の `deobfuscate.py` が必要でした。ここでは現行値を内蔵しつつ `refresh()`＋ディスクキャッシュできます (`python -m geetest_solver.deobfuscate`)。
4. **dddddocr サーバいらず** — Geeked の icon は外部サーバ必須でした。ここでは nine/icon のヒューリスティック内蔵で、`register_onnx_matcher` / `register_solver` で差し替えもできます。
5. **しぶといクライアント** — 同期＋非同期、`curl_cffi` の TLS 指紋 (ダメなら `requests` にフォールバック)、プロキシ対応、指数バックオフの `solve(retry)`、`pt` 自動＋`1→0` 降格 (pt2 は `smcryptopy` が要ります)。
6. **依存は軽め** — `requests+numpy+Pillow+pycryptodome` だけで動きます。`opencv-python`＋`curl_cffi` はあると快適 (`pip install -e ".[full]"`)。

## インストール

```bash
pip install -e .
pip install -e ".[full]"   # おすすめ: opencv + curl_cffi
pip install -e ".[icon]"    # icon 用 YOLO (torch + ultralytics)
```

## 使い方

```python
from geetest_solver import GeetestSolver

solver = GeetestSolver(captcha_id="54088bb07d2df3c46b79f80300b0abbe", risk_type="slide")
print(solver.solve())  # -> {lot_number, pass_token, gen_time, captcha_output}
# {'captcha_id': ..., 'lot_number': ..., 'pass_token': ..., 'gen_time': ..., 'captcha_output': ...}
```

対応 risk_type: `ai slide match winlinze/gobang nine icon word phrase` (+ レジストリで自作も足せます)。

```python
# 自作ソルバーの差し込み (wulu 式を全タイプに拡張)
@GeetestSolver.register_solver("icon")
def my_icon(data, solver):
    from geetest_solver.tracks import gen_click_track
    clicks = [(0.3, 0.4)]  # 規格化 [0,1]
    track, passtime = gen_click_track(clicks)
    return {"userresponse": [[3000, 4000]], "passtime": passtime, "track": track}

# ONNX nine マッチャーの差し込み (hshinosa 式のマージン判定つき)
from geetest_solver.solvers import register_onnx_matcher
@register_onnx_matcher
def my_matcher(prompt_bytes, grid_bytes) -> list[float]:
    return [0.0]*9
```

プロキシ / ヘッダ / 軌跡なしで：

```python
s = GeetestSolver(captcha_id, risk_type="slide", proxy="http://127.0.0.1:8080",
                  track_enable=True, timeout=20)
```

GeeTest が `gcaptcha4.js` を更新して定数が腐ったら：

```bash
python -m geetest_solver.deobfuscate
```

非ブラウザ TLS に `svg_seed` を返すサイト用 (hshinosa の `BrowserVT` のアイデア、おまけ)：

```python
from geetest_solver.browser_vt import BrowserVT  # playwright が要ります
vt = BrowserVT(signup_url="https://example.com/signup", ...)
token, lot = vt.get_vt_for("user@example.com")
```

## 中身の構成

```
geetest_solver/
  __init__.py  client.py (GeetestSolver 本体: load/verify/solve + レジストリ)
  config.py (abo/lib/biht をライブ更新できるやつ)  crypto.py (pt0/1/2 + td_sign)
  protocol_utils.py (lotParser + PoW)  tracks.py (ベジェ軌跡 + track_zip)
  solvers/slide.py (ハイブリッド)  solvers/board.py (五目/match/winlinze)
  solvers/nine_icon.py (セグメンテーション + ONNX フック)
  yolo_icons.py (おまけの YOLO 検出バックエンド)
  deobfuscate.py  browser_vt.py (おまけ)
tests/test_offline.py  examples/solve_slide.py
```

## 実測 — 公式デモ (2026-09-18)

https://www.geetest.com/en/adaptive-captcha-demo
(`captcha_id=fcd636b4514bf7ac4143922550b3008b`、ブラウザなし直 HTTPS)：

| risk_type | 結果 |
|---|---|
| `slide` | ✅ 3/3 |
| `ai` | ✅ 3/3 |
| `winlinze` | ✅ 3/3 |
| `match` | ✅ 6/6 (たまに難しい盤面あり) |
| `icon` | ❌ (なんか実装できなかった、下を見てください) |

live で検証してコードに反映したこと：

- `match` の盤面は**空行 (0) 完成も勝ち扱い** —
  実測したら `[[0,3,1],[2,0,2],[0,1,3]]` がそれ以外で解けませんでした。
  `solve_match` は非ゼロ成立を優先しつつ、交換セルが成立ラインに載る
  場合だけゼロ成立にフォールバックします (wulu よりちょっと厳しめ。
  wulu は無関係なゼロ成立も採用しちゃう)。
- `ques` は **2次元リスト**で来ます (フラット想定だと IndexError で死ぬ)。両対応しました。
- `icon` の `userresponse` は **ピクセル座標 x*33 / y*49**
  (wulu 想定の percent*10000 じゃありません。GeekedTest＋syncrain と一致、live 検証済み)。
- `icon` プロンプトは busy な写真背景の上に純黒シルエット：
  NCC/テンプレマッチは ~0.65 で頭打ち、有意なピークが出ません
  (明暗2値マップ・Canny 輪郭・chamfer 距離を試しました)。
  外部モデル/サーバなしの全参考リポジトリ共通の壁です
  (Geeked は `ddddocr` サーバ必須、hshinosa は非公開 SigLIP ONNX 必須)。
  うちはセグメンテーション＋原寸探索＋ハンガリアン法 (+任意YOLO) の
  ベストエフォート実装です。icon で本番精度が要るなら
  `register_solver("icon", ...)` か `register_onnx_matcher(...)` で分類器を差してください。

## テスト (オフライン、captcha_id 不要)

```bash
python -m pip install opencv-python numpy Pillow pycryptodome requests
python tests/test_offline.py
```

## 免責

研究・学習用です。GeeTest とは無関係です。対象サイトの利用規約を守って使ってくださいね。
