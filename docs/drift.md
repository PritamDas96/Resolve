# RESOLVE — Data drift

Population Stability Index (PSI) of the product-family mix each year vs the reference year **2023**, over the real CFPB complaints. Rule of thumb: <0.1 stable, 0.1-0.25 moderate, >0.25 significant.

| Year | PSI vs ref | Signal |
| --- | --- | --- |
| 2012 | 2.582 | significant |
| 2013 | 2.401 | significant |
| 2014 | 1.865 | significant |
| 2015 | 1.711 | significant |
| 2016 | 1.555 | significant |
| 2017 | 0.368 | significant |
| 2018 | 0.153 | moderate |
| 2019 | 0.093 | stable |
| 2020 | 0.094 | stable |
| 2021 | 0.022 | stable |
| 2022 | 0.004 | stable |
| 2023 | 0.000 | stable |
| 2024 | 0.047 | stable |
| 2025 | 0.051 | stable |
| 2026 | 0.063 | stable |

## Finding

Years with significant family-mix drift vs 2023: 2012, 2013, 2014, 2015, 2016, 2017. The family mix shifts markedly across the 2017 and ~2023 CFPB taxonomy revisions, which is why routing is evaluated on a temporal split and the router should be re-benchmarked per year (frozen-router F1 is the natural next metric).
