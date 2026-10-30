#!/usr/bin/env python3
"""
solvd_lib.py — SOLVD nonogram race solver for Kaggle (4 cores).

Portfolio design:
- 1 board  (e.g. 112x112): CP-SAT (2 workers) + CaDiCaL + Glucose race in
  parallel processes; first verified solution wins.
- 2+ boards (e.g. 4x 56x56): one CaDiCaL process per board, in parallel.

Every candidate grid is verified against all row/col clues before it is
accepted. The answer is only written when every board is solved+verified.

CLI:  python3 solvd_lib.py challenge.json answer.json [budget_seconds]
"""
import json
import sys
import time
from multiprocessing import get_context

# --------------------------------------------------------------------------
# CaDiCaL / Glucose CNF encoding (automaton per line) — "metode Ciel"
# --------------------------------------------------------------------------

def build_clauses(board):
    """Return (clauses, n_vars) for one nonogram board."""
    h = board["height"]
    w = board["width"]

    def cell(r, c):
        return r * w + c + 1

    counter = [h * w + 1]

    def new_var():
        v = counter[0]
        counter[0] += 1
        return v

    clauses = []

    def line_states(clues):
        states = []
        for j in range(len(clues) + 1):
            states.append((0, j, 0))  # gap_j
        for j, k in enumerate(clues):
            for t in range(1, k + 1):
                states.append((1, j, t))  # run j, t filled
        return states

    def sidx(states, kind, j, t):
        for idx, s in enumerate(states):
            if s == (kind, j, t):
                return idx
        raise KeyError((kind, j, t))

    lines = []
    for r in range(h):
        lines.append((board["rows"][r], [(r, c) for c in range(w)]))
    for c in range(w):
        lines.append((board["cols"][c], [(r, c) for r in range(h)]))

    for clues, cells in lines:
        n = len(cells)
        m = len(clues)
        states = line_states(clues)
        ns = len(states)
        P = [[new_var() for _ in range(ns)] for _ in range(n + 1)]
        for pos in range(n + 1):
            clauses.append(P[pos][:])
            lits = P[pos]
            nn = len(lits)
            if nn > 1:
                sv = [new_var() for _ in range(nn - 1)]
                clauses.append([-lits[0], sv[0]])
                clauses.append([-lits[-1], -sv[-1]])
                for ii in range(1, nn - 1):
                    clauses.append([-lits[ii], sv[ii]])
                    clauses.append([-sv[ii - 1], sv[ii]])
                    clauses.append([-lits[ii], -sv[ii - 1]])
        gap0 = sidx(states, 0, 0, 0)
        clauses.append([P[0][gap0]])
        for s_idx in range(ns):
            if s_idx != gap0:
                clauses.append([-P[0][s_idx]])
        accept = [P[n][sidx(states, 0, m, 0)]]
        if m > 0:
            accept.append(P[n][sidx(states, 1, m - 1, clues[m - 1])])
        if m == 0:
            accept = [P[n][gap0]]
        clauses.append(accept)
        for pos in range(n):
            cell_var = cell(*cells[pos])
            for s_idx, (kind_s, j, t) in enumerate(states):
                trans = []
                if kind_s == 0:
                    trans.append((sidx(states, 0, j, 0), 0))
                    if j < m:
                        trans.append((sidx(states, 1, j, 1), 1))
                else:
                    if t < clues[j]:
                        trans.append((sidx(states, 1, j, t + 1), 1))
                    else:
                        trans.append((sidx(states, 0, j + 1, 0), 0))
                clauses.append(
                    [-P[pos][s_idx]] + [P[pos + 1][ns_] for ns_, _ in trans]
                )
                for ns_, v in trans:
                    lit = cell_var if v == 1 else -cell_var
                    clauses.append([-P[pos][s_idx], -lit, P[pos + 1][ns_]])
                    clauses.append([-P[pos][s_idx], -P[pos + 1][ns_], lit])
    return clauses, counter[0]


