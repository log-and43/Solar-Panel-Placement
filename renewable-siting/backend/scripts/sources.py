"""
All external data source URLs in one place.

If a URL stops working (and they will, eventually), this is the only file
you should need to edit. Each entry includes:
  - the URL we use
  - a short description
  - where on the source's site to look if the URL has moved
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    description: str
    where_to_find_if_broken: str


# ---- Census population (Vintage 2023 estimates) ----

CENSUS_STATE_POP = Source(
    name="census_state_pop",
    url="https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/state/totals/NST-EST2023-ALLDATA.csv",
    description="State population estimates, Vintage 2023.",
    where_to_find_if_broken=(
        "https://www.census.gov/programs-surveys/popest.html → "
        "Datasets → State Population Totals → latest vintage CSV"
    ),
)

CENSUS_COUNTY_POP = Source(
    name="census_county_pop",
    url="https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/counties/totals/co-est2023-alldata.csv",
    description="County population estimates, Vintage 2023.",
    where_to_find_if_broken=(
        "https://www.census.gov/programs-surveys/popest.html → "
        "Datasets → County Population Totals → latest vintage CSV"
    ),
)

CENSUS_PLACE_POP = Source(
    name="census_place_pop",
    url="https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/cities/totals/sub-est2023.csv",
    description="Subcounty (incorporated place) population estimates, Vintage 2023.",
    where_to_find_if_broken=(
        "https://www.census.gov/programs-surveys/popest.html → "
        "Datasets → City and Town Population Totals → latest vintage CSV"
    ),
)


# ---- Census TIGER gazetteer (centroids) ----

CENSUS_GAZ_COUNTIES = Source(
    name="census_gaz_counties",
    url="https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_counties_national.zip",
    description="2023 county gazetteer with centroid lat/lon.",
    where_to_find_if_broken=(
        "https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html"
    ),
)

CENSUS_GAZ_PLACES = Source(
    name="census_gaz_places",
    url="https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_place_national.zip",
    description="2023 incorporated-place gazetteer with centroid lat/lon.",
    where_to_find_if_broken=(
        "https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html"
    ),
)


# ---- EPA eGRID 2022 (state generation mix) ----

EPA_EGRID = Source(
    name="epa_egrid",
    url="https://www.epa.gov/system/files/documents/2024-01/egrid2022_data.xlsx",
    description="EPA eGRID 2022 data file (state mix in sheet 'ST22').",
    where_to_find_if_broken=(
        "https://www.epa.gov/egrid/download-data → most recent year → "
        "'eGRIDYYYY Data File' (Excel)"
    ),
)


# ---- EIA SEDS (state electricity consumption) ----

EIA_SEDS_USE = Source(
    name="eia_seds_use",
    url="https://www.eia.gov/state/seds/sep_use/total/csv/use_all_btu.csv",
    description="State energy consumption all sectors, in billion BTU.",
    where_to_find_if_broken=(
        "https://www.eia.gov/state/seds/seds-data-complete.php → "
        "'Consumption: all-sectors, all-energy-sources' CSV"
    ),
)


ALL_SOURCES: tuple[Source, ...] = (
    CENSUS_STATE_POP,
    CENSUS_COUNTY_POP,
    CENSUS_PLACE_POP,
    CENSUS_GAZ_COUNTIES,
    CENSUS_GAZ_PLACES,
    EPA_EGRID,
    EIA_SEDS_USE,
)
