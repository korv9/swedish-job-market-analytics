# Job market report

Open `JobMarket.pbip` in a current Power BI Desktop release with Power BI Project/PBIR support. The report contains a role slicer and three visuals: monthly advertisement counts, monthly technology shares and the 2025-versus-2024 share change in percentage points.

Before opening, create the data and project files:

```powershell
python scripts/run_history_pipeline.py
```

The generator sets the semantic model's `DataFolder` parameter to this checkout's absolute `data/powerbi` path. After moving the repository, regenerate with `python scripts/build_powerbi.py` or change `DataFolder` under Transform data → Manage parameters. Refresh in Power BI Desktop to load the CSVs; no database driver or cloud account is needed. Raw advertisement texts and contact details are not exported into this report.

`JobMarket.SemanticModel/model.bim` contains the import model and DAX measures. Roles filter all three fact-like aggregate tables; Months filters the two monthly tables. The annual comparison intentionally uses the complete fixed years 2024 and 2025. Technology shares are recomputed from numerator/denominator totals rather than averaging percentages. Do not sum the Skills table's repeated denominator across technologies. The measures return blank when a single technology is not in context.

The annual change measure suppresses results with fewer than 20 cohort ads in either year or fewer than five mentions in both years. This is a display threshold, not a significance test. Source advertisement IDs are counted, including potential repostings. Select a single role when comparing within-role technology shifts; combining roles can change shares through changes in role mix.

Validation: `python scripts/validate_powerbi.py` checks PBIR against Microsoft's published JSON schemas and validates field/relationship references. This requires network access on the first run and caches schemas locally. Schema checks do not execute Power Query/DAX or verify rendering in Power BI Desktop. The generated project must be refreshed in Desktop to confirm runtime compatibility.

An independently rendered preview of the same exported data is available at `reports/generated/trends.html`, including all-role and individual-role views. It is not a screenshot of Power BI Desktop.

References: [Power BI projects](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview), [editable PBIR report definitions](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report), [semantic model files](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset).
