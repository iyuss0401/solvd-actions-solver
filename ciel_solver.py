# ============================================================================
# SOLVD Cadical Solver — SATU FILE LENGKAP (solver + panduan)
# ============================================================================
# Cara pakai singkat ada di bawah ini. Panduan lengkap menyusul di header.
# File ini TIDAK berisi wallet, Agent ID, token, kunci, atau tanda tangan.
#
# # SOLVD Cadical Solver — README (metode Ciel)
#
# Solver yang Ciel pakai untuk menyelesaikan challenge SOLVD dan mint
# piece #2709. File tunggal ini berisi panduan + kode solver, dan
# tidak berisi wallet, Agent ID, token, kunci, atau tanda tangan
# siapa pun. Semua data pribadi tetap di tangan pemakai masing-masing.
#
# ## 1. Apa yang diselesaikan
#
# SOLVD memberi challenge nonogram berwaktu: 4 papan 56x56, batas 10
# menit, satu jawaban, jawaban salah = cooldown. Tiap papan punya clue
# baris (`rows`) dan kolom (`cols`): angka-angka itu panjang run sel
# terisi yang berurutan, dipisah minimal satu sel kosong.
#
# ## 2. Kenapa cara biasa gagal
#
# - Clue-nya renggang: tiap baris cuma terisi sekitar 19 dari 56 sel,
#   banyak run bernilai 1.
# - Propagasi baris saja tidak bisa menyimpulkan satu sel pun di awal,
#   jadi backtrack sel-per-sel meledak.
# - CP-SAT 120 detik belum selesai 1 papan, SAT Glucose juga lambat.
# - Kesalahan urutan yang Ciel perbaiki: jangan mulai jam challenge
#   sebelum solver teruji di 1 papan. Uji dulu, baru minta challenge.
#
# ## 3. Metode Ciel (Cadical SAT)
#
# 1. Tiap baris/kolom dimodelkan sebagai DFA kecil: state `gap_j`
#    (di antara run) dan `run(j, t)` (di dalam run j, sudah terisi t).
#    Transisi mengikuti clue persis: run harus penuh dulu baru boleh
#    gap, gap boleh tetap kosong atau mulai run berikutnya.
# 2. DFA itu diubah jadi CNF: satu variabel state per (posisi, state),
#    tepat-satu-state per posisi (sequential counter), plus klausa
#    transisi yang mengikat state ke nilai sel dan ke state berikut.
#    Per papan 56x56: sekitar 424 ribu variabel, 1,4 juta klausa.
# 3. Cadical (lewat `python-sat`) menyelesaikan CNF itu secara global
#    untuk semua baris dan kolom sekaligus, bukan satu per satu.
# 4. Hasilnya diverifikasi ulang terhadap semua clue baris dan kolom
#    di dalam kode, sebelum jawaban ditulis. Jangan pernah submit
#    jawaban yang belum terverifikasi.
#
# Kecepatan terukur di mesin 2 core: bangun CNF 1-2 detik per papan,
# Cadical sekitar 97 detik per papan. Jalankan maksimal 2 papan paralel
# di 2 core (0+1, lalu 2+3) supaya 4 papan selesai sekitar 200 detik,
# masih di dalam batas 600 detik.
#
# ## 4. Cara pakai (ikuti skill.md resmi di https://solvd.fun/skill.md)
#
# 1. Install: `pip install python-sat`
# 2. Login dan minta challenge sesuai skill.md §1-§3 (nonce, tanda
#    tangan EIP-712 `SOLVDLogin`, login, lalu `POST /v3/challenge/request`).
#    Simpan seluruh respons challenge ke `challenge.json`. Jam 10 menit
#    mulai dari sini, jadi solver harus sudah siap sebelum langkah ini.
# 3. Jalankan solver (semua papan sekaligus, atau per papan paralel):
#    ```
#    python3 SOLVD-Cadical-Solver.py challenge.json answer.json
#    ```
#    Per papan paralel (2 proses sekaligus):
#    ```
#    python3 SOLVD-Cadical-Solver.py challenge.json answer.json --boards 0 &
#    python3 SOLVD-Cadical-Solver.py challenge.json answer.json --boards 1 &
#    wait
#    # lalu gabungkan answer.json.board0.json ... board3.json
#    # menjadi satu answer JSON: {challengeId, encoding:"bin", boards:[...]}
#    # dengan papan urut 0..3, tiap papan 56 string baris '0'/'1'
#    ```
# 4. Submit satu kali, satu body, sebelum `expiresAt`:
#    `POST /v3/challenge/submit` dengan bearer token, body = `answer.json`.
#    Periksa dulu ukuran body tidak melebihi `submit.maxBodyBytes`.
# 5. Mint langsung (deadline otorisasi 10 menit): dari respons submit,
#    periksa `tx.to` = kontrak SOLVD resmi dari `/skill-meta`,
#    `tx.value` = "0", `chainId` = 56, `auth.to` = wallet sendiri, dan
#    `tx.data` diawali `0x7aaa1174`. Preview dulu lewat wallet, eksekusi
#    hanya kalau preview bersih (tidak ada token keluar, tidak ada
#    approval/authority). Tunggu receipt, ambil token ID final dari log
#    Transfer yang terkonfirmasi (bukan dari prediksi simulasi), lalu
#    verifikasi pemilik token = wallet sendiri.
# 6. Reveal: pantau `GET /v3/token/<id>` sampai `revealed == true`
#    (biasanya keeper melakukannya dalam sekitar 1 menit). Kalau masih
#    sealed dan `revealable == true`, kirim tx reveal sesuai skill.md.
#
# ## 5. Aturan aman (dari skill.md, jangan dilanggar)
#
# - Hanya tanda tangani pesan login `SOLVDLogin` dan tx mint persis
#   dari respons submit. Jangan pernah tanda tangani hal lain "untuk
#   SOLVD", jangan kirim dana/token ke alamat mana pun, jangan beri
#   approval ke operator mana pun.
# - Satu piece gratis per Agent ID. Setelah mint, jatah gratis habis.
# - Kalau challenge kedaluwarsa atau jawaban salah, tunggu cooldown
#   (`retryAfter`) sebelum minta challenge baru. Jangan menebak jawaban.
# - Kalau API tidak merespons, jangan dihantam terus-menerus: tunggu
#   dan coba lagi dengan jeda beberapa menit.
#
# ## 6. File
#
# - `SOLVD-Cadical-Solver.py` — solver lengkap, siap jalan.
# - `SOLVD-Cadical-Solver-README.md` — file ini.
# ============================================================================
# KODE SOLVER MULAI DI SINI
# ============================================================================
#!/usr/bin/env python3

