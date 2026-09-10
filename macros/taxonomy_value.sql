{% macro taxonomy_value(field, attribute) -%}
case when json_type(json_extract(payload, '$.{{ field }}')) = 'ARRAY'
    then (select value ->> '$.{{ attribute }}'
          from json_each(json_extract(payload, '$.{{ field }}'))
          order by coalesce(try_cast(value ->> '$.original_value' as boolean), false) desc,
                   try_cast(key as integer)
          limit 1)
    else payload ->> '$.{{ field }}.{{ attribute }}' end
{%- endmacro %}
