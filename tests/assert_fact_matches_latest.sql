-- Catch missed updates as well as missing/extra facts after an incremental build.
select coalesce(f.job_id, s.job_id) as job_id
from {{ ref('fct_job_ads') }} f
full outer join {{ ref('stg_job_ads') }} s using (job_id)
where f.job_id is null or s.job_id is null or f.ingestion_id <> s.ingestion_id