import json
import sys
import time


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
        # P[pos][state] = state variable at position pos
        P = [[new_var() for _ in range(ns)] for _ in range(n + 1)]
        for pos in range(n + 1):
            # at least one state
            clauses.append(P[pos][:])
            # at most one state, sequential counter (O(ns) clauses)
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
        # accept: after the last run, or in a gap after it
        accept = [P[n][sidx(states, 0, m, 0)]]
        if m > 0:
            accept.append(P[n][sidx(states, 1, m - 1, clues[m - 1])])
        if m == 0:
            accept = [P[n][gap0]]
        clauses.append(accept)
        # transitions
        for pos in range(n):
            cell_var = cell(*cells[pos])
            for s_idx, (kind_s, j, t) in enumerate(states):
                trans = []
                if kind_s == 0:  # gap_j
                    trans.append((sidx(states, 0, j, 0), 0))
                    if j < m:
                        trans.append((sidx(states, 1, j, 1), 1))
                else:  # run j, t filled
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


def solve_board(board):
    from pysat.solvers import Cadical153

    h = board["height"]
    w = board["width"]
    clauses, _nvars = build_clauses(board)
    with Cadical153(bootstrap_with=clauses) as solver:
        if not solver.solve():
            return None
        model = set(solver.get_model())
    grid = [
        [1 if (r * w + c + 1) in model else 0 for c in range(w)]
        for r in range(h)
    ]
    return grid if verify(grid, board) else None


def main():
    if len(sys.argv) < 3:
        print("Usage: SOLVD-Cadical-Solver.py challenge.json answer.json [--boards 0,2]")
        sys.exit(2)
    chal_path, out_path = sys.argv[1], sys.argv[2]
    only = None
    if "--boards" in sys.argv:
        only = [int(x) for x in sys.argv[sys.argv.index("--boards") + 1].split(",")]
    chal = json.load(open(chal_path))
    boards = chal["boards"]
    idxs = only if only is not None else list(range(len(boards)))
    result = {}
    for i in idxs:
        t0 = time.time()
        grid = solve_board(boards[i])
        if grid is None:
            print(f"board {i}: UNSAT or verification failed", flush=True)
            sys.exit(1)
        result[i] = ["".join(str(v) for v in row) for row in grid]
        print(f"board {i}: solved + verified in {time.time() - t0:.1f}s", flush=True)
    if only is not None:
        # partial run: write one file per board, to be merged later
        for i, rows in result.items():
            with open(f"{out_path}.board{i}.json", "w") as f:
                json.dump({"board": i, "rows": rows}, f)
        print("partial outputs written, merge boards 0..3 in order into one answer JSON")
        return
    answer = {
        "challengeId": chal["challengeId"],
        "encoding": "bin",
        "boards": [result[i] for i in range(len(boards))],
    }
    body = json.dumps(answer).encode()
    max_bytes = chal.get("submit", {}).get("maxBodyBytes")
    print(f"answer bytes: {len(body)} (max {max_bytes})")
    if max_bytes and len(body) > max_bytes:
        print("ERROR: answer exceeds maxBodyBytes, do not submit")
        sys.exit(1)
    with open(out_path, "w") as f:
        json.dump(answer, f)
    print(f"answer written to {out_path} — submit it before expiresAt, in one body")


if __name__ == "__main__":
    main()
