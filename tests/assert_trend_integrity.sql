select publication_month, role_family, skill
from {{ ref('mart_skill_trends_monthly') }}
where ads_with_skill > total_ads or ads_with_skill < 0
    or skill_share not between 0 and 1 or unique_employers > ads_with_skill
    or (not is_complete and (ads_with_skill is not null or skill_share is not null or total_ads is not null))
