select publication_month, role_family, skill
from {{ ref('mart_skill_trends_monthly') }}
group by 1, 2, 3 having count(*) <> 1
