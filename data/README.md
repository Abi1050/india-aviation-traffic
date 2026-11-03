# Data location

The dashboard reads the original country-level file from
`aggregated/international/country.csv` (from
[Vonter/india-aviation-traffic](https://github.com/Vonter/india-aviation-traffic)).

To keep data somewhere else, set the `AVIATION_DATA_DIR` environment variable to the
folder that contains `country.csv` (and optionally `carrier.csv`, which is used only to
check that the latest quarter has all three months).

You can also upload a CSV on the **Dataset Explorer** page. Accepted layouts:

| Layout | Columns |
| --- | --- |
| Country-level | Year, Quarter, Country, PaxToIndia, PaxFromIndia, FreightToIndia, FreightFromIndia |
| Quarterly | Year, Quarter, PaxToIndia, PaxFromIndia, FreightToIndia, FreightFromIndia |
| Aggregated | Date, PaxToIndia, PaxFromIndia, FreightToIndia, FreightFromIndia |

Two-digit years (e.g. `15`) are read as 2000–2099.
