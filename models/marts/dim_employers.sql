select employer_id, organization_number, coalesce(employer_name, 'Unknown') as employer_name
from {{ ref('stg_job_ads') }}
qualify row_number() over (partition by employer_id order by ingestion_id desc, job_id) = 1
