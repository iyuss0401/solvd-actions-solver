import json, pathlib, sys, time
from ortools.sat.python import cp_model

def build_automaton(clues):
    k = len(clues)
    prefix = [0]*(k+1)
    for j in range(k):
        prefix[j+1] = prefix[j] + clues[j] + 1
    S = prefix[k] + 1
    def sid(j, run): return prefix[j] + run
    FIN = sid(k, 0)
    next1 = [-1]*S; next0 = [-1]*S
    for j in range(k):
        for run in range(clues[j]+1):
            s = sid(j, run)
            if run < clues[j]: next1[s] = sid(j, run+1)
            if run == 0: next0[s] = s
            elif run == clues[j]: next0[s] = sid(j+1, 0)
    next0[FIN] = FIN
    accept = {FIN}
    if k >= 1: accept.add(sid(k-1, clues[k-1]))
    triples = []
    for s in range(S):
        if next0[s] >= 0: triples.append((s, 0, next0[s]))
        if next1[s] >= 0: triples.append((s, 1, next1[s]))
    return triples, accept

def runs_of(line):
    runs, cur = [], 0
    for v in line:
        if v == 1: cur += 1
        elif cur: runs.append(cur); cur = 0
    if cur: runs.append(cur)
    return runs

def solve_board(board, time_limit=240.0, workers=2, seed=None):
    W, H = board["width"], board["height"]
    m = cp_model.CpModel()
    cells = [[m.NewBoolVar(f"c_{r}_{c}") for c in range(W)] for r in range(H)]
    for r in range(H):
        tr, acc = build_automaton(board["rows"][r])
        m.AddAutomaton(cells[r], 0, list(acc), tr)
    for c in range(W):
        tr, acc = build_automaton(board["cols"][c])
        m.AddAutomaton([cells[r][c] for r in range(H)], 0, list(acc), tr)
    for r in range(H):
        m.Add(sum(cells[r]) == sum(board["rows"][r]))
    for c in range(W):
        m.Add(sum(cells[r][c] for r in range(H)) == sum(board["cols"][c]))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = workers
    if seed is not None:
        solver.parameters.random_seed = seed
    status = solver.Solve(m)
    print(f"  cp status={status} ({solver.StatusName(status)}) wall={solver.WallTime():.1f}s", flush=True)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    sol = [[solver.Value(cells[r][c]) for c in range(W)] for r in range(H)]
    for r in range(H):
        if runs_of(sol[r]) != board["rows"][r]: return None
    for c in range(W):
        if runs_of([sol[r][c] for r in range(H)]) != board["cols"][c]: return None
    return sol

if __name__ == "__main__":
    WORK = pathlib.Path.home()/"workspace/solvd"
    ch = json.loads((WORK/"challenge.json").read_text())
    only = int(sys.argv[1]) if len(sys.argv) > 1 else None
    idxs = [only] if only is not None else range(len(ch["boards"]))
    t0 = time.time()
    for i in idxs:
        t1 = time.time()
        s = solve_board(ch["boards"][i])
        print(f"BOARD {i}: {'OK' if s else 'FAIL'} in {time.time()-t1:.2f}s", flush=True)
        if s is None: sys.exit(1)
    print(f"DONE in {time.time()-t0:.2f}s total", flush=True)
