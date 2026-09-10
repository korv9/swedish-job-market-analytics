with annual as (
    select year(publication_month) as publication_year, role_family, skill,
        count(*) filter (where is_complete) as complete_months,
        sum(ads_with_skill) as skill_ads, sum(total_ads) as total_ads
    from {{ ref('mart_skill_trends_monthly') }}
    group by 1, 2, 3
)
select a.role_family, a.skill,
    {{ var('baseline_year', 2024) }} as baseline_year,
    {{ var('comparison_year', 2025) }} as comparison_year,
    a.complete_months = 12 and b.complete_months = 12 as is_complete,
    case when a.complete_months = 12 then a.skill_ads end as baseline_skill_ads,
    case when a.complete_months = 12 then a.total_ads end as baseline_total_ads,
    case when b.complete_months = 12 then b.skill_ads end as comparison_skill_ads,
    case when b.complete_months = 12 then b.total_ads end as comparison_total_ads,
    case when a.complete_months = 12 and b.complete_months = 12 then
        100 * (b.skill_ads / nullif(b.total_ads, 0) - a.skill_ads / nullif(a.total_ads, 0))
    end as share_change_pp
from annual a
left join annual b on a.role_family=b.role_family and a.skill=b.skill
    and b.publication_year={{ var('comparison_year', 2025) }}
where a.publication_year={{ var('baseline_year', 2024) }}
