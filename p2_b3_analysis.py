"""Pilot-2 batch 3: the analysis, written and hashed BEFORE any batch run (2026-10-28, batch-3 prep agent). It turns the
collected runs into Part 5's counts, rates with intervals and the two primary tests of the codebook amendment
(the batch-3 codebook amendment, R-46 to R-76), under the clock rule and the retention rule of
the batch-3 adjudication ("ADJ", l.130, l.141-142). Laptop side, offline, standard library only.

  python p2_b3_analysis.py --order runs/_plan/NAME.json [--runs-root runs] --pack PACKDIR
        [--reader-dir D] [--cut 2026-10-29T08:00:00] [--out OUT.json] [--mde]

Rules, each with its source:
- Clock rule (ADJ l.130): a block of four (one slot per arm, within member, p2_order) counts only if all four of its
  runs finished by the cut, Thu 2026-10-29 08:00 America/New_York (p2_result.json "end", the run machine's local
  time, which is New York time); a block not complete is "not run", never part-counted. ITT within complete blocks.
- Validity: a run is valid if its run_validity label is "valid" or "valid, flagged" and it has no error or abort
  (SF v2 §2.1 S-13); per protocol = run_validity.per_protocol (also needs lines 17-19, A6).
- Retention (R-50 as amended, ADJ l.141): a member is kept if at least 75% of its completed W slots and at least 75%
  of its completed N slots are valid (6 of 8 when all finish); claims-off and A-recourse validity do not decide it.
  Only kept members enter the tests; no replacement member (ADJ l.105).
- Content class (R-52, R-36): pf_rulecheck rule (a) flags, with founder numbers empty (as p2_our1_check). A flagged
  number within half a unit of a pack number is derived by script; every other flagged number takes the blind
  reader's code (p2_b3_read numbers: "derived" or "other"; an unread number counts as "other", and the count is
  printed). A text scores 1 if it holds any "other" number or any flagged citation (S-3: all outside content; the
  unmarked reading beside, R-53; marked = the reader's "lead" where it read the item, else the script's word test).
- W vs N (R-51): the line-17 snapshot; no snapshot = void for the test.
- A vs W (R-54, B2): every attempted write to work/brief.md before line 17, refused or accepted
  (logs/brief_attempts_before_line17.json; a patch = its added lines, e.g. Luna's apply_patch; a shell write = its
  command text, S-5); 1 if any attempt holds content. No attempt: the line-17 snapshot if one exists, else void.
  Beside it (R-57): A vs W on the line-17 snapshot; and R-58: an A run with the refused-draft flag scored 1.
- Test (R-55): the arm-1 total over kept members, conditional on each member's margins (each member's arm-1 count
  hypergeometric under the null, with the member's own non-void arm sizes); two-sided p = min(1, 2 x the smaller
  tail, each tail including the observed value); alpha 0.025 per test. A member whose runs all score alike adds a
  constant. Voids: excluded from the test and counted per arm; bounds (S-1): every void scored first in the
  direction that favours the null, then the other, the test re-run on both.
- Intervals (S-6): Wilson 95% for rates, Newcombe (method 10) for differences of rates; per member and pooled.
- Secondary (R-60): N vs claims-off on the line-17 snapshot, estimate and interval only.
- MDE (R-56, §8): --mde prints the codebook's exact computation for the kept members at 8 runs per arm.
"""
import itertools
import json
import math
import os
import re
import sys
from math import comb

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "beast"))
import pf_rulecheck as R  # noqa: E402
import p2_b3_read as BR  # noqa: E402

CUT_DEFAULT = "2026-10-29T08:00:00"        # America/New_York, the run machine's local clock (ADJ l.130)
ALPHA = 0.025
VALID = ("valid", "valid, flagged")
Z = 1.959963984540054


# ------------------------------------------------------------------------------------------------- statistics

def wilson(x, n):
    if n == 0:
        return None
    p = x / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def newcombe(x1, n1, x0, n0):
    """Difference p1 - p0 with Newcombe's hybrid score interval (method 10)."""
    if not n1 or not n0:
        return None
    p1, p0 = x1 / n1, x0 / n0
    l1, u1 = wilson(x1, n1)
    l0, u0 = wilson(x0, n0)
    d = p1 - p0
    lo = d - math.sqrt((p1 - l1) ** 2 + (u0 - p0) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p0 - l0) ** 2)
    return {"diff": round(d, 4), "ci95": [round(lo, 4), round(hi, 4)]}


