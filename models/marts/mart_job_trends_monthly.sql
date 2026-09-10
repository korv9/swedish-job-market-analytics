with counts as (
    select date_trunc('month', f.published_at)::date as publication_month,
        f.role_family, count(*) as observed_ads,
        count(distinct case when e.employer_name <> 'Unknown' then f.employer_id end) as observed_employers
    from {{ ref('fct_job_ads') }} f
    join {{ ref('dim_employers') }} e using (employer_id)
    where f.role_family <> 'Other'
    group by 1, 2
), grid as (
    select m.publication_month, r.role_family,
        coalesce(c.status = 'complete', false) as is_complete,
        coalesce(n.observed_ads, 0) as observed_ads,
        case when c.status = 'complete' then coalesce(n.observed_ads, 0) end as total_ads,
        case when c.status = 'complete' then coalesce(n.observed_employers, 0) end as unique_employers
    from {{ ref('int_analysis_months') }} m
    cross join {{ ref('role_patterns') }} r
    left join {{ ref('stg_collection_coverage') }} c using (publication_month)
    left join counts n on n.publication_month=m.publication_month and n.role_family=r.role_family
), previous as (
    select *,
        lag(total_ads) over w as previous_month_ads,
        lag(total_ads, 12) over w as previous_year_ads,
        case when count(total_ads) over w3 = 3 then avg(total_ads) over w3 end as ads_3m_average
    from grid
    window w as (partition by role_family order by publication_month),
        w3 as (partition by role_family order by publication_month rows between 2 preceding and current row)
)
select *,
    total_ads - previous_month_ads as ads_mom_change,
    total_ads::double / nullif(previous_month_ads, 0) - 1 as ads_mom_pct,
    total_ads - previous_year_ads as ads_yoy_change,
    total_ads::double / nullif(previous_year_ads, 0) - 1 as ads_yoy_pct
from previous
