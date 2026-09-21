"""スライドを解く最小例です。

自分の captcha_id に差し替えて実行してください
(DevTools -> Network -> `verify` で探せます)。
"""
from geetest_solver import GeetestSolver

# 自分の captcha_id に書き換えてくださいね
captcha_id = "54088bb07d2df3c46b79f80300b0abbe"

# slide / ai / gobang(winlinze) / match / nine / icon / word
solver = GeetestSolver(captcha_id, risk_type="slide")
print(solver.solve())
