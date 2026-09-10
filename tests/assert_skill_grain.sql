select job_id, skill from {{ ref('bridge_job_skills') }}
group by 1, 2 having count(*) > 1
