"""スライドを解く最小例。

自分の captcha_id に差し替えて実行する (DevTools -> Network -> `verify` で検索)。
"""
from geetest_solver import GeetestSolver

# 自分の captcha_id に書き換える
captcha_id = "54088bb07d2df3c46b79f80300b0abbe"

# slide / ai / gobang(winlinze) / match / nine / icon / word
solver = GeetestSolver(captcha_id, risk_type="slide")
print(solver.solve())
