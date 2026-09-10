select distinct location_id, municipality_code, coalesce(municipality, 'Unknown') as municipality,
    coalesce(region, 'Unknown') as region, coalesce(country, 'Unknown') as country
from {{ ref('stg_job_ads') }}