def verify(grid, board):
    """True iff grid satisfies every row and column clue."""
    h = board["height"]
    w = board["width"]
    for r in range(h):
        runs = []
        cnt = 0
        for c in range(w):
            if grid[r][c] == 1:
                cnt += 1
            elif cnt:
                runs.append(cnt)
                cnt = 0
        if cnt:
            runs.append(cnt)
        if runs != board["rows"][r]:
            return False
    for c in range(w):
        runs = []
        cnt = 0
        for r in range(h):
            if grid[r][c] == 1:
                cnt += 1
            elif cnt:
                runs.append(cnt)
                cnt = 0
        if cnt:
            runs.append(cnt)
        if runs != board["cols"][c]:
            return False
    return True


def solve_sat(board, engine="cadical"):
    from pysat.solvers import Cadical153, Glucose4

    h = board["height"]
    w = board["width"]
    clauses, _nvars = build_clauses(board)
    cls = Cadical153 if engine == "cadical" else Glucose4
    with cls(bootstrap_with=clauses) as solver:
        if not solver.solve():
            return None
        model = set(solver.get_model())
    grid = [
        [1 if (r * w + c + 1) in model else 0 for c in range(w)]
        for r in range(h)
    ]
    return grid if verify(grid, board) else None


# --------------------------------------------------------------------------
# CP-SAT (OR-Tools) with per-line automata + line sums
# --------------------------------------------------------------------------

def _build_automaton(clues):
    k = len(clues)
    prefix = [0] * (k + 1)
    for j in range(k):
        prefix[j + 1] = prefix[j] + clues[j] + 1
    S = prefix[k] + 1

    def sid(j, run):
        return prefix[j] + run

    FIN = sid(k, 0)
    next1 = [-1] * S
    next0 = [-1] * S
    for j in range(k):
        for run in range(clues[j] + 1):
            s = sid(j, run)
            if run < clues[j]:
                next1[s] = sid(j, run + 1)
            if run == 0:
                next0[s] = s
            elif run == clues[j]:
                next0[s] = sid(j + 1, 0)
    next0[FIN] = FIN
    accept = {FIN}
    if k >= 1:
        accept.add(sid(k - 1, clues[k - 1]))
    triples = []
    for s in range(S):
        if next0[s] >= 0:
            triples.append((s, 0, next0[s]))
        if next1[s] >= 0:
            triples.append((s, 1, next1[s]))
    return triples, accept


def _runs_of(line):
    runs, cur = [], 0
    for v in line:
        if v == 1:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    return runs


def solve_cpsat(board, time_limit=540.0, workers=2, seed=None):
    from ortools.sat.python import cp_model

    W, H = board["width"], board["height"]
    m = cp_model.CpModel()
    cells = [[m.NewBoolVar(f"c_{r}_{c}") for c in range(W)] for r in range(H)]
    for r in range(H):
        tr, acc = _build_automaton(board["rows"][r])
        m.AddAutomaton(cells[r], 0, list(acc), tr)
    for c in range(W):
        tr, acc = _build_automaton(board["cols"][c])
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
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    sol = [[solver.Value(cells[r][c]) for c in range(W)] for r in range(H)]
    for r in range(H):
        if _runs_of(sol[r]) != board["rows"][r]:
            return None
    for c in range(W):
        if _runs_of([sol[r][c] for r in range(H)]) != board["cols"][c]:
            return None
    return sol


# --------------------------------------------------------------------------
# Race engine
# --------------------------------------------------------------------------

def _race_worker(board, cfg, budget, q):
    name = cfg[0]
    try:
        if name == "cpsat":
            grid = solve_cpsat(board, time_limit=budget, workers=cfg[1])
        else:
            grid = solve_sat(board, engine=name)
        if grid is not None and verify(grid, board):
            q.put((name, grid))
            return
    except Exception:
        pass
    q.put((name, None))


