# Creating company panel data out of company names with OpenAI LLM API

🚧 WIP - scripts and prints will change.

## Documentation of the `.dta` file fields

- `BVD_ID`: the BVD of the company. Constant for years 1995-2015.

- `year`: year range from 1995 to 2015, in panel shape.

- `establishment_year`: The establishment year of the company.

- `orbis_company_name`: Tracks if the legal company name changed year by year.

- `company_name_orbis`: The name of the company according to Orbis, stays constant (as opposed to `company_name`).

- `company_international_name`: The name of the company in a second format, given by the raw file, extended by the LLM for out of range years.

- `parent_company_name_orbis`: The name of the direct parent company according to Orbis for the years Orbis had this data, extended by the LLM for out of range years. This field is only populated if the company is a subsidiary. Given that companies can be Joint Ventures (JVs), there can be multiple parent companies.

- `parent_BVD_ID`: the BVD of the parent company, if the name of the company is avaiblable in the raw data (`Ownership_data_for_ChatGPT.dta`). If the name of the owner is not in the file (e.g. "Eon Electric Ltd", "Government of Gujarat"), then the ID is not populated. Since the name of the owner is LLM generated and the `.dta` file do not contain all the possible arent company for all possible years, this field cannot be complete.

- `parent_company_ownership_years`: From which year to which year the parent company had ownership of the subsidiary (e.g. 2000-2011). The range years can go before 1995 and beyond 2015 (e.g. 1980-2015+).

- `parent_company_country`: The country of the headquarters of the parent company.

- `JV`: 1 if the company is owned by a Joint Venture, 0 if not.

- `JV_with_india`: 1 if at least one of the Joint Venture company is Indian for a given year, 0 if not.

