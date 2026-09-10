{{ config(materialized='incremental', unique_key='job_id', incremental_strategy='delete+insert', on_schema_change='fail') }}

select job_id, employer_id, location_id, occupation_id, title,
    published_at, last_application_date, employment_type, role_family, seniority,
    ingestion_id, ingested_at, source_kind,
    classification_basis, role_match_count, number_of_vacancies, original_id
from {{ ref('int_job_ads_enriched') }}
{% if is_incremental() %}
where ingestion_id > (select coalesce(max(ingestion_id), 0) from {{ this }})
{% endif %}
