# Recruitment Resource Allocation After SFFA

Taylor McAndrew, 14.33

Did public universities that were newly restricted by *Students for Fair Admissions v. Harvard* (June 2023) shift a larger share of their high-school recruitment visits toward high schools with majority underrepresented-minority (URM) enrollment?

## Inputs

| File | What it is | Where it comes from |
|---|---|---|
| `data/raw/visits/<university>.csv` or `.xlsx` | Recruitment event records, Aug 2021 to Sep 2026, one file per university, **unedited, exactly as returned** | State public-records requests (CU Boulder: CORA request no. 879) |
| `data/raw/universities.csv` | One row per university: `univ_id, name, state, exposed, admit_rate_2021, rep_share_2020, complete_records` | Hand-built. `exposed` = 1 if the state had no race-conscious admissions ban before 2023. Admit rate from IPEDS Fall 2021. GOP share of the 2020 presidential vote. |
| `data/raw/nces/elsi_public_2021_22.csv` | Public high schools, 2021-22: name, NCES ID, location, grade span, total students and AIAN/Hispanic/Black/NHPI counts | NCES ElSi table generator (Common Core of Data) |
| `data/raw/nces/pss2122_pu.csv`, `pss2324_pu.csv` | Private schools: name, location, grade span, enrollment and percentages by race. 2021-22 is used; 2023-24 only fills in schools missing from 2021-22 | NCES Private School Survey public-use files, <https://nces.ed.gov/surveys/pss/pssdata.asp> |
| `data/raw/acs_zcta_2021.csv` | Residents by race/ethnicity for every ZIP (ZCTA), ACS 2017-2021 5-year, tables B03002 and B01001B/C/E/I | Downloaded automatically from the Census API on the first run, then reused (commit it) |
| `data/manual/hs_crosswalk.csv` | Hand matches for visits the name match misses: `school_name, city, state, nces_id`. Put `EXCLUDE` as the `nces_id` for records that are not high schools. | Hand-coded from `output/unmatched_schools.csv` |

All analysis choices (cycle dates, URM threshold, which event categories count, the column layout of each university's file) are in `code/config.py`.

## Adding a university's records

1. Save the file, unedited, in `data/raw/visits/` (e.g. `ucla.xlsx`).
2. Add an entry to `VISIT_FILES` in `code/config.py` naming the columns that hold the date, the school (a school-name column or an event title), the location and the event type. The CU Boulder entry is a worked example.
3. Add a row to `data/raw/universities.csv`.
4. Run `bash run.sh`, then check:
   - `output/event_categories.csv`: every distinct event title with its category. If one is wrong, adjust `EVENT_RULES` in `config.py`.
   - `output/unmatched_schools.csv`: fill in `nces_id` for the rows that matter and copy them to `data/manual/hs_crosswalk.csv`.
   - The `match_method` column of `data/intermediate/visits_clean.csv`: spot-check rows matched by `fuzzy_zip`.

## Running with only some universities

The pipeline runs at any stage of data collection:

- **One university, or only universities from one group:** you get the descriptive outputs: `trends.png`, `trends_by_university.csv` and `prepost_by_university.csv` (a before/after comparison within each university, which is descriptive and not causal). The difference-in-differences is skipped with a message.
- **Both prior-ban and no-ban universities:** the difference-in-differences, robustness table and event studies are added automatically.
- **No NCES files yet:** the school-level outcome is left empty and the ZIP-level outcome still runs.
- **Census download fails:** the ZIP-level outcome is left empty and everything else runs. The warning prints a link; open it in a browser and save the page as `data/raw/acs_zcta_2021.json`.

## Matching quality (CU Boulder, first run)

85.5% of CU's 3,382 eligible visits match a high school with demographics. A hand check of 75 random matches (exact name + ZIP, and close-name matches within a ZIP) found all 75 correct. Unmatched visits are mostly private schools that did not answer the Private School Survey in either year; they are listed in `output/unmatched_schools.csv`.

## Setup (once)

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Run

From the repository root:

```bash
bash run.sh
```

1. `code/prep_high_schools.py` builds each high school's URM share.
2. `code/prep_zip_demographics.py` builds each ZIP's resident URM share.
3. `code/standardize.py` reads each university's file into one common format and labels each event (`hs_visit`, `school_fair`, `regional_event`, `materials_dropoff`, `admitted_student`, `other`).
4. `code/build_panel.py` matches visits to high schools and ZIPs and builds the university × cycle panel.
5. `code/estimate.py` runs the difference-in-differences, robustness checks and event studies.

## Outputs

| File | Contents |
|---|---|
| `output/tables/descriptives.csv` | Universities, visits, match rate and mean outcome by exposed × post |
| `output/tables/trends_by_university.csv` | Outcome shares by university × cycle |
| `output/tables/prepost_by_university.csv` | Before/after SFFA within each university, SEs clustered by school (or ZIP) |
| `output/figures/trends.png` | Outcome shares by cycle, exposed vs control universities |
| `output/tables/did_results.csv` / `.tex` | Main estimate and robustness columns |
| `output/figures/event_study_cycle.png` | Event study by recruitment cycle (reference: 2022-23) |
| `output/figures/event_study_semester.png` | Event study by semester (reference: spring 2023) |
| `output/unmatched_schools.csv` | Visited schools not yet matched to demographics |
| `output/event_categories.csv` | Every distinct event title and the category it was given |

## Specification

$$Y_{it} = \alpha_i + \lambda_t + \beta\,(Post_t \times Exposed_i) + \varepsilon_{it}$$

- *Y_it*: share of university *i*'s eligible visits in recruitment cycle *t* (August–July) that go to high schools with more than 50% URM enrollment.
- α_i: university fixed effects.
- λ_t: recruitment-cycle fixed effects.
- *Post_t* = 1 from the 2023-24 cycle onward.

Eligible events are visits to one high school, in person or virtual (`hs_visit`). Regressions are weighted by matched eligible visits, with standard errors clustered by state and a wild cluster bootstrap p-value (Webb weights, 9,999 draws, seed 1433).

Robustness columns:
- 40% and 60% URM thresholds
- dropping the 2023-24 cycle
- selectivity tier × cycle fixed effects
- Post × 2020 GOP vote share
- universities with complete records only
- also counting fairs hosted at a single high school
- ZIP-level outcome: share of visits located in ZIPs whose residents are more than 50% URM (`ZIP_MEASURE` in `config.py` picks all ages or ages 15-19)