- `GUO`: The name of the Global Ultimate Owner (if it`s a subsidiary). In case of a JV, it will be the name of the company with more ownership. In case of a 50:50 ownership, there can be multiple GUOs (e.g. IN0000249001).

- `GUO_BVD_ID`: the BVD of the Global Ultimate Owner, if the name of the company is avaiblable on the raw data (`Ownership_data_for_ChatGPT.dta`). This ID cannot be populated if the name of the parent company (e.g. "Eon Electric Ltd", "Government of Gujarat") is not in the raw file. Since the name of the owner is LLM generated and the `.dta` file do not contain all the possible arent company for all possible years, this field cannot be complete.

- `GUO_country`. The GUO's headquarters country.

- `foreign_controlled`: 1 if the company do not have at least one Indian GUO at a given year, otherwise 0.

- `GUO_only_india`: The name of the GUO if the GUO_contry is India for a given year, missing value otherwise.

  _For multiple GUOs_:
  - 50:50 Indian–Foreign: this field will only display one the Indian GUO for a given year (e.g. IN0000249001).
  - 50:50 Indian–Indian: this field will be the same as `GUO`.
  - 50:50 Foreign–Foreign: this field will be missing.

  _For a single GUO_:
  - Mayority stakeholder Indian: This field will display the Indian GUO.
  - Mayority stakeholder Not Indian: This field will be missing.

- `GUO_only_India_BVD_ID`: same as `GUO_BVD_ID` field but only populated for `GUO_only_india`.

- `IBG`: 1 if the company is part of a "Indian Business Group", 0 otherwise. (The Oxford Handbook of Business Groups (2010; online edn, Oxford Academic, 2 Sept. 2010 - https://doi.org/10.1093/oxfordhb/9780199552863.003.0011)

- `sources`: The URL of the online sources that the LLM used to extract the information. If you are in doubt on why it wrote a given peace of information at a given year, visit the URL under sources.

## Scripts

### Core Scripts

- `merge_raw_data.py`: Merges the 2 raw files given by the researcher. `llm_web_search_call.py` use this merged file.

- `llm_web_search_call.py`: OpenAI web search call to scrape a individual company information from the internet. **Using gpt-5 at real-time, it cost around $0.10 to $0.20 per company**

- `llm_code_interpreter_call.py`: OpenAI code_interpreter call to format the data from `llm_web_search_call.py` into a readable dataframe. **Using gpt-5 at real-time, it cost around $0.05 to $0.10 per company**

- `post_llm_format.py`: formats the response from OpenAI into a readable `.csv` file, with extra fields and clean formatting.

- `loop_all_companies`: Loops `llm_company_call.py` and `post_llm_format.py` for every BVD ID in the raw master file.

- `merge_processed_data.py`: merges all companyc`.csv` files into a single file "master file" in `.csv` and `.dta` formats.

## Example of use

### Loop all companies

In most cases, you would like to loop over a certain number of companies to extract their information. For example, limiting the reseach for 2 companies (`--limit`):

```
(gpt) pg@mbpwork dev % python src/loop_all_companies.py --limit 2

Already processed: 0/1845 companies
Limiting to 2 new companies (skipping already processed ones).
Processing companies:   0%|                                    | 0/2 [00:00<?, ?it/s]
============================================================
Processing BVD_ID: IN*110348475424
============================================================
✗ Websearch LLM response not found. Running llm_web_search_call.py...
API call estimated cost: $0.19
Function create_websearch_llm_response took 293.9 seconds
✓ llm_web_search_call.py completed successfully
✗ JSON LLM response not found. Running llm_code_interpreter_call.py...
API call estimated cost: $0.08
Function create_json_llm_response took 163.8 seconds
✓ llm_code_interpreter_call.py completed successfully
Running post_llm_format.py...
Cleaning panel data of Matsushita Electric Indl. Co. Ltd. (IN*110348475424)...
Done! Saved as /.../processed_data/company_files/IN*110348475424_gpt-5_panel.csv
✓ post_llm_format.py completed successfully
Processing companies:  50%|███████████       | 1/2 [07:42<02:48, 42.03s/it]
============================================================
Processing BVD_ID: IN*1226255
============================================================
✗ Websearch LLM response not found. Running llm_web_search_call.py...
API call estimated cost: $0.19
Function create_websearch_llm_response took 257.9 seconds
✓ llm_web_search_call.py completed successfully
✗ JSON LLM response not found. Running llm_code_interpreter_call.py...
API call estimated cost: $0.10
Function create_json_llm_response took 155.5 seconds
✓ llm_code_interpreter_call.py completed successfully
Running post_llm_format.py...
Cleaning panel data of Sigma Phoenix (p) Ltd. (IN*1226255)...
Done! Saved as /.../processed_data/company_files/IN*1226255_gpt-5_panel.csv
✓ post_llm_format.py completed successfully
Processing companies:  100%|█████████████████████▌| 2/2 [14:40<04:15, 85.23s/it]

============================================================
All processing complete!
============================================================
```

### Skipping already processed companies

The scripts skip the companies already processed via LLM to avoid extra costs.

```
(gpt) pg@mbpwork dev % python src/loop_all_companies.py --limit 3

Already processed: 2/1845 companies
Limiting to 3 new companies (skipping already processed ones).
Processing companies:   0%|                                    | 0/5 [00:00<?, ?it/s]

============================================================
Processing BVD_ID: IN0000249001
============================================================
✓ Already processed. Skipping.

============================================================
Processing BVD_ID: IN0000249725
============================================================
✓ Already processed. Skipping.

============================================================
Processing BVD_ID: IN*110348475424
============================================================
✗ Websearch LLM response not found. Running llm_web_search_call.py...
```

### Reloading responses for a single company

If the data generated is not satisfactory for a company, just delete the `_websearch.json` or/and `_json.json` files from the `response` for the given company in the `responses` folder and call the single company scripts sequentially.

```
(gpt) pg@mbpwork dev % python src/llm_web_search_call.py --bvd_id "IN31739FI"
✗ Web search LLM response not found. Running llm_web_search_call.py...
API call estimated cost: $0.13
Function create_websearch_llm_response took 163.6 seconds

(gpt) pg@mbpwork dev % python src/post_llm_format.py --bvd_id "IN31739FI"
✗ JSON LLM response not found. Running llm_code_interpreter_call.py...
API call estimated cost: $0.08
Function create_json_llm_response took 150.7 seconds
✓ llm_code_interpreter_call.py completed successfully

(gpt) pg@mbpwork dev % python src/post_llm_format.py --bvd_id "IN31739FI"
Cleaning panel data of Sibar Auto Parts Ltd. (IN31739FI)...
Done! Saved as /.../processed_data/company_files/IN31739FI_gpt-5_panel.csv

(gpt) pg@mbpwork dev % python src/merge_processed_data.py
Merged 20 CSV files into processed_master_file CSV and dta
Done! saved at: /.../processed_data/processed_master_file
```

## Parent directory structure

```
.
├── raw_data
│   ├── Ownership_data_for_ChatGPT.dta
│   ├── ALL_BvDID_all_firms_update.dta
│   └── PANEL_controlling_firms_orbis.dta
├── processed_data
│   ├── raw_master_data.csv
│   ├── processed_master_file.csv
│   ├── processed_master_file.dta
│   ├── company_files
│   │   ├── IN*110157064108_gpt-5_panel.csv
│   │   ├── IN*110190685171_gpt-5_panel.csv
│   ├── responses
│   │   ├── IN*110157064108_gpt-5_websearch.json
│   │   ├── IN*110157064108_gpt-5_json.json
│   │   ├── IN*110190685171_gpt-5_websearch.json
│   │   ├── IN*110190685171_gpt-5_json.json
├── src
│   ├── llm_web_search_call.py
│   ├── merge_raw_data.py
│   ├── llm_code_interpreter_call.py
│   ├── merge_processed_data.py
│   ├── post_llm_format.py
│   └── loop_all_companies.py
├── environment.yml
└── README.md
```