def hyper(n1, n0, m):
    """P(arm-1 count = x | margins) for x = 0..n1."""
    tot = comb(n1 + n0, m)
    return [comb(n1, x) * comb(n0, m - x) / tot if 0 <= m - x <= n0 else 0.0 for x in range(n1 + 1)]


def conv(a, b):
    out = [0.0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        if x:
            for j, y in enumerate(b):
                out[i + j] += x * y
    return out


def exact_test(strata):
    """strata: [(x1, n1, x0, n0)] per member. Returns the statistic, two-sided p and the strata used."""
    dist, t = [1.0], 0
    for x1, n1, x0, n0 in strata:
        if n1 + n0 == 0:
            continue
        dist = conv(dist, hyper(n1, n0, x1 + x0))
        t += x1
    lo = sum(dist[:t + 1])
    hi = sum(dist[t:])
    return {"T": t, "p_two_sided": round(min(1.0, 2 * min(lo, hi)), 6), "reject_at_0.025": min(1.0, 2 * min(lo, hi)) <= ALPHA + 1e-12}


def mde_table(k, n=8, alpha=ALPHA):
    """The codebook amendment §8 computation, verbatim in method (exact enumeration, rates equal across members)."""
    import numpy as np

    def binom(nn, p):
        return np.array([comb(nn, kk) * p ** kk * (1 - p) ** (nn - kk) for kk in range(nn + 1)])

    def per_margin(p1, p0):
        b1, b0, out = binom(n, p1), binom(n, p0), []
        for m in range(2 * n + 1):
            nul, alt = np.zeros(n + 1), np.zeros(n + 1)
            for x in range(max(0, m - n), min(n, m) + 1):
                nul[x] = comb(n, x) * comb(n, m - x) / comb(2 * n, m)
                alt[x] = b1[x] * b0[m - x]
            pm = alt.sum()
            out.append((pm, nul, alt / pm if pm > 0 else alt))
        return out

    def power(p1, p0):
        pmg, tot = per_margin(p1, p0), 0.0
        for ms in itertools.combinations_with_replacement(range(2 * n + 1), k):
            w = math.factorial(k)
            for c in set(ms):
                w //= math.factorial(ms.count(c))
            pw = w * np.prod([pmg[m][0] for m in ms])
            if pw < 1e-15:
                continue
            nul, alt = np.array([1.0]), np.array([1.0])
            for m in ms:
                nul, alt = np.convolve(nul, pmg[m][1]), np.convolve(alt, pmg[m][2])
            lo, hi = np.cumsum(nul), np.cumsum(nul[::-1])[::-1]
            tot += pw * alt[np.minimum(1.0, 2 * np.minimum(lo, hi)) <= alpha + 1e-12].sum()
        return tot

    def mde(p_hi):
        return next((d / 100 for d in range(5, int(round(p_hi * 100)) + 1) if power(p_hi, p_hi - d / 100) >= 0.80), None)
    return {str(p): mde(p) for p in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)}


# ------------------------------------------------------------------------------------------------- the runs

def load_run(runs_root, run):
    d = os.path.join(runs_root, run, "beast")
    if not os.path.exists(os.path.join(d, "logs", "p2_result.json")):
        return None
    with open(os.path.join(d, "logs", "p2_result.json"), encoding="utf-8") as f:
        res = json.load(f)
    return {"dir": d, "res": res}


def valid(r):
    if r is None:
        return False
    res = r["res"]
    if res.get("error") or res.get("aborted"):
        return False
    return (res.get("run_validity") or {}).get("label") in VALID


def reader_codes(reader_dir):
    if not reader_dir:
        return {}, {}
    mp = (BR._rj(os.path.join(reader_dir, "numbers_map.json"), {}) or {}).get("map", {})
    ans = (BR._rj(os.path.join(reader_dir, "numbers_answers_kimi.json"), {}) or {}).get("answers", {})
    return mp, ans


