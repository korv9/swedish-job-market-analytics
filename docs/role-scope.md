# Role scope v1

The analysis covers advertised Data Engineer, Analytics Engineer and Data Scientist roles, including junior/senior and contract roles. The reproducible inclusion rules live in `seeds/role_patterns.csv` and apply to all periods.

An explicit role title or an equally specific occupation label qualifies a candidate. Broad taxonomy labels such as Database Developer and Software Developer do not qualify on their own. A matching title remains eligible across taxonomy groups, since the January 2024 pilot placed Data Engineers under multiple occupation codes. The Data/IT concept `apaJ_2ja_LuF` is retained as corroborating context rather than a mandatory filter, avoiding exclusions of statistical/scientific roles.

Management/recruitment/sales titles are excluded by dbt. A title matching more than one target role is classified using seed priority and marked ambiguous for review. Description-only mentions do not qualify. These rules define a role cohort, not the whole Swedish technology market. Vacancies, repostings and staffing-company duplicates are distinct from unique source advertisement IDs.

The archive loader retains the union of title and specific-taxonomy candidates. Full original archives stay in ignored local storage, permitting broader future rules without another download. Changes to candidate rules require reprocessing archives; changes to dbt classification require a full refresh. Raw historical IDs are scoped to the historical database and must not be equated with live JobSearch IDs without source-specific reconciliation.
