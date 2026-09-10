select occupation_id, occupation_code, coalesce(occupation, 'Unknown') as occupation
from {{ ref('stg_job_ads') }}
qualify row_number() over (partition by occupation_id order by ingestion_id desc, job_id) = 1
