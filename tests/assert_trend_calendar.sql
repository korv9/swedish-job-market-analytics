select role_family, skill
from {{ ref('mart_skill_trends_monthly') }}
group by 1, 2
having count(*) <> (select count(*) from {{ ref('int_analysis_months') }})
