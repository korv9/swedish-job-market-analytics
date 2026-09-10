{% macro clean_string(expression) -%}
nullif(trim({{ expression }}), '')
{%- endmacro %}
