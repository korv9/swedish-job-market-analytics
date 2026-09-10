select date_trunc('month', f.published_at)::date as publication_month,
    f.role_family, l.region, f.seniority, count(*) as job_count
from {{ ref('fct_job_ads') }} f
left join {{ ref('dim_locations') }} l using (location_id)
group by 1, 2, 3, 4
