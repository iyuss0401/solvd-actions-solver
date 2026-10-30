"""Solve ONE board of a challenge file using solvd_lib's portfolio race.
Writes answer_board{i}.json: {"challengeId", "board", "rows"} — exit 1 if unsolved."""
import json, sys
sys.path.insert(0, ".")
from solvd_lib import solve_challenge

chal_path, idx, budget = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
chal = json.load(open(chal_path))
single = dict(chal)
single["boards"] = [chal["boards"][idx]]
ans = solve_challenge(single, budget=budget)
if ans is None:
    print(f"board {idx}: NO SOLUTION within {budget}s", flush=True)
    sys.exit(1)
out = {"challengeId": chal["challengeId"], "board": idx, "rows": ans["boards"][0]}
json.dump(out, open(f"answer_board{idx}.json", "w"))
print(f"board {idx}: SOLVED, answer_board{idx}.json written", flush=True)
