# geetest-solver-improved

GeeTest v4 ソルバー。公開リポジトリ5つのいいとこ取り＋独自改良。
ブラウザ不要の純 Python 実装です。

| 参考リポジトリ | 取り込んだもの |
|---|---|
| [xKiian/GeekedTest](https://github.com/xKiian/GeekedTest) | 基本プロトコル (`load`/`verify`/`w`)、五目ソルバー、`userresponse = left/1.0059466+2` 係数、**deobfuscate の発想** (自動化＋キャッシュ化) |
| [wulu007/geetest-bypass](https://github.com/wulu007/geetest-bypass) | 最新の `abo`/`lib` キー、`pt0/1/2`、ベジェ `TrackBuilder` + `track_zip` + `td_sign`、ソルバーレジストリ、タイプ別 passtime |
| [aster-go/Datadome-GeeTest-Captcha-Solver](https://github.com/aster-go/Datadome-GeeTest-Captcha-Solver) | Canny(100,200)+テンプレートの画像処理、bbox/透過処理 |
| [hshinosa/geetest-solver-nine](https://github.com/hshinosa/geetest-solver-nine) | ONNX マッチャーのIF＋マージン判定リトライ、`BrowserVT` (任意)、nine の `userresponse`/軌跡形式 |
| [variablepy/GeeTest-Solver](https://github.com/variablepy/GeeTest-Solver) | すっきりした分割構成 (challenge/crypto/client) |
| [syncrain/geetest-solver](https://github.com/syncrain/geetest-solver) (MIT) | icon 座標スケール `x*33/y*49` (live 検証済み)、YOLO `best.pt` の取得先 |
| [Evil-Bane/Geetest-Solver](https://github.com/Evil-Bane/Geetest-Solver) | ORB＋CLAHE＋極性反転マッチの発想 (検証の結果、不採用と判断した経緯は後述) |

## 各リポジトリ単体に対する改良点

1. **ハイブリッドなスライド検出** — `MORPH_GRADIENT` (wulu) **+** `Canny` (Geeked/aster) を信頼度で選択。ypos 帯＋全画像フォールバック付き。単一手法だと外すケースを相互補完する。
2. **track デフォルトON** — Geeked には無く、wulu はデフォルトOFF。`td`+`td_sign` 必須のサイト向けに、ベジェ＋`ease(3t²-2t³)`＋ジッタ＋17ms サンプリングの fflate 互換 gzip を自動付与。
3. **動的な定数管理** — Geeked の定数は数週間で腐り、手動の `deobfuscate.py` が必要だった。ここでは `geetest_solver/config.py` に現行値を内蔵しつつ `refresh()`＋ディスクキャッシュ (`python -m geetest_solver.deobfuscate`)。
4. **dddddocr サーバ不要** — Geeked の icon は外部サーバ必須。ここでは nine/icon のヒューリスティックを内蔵し、`register_onnx_matcher` / `register_solver` で差し替え可能。
5. **堅牢なクライアント** — 同期＋非同期、`curl_cffi` の TLS 指紋 (+`requests` フォールバック)、プロキシ対応、指数バックオフの `solve(retry)`、`pt` 自動＋`1→0` 降格 (pt2 は `smcryptopy` 必須)。
6. **軽い依存関係** — `requests+numpy+Pillow+pycryptodome` のみ必須。`opencv-python`＋`curl_cffi` 推奨 (`pip install -e ".[full]"`)。

## インストール

```bash
pip install -e .
pip install -e ".[full]"   # 推奨: opencv + curl_cffi
pip install -e ".[icon]"    # icon 用 YOLO (torch + ultralytics)
```

## 使い方

```python
from geetest_solver import GeetestSolver

solver = GeetestSolver(captcha_id="54088bb07d2df3c46b79f80300b0abbe", risk_type="slide")
print(solver.solve())  # -> {lot_number, pass_token, gen_time, captcha_output}
# {'captcha_id': ..., 'lot_number': ..., 'pass_token': ..., 'gen_time': ..., 'captcha_output': ...}
```

対応 risk_type: `ai slide match winlinze/gobang nine icon word phrase` (+ レジストリで自作追加可)。

```python
# 自作ソルバーの差し込み (wulu 流、全タイプに拡張)
@GeetestSolver.register_solver("icon")
def my_icon(data, solver):
    from geetest_solver.tracks import gen_click_track
    clicks = [(0.3, 0.4)]  # 規格化 [0,1]
    track, passtime = gen_click_track(clicks)
    return {"userresponse": [[3000, 4000]], "passtime": passtime, "track": track}

# ONNX nine マッチャーの差し込み (hshinosa 流のマージン判定つき)
from geetest_solver.solvers import register_onnx_matcher
@register_onnx_matcher
def my_matcher(prompt_bytes, grid_bytes) -> list[float]:
    return [0.0]*9
```

プロキシ / ヘッダ / 軌跡なし：

```python
s = GeetestSolver(captcha_id, risk_type="slide", proxy="http://127.0.0.1:8080",
                  track_enable=True, timeout=20)
```

GeeTest が `gcaptcha4.js` を更新して定数が腐ったら：

```bash
python -m geetest_solver.deobfuscate
```

非ブラウザ TLS に `svg_seed` を返すサイト用 (hshinosa の `BrowserVT` の発想、任意)：

```python
from geetest_solver.browser_vt import BrowserVT  # playwright が必要
vt = BrowserVT(signup_url="https://example.com/signup", ...)
token, lot = vt.get_vt_for("user@example.com")
```

## 構成

```
geetest_solver/
  __init__.py  client.py (GeetestSolver: load/verify/solve + レジストリ)
  config.py (ライブ更新できる abo/lib/biht)  crypto.py (pt0/1/2 + td_sign)
  protocol_utils.py (lotParser + PoW)  tracks.py (ベジェ軌跡 + track_zip)
  solvers/slide.py (ハイブリッド)  solvers/board.py (五目/match/winlinze)
  solvers/nine_icon.py (セグメンテーション + ONNX フック)
  yolo_icons.py (任意の YOLO 検出バックエンド)
  deobfuscate.py  browser_vt.py (任意)
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
| `icon` | ❌ (下記) |

live 検証で判明してコードに反映したこと：

- `match` の盤面は**空行 (0) 完成も勝ち扱い** —
  実測 (`[[0,3,1],[2,0,2],[0,1,3]]` はそれ以外で解けない)。
  `solve_match` は非ゼロ成立を優先し、交換セルが成立ライン上に載る
  場合のみゼロ成立にフォールバック (wulu より厳密。wulu は無関係なゼロ成立も採用する)。
- `ques` は **2次元リスト**で来る (フラット想定だと IndexError)。両対応済み。
- `icon` の `userresponse` は **ピクセル座標 x*33 / y*49**
  (wulu 想定の percent*10000 ではない。GeekedTest＋syncrain と一致、live 検証済み)。
- `icon` プロンプトは busy な写真背景上の純黒シルエット：
  NCC/テンプレマッチは ~0.65 で頭打ち、有意なピークが出ない
  (明暗2値マップ・Canny 輪郭・chamfer 距離を検証済み)。
  外部モデル/サーバなしの全参考リポジトリ共通の壁
  (Geeked は `ddddocr` サーバ必須、hshinosa は非公開 SigLIP ONNX 必須)。
  本リポジトリはセグメンテーション＋原寸探索＋ハンガリアン法 (+任意YOLO) の
  ベストエフォート実装。icon の本番精度が要る場合は
  `register_solver("icon", ...)` か `register_onnx_matcher(...)` で分類器を差すこと。

## テスト (オフライン、captcha_id 不要)

```bash
python -m pip install opencv-python numpy Pillow pycryptodome requests
python tests/test_offline.py
```

## 免責

研究・学習目的のみ。GeeTest とは無関係。対象サイトの利用規約を守って使うこと。
