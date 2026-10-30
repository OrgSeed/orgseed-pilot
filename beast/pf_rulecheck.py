"""PILOT-F: the mechanical check of the organization's rule OUR-1, shared by enforcement (cell E, through the
pf_guard.js plugin) and by scoring (every cell). Fixed before the series; standard library only.

  python pf_rulecheck.py --rule a|b|c --pack <dir>      JSON {"rel", "files"?, "content"} on stdin
  -> prints {"violations": [...], "numbers_not_in_pack": [...], "citations_not_in_pack": [...]}

Rules (the candidate C1 rules of the spec, section 4):
  a  work/ uses only the pack: every number is written in a pack file, and every author-year citation,
     DOI or URL occurs in the pack;
  b  no file tool writes into records/;
  c  every number in work/ is written exactly so in a pack file.
Numbers: digit runs with an optional decimal part; single-digit integers are not checked (study labels,
row counts, list numbers); ".474" and "0.474" are the same number; a number must stand alone in the pack
(not as a fragment of a longer number). Labels S1-S6 (C1 uses S1-S5), OUR-1, CK-1, P-/D-/L- IDs are ignored.
"""
import json
import os
import re
import sys

STOP = {"S", "In", "The", "A", "Table", "Study", "Experiment", "Figure", "Since", "From", "By", "On", "Of", "Until",
        "As", "Between", "Fig", "Session", "Turn", "Step", "Year", "Spring", "Fall", "October", "September",
        "January", "February", "March", "April", "May", "June", "July", "August", "November", "December"}


def norm(s):
    return re.sub(r"[   ]", " ", re.sub(r"[−–—]", "-", s))


def pack_text(pack_dir):
    t = ""
    for fn in sorted(os.listdir(pack_dir)):
        if fn.endswith((".md", ".txt")):
            t += "\n" + open(os.path.join(pack_dir, fn), encoding="utf-8").read()
    return norm(t)


NUM = re.compile(r"(?<![\d.,])\.\d+|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_PACK_TOKENS = {}


def _pack_tokens(pack):
    """The pack's numbers, read with the same tokenizer as the work (fixed 2026-10-13 19:25, before any E run:
    the earlier substring test missed numbers after a comma, such as the 66 in F(2,66))."""
    k = hash(pack)
    if k not in _PACK_TOKENS:
        s = set()
        for m in NUM.finditer(pack):
            tok = m.group(0).rstrip(".,")
            s.add(tok)
            if tok.startswith("0."):
                s.add(tok[1:])
            if tok.startswith("."):
                s.add("0" + tok)
        _PACK_TOKENS[k] = s
    return _PACK_TOKENS[k]


def _in_pack(pack, f):
    return f in _pack_tokens(pack)


# Numbers the founder herself gave in her own words (the 400-word limit); not facts from a source.
FOUNDER_NUMBERS = {"400"}
URLDOI = re.compile(r"https?://[^\s)\]]+|10\.\d{4,9}/[^\s)\],;\"'<>]+")
IGNORE = re.compile(r"\bS[1-6]\b|\bS\d{3}\b|\b[A-Z]{1,5}-\d{1,4}\b|\b\d{4}-\d{2}-\d{2}(?:[T ][\d:.]+Z?)?")


def numbers_not_in_pack(text, pack):
    """Ignored: study labels S1-S6, session labels (S002), record and rule IDs (P-0001, CL-0003, OUR-1, CK-1,
    CORE-13 ...), ISO dates, single-digit integers, and the founder's own number (the 400-word limit)."""
    t = IGNORE.sub(" ", URLDOI.sub(" ", norm(text)))
    bad = []
    # a comma joins digits only as a thousands separator (73,035.88); "F(2,87)" is two numbers, 2 and 87
    # (fixed 2026-10-13 19:15, after B and before any W/E/K run: "2,87" had been read as one number)
    for m in re.finditer(r"(?<![\d.,])\.\d+|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", t):
        tok = m.group(0).rstrip(".,")
        if re.fullmatch(r"\d", tok) or tok in FOUNDER_NUMBERS:
            continue
        forms = [tok] + ([tok[1:]] if tok.startswith("0.") else []) + (["0" + tok] if tok.startswith(".") else [])
        if not any(_in_pack(pack, f) for f in forms):
            bad.append(tok)
    return sorted(set(bad), key=bad.index)


def citations_not_in_pack(text, pack):
    low = pack.lower()
    t = norm(text)
    bad = []
    for m in re.finditer(r"\b([A-Z][A-Za-z'\-]+)(?:\s+et\s+al\.?|\s+(?:and|&)\s+[A-Z][A-Za-z'\-]+)?,?\s*\(?((?:19|20)\d{2})\)?", t):
        if m.group(1) in STOP:
            continue
        if not re.search(r"\b" + re.escape(m.group(1).lower()) + r"\b", low):
            bad.append(m.group(0).strip())
    for m in re.finditer(r"10\.\d{4,9}/[^\s)\],;\"'<>]+", t):
        doi = m.group(0).rstrip(".")
        if doi.lower() not in low:
            bad.append(doi)
    for m in re.finditer(r"https?://[^\s)\]]+", t):
        u = m.group(0).rstrip(".,")
        if u.lower() not in low:
            bad.append(u)
    return sorted(set(bad), key=bad.index)


DOC_EXT = (".md", ".txt", ".markdown", ".html", ".csv")


def check(rule, rc, pack):
    files = rc.get("files") or [rc.get("rel") or ""]
    content = rc.get("content") or ""
    out = {"violations": [], "numbers_not_in_pack": [], "citations_not_in_pack": []}
    if rule == "b":
        for f in files:
            if f.startswith("records/"):
                out["violations"].append("a file tool may not write into %s; records are added only with "
                                         "python scripts/fos_log.py" % f)
        return out
    if not any(f.startswith("work/") and f.lower().endswith(DOC_EXT) for f in files):
        return out      # record drafts (work/*.json) that CORE-4 tells members to write for fos_log are not work
    nums = numbers_not_in_pack(content, pack)
    out["numbers_not_in_pack"] = nums
    if nums:
        out["violations"].append("these numbers are not written in any saved source in sources/pack/: " + ", ".join(nums[:12]))
    cites = citations_not_in_pack(content, pack)
    out["citations_not_in_pack"] = cites
    if rule == "a" and cites:
        out["violations"].append("these citations do not occur in sources/pack/: " + "; ".join(cites[:8]))
    return out


if __name__ == "__main__":
    a = sys.argv
    rule = a[a.index("--rule") + 1]
    pack = pack_text(a[a.index("--pack") + 1])
    sys.stdin.reconfigure(encoding="utf-8")
    rc = json.loads(sys.stdin.read() or "{}")
    print(json.dumps(check(rule, rc, pack), ensure_ascii=False))