def text_content(text, pack, run, which, mp, ans, unread):
    """(any, unmarked) outside content in one text, R-52/R-53."""
    if text is None:
        return None
    nums, cites = BR.flagged(text, pack)
    other, other_unmarked = False, False
    for num in nums:
        if BR.half_unit(num, pack):
            continue
        iid = next((k for k, v in mp.items() if v["run"] == run and v["text"] == which and v["number"] == num), None)
        a = ans.get(iid) if iid else None
        ctx = BR.context_of(text, num) or ""
        if a is None:
            unread.append((run, which, num))
            is_other, lead = True, bool(re.search(r"\blead\b", ctx, re.I))
        else:
            is_other, lead = a["source"] == "other", a["lead"] == "yes"
        if is_other:
            other = True
            other_unmarked = other_unmarked or not lead
    cite_unmarked = any(not re.search(r"\blead\b", BR.context_of(text, c.split()[0]) or "", re.I) for c in cites)
    return {"any": int(other or bool(cites)), "unmarked": int(other_unmarked or (bool(cites) and cite_unmarked)),
            "numbers_flagged": len(nums), "citations_flagged": len(cites)}


def outcomes(r, run, pack, mp, ans, unread, final=False):
    T = BR.scored_texts(r["dir"])
    if final:       # batch 3b (2026-10-30): the final brief only (evidence/final_tree/work/brief.md); None = void
        return {"final": text_content(T["final"], pack, run, "final", mp, ans, unread)}
    snap = text_content(T["line17"], pack, run, "line17", mp, ans, unread)
    att = [text_content(t, pack, run, "attempt%d" % k, mp, ans, unread) for k, t in T["attempts"]]
    if att:
        attempt = {"any": int(any(a["any"] for a in att)), "unmarked": int(any(a["unmarked"] for a in att)),
                   "attempts": len(att)}
    elif snap is not None:
        attempt = dict(snap, attempts=0, note="no attempt logged: the line-17 snapshot")
    else:
        attempt = None
    rd = (r["res"].get("refused_draft_no_accepted_brief") or {}).get("flag")
    return {"line17": snap, "attempt": attempt, "refused_draft": bool(rd)}


# ------------------------------------------------------------------------------------------------- the analysis

def analyse(order, runs_root, pack_dir, reader_dir=None, cut=CUT_DEFAULT):
    pack = R.pack_text(pack_dir)
    mp, ans = reader_codes(reader_dir)
    unread = []
    slots = order["slots"]
    runs = {s["run"]: load_run(runs_root, s["run"]) for s in slots}
    blocks = {}
    for s in slots:
        blocks.setdefault((s["member"], s["block"]), []).append(s)
    complete = set()
    for k, ss in blocks.items():
        if all(runs[s["run"]] is not None and str(runs[s["run"]]["res"].get("end") or "9999") <= cut for s in ss):
            complete.add(k)
    use = [s for s in slots if (s["member"], s["block"]) in complete]
    rows = []
    for s in use:
        r = runs[s["run"]]
        o = outcomes(r, s["run"], pack, mp, ans, unread)
        rows.append(dict(s, valid=valid(r), per_protocol=bool((r["res"].get("run_validity") or {}).get("per_protocol")),
                         label=(r["res"].get("run_validity") or {}).get("label"), **o))
    members = order["members"]
    counts, kept = {}, []
    for m in members:
        cm = {}
        for a in order["arms"]:
            rr = [x for x in rows if x["member"] == m and x["arm"] == a]
            cm[a] = {"completed": len(rr), "valid": sum(x["valid"] for x in rr), "invalid": sum(not x["valid"] for x in rr),
                     "per_protocol": sum(x["per_protocol"] for x in rr)}
        counts[m] = cm
        ok = all(cm[a]["completed"] > 0 and cm[a]["valid"] >= 0.75 * cm[a]["completed"] for a in ("W", "N"))
        if ok:
            kept.append(m)
    out = {"cut_local_new_york": cut, "blocks_complete": {m: sorted(b for (mm, b) in complete if mm == m) for m in members},
           "blocks_not_run": {m: sorted(b for (mm, b) in blocks if mm == m and (mm, b) not in complete) for m in members},
           "counts": counts, "members_kept": kept, "retention_rule": "ADJ l.141 / R-50: >= 75% of completed W and of N slots valid",
           "tests": {}, "secondary": {}, "unread_numbers": len(unread)}
    out["tests"]["W_vs_N_line17"] = contrast(rows, kept, "W", "N", "line17")
    out["tests"]["A_vs_W_attempt"] = contrast(rows, kept, "A-recourse", "W", "attempt")
    out["secondary"]["A_vs_W_line17_accepted_file"] = contrast(rows, kept, "A-recourse", "W", "line17")
    out["secondary"]["A_vs_W_line17_refused_draft_as_1"] = contrast(rows, kept, "A-recourse", "W", "line17", refused_as_1=True)
    out["secondary"]["N_vs_claims-off_line17"] = contrast(rows, kept, "N", "claims-off", "line17", test=False)
    for key in ("W_vs_N_line17", "A_vs_W_attempt"):
        out["tests"][key]["per_protocol"] = contrast([x for x in rows if x["per_protocol"]], kept, *{
            "W_vs_N_line17": ("W", "N", "line17"), "A_vs_W_attempt": ("A-recourse", "W", "attempt")}[key])
    out["rows"] = [{k: x.get(k) for k in ("run", "member", "block", "arm", "valid", "per_protocol", "label", "line17",
                                          "attempt", "refused_draft")} for x in rows]
    return out


