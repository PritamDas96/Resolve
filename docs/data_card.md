# RESOLVE — Data card

Provenance, filters, counts and known limitations for the data foundation. All personal data is synthetic; no real customer or client data is used. Regenerate with `make data-card`.

## Sources

- **CFPB Consumer Complaint Database** (public search API, CSV export). Metadata only — CFPB no longer distributes narrative text. Retrieved 2026-10-03T21:10:30.075227+00:00.
- **eCFR** point-in-time regulation snapshots (Title 12 parts, plus Supplement I).
- **Bank documents** (public deposit agreements and fee schedules): 0 document(s) ingested. PDFs and extracted text are never committed — only the manifest.
- **Synthetic accounts, transactions and disputes** — generated locally, fully seeded; no real customer data is ever used.

## Filters

- Six banks (JPMorgan Chase, Bank of America, Wells Fargo, Citi, Capital One, U.S. Bank).
- Complaints that originally had a consumer narrative (`has_narrative=true`).
- Four in-scope, regulation-aligned product families (deposits, cards, mortgage, credit reporting as furnisher); all other products are out of scope.
- Deduplicated on `complaint_id`.

## Counts

- **Total in-scope complaints:** 787,717
- **UNMAPPED** (product outside the four families; excluded from routing metrics, never silently dropped): 0

### By bank

| Bank | Complaints |
| --- | --- |
| Bank of America | 168,586 |
| Capital One | 146,705 |
| Citi | 125,494 |
| JPMorgan Chase | 153,299 |
| U.S. Bank | 45,003 |
| Wells Fargo | 148,630 |

### By bank x year x product family

