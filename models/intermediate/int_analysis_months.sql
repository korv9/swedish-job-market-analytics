-- Calendar rows remain present when ingestion coverage is missing.
select month::date as publication_month
from generate_series(
    '{{ var("analysis_start", "2024-01-01") }}'::date,
    '{{ var("analysis_end", "2025-12-01") }}'::date,
    interval '1 month'
) as months(month)