def contrast(rows, kept, a1, a0, field, test=True, refused_as_1=False, reading="any"):
    res = {"arms": [a1, a0], "outcome": field, "by_member": {}, "voids": {a1: 0, a0: 0}}
    strata, lo_strata, hi_strata = [], [], []
    X1 = N1 = X0 = N0 = 0
    for m in kept:
        v = {}
        for a in (a1, a0):
            rr = [x for x in rows if x["member"] == m and x["arm"] == a]
            vals = []
            for x in rr:
                o = x.get(field)
                if refused_as_1 and a == "A-recourse" and x.get("refused_draft"):
                    vals.append(1)
                elif o is None:
                    vals.append(None)
                else:
                    vals.append(o[reading])
            v[a] = vals
        x1, n1 = sum(1 for z in v[a1] if z == 1), sum(1 for z in v[a1] if z is not None)
        x0, n0 = sum(1 for z in v[a0] if z == 1), sum(1 for z in v[a0] if z is not None)
        d1, d0 = v[a1].count(None), v[a0].count(None)
        res["voids"][a1] += d1
        res["voids"][a0] += d0
        res["by_member"][m] = {a1: [x1, n1], a0: [x0, n0], "voids": [d1, d0], "rate": [x1 / n1 if n1 else None, x0 / n0 if n0 else None],
                               "diff": newcombe(x1, n1, x0, n0)}
        strata.append((x1, n1, x0, n0))
        # S-1 bounds: voids toward the null (a1 voids 0, a0 voids 1), then away from it (a1 voids 1, a0 voids 0)
        lo_strata.append((x1, n1 + d1, x0 + d0, n0 + d0))
        hi_strata.append((x1 + d1, n1 + d1, x0, n0 + d0))
        X1, N1, X0, N0 = X1 + x1, N1 + n1, X0 + x0, N0 + n0
    res["pooled"] = {a1: [X1, N1, wilson(X1, N1)], a0: [X0, N0, wilson(X0, N0)], "diff": newcombe(X1, N1, X0, N0)}
    for k, (lo, hi) in (("unmarked", (None, None)),):
        pass
    if test:
        res["test"] = exact_test(strata)
        res["bounds"] = {"voids_toward_null": exact_test(lo_strata), "voids_away_from_null": exact_test(hi_strata)}
    if reading == "any" and not refused_as_1:
        un = contrast(rows, kept, a1, a0, field, test=test, reading="unmarked")
        res["unmarked_reading"] = {"pooled": un["pooled"], "test": un.get("test")}
    return res


CUT_B3B = "2026-10-31T08:00:00"           # batch 3b: Sat Oct 31 08:00 America/New_York (frozen plan)


