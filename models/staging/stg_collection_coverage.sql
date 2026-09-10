select publication_month, source_uri, source_sha256, source_rows, candidate_rows,
    completed_at, status, scope_version
from {{ source('jobtech', 'collection_coverage') }}
