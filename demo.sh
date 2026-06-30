#!/usr/bin/env bash
# Guided ~2-minute demo. Press Enter to advance through each beat.
# Usage:  ./demo.sh        (or)  bash demo.sh
#
# Runs the pipeline and shows the OUTPUTS (it doesn't open every input file).
# Press Enter between beats so you can narrate.

cd "$(dirname "$0")"
[ -f .venv/bin/activate ] && source .venv/bin/activate
command -v transformer >/dev/null 2>&1 || transformer(){ python -m transformer.cli "$@"; }
PY=python3; command -v "$PY" >/dev/null 2>&1 || PY=.venv/bin/python

pause(){ printf "\n\033[2m  ── press Enter to continue ──\033[0m "; read -r _; }
banner(){ clear 2>/dev/null || printf '\033c'; printf "\033[1;36m\n  %s\033[0m\n\n" "$1"; }

# ===========================================================================
banner "1 · RUN END-TO-END  →  default canonical schema (5 sources in, 2 people out)"
echo "  Inputs: recruiter CSV + ATS JSON (structured) · resume + notes + GitHub (unstructured)."
echo
transformer run --manifest samples/manifest.json --out outputs/default_output.json
echo
$PY - <<'PY'
import json
ps = json.load(open("outputs/default_output.json"))
p, m = ps[0], ps[1]
print("CANDIDATE 1 — Priya, fused from all five sources")
for k in ("full_name", "emails", "phones", "location", "headline", "years_experience"):
    print(f"   {k:<17}: {p[k]}")
print("   skills (canonical · confidence · backing sources):")
for s in p["skills"][:4]:
    print(f"       {s['name']:<12} {s['confidence']:<5} {s['sources']}")
print(f"   provenance rows : {len(p['provenance'])}   overall_confidence: {p['overall_confidence']}")
print()
print("CANDIDATE 2 — Marcus, CSV only → unknown fields stay null/[], never invented")
print(f"   emails={m['emails']}  phones={m['phones']}  skills={m['skills']}")
PY
echo
echo "  Note: phone deduped to one E.164; 'Golang'/'Go'/repo-language → one 'Go';"
echo "  'Bengaluru' (3 sources) beat 'Bangalore' (resume) by trust × agreement."
pause

# ===========================================================================
banner "2 · CONFIGURABLE OUTPUT  —  reshape the result with NO code change"
echo "  The canonical record is one fixed shape; each consumer wants its own. A runtime"
echo "  CONFIG (not code) selects/renames/re-normalizes fields and toggles the metadata."
echo
transformer run --manifest samples/manifest.json --config configs/recruiter_view.json \
    --out outputs/recruiter_view_output.json --quiet
$PY - <<'PY'
import json
p = json.load(open("outputs/recruiter_view_output.json"))[0]
print("  recruiter_view.json → renamed keys, primary email/phone, flat skills,")
print("  per-field confidence map, provenance OFF:")
print(json.dumps(p, indent=2))
PY
pause

# ===========================================================================
banner "3 · EDGE CASE A · ROBUSTNESS  —  garbage in, clean profile still out"
echo "  Manifest adds 3 broken sources: invalid JSON, an empty CSV, a missing file."
echo "  Each becomes a warning on stderr; the run continues:"
echo
transformer run --manifest samples/manifest_robust.json --out /tmp/robust_out.json
echo
transformer run --manifest samples/manifest.json --quiet --out /tmp/clean_out.json
if diff -q /tmp/robust_out.json /tmp/clean_out.json >/dev/null; then
    printf "  \033[1;32mProfiles are BYTE-IDENTICAL to the clean run — garbage changed nothing.\033[0m\n"
fi
pause

# ===========================================================================
banner "4 · EDGE CASE B · SAME NAME, DIFFERENT PEOPLE  —  segregated, not fused"
echo "  Two different 'John Doe's: A appears in 3 sources (csv+ats+resume, one email),"
echo "  B in 2 (csv+notes, a different email). Name alone NEVER merges identities."
echo
transformer run --manifest samples/samename_manifest.json --out /tmp/samename.json --quiet
$PY - <<'PY'
import json
ps = json.load(open("/tmp/samename.json"))
print(f"  → {len(ps)} separate profiles produced:\n")
for p in ps:
    exp = p["experience"][0] if p["experience"] else {}
    srcs = sorted(set(pr["source"] for pr in p["provenance"]))
    print(f"   {p['candidate_id']}   {p['full_name']}")
    print(f"      email   : {p['emails'][0]}")
    print(f"      company : {exp.get('company')}   ({len(srcs)} sources: {srcs})")
    print(f"      skills  : {[s['name'] for s in p['skills']]}")
    print()
print("  Same name, zero field-bleed. Each person consolidates only via shared strong")
print("  anchors (email / phone / github / linkedin) — never on the name itself.")
PY
pause

# ===========================================================================
banner "5 · DESIGN DECISION + DETERMINISTIC + TESTED"
echo "  Design decision: a strict two-layer split — an internal CANONICAL record (always"
echo "  the full normalized profile w/ provenance) and a separate PROJECTION layer that"
echo "  reshapes it per config. That boundary is why configurable output needs NO engine"
echo "  changes, and why the result can be validated against the requested schema."
echo
transformer run --manifest samples/manifest.json --quiet --out /tmp/run_a.json
transformer run --manifest samples/manifest.json --quiet --out /tmp/run_b.json
if diff -q /tmp/run_a.json /tmp/run_b.json >/dev/null; then
    printf "  \033[1;32mSame inputs → byte-identical output (no clock, no randomness anywhere).\033[0m\n\n"
fi
pytest -q
printf "\n\033[1;36m  Done.\033[0m\n\n"
