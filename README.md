# Canonical Profile Builder

Turns messy, overlapping candidate data from many sources into **one clean,
canonical profile** per person — normalized, deduplicated, and carrying a record
of **where each value came from (provenance)** and **how confident we are
(confidence)**. The guiding rule throughout: *wrong-but-confident is worse than
honestly-empty*, so the engine **never invents values** — anything it can't
determine stays `null`.

On top of the default schema, a **runtime config** can reshape the output
(select / rename / re-normalize fields, toggle provenance & confidence, choose a
missing-value policy) — **same engine, no code changes**.

---

## Pipeline

```
ingest → detect → extract (per-source adapter) → normalize → resolve (group records → candidates)
       → merge (per-field winner / union) → score (confidence) → canonical record
       → project (config-driven) → validate (against requested schema) → emit JSON
```

The design keeps two layers strictly separate:

- an **internal canonical record** — always the full, normalized schema, with
  provenance and confidence;
- a **projection layer** — reshapes that record per the runtime config and
  validates the result.

## Sources implemented

| Group | Source | Adapter |
|-------|--------|---------|
| **Structured** | Recruiter CSV export | `recruiter_csv` |
| **Structured** | ATS JSON blob (field names that do *not* match ours) | `ats_json` |
| **Unstructured** | GitHub profile (public REST API; fixture or live) | `github` |
| **Unstructured** | Résumé (`.txt`, or `.pdf` with `pypdf`) | `resume` |
| **Unstructured** | Recruiter notes (free text `.txt`) | `recruiter_notes` |

(At least one structured and one unstructured source is enough; this ships five.)

## Canonical schema & normalized formats

`candidate_id, full_name, emails[], phones[], location{city,region,country},
links{linkedin,github,portfolio,other[]}, headline, years_experience,
skills[{name,confidence,sources[]}], experience[{company,title,start,end,summary}],
education[{institution,degree,field,end_year}], provenance[{field,source,method}],
overall_confidence`

- **Phones** → E.164 (`+919876543210`), via libphonenumber; region inferred from the
  resolved location. Unparseable numbers are **dropped**, never faked.
- **Dates** → `YYYY-MM` (year-only kept as `YYYY`); `"present"` → open-ended (`end: null`).
- **Country** → ISO-3166 alpha-2 (`"India"` → `IN`); unknown → `null`.
- **Skills** → canonical names (`golang`/`Go` → `Go`, `JS` → `JavaScript`, `k8s` → `Kubernetes`).
- **Emails / links** → lower-cased, trimmed, deduped.

## Merge & confidence (how a winner is picked)

- **Entity resolution:** records are clustered into one person using strong
  identity anchors — email, phone (10-digit tail), linkedin/github username.
  *Name alone never merges* (avoids fusing two different "John Smith"s).
- **Scalars** (name, headline, country…) pick a **winner**:
  `source_trust × agreement`, deterministic tie-break by source priority then lexical.
- **Multi-value** fields (emails, phones, skills, experience, education) are
  **unioned and deduped**; the most-corroborated value sorts first (so `emails[0]`
  is the best primary).
- **Source trust:** `ats 0.90 ≥ csv 0.85 ≥ linkedin 0.80 ≥ resume 0.70 ≥ github 0.65 ≥ notes 0.50`.
- **Confidence** rises with independent agreement (`1−∏(1−wᵢ)`) and takes a small
  penalty under conflict. Every emitted value gets a `provenance` row.

---

## Install

Requires Python ≥ 3.10.

```bash
cd candidate-data-transformer
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,pdf]"      # 'dev' = pytest, 'pdf' = pypdf (optional)
```

`pip install -e .` installs the `transformer` CLI. (`pip install -r requirements.txt`
also works if you prefer.)

## Run

**Default schema, from a manifest of sources:**

```bash
transformer run --manifest samples/manifest.json
```

**A custom output config (the configurable-output twist):**

```bash
transformer run --manifest samples/manifest.json --config configs/recruiter_view.json
transformer run --manifest samples/manifest.json --config configs/contacts_min.json
```

**Point at individual files instead of a manifest:**

```bash
transformer run \
  --csv samples/recruiter.csv \
  --ats samples/ats.json \
  --resume samples/resume_priya.txt \
  --notes samples/notes_priya.txt \
  --github-fixture samples/github_priya.json --github-url https://github.com/priyasharma
```

**Write to a file / detect a source type:**

```bash
transformer run --manifest samples/manifest.json --out outputs/default_output.json
transformer detect --input samples/ats.json     # -> ats_json
```

Use `--github-live` to fetch the GitHub REST API instead of a fixture (the fixture
keeps the sample run deterministic and offline). `--quiet` silences warnings;
exit code is `1` if the output fails schema validation.

## The runtime config

