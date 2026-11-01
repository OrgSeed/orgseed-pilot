# OrgSeed pilot: plan, code and scoring data

OrgSeed is a seed for a human–AI organization: a folder of plain files that a scholar grows, in conversation with an AI model, into an organization of their own. This repository holds the plan, the code and the scoring data of the pilot's second batch, called batch 3b in the files. **It does not hold the seed.** The version of the seed the pilot ran, v1.3.2, is in [`OrgSeed/orgseed`](https://github.com/OrgSeed/orgseed). In the pilot the founder was a script. AI agents wrote this code at the author's direction, and the author has not yet verified it line by line.

## Frozen before the runs

The second batch's plan was frozen, fingerprinted and committed before the runs. The first commit here, `7b6768e`, holds it: the plan, the SHA-256 fingerprint of each file, the analysis and reader code, the reader prompts, the lane table (how runs were dealt to parallel slots) and the run order. Later commits add this page, the two licence files, a `.gitattributes` that keeps line endings exact, and the `scoring/` folder, and change none of those files. To check: `git diff --stat 7b6768e HEAD`.

The plan's line 61 says "The seed published with the paper is v1.4.0". The plan stays as it was frozen. The seed published here is v1.3.2, which the same line names as the one the evidence uses.

## What is here

| Path | What it is |
|---|---|
| `plan/b3b_FROZEN_PLAN.md` | The plan |
| `plan/b3b_HASHES.txt` | The fingerprints taken before run 1; `[pub]` marks a file also in this repository |
| `plan/b3b_lanes.json`, `plan/b3b-main.json` | The lane table and the run order |
| `plan/prompts/` | The reader prompts |
| `p2_b3_analysis.py`, `beast/p2_b3_read.py`, `beast/pf_rulecheck.py` | The analysis and reader code. `p2_b3_analysis.py` does not load as published, because a reader module needs the unpublished test bench; its statistics functions run if those imports are stubbed |
| `scoring/analysis_FINAL.json` | The analysis output |
| `scoring/conduct.json` | Conduct by run and by member and arm |
| `scoring/desc_rows.json` | One row for each of the 48 runs |
| `scoring/probes_description.json` | The probes, described by cell |
| `scoring/cost_b3b.json` | Cost by member |
| `scoring/HASHES.txt` | SHA-256 of the scoring files |

`scoring/HASHES.txt` also lists item-level reading files and readers' answers. Those are not published here, and neither are the run records or the test bench. So `sha256sum -c --ignore-missing HASHES.txt`, run in `scoring/`, confirms the five data files above; without that option it also reports the others as missing.

## Licence

Free for research and other noncommercial use. Code: PolyForm Noncommercial License 1.0.0 (`LICENSE`). The plan, the prompts and the data: CC BY-NC 4.0 (`LICENSE-docs`).
