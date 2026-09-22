"""GeeTest v4 solver package.

複数の公開実装を読み比べつつ、使いやすい形にまとめています。
詳しいクレジットは README と THIRD_PARTY_NOTICES.md を見てください。
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
