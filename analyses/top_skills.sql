select skill, count(*) as ads_mentioning_skill
from {{ ref('bridge_job_skills') }}
group by skill order by ads_mentioning_skill desc, skill
