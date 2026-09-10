with candidates as (
    select j.*, r.role_family as matched_role,
        r.priority,
        count(r.role_family) over (partition by j.job_id) as role_match_count,
        regexp_matches(lower(coalesce(j.title, '')), r.title_pattern) as title_matched,
        regexp_matches(lower(coalesce(j.title, '')),
            '\b(manager|director|head of|chef|rekryterare|recruiter|sales|säljare)\b|\bdata analyst\b.{0,30}\b(with|med)\b') as excluded_role
    from {{ ref('stg_job_ads') }} j
    left join {{ ref('role_classification_patterns') }} r
        on regexp_matches(lower(coalesce(j.title, '')), r.title_pattern)
    qualify row_number() over (partition by j.job_id order by
        strpos(lower(coalesce(j.title, '')), regexp_extract(lower(coalesce(j.title, '')), r.title_pattern, 0)) nulls last,
        r.priority nulls last) = 1
)
select * exclude (matched_role, priority, title_matched, excluded_role),
    case when excluded_role then 'Other' else coalesce(matched_role, 'Other') end as role_family,
    case when excluded_role then 'excluded_title'
         when matched_role is null then 'unmatched'
         when role_match_count > 1 then 'ambiguous'
         when title_matched and occupation_field_id = 'apaJ_2ja_LuF' then 'title_and_it_taxonomy'
         when title_matched then 'title'
         else 'specific_taxonomy' end as classification_basis,
    case
        when regexp_matches(lower(coalesce(title, '')), '\b(senior|lead|principal|sr)\b') then 'senior'
        when regexp_matches(lower(coalesce(title, '')), '\b(junior|graduate|trainee|jr)\b') then 'junior'
        else 'unspecified'
    end as seniority
from candidates