| Bank | Year | Family | Count |
| --- | --- | --- | --- |
| Bank of America | 2012 | cards | 2,081 |
| Bank of America | 2012 | credit_reporting | 9 |
| Bank of America | 2012 | deposits | 2,031 |
| Bank of America | 2012 | mortgage | 11,742 |
| Bank of America | 2013 | cards | 1,498 |
| Bank of America | 2013 | credit_reporting | 12 |
| Bank of America | 2013 | deposits | 2,191 |
| Bank of America | 2013 | mortgage | 12,404 |
| Bank of America | 2014 | cards | 1,345 |
| Bank of America | 2014 | credit_reporting | 9 |
| Bank of America | 2014 | deposits | 2,427 |
| Bank of America | 2014 | mortgage | 5,819 |
| Bank of America | 2015 | cards | 1,662 |
| Bank of America | 2015 | credit_reporting | 7 |
| Bank of America | 2015 | deposits | 2,924 |
| Bank of America | 2015 | mortgage | 4,584 |
| Bank of America | 2016 | cards | 1,809 |
| Bank of America | 2016 | deposits | 3,243 |
| Bank of America | 2016 | mortgage | 3,988 |
| Bank of America | 2017 | cards | 1,815 |
| Bank of America | 2017 | credit_reporting | 577 |
| Bank of America | 2017 | deposits | 3,281 |
| Bank of America | 2017 | mortgage | 2,347 |
| Bank of America | 2018 | cards | 1,885 |
| Bank of America | 2018 | credit_reporting | 776 |
| Bank of America | 2018 | deposits | 3,422 |
| Bank of America | 2018 | mortgage | 1,359 |
| Bank of America | 2019 | cards | 1,886 |
| Bank of America | 2019 | credit_reporting | 649 |
| Bank of America | 2019 | deposits | 3,320 |
| Bank of America | 2019 | mortgage | 890 |
| Bank of America | 2020 | cards | 2,689 |
| Bank of America | 2020 | credit_reporting | 1,062 |
| Bank of America | 2020 | deposits | 3,501 |
| Bank of America | 2020 | mortgage | 1,181 |
| Bank of America | 2021 | cards | 3,164 |
| Bank of America | 2021 | credit_reporting | 1,649 |
| Bank of America | 2021 | deposits | 4,147 |
| Bank of America | 2021 | mortgage | 971 |
| Bank of America | 2022 | cards | 3,456 |
| Bank of America | 2022 | credit_reporting | 1,865 |
| Bank of America | 2022 | deposits | 5,227 |
| Bank of America | 2022 | mortgage | 777 |
| Bank of America | 2023 | cards | 3,867 |
| Bank of America | 2023 | credit_reporting | 2,230 |
| Bank of America | 2023 | deposits | 6,131 |
| Bank of America | 2023 | mortgage | 527 |
| Bank of America | 2024 | cards | 3,890 |
| Bank of America | 2024 | credit_reporting | 3,191 |
| Bank of America | 2024 | deposits | 4,996 |
| Bank of America | 2024 | mortgage | 500 |
| Bank of America | 2025 | cards | 4,512 |
| Bank of America | 2025 | credit_reporting | 4,220 |
| Bank of America | 2025 | deposits | 6,680 |
| Bank of America | 2025 | mortgage | 534 |
| Bank of America | 2026 | cards | 4,949 |
| Bank of America | 2026 | credit_reporting | 3,423 |
| Bank of America | 2026 | deposits | 6,804 |
| Bank of America | 2026 | mortgage | 451 |
| Capital One | 2012 | cards | 3,061 |
| Capital One | 2012 | credit_reporting | 9 |
| Capital One | 2012 | deposits | 440 |
| Capital One | 2012 | mortgage | 205 |
| Capital One | 2013 | cards | 2,222 |
| Capital One | 2013 | credit_reporting | 75 |
| Capital One | 2013 | deposits | 429 |
| Capital One | 2013 | mortgage | 203 |
| Capital One | 2014 | cards | 1,923 |
| Capital One | 2014 | credit_reporting | 55 |
| Capital One | 2014 | deposits | 370 |
| Capital One | 2014 | mortgage | 171 |
| Capital One | 2015 | cards | 2,173 |
| Capital One | 2015 | credit_reporting | 32 |
| Capital One | 2015 | deposits | 448 |
| Capital One | 2015 | mortgage | 180 |
| Capital One | 2016 | cards | 2,474 |
| Capital One | 2016 | credit_reporting | 29 |
| Capital One | 2016 | deposits | 570 |
| Capital One | 2016 | mortgage | 187 |
| Capital One | 2017 | cards | 2,815 |
| Capital One | 2017 | credit_reporting | 1,157 |
| Capital One | 2017 | deposits | 596 |
| Capital One | 2017 | mortgage | 152 |
| Capital One | 2018 | cards | 3,322 |
| Capital One | 2018 | credit_reporting | 1,994 |
| Capital One | 2018 | deposits | 966 |
| Capital One | 2018 | mortgage | 83 |
| Capital One | 2019 | cards | 3,665 |
| Capital One | 2019 | credit_reporting | 1,937 |
| Capital One | 2019 | deposits | 784 |
| Capital One | 2019 | mortgage | 26 |
| Capital One | 2020 | cards | 4,542 |
| Capital One | 2020 | credit_reporting | 2,843 |
| Capital One | 2020 | deposits | 904 |
| Capital One | 2020 | mortgage | 5 |
| Capital One | 2021 | cards | 4,230 |
| Capital One | 2021 | credit_reporting | 4,472 |
| Capital One | 2021 | deposits | 1,328 |
| Capital One | 2021 | mortgage | 2 |
| Capital One | 2022 | cards | 4,975 |
| Capital One | 2022 | credit_reporting | 5,322 |
| Capital One | 2022 | deposits | 1,389 |
| Capital One | 2022 | mortgage | 6 |
| Capital One | 2023 | cards | 6,203 |
| Capital One | 2023 | credit_reporting | 7,313 |
| Capital One | 2023 | deposits | 1,849 |
| Capital One | 2023 | mortgage | 1 |
| Capital One | 2024 | cards | 7,067 |
| Capital One | 2024 | credit_reporting | 8,714 |
| Capital One | 2024 | deposits | 2,064 |
| Capital One | 2024 | mortgage | 4 |
| Capital One | 2025 | cards | 9,948 |
| Capital One | 2025 | credit_reporting | 11,131 |
| Capital One | 2025 | deposits | 7,912 |
| Capital One | 2025 | mortgage | 7 |
| Capital One | 2026 | cards | 10,511 |
| Capital One | 2026 | credit_reporting | 8,041 |
| Capital One | 2026 | deposits | 3,163 |
| Capital One | 2026 | mortgage | 6 |
| Citi | 2012 | cards | 2,979 |
| Citi | 2012 | credit_reporting | 6 |
| Citi | 2012 | deposits | 356 |
| Citi | 2012 | mortgage | 1,769 |
| Citi | 2013 | cards | 2,526 |
| Citi | 2013 | credit_reporting | 54 |
| Citi | 2013 | deposits | 408 |
| Citi | 2013 | mortgage | 2,391 |
| Citi | 2014 | cards | 2,425 |
| Citi | 2014 | credit_reporting | 40 |
| Citi | 2014 | deposits | 494 |
| Citi | 2014 | mortgage | 1,647 |
| Citi | 2015 | cards | 3,064 |
| Citi | 2015 | credit_reporting | 33 |
| Citi | 2015 | deposits | 597 |
| Citi | 2015 | mortgage | 1,387 |
| Citi | 2016 | cards | 4,496 |
| Citi | 2016 | credit_reporting | 21 |
| Citi | 2016 | deposits | 2,090 |
| Citi | 2016 | mortgage | 1,154 |
| Citi | 2017 | cards | 3,665 |
| Citi | 2017 | credit_reporting | 820 |
| Citi | 2017 | deposits | 1,036 |
| Citi | 2017 | mortgage | 831 |
| Citi | 2018 | cards | 3,636 |
| Citi | 2018 | credit_reporting | 1,112 |
| Citi | 2018 | deposits | 1,229 |
| Citi | 2018 | mortgage | 415 |
| Citi | 2019 | cards | 3,783 |
| Citi | 2019 | credit_reporting | 1,035 |
| Citi | 2019 | deposits | 1,223 |
| Citi | 2019 | mortgage | 208 |
| Citi | 2020 | cards | 4,919 |
| Citi | 2020 | credit_reporting | 1,398 |
| Citi | 2020 | deposits | 1,437 |
| Citi | 2020 | mortgage | 126 |
| Citi | 2021 | cards | 3,793 |
| Citi | 2021 | credit_reporting | 1,957 |
| Citi | 2021 | deposits | 2,178 |
| Citi | 2021 | mortgage | 181 |
| Citi | 2022 | cards | 3,632 |
| Citi | 2022 | credit_reporting | 1,688 |
| Citi | 2022 | deposits | 2,394 |
| Citi | 2022 | mortgage | 63 |
| Citi | 2023 | cards | 4,710 |
| Citi | 2023 | credit_reporting | 1,855 |
| Citi | 2023 | deposits | 2,376 |
| Citi | 2023 | mortgage | 41 |
| Citi | 2024 | cards | 6,702 |
| Citi | 2024 | credit_reporting | 3,590 |
| Citi | 2024 | deposits | 2,935 |
| Citi | 2024 | mortgage | 50 |
| Citi | 2025 | cards | 8,651 |
| Citi | 2025 | credit_reporting | 4,961 |
| Citi | 2025 | deposits | 3,458 |
| Citi | 2025 | mortgage | 43 |
| Citi | 2026 | cards | 9,247 |
| Citi | 2026 | credit_reporting | 3,354 |
| Citi | 2026 | deposits | 2,779 |
| Citi | 2026 | mortgage | 46 |
| JPMorgan Chase | 2012 | cards | 1,950 |
| JPMorgan Chase | 2012 | credit_reporting | 4 |
| JPMorgan Chase | 2012 | deposits | 1,318 |
| JPMorgan Chase | 2012 | mortgage | 3,706 |
| JPMorgan Chase | 2013 | cards | 1,497 |
| JPMorgan Chase | 2013 | credit_reporting | 5 |
| JPMorgan Chase | 2013 | deposits | 1,418 |
| JPMorgan Chase | 2013 | mortgage | 4,560 |
| JPMorgan Chase | 2014 | cards | 1,596 |
| JPMorgan Chase | 2014 | credit_reporting | 29 |
| JPMorgan Chase | 2014 | deposits | 1,666 |
| JPMorgan Chase | 2014 | mortgage | 3,472 |
| JPMorgan Chase | 2015 | cards | 1,917 |
| JPMorgan Chase | 2015 | credit_reporting | 25 |
| JPMorgan Chase | 2015 | deposits | 2,006 |
| JPMorgan Chase | 2015 | mortgage | 3,144 |
| JPMorgan Chase | 2016 | cards | 2,484 |
| JPMorgan Chase | 2016 | credit_reporting | 26 |
| JPMorgan Chase | 2016 | deposits | 2,580 |
| JPMorgan Chase | 2016 | mortgage | 2,707 |
| JPMorgan Chase | 2017 | cards | 2,514 |
| JPMorgan Chase | 2017 | credit_reporting | 722 |
| JPMorgan Chase | 2017 | deposits | 2,599 |
| JPMorgan Chase | 2017 | mortgage | 1,681 |
| JPMorgan Chase | 2018 | cards | 2,644 |
| JPMorgan Chase | 2018 | credit_reporting | 1,077 |
| JPMorgan Chase | 2018 | deposits | 2,985 |
| JPMorgan Chase | 2018 | mortgage | 1,230 |
| JPMorgan Chase | 2019 | cards | 2,415 |
| JPMorgan Chase | 2019 | credit_reporting | 897 |
| JPMorgan Chase | 2019 | deposits | 3,049 |
| JPMorgan Chase | 2019 | mortgage | 940 |
| JPMorgan Chase | 2020 | cards | 3,038 |
| JPMorgan Chase | 2020 | credit_reporting | 1,148 |
| JPMorgan Chase | 2020 | deposits | 3,169 |
| JPMorgan Chase | 2020 | mortgage | 851 |
| JPMorgan Chase | 2021 | cards | 2,881 |
| JPMorgan Chase | 2021 | credit_reporting | 1,799 |
| JPMorgan Chase | 2021 | deposits | 3,558 |
| JPMorgan Chase | 2021 | mortgage | 719 |
| JPMorgan Chase | 2022 | cards | 3,143 |
| JPMorgan Chase | 2022 | credit_reporting | 1,958 |
| JPMorgan Chase | 2022 | deposits | 4,466 |
| JPMorgan Chase | 2022 | mortgage | 608 |
| JPMorgan Chase | 2023 | cards | 4,446 |
| JPMorgan Chase | 2023 | credit_reporting | 2,707 |
| JPMorgan Chase | 2023 | deposits | 6,135 |
| JPMorgan Chase | 2023 | mortgage | 410 |
| JPMorgan Chase | 2024 | cards | 5,292 |
| JPMorgan Chase | 2024 | credit_reporting | 3,994 |
| JPMorgan Chase | 2024 | deposits | 7,036 |
| JPMorgan Chase | 2024 | mortgage | 485 |
| JPMorgan Chase | 2025 | cards | 5,976 |
| JPMorgan Chase | 2025 | credit_reporting | 4,722 |
| JPMorgan Chase | 2025 | deposits | 8,937 |
| JPMorgan Chase | 2025 | mortgage | 549 |
| JPMorgan Chase | 2026 | cards | 5,400 |
| JPMorgan Chase | 2026 | credit_reporting | 3,413 |
| JPMorgan Chase | 2026 | deposits | 7,043 |
| JPMorgan Chase | 2026 | mortgage | 553 |
| U.S. Bank | 2012 | cards | 308 |
| U.S. Bank | 2012 | credit_reporting | 3 |
| U.S. Bank | 2012 | deposits | 478 |
| U.S. Bank | 2012 | mortgage | 639 |
| U.S. Bank | 2013 | cards | 330 |
| U.S. Bank | 2013 | credit_reporting | 11 |
| U.S. Bank | 2013 | deposits | 619 |
| U.S. Bank | 2013 | mortgage | 902 |
| U.S. Bank | 2014 | cards | 406 |
| U.S. Bank | 2014 | credit_reporting | 10 |
| U.S. Bank | 2014 | deposits | 716 |
| U.S. Bank | 2014 | mortgage | 1,108 |
| U.S. Bank | 2015 | cards | 771 |
| U.S. Bank | 2015 | credit_reporting | 5 |
| U.S. Bank | 2015 | deposits | 750 |
| U.S. Bank | 2015 | mortgage | 897 |
| U.S. Bank | 2016 | cards | 669 |
| U.S. Bank | 2016 | credit_reporting | 5 |
| U.S. Bank | 2016 | deposits | 891 |
| U.S. Bank | 2016 | mortgage | 770 |
| U.S. Bank | 2017 | cards | 730 |
| U.S. Bank | 2017 | credit_reporting | 174 |
| U.S. Bank | 2017 | deposits | 756 |
| U.S. Bank | 2017 | mortgage | 575 |
| U.S. Bank | 2018 | cards | 626 |
| U.S. Bank | 2018 | credit_reporting | 238 |
| U.S. Bank | 2018 | deposits | 731 |
| U.S. Bank | 2018 | mortgage | 496 |
| U.S. Bank | 2019 | cards | 683 |
| U.S. Bank | 2019 | credit_reporting | 253 |
| U.S. Bank | 2019 | deposits | 789 |
| U.S. Bank | 2019 | mortgage | 441 |
| U.S. Bank | 2020 | cards | 2,013 |
| U.S. Bank | 2020 | credit_reporting | 354 |
| U.S. Bank | 2020 | deposits | 921 |
| U.S. Bank | 2020 | mortgage | 481 |
| U.S. Bank | 2021 | cards | 1,432 |
| U.S. Bank | 2021 | credit_reporting | 484 |
| U.S. Bank | 2021 | deposits | 976 |
| U.S. Bank | 2021 | mortgage | 498 |
| U.S. Bank | 2022 | cards | 1,034 |
| U.S. Bank | 2022 | credit_reporting | 567 |
| U.S. Bank | 2022 | deposits | 1,187 |
| U.S. Bank | 2022 | mortgage | 559 |
| U.S. Bank | 2023 | cards | 1,151 |
| U.S. Bank | 2023 | credit_reporting | 669 |
| U.S. Bank | 2023 | deposits | 1,625 |
| U.S. Bank | 2023 | mortgage | 378 |
| U.S. Bank | 2024 | cards | 1,502 |
| U.S. Bank | 2024 | credit_reporting | 881 |
| U.S. Bank | 2024 | deposits | 1,408 |
| U.S. Bank | 2024 | mortgage | 378 |
| U.S. Bank | 2025 | cards | 1,737 |
| U.S. Bank | 2025 | credit_reporting | 999 |
| U.S. Bank | 2025 | deposits | 1,886 |
| U.S. Bank | 2025 | mortgage | 399 |
| U.S. Bank | 2026 | cards | 1,647 |
| U.S. Bank | 2026 | credit_reporting | 707 |
| U.S. Bank | 2026 | deposits | 1,860 |
| U.S. Bank | 2026 | mortgage | 490 |
| Wells Fargo | 2012 | cards | 662 |
| Wells Fargo | 2012 | credit_reporting | 5 |
| Wells Fargo | 2012 | deposits | 2,266 |
| Wells Fargo | 2012 | mortgage | 5,906 |
| Wells Fargo | 2013 | cards | 632 |
| Wells Fargo | 2013 | credit_reporting | 38 |
| Wells Fargo | 2013 | deposits | 2,391 |
| Wells Fargo | 2013 | mortgage | 7,310 |
| Wells Fargo | 2014 | cards | 680 |
| Wells Fargo | 2014 | credit_reporting | 22 |
| Wells Fargo | 2014 | deposits | 2,363 |
| Wells Fargo | 2014 | mortgage | 4,967 |
| Wells Fargo | 2015 | cards | 716 |
| Wells Fargo | 2015 | credit_reporting | 22 |
| Wells Fargo | 2015 | deposits | 2,329 |
| Wells Fargo | 2015 | mortgage | 5,100 |
| Wells Fargo | 2016 | cards | 1,036 |
| Wells Fargo | 2016 | credit_reporting | 20 |
| Wells Fargo | 2016 | deposits | 3,064 |
| Wells Fargo | 2016 | mortgage | 5,650 |
| Wells Fargo | 2017 | cards | 978 |
| Wells Fargo | 2017 | credit_reporting | 550 |
| Wells Fargo | 2017 | deposits | 2,503 |
| Wells Fargo | 2017 | mortgage | 3,633 |
| Wells Fargo | 2018 | cards | 963 |
| Wells Fargo | 2018 | credit_reporting | 856 |
| Wells Fargo | 2018 | deposits | 2,467 |
| Wells Fargo | 2018 | mortgage | 3,040 |
| Wells Fargo | 2019 | cards | 930 |
| Wells Fargo | 2019 | credit_reporting | 840 |
| Wells Fargo | 2019 | deposits | 2,437 |
| Wells Fargo | 2019 | mortgage | 2,065 |
| Wells Fargo | 2020 | cards | 942 |
| Wells Fargo | 2020 | credit_reporting | 1,177 |
| Wells Fargo | 2020 | deposits | 2,294 |
| Wells Fargo | 2020 | mortgage | 1,852 |
| Wells Fargo | 2021 | cards | 901 |
| Wells Fargo | 2021 | credit_reporting | 1,625 |
| Wells Fargo | 2021 | deposits | 3,083 |
| Wells Fargo | 2021 | mortgage | 1,599 |
| Wells Fargo | 2022 | cards | 1,151 |
| Wells Fargo | 2022 | credit_reporting | 1,672 |
| Wells Fargo | 2022 | deposits | 4,552 |
| Wells Fargo | 2022 | mortgage | 1,394 |
| Wells Fargo | 2023 | cards | 2,019 |
| Wells Fargo | 2023 | credit_reporting | 1,953 |
| Wells Fargo | 2023 | deposits | 9,917 |
| Wells Fargo | 2023 | mortgage | 3,456 |
| Wells Fargo | 2024 | cards | 2,155 |
| Wells Fargo | 2024 | credit_reporting | 2,592 |
| Wells Fargo | 2024 | deposits | 6,805 |
| Wells Fargo | 2024 | mortgage | 1,485 |
| Wells Fargo | 2025 | cards | 2,727 |
| Wells Fargo | 2025 | credit_reporting | 3,569 |
| Wells Fargo | 2025 | deposits | 8,181 |
| Wells Fargo | 2025 | mortgage | 1,237 |
| Wells Fargo | 2026 | cards | 2,840 |
| Wells Fargo | 2026 | credit_reporting | 2,611 |
| Wells Fargo | 2026 | deposits | 7,491 |
| Wells Fargo | 2026 | mortgage | 909 |

