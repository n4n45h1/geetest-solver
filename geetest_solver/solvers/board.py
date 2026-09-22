"""Board puzzle solvers.

gobang / winlinze / match をここにまとめています。
"""

from __future__ import annotations


def _lines(board):
    """行・列・斜めの候補 line を列挙します。"""
    n = len(board)
    rows = [[(r, c) for c in range(n)] for r in range(n)]
    cols = [[(r, c) for r in range(n)] for c in range(n)]
    d1 = [[(k, k + o) for k in range(n) if 0 <= k + o < n] for o in range(-n + 1, n)]
    d2 = [[(k, n - 1 - k + o) for k in range(n) if 0 <= n - 1 - k + o < n]
          for o in range(-n + 1, n)]
    for group in (rows, cols, d1, d2):
        for line in group:
            if len(line) >= 2:
                yield line


def _to_grid(ques, n: int):
    """flat / 2D のどちらも 2D grid に揃えます。"""
    if isinstance(ques, (list, tuple)) and ques and isinstance(ques[0], (list, tuple)):
        return [list(r) for r in ques]
    flat = list(ques)
    return [flat[i * n:(i + 1) * n] for i in range(n)]


def _find_completion(board, line_len: int | None = None):
    """同種駒 n-1 + 空き1 のラインを探して、(既存駒, 空きマス) を返します。"""
    n = len(board)
    need = (line_len or n) - 1
    for line in _lines(board):
        vals = [board[r][c] for r, c in line]
        if len(line) < need:
            continue
        non0 = [v for v in vals if v != 0]
        zeros = [pos for pos, v in zip(line, vals) if v == 0]
        if len(zeros) == 1 and len(non0) >= need and len(set(non0)) == 1:
            filled = [pos for pos, v in zip(line, vals) if v != 0]
            return filled, list(zeros[0])
    return None


def solve_gobang(board, line_len: int | None = None):
    """Geeked 互換:[[移動元行, 移動元列], [移動先行, 移動先列]] 形式で返します。

    フラット25要素 (Geeked の線路形式) でも 2次元盤面でもOKです。
    """
    if isinstance(board, (list, tuple)) and board and not isinstance(board[0], (list, tuple)):
        n = int(len(board) ** 0.5)
        grid = [list(board[i * n:(i + 1) * n]) for i in range(n)]
    else:
        grid = [list(r) for r in board]
    hit = _find_completion(grid, line_len)
    if not hit:
        return None
    filled, empty = hit
    # 既存の駒を 1 つ空きマスへ動かす
    return [list(filled[0]), list(empty)]


def _win_3x3(b, allow_zero: bool = False) -> bool:
    """3x3 の勝敗判定です。allow_zero=True だと空行 (0並び) も勝ち扱いにします。"""
    for i in range(3):
        if allow_zero:
            if b[i][0] == b[i][1] == b[i][2]:
                return True
            if b[0][i] == b[1][i] == b[2][i]:
                return True
        else:
            if b[i][0] == b[i][1] == b[i][2] != 0:
                return True
            if b[0][i] == b[1][i] == b[2][i] != 0:
                return True
    if allow_zero:
        return (b[0][0] == b[1][1] == b[2][2]) or (b[0][2] == b[1][1] == b[2][0])
    return (b[0][0] == b[1][1] == b[2][2] != 0) or (b[0][2] == b[1][1] == b[2][0] != 0)


def _line_through(cells, r: int, c: int) -> bool:
    """(r, c) がライン上に載ってるかどうかです。"""
    return (r, c) in cells


def solve_match(ques) -> tuple | None:
    """3x3 隣接スワップソルバーです (wulu の match.py を整理したもの)。

    フラット9要素でも 2次元 3x3 でも受け付けます。公式デモの実測で
    空行 (0) もサーバ側では勝ち扱いと分かったので、非ゼロ成立を優先しつつ、
    交換セルが成立ライン上に載る場合だけゼロ成立にフォールバックします
    (wulu よりちょっと厳しめ。wulu は無関係なゼロ成立も採用しちゃう)。
    """
    b = _to_grid(ques, 3)
    swaps = []
    for r in range(3):
        for c in range(3):
            for dr, dc in ((0, 1), (1, 0)):
                r2, c2 = r + dr, c + dc
                if r2 >= 3 or c2 >= 3:
                    continue
                swaps.append((r, c, r2, c2))
    for allow_zero in (False, True):
        for r, c, r2, c2 in swaps:
            b[r][c], b[r2][c2] = b[r2][c2], b[r][c]
            try:
                if _win_3x3(b, allow_zero):
                    if allow_zero:
                        # swap した cell が成立 line に関わっていること
                        # 既存 line と無関係な手は返さない
                        lines = ([[(i, k) for k in range(3)] for i in range(3)]
                                 + [[(k, i) for k in range(3)] for i in range(3)]
                                 + [[(k, k) for k in range(3)],
                                    [(k, 2 - k) for k in range(3)]])
                        ok = any(
                            _line_through(L, r, c) or _line_through(L, r2, c2)
                            for L in lines
                            if len({b[x][y] for x, y in L}) == 1)
                        if not ok:
                            continue
                    return ((r, c), (r2, c2))
            finally:
                b[r][c], b[r2][c2] = b[r2][c2], b[r][c]
    return None


def _win_5x5(b) -> bool:
    """5x5 の五目勝敗判定です (全ウィンドウ:横・縦・斜め2方向)。"""
    n = 5
    for r in range(n):
        for c in range(n - 4):
            if b[r][c] != 0 and all(b[r][c + k] == b[r][c] for k in range(5)):
                return True
    for c in range(n):
        for r in range(n - 4):
            if b[r][c] != 0 and all(b[r + k][c] == b[r][c] for k in range(5)):
                return True
    for r in range(n - 4):
        for c in range(n - 4):
            if b[r][c] != 0 and all(b[r + k][c + k] == b[r][c] for k in range(5)):
                return True
    for r in range(n - 4):
        for c in range(4, n):
            if b[r][c] != 0 and all(b[r + k][c - k] == b[r][c] for k in range(5)):
                return True
    return False


def solve_winlinze(ques) -> tuple | None:
    """5x5 五目です:どれか1駒を空きマスへ動かして勝てる手を探します (wulu 流)。

    フラット25要素でも 2次元 5x5 でも受け付けます。
    """
    n = 5
    b = _to_grid(ques, n)
    pieces = [(r, c) for r in range(n) for c in range(n) if b[r][c] != 0]
    empties = [(r, c) for r in range(n) for c in range(n) if b[r][c] == 0]
    for r1, c1 in pieces:
        for r2, c2 in empties:
            v = b[r1][c1]
            b[r1][c1], b[r2][c2] = 0, v
            if _win_5x5(b):
                return ((r1, c1), (r2, c2))
            b[r1][c1], b[r2][c2] = v, 0
    return None
