# geetest-solver

GeeTest v4 を Pure Python で扱うための solver です。

既存の実装をいくつか触ってみたら、

- repo ごとに対応してる challenge が違う
- track 周りの実装がバラバラ
- 定数が古くなると急に死ぬ
- icon / nine がそれぞれ独自路線
- ブラウザや外部 solver が必要なものもある

みたいな感じだったので、良さそうな実装を読み比べつつ、使いやすい形にまとめました。

基本は **ブラウザなし** で動かす方針です。

> [!NOTE]
> 全部が完璧に解けるわけではないです。特に `icon` はまだ沼です。

## Features

ざっくりこんな感じです。

- GeeTest v4
- `slide` / `ai` / `match` / `winlinze` / `gobang` / `nine` / `icon` / `word` / `phrase`
- proxy 対応
- `curl_cffi` 対応
- track 生成
- `pt0 / pt1 / pt2`
- solver の差し替え
- protocol 定数の更新・キャッシュ
- sync API + async wrapper

### Slide

slide は 1 つの方式に決め打ちせず、

- `MORPH_GRADIENT`
- `Canny`

の両方で探して、スコアが高い方を使っています。

`ypos` が取れるときはその周辺を優先して、怪しいときは全体検索にフォールバックします。

片方だけだと普通に外すケースがあったので、両方走らせる形にしました。

### Track

track はデフォルトで ON です。

ベジェ曲線 + easing + 少しの jitter を入れて生成して、`td` / `td_sign` までまとめて処理します。

### Config refresh

GeeTest 側の JS が更新されると、`abo` や `lib` 周りの値が変わることがあります。

毎回手で追うのがだるいので、更新用の処理とローカルキャッシュを入れてあります。

```bash
python -m geetest_solver.deobfuscate
```

## Install

基本:

```bash
pip install -e .
```

slide を使うなら OpenCV も入れてください。普段はこれがおすすめです。

```bash
pip install -e ".[full]"
```

icon 用の追加依存:

```bash
pip install -e ".[icon]"
```

Playwright を使う場合:

```bash
pip install -e ".[browser]"
playwright install chromium
```

## Usage

一番シンプルなのはこれです。

```python
from geetest_solver import GeetestSolver

solver = GeetestSolver(
    captcha_id="54088bb07d2df3c46b79f80300b0abbe",
    risk_type="slide",
)

print(solver.solve())
```

成功するとだいたいこんな形で返ります。

```python
{
    "lot_number": "...",
    "pass_token": "...",
    "gen_time": "...",
    "captcha_output": "..."
}
```

proxy もそのまま渡せます。

```python
solver = GeetestSolver(
    captcha_id,
    risk_type="slide",
    proxy="http://127.0.0.1:8080",
    timeout=20,
)
```

対応 `risk_type`:

```text
ai
slide
match
winlinze
gobang
nine
icon
word
phrase
```

## Custom solver

内蔵 solver を使わず、自分の処理に差し替えることもできます。

```python
from geetest_solver import GeetestSolver

@GeetestSolver.register_solver("icon")
def my_icon(data, solver):
    from geetest_solver.tracks import gen_click_track

    clicks = [(0.3, 0.4)]
    track, passtime = gen_click_track(clicks)

    return {
        "userresponse": [[3000, 4000]],
        "passtime": passtime,
        "track": track,
    }
```

nine 用の matcher も差し替えできます。

```python
from geetest_solver.solvers import register_onnx_matcher

@register_onnx_matcher
def my_matcher(prompt_bytes, grid_bytes) -> list[float]:
    return [0.0] * 9
```

## Project structure

```text
geetest_solver/
├── client.py
│   └── load / verify / solve
├── config.py
│   └── protocol constants / cache
├── crypto.py
│   └── pt0 / pt1 / pt2 / td_sign
├── protocol_utils.py
│   └── PoW / lot parser
├── tracks.py
│   └── pointer track generation
├── solvers/
│   ├── slide.py
│   ├── board.py
│   └── nine_icon.py
├── yolo_icons.py
├── deobfuscate.py
└── browser_vt.py

tests/test_offline.py
examples/solve_slide.py
```

## Tested

公式デモで確認した結果です。

Tested: **2026-09-18**

| risk_type | result |
|---|---|
| `slide` | ✅ 3/3 |
| `ai` | ✅ 3/3 |
| `winlinze` | ✅ 3/3 |
| `match` | ✅ 6/6 |
| `icon` | ⚠️ unstable |

### いくつかハマったところ

`match` の `ques` は 2 次元リストで来るケースがありました。
最初フラット前提で書いて普通に `IndexError` 踏んだので、今は両対応です。

`slide` は画像によって gradient と Canny の得意不得意が割と違います。
このへんは「これだけ使っとけばOK」がなかったので、両方試して選ぶ形になっています。

### icon について

ここが今の一番弱いところです。

プロンプト側は比較的きれいなシルエットなのに、実際の画像側は写真背景の上にアイコンが載るので、普通の template matching だけだとかなり厳しいです。

今は、

- segmentation
- multi-scale matching
- Hungarian matching
- optional YOLO backend

あたりを組み合わせています。

モデルなしでもベストエフォートでは動きますが、安定した精度が必要なら独自 matcher / solver を差し込む前提で考えた方がいいです。

## Tests

ネット接続や `captcha_id` がなくても動く offline test があります。

```bash
python -m pip install opencv-python numpy Pillow pycryptodome requests
python tests/test_offline.py
```

PoW、crypto、board solver、track、slide detection あたりをまとめて確認できます。

## References

この repo は以下の実装をかなり参考にしています。

| Repo | 参考にしたところ |
|---|---|
| [xKiian/GeekedTest](https://github.com/xKiian/GeekedTest) | 基本 protocol、board solver、deobfuscate 周り |
| [wulu007/geetest-bypass](https://github.com/wulu007/geetest-bypass) | protocol constants、track、solver registry など |
| [aster-go/Datadome-GeeTest-Captcha-Solver](https://github.com/aster-go/Datadome-GeeTest-Captcha-Solver) | Canny / template matching 周り |
| [hshinosa/geetest-solver-nine](https://github.com/hshinosa/geetest-solver-nine) | nine matcher の IF、BrowserVT のアイデア |
| [variablepy/GeeTest-Solver](https://github.com/variablepy/GeeTest-Solver) | module 構成 |
| [syncrain/geetest-solver](https://github.com/syncrain/geetest-solver) | icon 周り、YOLO backend |
| [Evil-Bane/Geetest-Solver](https://github.com/Evil-Bane/Geetest-Solver) | 画像マッチング周りのアイデア |

実装の方向性がかなり違うので、読み比べるだけでも結構おもしろかったです。

各作者に感謝します。

## License

Apache-2.0. Third-party references and notices are listed in [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).

## Disclaimer

Research / educational use only.

GeeTest とは関係ありません。
利用する場合は対象サービスの利用規約やルールを確認してください。
