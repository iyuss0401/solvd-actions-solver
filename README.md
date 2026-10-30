# solvd-actions-solver
Nonogram solver on GitHub Actions. One workflow run = 4 parallel runners
(matrix), each solving one board of `challenge.json` with the portfolio
race from solvd_lib.py (CP-SAT + CaDiCaL + Glucose). Answers land as
per-board artifacts. Trigger: Actions tab -> solve-nonogram -> Run workflow.
