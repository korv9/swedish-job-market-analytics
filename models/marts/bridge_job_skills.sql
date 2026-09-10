-- Mention detection, not proof that a skill is required.
select distinct j.job_id, s.skill
from {{ ref('int_job_ads_enriched') }} j
cross join {{ ref('technology_patterns') }} s
where regexp_matches(lower(coalesce(j.title, '') || ' ' || j.description || ' ' || cast(j.required_skills as varchar)), s.pattern)