def race_board(board, budget=540.0):
    """Race engines on ONE board. Return (grid, engine_name) or (None, None)."""
    ctx = get_context("fork")
    q = ctx.Queue()
    cfgs = [("cpsat", 2), ("cadical",), ("glucose",)]
    procs = []
    t0 = time.time()
    for cfg in cfgs:
        p = ctx.Process(target=_race_worker, args=(board, cfg, budget, q))
        p.start()
        procs.append(p)
    winner = (None, None)
    pending = len(cfgs)
    try:
        while time.time() - t0 < budget and pending > 0:
            try:
                name, grid = q.get(timeout=2.0)
            except Exception:
                continue
            pending -= 1
            if grid is not None:
                winner = (grid, name)
                break
    finally:
        for p in procs:
            if p.is_alive():
                p.terminate()
        for p in procs:
            p.join(timeout=5)
    return winner


def _board_worker(idx, board, q):
    try:
        grid = solve_sat(board, engine="cadical")
        if grid is not None and verify(grid, board):
            q.put((idx, grid))
            return
    except Exception:
        pass
    q.put((idx, None))


def solve_all_boards(boards, budget=540.0):
    """Return list of grids (one per board) or None if any board fails."""
    if len(boards) == 1:
        grid, engine = race_board(boards[0], budget=budget)
        if grid is None:
            print("  board 0: NO solution within budget", flush=True)
            return None
        print(f"  board 0: solved by {engine}", flush=True)
        return [grid]
    ctx = get_context("fork")
    q = ctx.Queue()
    procs = []
    t0 = time.time()
    for i, b in enumerate(boards):
        p = ctx.Process(target=_board_worker, args=(i, b, q))
        p.start()
        procs.append(p)
    results = {}
    try:
        while len(results) < len(boards) and time.time() - t0 < budget:
            try:
                idx, grid = q.get(timeout=2.0)
            except Exception:
                continue
            results[idx] = grid
            print(f"  board {idx}: {'solved' if grid else 'FAILED'} "
                  f"at {time.time() - t0:.0f}s", flush=True)
    finally:
        for p in procs:
            if p.is_alive():
                p.terminate()
        for p in procs:
            p.join(timeout=5)
    if len(results) < len(boards) or any(g is None for g in results.values()):
        return None
    return [results[i] for i in range(len(boards))]


def solve_challenge(challenge, budget=540.0):
    """Return the submit-ready answer dict, or None. Verified boards only."""
    boards = challenge["boards"]
    print(f"challenge {challenge.get('challengeId')}: {len(boards)} board(s), "
          f"{boards[0]['width']}x{boards[0]['height']}, budget {budget:.0f}s",
          flush=True)
    t0 = time.time()
    grids = solve_all_boards(boards, budget=budget)
    if grids is None:
        print(f"FAILED after {time.time() - t0:.0f}s — do not submit anything",
              flush=True)
        return None
    answer = {
        "challengeId": challenge["challengeId"],
        "encoding": "bin",
        "boards": [["".join(str(v) for v in row) for row in g] for g in grids],
    }
    body = json.dumps(answer).encode()
    max_bytes = challenge.get("submit", {}).get("maxBodyBytes")
    print(f"SOLVED + verified in {time.time() - t0:.0f}s; "
          f"answer {len(body)} bytes (max {max_bytes})", flush=True)
    if max_bytes and len(body) > max_bytes:
        print("ERROR: answer exceeds maxBodyBytes — do not submit", flush=True)
        return None
    return answer


if __name__ == "__main__":
    chal_path = sys.argv[1] if len(sys.argv) > 1 else "challenge.json"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "answer.json"
    budget = float(sys.argv[3]) if len(sys.argv) > 3 else 540.0
    chal = json.load(open(chal_path))
    ans = solve_challenge(chal, budget=budget)
    if ans is None:
        sys.exit(1)
    with open(out_path, "w") as f:
        json.dump(ans, f)
    print(f"answer written to {out_path}", flush=True)
