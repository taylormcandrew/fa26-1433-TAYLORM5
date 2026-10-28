#!/usr/bin/env bash
# Rebuild every output from the raw data. Run from the repository root:
#   bash run.sh
set -euo pipefail
cd "$(dirname "$0")"

python code/prep_high_schools.py     # NCES demographics -> URM share by high school
python code/prep_zip_demographics.py # Census ACS -> URM share of residents by ZIP
python code/standardize.py           # each university's raw file -> one common format, events categorized
python code/build_panel.py           # match visits to schools and ZIPs -> university x cycle panel
python code/estimate.py              # DiD, robustness, event studies -> output/
