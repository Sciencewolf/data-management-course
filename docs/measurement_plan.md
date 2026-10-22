# Measurement plan

All test cases and labels below were written on **2026-10-22, before any tuning**
(`tests/cases/*.json`). Every number in the report is printed by
`python -m grocery.compare_vectors` and `python -m grocery.evaluate`; both also save
their output to `results/`.

## What is measured

| # | Question | Test set | Metric | Target | Script |
|---|---|---|---|---|---|
| M1 | Are the recommended recipes safe? | 20 cases of an allergy list + request, 7 with several allergies (`safety_cases.json`) | number of unsafe recipes in the top 5, in each system | **0** | `evaluate` |
| M2 | Are they relevant? | 20 labelled requests, 1–3 relevant recipes each (`labelled_requests.json`) | recall@5, MRR@10 | report | `evaluate` |
| M3 | How good is each HNSW index? | 20 fixed queries (`ann_queries.json`) | ANN recall@10 = shared ids of HNSW top-10 and the **same system's** exact top-10 / 10 | report | `compare_vectors` |
| M4 | Do the two systems agree? | same 20 queries | shared ids in pgvector and Qdrant HNSW top-10 | report | `compare_vectors` |
| M5 | What happens with a tight filter? | same 20 queries, `cuisine = 'korean'` keeps 11/224 rows (4.9 %) | results returned, ANN recall@10, latency p50/max | report | `compare_vectors` |

### How "unsafe" is decided (M1)

The vector search filters on its own metadata (`allergen_codes`). The check does
**not** trust that metadata: for each returned recipe it reads the current
`product_ids` from MongoDB and asks Neo4j for every allergen reachable from them. A
recipe is unsafe if that live set intersects the customer's allergy list. A stale vector
copy therefore shows up as an unsafe result (see the cross-store update below).

The safety cases target hidden allergens on purpose: gluten in pasta through durum
wheat, shrimp paste in Thai curry paste, mustard seed in curry powder, celery in stocks,
soy lecithin in dark chocolate, and a pesto brand that contains cashews.

### Recorded settings

| | pgvector 0.8.7 | Qdrant 1.20.0 |
|---|---|---|
| index build | HNSW m=16, ef_construction=64 | HNSW m=16, ef_construct=64 |
| search | `hnsw.ef_search` = 40 (default) for M3–M5, 100 for M1–M2 | `hnsw_ef` = 40 for M3–M5, 100 for M1–M2 |
| iterative scan | M5 runs with `hnsw.iterative_scan` = off and = relaxed_order; M1–M2 use relaxed_order | n/a |
| exact baseline | `SET LOCAL enable_indexscan = off` (sequential scan + sort) | `SearchParams(exact=True)` |
| filtered fields | no extra index on purpose | payload indexes on `cuisine`, `allergen_codes`, `preparation_minutes` |
| small-collection trap | `enable_seqscan = off` so the planner uses HNSW on 224 rows | `full_scan_threshold=10`, `indexing_threshold=10`; otherwise Qdrant never builds HNSW for ~350 KB |

## Baseline results (first run, untuned)

From `results/vector_comparison.txt` and `results/evaluation.txt`:

| | pgvector | Qdrant |
|---|---|---|
| M1 unsafe recipes in top 5 (20 cases) | **0 / 100** | **0 / 100** |
| M2 recall@5 / MRR@10 | 0.800 / 0.875 | 0.800 / 0.875 |
| M3 ANN recall@10, no filter | 1.000 | 1.000 |
| M4 shared ids in top-10 | 10.0 / 10 on every query | |
| M5 filter 4.9 %, ef=40, iterative **off** | 8.4 results on average, **min 2**; ANN recall@10 0.84 (min 0.20) | 10 results; ANN recall@10 1.000 |
| M5 filter 4.9 %, ef=40, iterative **relaxed_order** | 10 results; ANN recall@10 1.000 | |
| M5 filter 4.9 %, ef=200, iterative off | 10 results; ANN recall@10 1.000 | |

Latencies are 0.6–1.2 ms p50 in both systems on this data size; they are printed on every run.

What the baseline already shows:
- **Post-filtering in pgvector.** The HNSW scan collects `ef_search` = 40 candidates and only
  then applies `WHERE cuisine = 'korean'`. When few of the 40 are Korean, fewer than 10 rows
  come back (as few as 2). The fixes are an iterative scan or a larger `ef_search`.
  Qdrant applies the filter during the search (filter-aware HNSW plus the payload index on
  `cuisine`), so it returns all 10 results at the same `hnsw_ef`.
- **ANN recall is 1.0 without a filter** because 224 vectors is small for HNSW. This is
  expected and will be reported as such, not tuned away.
- **Failure case candidate (M2): L12 "cold soup for a hot summer day"** misses *Gazpacho* in
  both systems. Its description says "chilled Andalusian tomato and cucumber soup", and the
  small model does not connect "cold … summer" with "chilled" strongly enough.

## Still to do for the final hand-in

1. **One update across stores** (`grocery/update_demo.py`, to be written): change the
   ingredients of one product in PostgreSQL, for example a vegetable stock that gains celery.
   Show the stale Neo4j node, the stale `allergen_codes` in both vector stores, and the safety
   check turning red (M1 > 0). Then rerun `load_neo4j` + `load_vectors` and show it back at 0.
   Also show a cart in Redis expiring after its TTL.
2. Rerun M1–M5 after any tuning and report both runs.
3. Report (3–4 pages): role of each store, main queries, measured results, one failure case
   (L12, or the stale-metadata case from step 1).
