"""ソルバー関数の一覧 (公開 API)。
"""

from .board import solve_gobang, solve_match, solve_winlinze
from .nine_icon import find_prompt_in_grid, register_onnx_matcher, score_prompt_box, solve_icon_clicks, solve_icon_yolo, solve_nine, solve_nine_heuristic
from .slide import solve_slide, solve_slide_hybrid, userresponse_from_setleft

__all__ = [
    "solve_slide", "solve_slide_hybrid", "userresponse_from_setleft",
    "solve_gobang", "solve_match", "solve_winlinze",
    "solve_nine", "solve_nine_heuristic", "solve_icon_clicks",
    "solve_icon_yolo", "score_prompt_box",
    "find_prompt_in_grid", "register_onnx_matcher",
]
