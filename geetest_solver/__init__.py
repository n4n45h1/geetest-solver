"""GeeTest v4 ソルバーです。いろんな公開リポジトリのいいとこ取り＋独自改良です。

参考にしたリポジトリ:
- xKiian/GeekedTest            (基本プロトコル、五目、deobfuscate のアイデア)
- wulu007/geetest-bypass       (最新の abo/lib キー、pt0/1/2、ベジェ軌跡、プラグインレジストリ、async)
- aster-go/Datadome-GeeTest-Captcha-Solver (Canny+テンプレートの画像処理、bbox 切り出し)
- hshinosa/geetest-solver-nine (ONNX nine マッチャーのIF、マージン判定リトライ、BrowserVT 回避)
- variablepy/GeeTest-Solver    (すっきりした分割構成)

各リポジトリ単体に対する改良ポイント:
1. ハイブリッドなスライド検出:MORPH_GRADIENT (wulu) + Canny (Geeked/aster) を
   信頼度でいい方採用。どっちかだけだと外すケースがあるんです。
2. 軌跡 (track) はデフォルトON (Geeked には無くて、wulu はデフォルトOFF)。
   ベジェ曲線の人間らしい軌跡 + fflate 互換 gzip + td_sign を自動で付けます。
3. 定数は自動更新 (abo/lib/biht) できます。`deobfuscate` で更新 + ディスクキャッシュ付き。
   (Geeked は手動実行が必要でした)
4. 全タイプ対応のソルバーレジストリ (+ nine/icon のヒューリスティックつき) なので、
   外部の ddddocr サーバはいりません (Geeked は必須でした)。
5. 同期+非同期クライアント、curl_cffi の TLS 指紋 (+ requests フォールバック)、
   プロキシ対応、指数バックオフのリトライ (wulu は固定回数のみ)。
6. pt フォールバック:サーバ指定の pt を使って、ダメなら 1 -> 0 に自動で落とします。
"""

from .client import GeetestSolver
from .solvers import (
    find_prompt_in_grid,
    solve_gobang,
    solve_match,
    solve_slide,
    solve_slide_hybrid,
    solve_winlinze,
)
from .tracks import (
    gen_click_track,
    gen_match_track,
    gen_nine_track,
    gen_slide_track,
    gen_winlinze_track,
    track_zip,
)

__all__ = [
    "GeetestSolver",
    "solve_slide",
    "solve_slide_hybrid",
    "solve_gobang",
    "solve_match",
    "solve_winlinze",
    "find_prompt_in_grid",
    "gen_slide_track",
    "gen_click_track",
    "gen_nine_track",
    "gen_match_track",
    "gen_winlinze_track",
    "track_zip",
]

__version__ = "1.0.0"