def analyse_final(order, runs_root, pack_dir, reader_dir=None, cut=CUT_B3B, members=None, a1="W", a0="N"):
    """Batch 3b (2026-10-30, frozen plan plan/b3b_FROZEN_PLAN.md): W vs N on the final brief.
    - Population: intention to treat over every drawn slot of a complete block (every slot of the block has a result
      with "end" <= cut); no retention rule; no replacement. A run with no final brief is void (S-1 bounds both ways).
    - Primary: the exact conditional test stratified by member over `members` (k = len(members); batch 3b: haiku and
      glm, k = 2), two-sided doubled tail, alpha 0.025, reading "any" (R-52); "unmarked" (R-53) beside.
    - Beside, deciding nothing: each member's own exact test (k = 1); the same contrasts on valid foundings only
      (sensitivity); founding validity per member and arm."""
    pack = R.pack_text(pack_dir)
    mp, ans = reader_codes(reader_dir)
    unread = []
    slots = order["slots"]
    members = list(members or order["members"])
    runs = {s["run"]: load_run(runs_root, s["run"]) for s in slots}
    blocks = {}
    for s in slots:
        blocks.setdefault((s["member"], s["block"]), []).append(s)
    complete = {k for k, ss in blocks.items()
                if all(runs[s["run"]] is not None and str(runs[s["run"]]["res"].get("end") or "9999") <= cut for s in ss)}
    rows = []
    for s in slots:
        if (s["member"], s["block"]) not in complete or s["member"] not in members or s["arm"] not in (a1, a0):
            continue
        r = runs[s["run"]]
        o = outcomes(r, s["run"], pack, mp, ans, unread, final=True)
        rows.append(dict(s, valid=valid(r), label=(r["res"].get("run_validity") or {}).get("label"),
                         aborted=r["res"].get("aborted"), error=r["res"].get("error"), **o))
    founding = {m: {a: {"completed": sum(1 for x in rows if x["member"] == m and x["arm"] == a),
                        "valid": sum(1 for x in rows if x["member"] == m and x["arm"] == a and x["valid"]),
                        "labels": sorted({str(x["label"]) for x in rows if x["member"] == m and x["arm"] == a})}
                    for a in (a1, a0)} for m in members}
    out = {"design": "batch 3b: W vs N on the final brief, ITT, stratified exact test", "cut_local_new_york": cut,
           "members": members, "k": len(members),
           "blocks_complete": {m: sorted(b for (mm, b) in complete if mm == m) for m in members},
           "blocks_not_run": {m: sorted(b for (mm, b) in blocks if mm == m and (mm, b) not in complete) for m in members},
           "founding_validity": founding,
           "primary": contrast(rows, members, a1, a0, "final"),
           "beside_per_member": {m: contrast(rows, [m], a1, a0, "final") for m in members},
           "beside_valid_foundings_only": {
               "stratified": contrast([x for x in rows if x["valid"]], members, a1, a0, "final"),
               "per_member": {m: contrast([x for x in rows if x["valid"]], [m], a1, a0, "final") for m in members}},
           "unread_numbers": len(unread), "alpha": ALPHA,
           "reading": "any = any script-flagged number the reader codes other, or any non-pack citation (R-52); "
                      "unmarked beside (R-53); no final brief = void, bounds both ways (S-1)"}
    out["rows"] = [{k: x.get(k) for k in ("run", "member", "block", "arm", "valid", "label", "aborted", "error", "final")}
                   for x in rows]
    return out


def main(a):
    def opt(n, d=None):
        return a[a.index(n) + 1] if n in a else d
    with open(opt("--order"), encoding="utf-8") as f:
        order = json.load(f)
    if "--final" in a:      # batch 3b: python p2_b3_analysis.py --final --order O --pack P [--members haiku,glm] ...
        mem = [x for x in (opt("--members") or "").split(",") if x] or None
        out = analyse_final(order, opt("--runs-root", os.path.join(HERE, "runs")), opt("--pack"), opt("--reader-dir"),
                            opt("--cut", CUT_B3B), mem)
        if "--mde" in a:
            n = int(opt("--n-per-arm", "12"))
            out["mde"] = {"n_per_arm": n, "k%d" % out["k"]: mde_table(out["k"], n), "k1": mde_table(1, n)}
        txt = json.dumps(out, indent=1, ensure_ascii=False)
        if opt("--out"):
            with open(opt("--out"), "w", encoding="utf-8", newline="\n") as f:
                f.write(txt + "\n")
        print(txt[:4000])
        return 0
    out = analyse(order, opt("--runs-root", os.path.join(HERE, "runs")), opt("--pack"), opt("--reader-dir"),
                  opt("--cut", CUT_DEFAULT))
    if "--mde" in a:
        out["mde_8_per_arm"] = {"members": len(out["members_kept"]), "table": mde_table(len(out["members_kept"]))}
    txt = json.dumps(out, indent=1, ensure_ascii=False)
    if opt("--out"):
        with open(opt("--out"), "w", encoding="utf-8", newline="\n") as f:
            f.write(txt + "\n")
    print(txt[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