```jsonc
{
  "fields": [
    { "path": "full_name",     "type": "string",   "required": true },
    { "path": "primary_email", "from": "emails[0]", "type": "string", "required": true },
    { "path": "phone",         "from": "phones[0]", "type": "string",   "normalize": "E164" },
    { "path": "skills",        "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
  ],
  "include_confidence": true,
  "include_provenance": false,
  "on_missing": "null"          // null | omit | error  (per-field override allowed)
}
```

- **`from`** path grammar: `full_name`, `location.country`, `emails[0]`, `skills[].name`.
- **`required`** missing → hard validation error. Otherwise **`on_missing`** decides
  (`null` keeps the key, `omit` drops it, `error` fails).
- Toggle **`include_confidence`** / **`include_provenance`** independently.
- The projected output is **validated against the requested schema** (types +
  required) before it's returned.

See `configs/recruiter_view.json` and `configs/contacts_min.json`.

## Sample output (excerpt)

The bundled sample has Priya Sharma across all 5 sources (with conflicts) and
Marcus Lee in the CSV only. Default-schema excerpt:

```json
{
  "candidate_id": "cand_e700c63c09b6",
  "full_name": "Priya Sharma",
  "emails": ["priya.sharma@example.com", "p.sharma@acme.com"],
  "phones": ["+919876543210"],
  "location": { "city": "Bengaluru", "region": "Karnataka", "country": "IN" },
  "headline": "Senior Backend Engineer",
  "years_experience": 7,
  "skills": [{ "name": "Go", "confidence": 0.99, "sources": ["ats_json","resume","github"] }],
  "overall_confidence": 0.9
}
```

Full produced outputs are committed under [`outputs/`](outputs/):
`default_output.json`, `recruiter_view_output.json`, `contacts_min_output.json`.

## Edge cases handled

1. **Conflicting scalars** (Bengaluru vs Bangalore; two headlines) → agreement/trust winner; both kept in provenance.
2. **Garbage / missing source** (invalid JSON, empty CSV, unreachable GitHub) → warned and skipped; output unchanged. See `samples/manifest_robust.json`.
3. **Unparseable phone** → dropped, never emitted as a fake E.164.
4. **Cross-source dedup** — the same phone in 3 formats collapses to one `+E.164`; `Go`/`Golang`/repo-language all merge to one skill.
5. **`required` field missing under a custom config** → validation fails loudly (non-zero exit), pointing at the field.
6. **Same name, different people** — two "John Doe"s are **never fused on name alone**; each consolidates only via shared strong anchors (email / phone tail / GitHub / LinkedIn username), so one John Doe across 3 sources and another across 2 resolve to **two separate profiles with no field bleed**. (Honest limit: if a single person's records share *no* anchor at all, they stay split rather than risk a wrong merge — under-merge is safe, over-merge pollutes hiring.)

## Determinism, robustness, scale

- **Deterministic & explainable** — same inputs → byte-identical output; every field traces to `{source, method}`. (No wall-clock/RNG anywhere.)
- **Robust** — a missing/garbage source is caught per-source; the run continues. Unknown values become `null`/`[]`, never invented.
- **Scale** — entity resolution uses hash-anchor blocking (near-linear); the pipeline streams per source and merges per cluster, so thousands of candidates are fine.

## Tests

```bash
pytest -q          # 70 tests
```

Covers normalizers, entity resolution & conflict resolution, the projection path
resolver, config validation, an end-to-end **gold-profile** comparison on the
sample inputs, and robustness (garbage/missing sources, unparseable phone).

## Out of scope (deliberate, under time pressure)

- Live LinkedIn scraping (no public API) — a JSON-export adapter would slot in beside the others.
- Deep PDF/DOCX layout parsing — text + basic `pypdf` extraction only.
- Fuzzy/ML name matching — deterministic anchors only (by design — avoids false merges).
- GitHub GraphQL — REST is sufficient for name/bio/location/languages.

## Project layout

```
src/transformer/
  models.py        canonical + claim data models
  normalize/       phone, dates, country, skills, text
  sources/         recruiter_csv, ats_json, github, resume_text, recruiter_notes (+ detect)
  merge.py         entity resolution + per-field merge + confidence + provenance
  confidence.py    source-trust weights + agreement model
  config.py        runtime output config (parse/validate)
  projection.py    config-driven projection + path resolver
  validation.py    validate projected output against the requested schema
  pipeline.py      orchestration
  cli.py           CLI
configs/           example runtime configs
samples/           sample inputs + manifests
outputs/           produced JSON (committed as evidence)
tests/             pytest suite
```

Demo Video URL: https://drive.google.com/file/d/1lKqBPyUyPPflDYEz5tjdo9jLJ-rfAyOz/view?usp=sharing
