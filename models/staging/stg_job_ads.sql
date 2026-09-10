with identified as (
    select * exclude (job_id), job_id as source_record_id,
        case when source_kind = 'historical' and nullif(trim(payload ->> '$.original_id'), '') is not null
            then 'historical-original:' || trim(payload ->> '$.original_id')
            else job_id end as job_id
    from {{ source('jobtech', 'job_ads') }}
), latest as (
    select * from identified
    qualify row_number() over (partition by job_id order by ingestion_id desc) = 1
), cleaned as (
    select
        job_id, source_record_id,
        {{ clean_string("payload ->> '$.headline'") }} as title,
        {{ clean_string("payload ->> '$.employer.organization_number'") }} as organization_number,
        {{ clean_string("payload ->> '$.employer.name'") }} as employer_name,
        {{ clean_string("payload ->> '$.workplace_address.municipality_code'") }} as municipality_code,
        {{ clean_string("payload ->> '$.workplace_address.municipality'") }} as municipality,
        {{ clean_string("payload ->> '$.workplace_address.region'") }} as region,
        {{ clean_string("payload ->> '$.workplace_address.country'") }} as country,
        {{ clean_string(taxonomy_value('occupation', 'concept_id')) }} as occupation_code,
        {{ clean_string(taxonomy_value('occupation', 'label')) }} as occupation,
        {{ clean_string(taxonomy_value('occupation_field', 'concept_id')) }} as occupation_field_id,
        {{ clean_string("payload ->> '$.original_id'") }} as original_id,
        try_cast(payload ->> '$.number_of_vacancies' as integer) as number_of_vacancies,
        try_cast(payload ->> '$.publication_date' as timestamp) as published_at,
        try_cast(payload ->> '$.application_deadline' as timestamp) as last_application_date,
        {{ clean_string(taxonomy_value('employment_type', 'label')) }} as employment_type,
        coalesce(payload ->> '$.description.text', '') as description,
        coalesce(json_extract(payload, '$.must_have.skills'), '[]'::json) as required_skills,
        ingestion_id, ingested_at, source_kind
    from latest
)
select *,
    md5(coalesce('org:' || organization_number, 'name:' || lower(employer_name), 'unknown')) as employer_id,
    md5(to_json(list_value(country, municipality_code, municipality, region))) as location_id,
    md5(coalesce('code:' || occupation_code, 'label:' || lower(occupation), 'unknown')) as occupation_id
from cleaned
