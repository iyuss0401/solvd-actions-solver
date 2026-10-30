"""Benchmark one solver configuration on one board.
Usage: bench_one.py <method> <board_idx> <budget_s> <perm_seed>
Methods: cadical | glucose | maplecm | cryptominisat | cpsat
SAT runs go through a subprocess watchdog so the budget is a hard wall.
On success writes answer_board{idx}.json (same schema as solve_board.py)."""
import json, random, subprocess, sys, time

def run_sat(method, idx, budget, perm_seed):
    code = r'''
import json, random, sys, time
sys.path.insert(0, ".")
from ciel_solver import build_clauses, verify
method, idx, perm = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
chal = json.load(open("challenge.json"))
board = chal["boards"][idx]
clauses, n_vars = build_clauses(board)
if perm:
    rng = random.Random(perm)
    p = list(range(n_vars + 1))
    core = list(range(1, n_vars + 1))
    rng.shuffle(core)
    for new_id, old_id in enumerate(core, start=1):
        p[old_id] = new_id
    clauses = [[(1 if l > 0 else -1) * p[abs(l)] for l in cl] for cl in clauses]
from pysat.solvers import Cadical153, Glucose4, MapleCM
CLS = {"cadical": Cadical153, "glucose": Glucose4, "maplecm": MapleCM}
if method == "cryptominisat":
    from pysat.solvers import CryptoMinisat
    CLS["cryptominisat"] = CryptoMinisat
t0 = time.time()
with CLS[method](bootstrap_with=clauses) as s:
    ok = s.solve()
    model = s.get_model() if ok else None
print(f"sat={ok} in {time.time()-t0:.1f}s", flush=True)
if not ok:
    sys.exit(2)
sign = {}
for lit in model:
    sign[abs(lit)] = lit > 0
h, w = board["height"], board["width"]
def cellval(r, c):
    v = r * w + c + 1
    if perm:
        v = p[v]
    return 1 if sign.get(v, False) else 0
grid = [[cellval(r, c) for c in range(w)] for r in range(h)]
if not verify(grid, board):
    print("VERIFY FAILED", flush=True); sys.exit(3)
rows = ["".join(str(v) for v in row) for row in grid]
json.dump({"challengeId": chal["challengeId"], "board": idx, "rows": rows},
          open(f"answer_board{idx}.json", "w"))
print(f"board {idx}: SOLVED + verified ({method}, perm {perm})", flush=True)
'''
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, "-c", code, method, str(idx), str(perm_seed)],
                           timeout=budget, capture_output=True, text=True)
        print(r.stdout.strip(), flush=True)
        if r.returncode != 0:
            print(f"{method} perm={perm_seed}: NO-SOLVE (rc={r.returncode}) "
                  f"in {time.time()-t0:.1f}s {r.stderr.strip()[-200:]}", flush=True)
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"{method} perm={perm_seed}: TIMEOUT at {budget}s", flush=True)
        return False

def main():
    method, idx, budget, perm = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
    if method == "cpsat":
        sys.path.insert(0, ".")
        from cp_solver import solve_board
        chal = json.load(open("challenge.json"))
        board = chal["boards"][idx]
        t0 = time.time()
        s = solve_board(board, time_limit=budget, workers=4)
        if s is None:
            print(f"cpsat: NO-SOLVE in {time.time()-t0:.1f}s", flush=True)
            sys.exit(1)
        rows = ["".join(str(v) for v in row) for row in s]
        json.dump({"challengeId": chal["challengeId"], "board": idx, "rows": rows},
                  open(f"answer_board{idx}.json", "w"))
        print(f"board {idx}: SOLVED + verified (cpsat) in {time.time()-t0:.1f}s", flush=True)
        return
    ok = run_sat(method, idx, budget, perm)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
