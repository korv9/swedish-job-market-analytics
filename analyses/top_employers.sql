select e.employer_name, count(*) as ads
from {{ ref('fct_job_ads') }} f
join {{ ref('dim_employers') }} e using (employer_id)
group by 1 order by ads desc, employer_name