### Synthetic data

| Table | Rows |
| --- | --- |
| accounts | 500 |
| disputes | 384 |
| transactions | 1,183 |

## Splits

Temporal split (never random) to prevent leakage into the routing golden set:

| Split | Complaint dates | Complaints |
| --- | --- | --- |
| train | ≤ 31 Dec 2023 | 519,287 |
| val | 2024 | 77,716 |
| test | 2025 - present | 190,714 |

## Taxonomy mapping

CFPB revised its product/issue categories (2017 consolidation; ~2023 split/rename), so raw product strings are mapped to four stable, regulation-aligned families (`data/taxonomy_map.yaml`, verified against observed values — never from memory):

| Family | Label | Governing regulation |
| --- | --- | --- |
| cards | Credit and prepaid cards | Reg Z |
| credit_reporting | Credit reporting (as furnisher) | Reg V |
| deposits | Deposit accounts | Reg E / Reg DD |
| mortgage | Mortgage | Reg X |

- 9 CFPB product strings (all eras) map to these families; 18 legacy issue strings are crosswalked to the current vocabulary.
- Unmappable labels become `UNMAPPED`: excluded from routing metrics, counted above.

## Known biases and limitations

- CFPB narratives are **consent-only** submissions and are **not a representative sample** of all complaints or of any bank's customers.
- Complaint **volume depends on company size** and submission propensity; the counts above must not be read as a bank quality ranking.
- CFPB states that narrative allegations are **unverified** consumer opinions. RESOLVE presents them as allegations only and never concludes that a named bank violated a law.
- Narrative text is not distributed by CFPB; synthetic narratives (generated separately) are grounded in the real routing labels.
- All account holders, transactions and disputes are **synthetic**; no attempt is made to re-identify anyone.

## Licence

- **CFPB Consumer Complaint Database:** U.S. Government work, public domain.
- **eCFR:** U.S. Government work, public domain.
- **Bank documents:** public materials, redistributed only as hashes/metadata (the PDFs themselves are not committed).
- **Synthetic data:** produced by this project; no licence restrictions.
