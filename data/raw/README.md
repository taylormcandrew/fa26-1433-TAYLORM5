# Raw data

Store original, unmodified source data here. These files are ignored by Git by default. Document each source, access date, and any instructions needed to obtain the data.

## Files in this folder (not committed; see .gitignore)

| Path | Contents | How to get it |
|---|---|---|
| `visits/cu_boulder.xlsx` | CU Boulder recruitment events, Aug 2021 – Jun 2026 | Colorado Open Records Act request no. 879 (received October 2026). Saved unedited. |
| `nces/elsi_public_2021_22.csv` | Public schools, 2021-22: name, 12-digit NCES ID, location city/state/ZIP, lowest/highest grade, total students, AIAN, Asian, Hispanic, Black and NHPI counts | NCES ElSi Table Generator (https://nces.ed.gov/ccd/elsi/), Public School row, 2021-22, all 50 states + DC. Export as CSV. |
| `nces/pss2122_pu.csv` | Private School Survey 2021-22 public-use file | https://nces.ed.gov/surveys/pss/pssdata.asp → 2021–22 → Data: Text (CSV) ZIP |
| `nces/pss2324_pu.csv` | Private School Survey 2023-24 public-use file | Same page → 2023–24 → Data: Text (CSV) ZIP |
| `acs_zcta_2021.csv` | ACS 2017-2021 5-year, race/ethnicity by ZIP | Downloaded automatically by `code/prep_zip_demographics.py` |

Place each file at the path shown, then run `bash run.sh` from the repository root.
