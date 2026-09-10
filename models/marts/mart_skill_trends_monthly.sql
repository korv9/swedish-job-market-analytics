with counts as (
    select date_trunc('month', f.published_at)::date as publication_month,
        f.role_family, s.skill, count(distinct f.job_id) as observed_skill_ads,
        count(distinct case when e.employer_name <> 'Unknown' then f.employer_id end) as observed_skill_employers
    from {{ ref('fct_job_ads') }} f
    join {{ ref('bridge_job_skills') }} s using (job_id)
    join {{ ref('dim_employers') }} e using (employer_id)
    where f.role_family <> 'Other'
    group by 1, 2, 3
), grid as (
    select j.publication_month, j.role_family, s.skill, j.is_complete, j.total_ads,
        case when j.is_complete then coalesce(n.observed_skill_ads, 0) end as ads_with_skill,
        case when j.is_complete then coalesce(n.observed_skill_employers, 0) end as unique_employers
    from {{ ref('mart_job_trends_monthly') }} j
    cross join {{ ref('technology_patterns') }} s
    left join counts n on n.publication_month=j.publication_month
        and n.role_family=j.role_family and n.skill=s.skill
), shares as (
    select *, ads_with_skill::double / nullif(total_ads, 0) as skill_share
    from grid
), previous as (
    select *, lag(ads_with_skill) over w as previous_month_skill_ads,
        lag(ads_with_skill, 12) over w as previous_year_skill_ads,
        lag(skill_share) over w as previous_month_share,
        lag(skill_share, 12) over w as previous_year_share,
        case when count(ads_with_skill) over w3 = 3
            then sum(ads_with_skill) over w3 / nullif(sum(total_ads) over w3, 0) end as skill_share_3m,
        case when total_ads >= {{ var('minimum_cohort_ads', 20) }} and ads_with_skill >= 5
            then true else false end as sufficient_volume
    from shares
    window w as (partition by role_family, skill order by publication_month),
        w3 as (partition by role_family, skill order by publication_month rows between 2 preceding and current row)
)
select *,
    ads_with_skill::double / nullif(previous_month_skill_ads, 0) - 1 as skill_ads_mom_pct,
    ads_with_skill::double / nullif(previous_year_skill_ads, 0) - 1 as skill_ads_yoy_pct,
    100 * (skill_share - previous_month_share) as share_mom_pp,
    100 * (skill_share - previous_year_share) as share_yoy_pp
from previous
