# Architecture and data coverage

Reviewed 2026-09-10. API values and file availability can change. This document separates implemented behaviour, published source limits and proposed extensions.

## dbt structure

The project uses 13 SQL models: two staging models, two intermediate models and nine marts. Staging exposes advertisements and the ingestion coverage ledger. Entity-specific deduplication belongs in the dimensions. Intermediate models supply role classifications and a calendar; marts include monthly trends and full-year comparisons.

This is consistent with [dbt's structure guidance](https://docs.getdbt.com/best-practices/how-we-structure/1-guide-overview). Its [staging guidance](https://docs.getdbt.com/best-practices/how-we-structure/2-staging) recommends one staging model per source table and permits flat staging directories and shorter names for a single source. Additional source/domain folders would add little value at this size. The fact/dimension split supports the required employer, occupation and geographic analysis; dbt does not require dimensional modelling for every project.

Views in staging and intermediate, tables for the small dimensions, and a fact keyed by job ID are reasonable local defaults. The incremental fact avoids rewriting unchanged rows but is not currently justified by a measured performance bottleneck. Raw-history scans and full dimension/bridge rebuilds remain. Benchmark before adding further incremental models, partitioning, orchestration or infrastructure.

## Available data and limits

| Route | Available period | Volume and retrieval | Implemented here |
| --- | --- | --- | --- |
| JobSearch | Currently published ads | `limit` up to 100; `offset` up to 2,000 | Yes, bounded free-text searches |
| Historical API | Unpublished ads from 2016 onward | Same documented `limit` and `offset` bounds; publication-date filters | Used for a five-ad format pilot; not the bulk ingestion route |
| Historical files | 2006 through 2025; 2026 Q1 and Q2 listed at review | Bulk ZIP/JSONL files; catalogue describes more than 7 million ads | Yes, annual 2024 and 2025 archives |
| JobStream v2 | Current snapshot and subsequent observed changes | `/v2/snapshot`, then `/v2/stream` using `updated-after` and `updated-before`; JSON or JSONL | No |

Sources: [JobSearch specification](https://jobsearch.api.jobtechdev.se/swagger.json), [Historical API specification](https://historical.api.jobtechdev.se/swagger.json), [historical service coverage](https://data.arbetsformedlingen.se/dataservice/historiska_annonser/), [historical file catalogue](https://data.arbetsformedlingen.se/annonser/historiska/), [JobStream specification](https://jobstream.api.jobtechdev.se/swagger.json).

**Search pagination is bounded, not a daily account quota.** A live JobSearch request at `offset=2000&limit=100` returned 100 ads during verification, so this endpoint allowed retrieval through result 2,100 for a fixed query. That boundary behaviour was tested on JobSearch only. For larger populations, use bulk files or JobStream rather than assuming unlimited offsets. A total-hit count is not a promise that every hit is retrievable through a single search.

The current script deliberately permits 1–20 pages: at most **2,000 rows per query**, or **300 by default**. Three default queries therefore retrieve at most 900 rows before ID deduplication. There is no built-in retention expiry or lifetime row cap in the local raw table; storage and processing costs increase with observed changes. No daily/monthly JobSearch request quota was established from the reviewed documentation.

During verification, the API reported 43,383 current ads across the unfiltered search. Individual free-text totals were 77 for `data engineer`, 1,294 for `analytics engineer`, and 31 for `data scientist`. These changing counts overlap and reflect API search semantics, including matches beyond exact titles. They must not be summed as distinct role counts. The default three-page setting truncates the second query; `--max-pages 20` covers each of these observed result counts but does not guarantee future completeness.

## Collection cadence and history

The older [official JobStream guide](https://gitlab.com/arbetsformedlingen/job-ads/jobsearch-apis/-/blob/main/docs/GettingStartedJobStreamEN.md) states one request per minute and that removal objects disappear after 90 days. It documents older endpoints; the current v2 specification does not restate those retention/rate guarantees. Treat them as conservative operational guidance, not a verified v2 service-level guarantee. Do not use JobStream as an archive back to 2006.

Recommended operating design: a historical backfill, a current snapshot, and a stream poll every 15–60 minutes. This cadence is an engineering choice, not a provider requirement. Persist successful interval checkpoints, overlap adjacent windows, deduplicate, and preserve existing ad attributes when applying removal events. Recover missed historical coverage separately. Indefinite ongoing collection is an architectural possibility, dependent on continued API availability and local capacity; no guaranteed collection lifetime is published in the reviewed specifications.

The present implementation neither schedules runs nor handles removal events. Daily reruns of JobSearch accumulate observed payload changes but can miss ads published and removed between runs. They cannot reconstruct older ads that were never observed.

## Initial analysis window and local capacity

Implemented scope: **2024–2025**, filtered using the versioned [role rules](role-scope.md). The 2026 quarters remain an optional extension and are not part of the current report.

The [catalogue](https://data.arbetsformedlingen.se/annonser/historiska/) lists compressed JSONL ZIP sizes of about 897 MB for 2024, 797 MB for 2025, 214 MB for 2026 Q1 and 196 MB for Q2: approximately **2.10 GB combined**, before decompression and database storage. These are whole-market files, not the size of a data-role subset. Exact relevant-ad counts require applying the chosen filter.

The archive loader now streams compressed JSONL and writes candidates in batches of 500. Original ZIP files are retained with SHA-256 fingerprints. Each file is read to EOF (including ZIP CRC verification) before its year is marked complete. A failed import leaves the relevant months in loading status and the report export refuses incomplete coverage. Candidate-rule fingerprints prevent stale exports after a scope change.

Archive filenames do not perfectly match publication years: boundary spillovers are preserved and publication dates determine analytical membership. Completeness means the selected archive releases were fully processed, not universal completeness of all Swedish job advertisements. Historical and live data remain in separate databases; reconciliation and deletion-event processing are still future work. See [quality review](quality-review.md) for measured counts and validation.

Both annual ZIPs (approximately 1.69 GB compressed) have been downloaded locally. Download time depends on connection and server throughput. Subsequent runs use the cached archives; parsing and filtering each year took roughly 1.5–2 minutes on this machine during verification. This is an observed runtime, not a service-level guarantee.
