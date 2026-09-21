"""GeeTest v4 改良ソルバー。

参考にした公開リポジトリのいいとこ取り:
- xKiian/GeekedTest            (基本プロトコル、五目並べ、deobfuscate の発想)
- wulu007/geetest-bypass       (最新の abo/lib キー、pt0/1/2、ベジェ軌跡、プラグインレジストリ、async)
- aster-go/Datadome-GeeTest-Captcha-Solver (Canny+テンプレートの画像処理、bbox 切り出し)
- hshinosa/geetest-solver-nine (ONNX nine マッチャーのIF、マージン判定リトライ、BrowserVT 回避)
- variablepy/GeeTest-Solver    (すっきりした分割構成)

各リポジトリ単体に対する改良点:
1. ハイブリッドなスライド検出:MORPH_GRADIENT (wulu) + Canny (Geeked/aster) を
   信頼度で選択。単一手法だと外すケースを相互に補完する。
2. 軌跡 (track) はデフォルトON (Geeked はなし、wulu はデフォルトOFF)。
   ベジェ曲線の人間らしい軌跡 + fflate 互換 gzip + td_sign を自動付与。
3. 動的な定数管理 (abo/lib/biht):`deobfuscate` による自動更新 + ディスクキャッシュ。
   (Geeked は手動実行が必要だった)
4. 全タイプ対応のソルバーレジストリ (+ nine/icon のヒューリスティック)。
   外部の ddddocr サーバが不要 (Geeked は必須だった)。
5. 同期+非同期クライアント、curl_cffi の TLS 指紋 (+ requests フォールバック)、
   プロキシ対応、指数バックオフのリトライ (wulu は固定回数のみ)。
6. pt フォールバック:サーバ指定の pt を使い、失敗時は 1 -> 0 に自動降格。
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
