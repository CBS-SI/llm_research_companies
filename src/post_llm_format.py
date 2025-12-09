import os
import json
import dotenv
import argparse
import pandas as pd
import numpy as np
from io import StringIO

pd.set_option('future.no_silent_downcasting', True)

def load_dotenv():
    # Ref: https://stackoverflow.com/a/78972639/
    dotenv.load_dotenv()
    dotenv.load_dotenv(dotenv.find_dotenv(usecwd=True))

def get_orbis_company_name(MASTER_DATA_PATH, BVD_ID):
    # Selected company
    df = pd.read_csv(MASTER_DATA_PATH)
    company_string = df[df["BVD_ID"] == BVD_ID].orbis_company_name.unique()[0]

    return company_string

def load_llm_json_response_text(LLM_RESPONSES_DATA_PATH,
                                BVD_ID,
                                MODEL):
    response_json = f"{LLM_RESPONSES_DATA_PATH}/{BVD_ID}_{MODEL}_json.json"

    with open(response_json, "r", encoding="utf-8") as f:
        raw_json = f.read()

    json_parsed = json.loads(raw_json)
    response_text = json_parsed['response']['output'][1]['content'][0]['text']

    return pd.read_json(StringIO(response_text))

def create_bvd_id_map_dicts(RAW_OWNERSHIP_DATA_PATH):
    df = pd.read_stata(RAW_OWNERSHIP_DATA_PATH)

    bvd_company_name_map = (
        df[["bvd_id_number", "OrbisCompanyName"]]
        .drop_duplicates()
        .replace("", pd.NA)
        .dropna()
        .set_index("OrbisCompanyName")["bvd_id_number"]
        .to_dict()
    )

    bvd_inter_company_name_map = (
        df[["controlling_bvd_id", "Orbis_controlling_name"]]
        .drop_duplicates()
        .replace("", pd.NA)
        .dropna()
        .set_index("Orbis_controlling_name")["controlling_bvd_id"]
        .to_dict()
    )

    company_id_map = {
        **bvd_company_name_map,
        **bvd_inter_company_name_map,
    }

    company_id_map = dict(sorted(company_id_map.items()))

    return company_id_map

def ensure_list(x):
    # Convert scalars or NaNs to single-element lists
    if isinstance(x, list):
        return x
    elif pd.isna(x):
        return [None]
    else:
        return [x]

def repeat_to_length(lst, target_len):
    # Repeat list elements to reach target_len
    if not lst:  # empty list or None
        return [None] * target_len
    repeats = (target_len + len(lst) - 1) // len(lst)  # ceiling division
    extended = (lst * repeats)[:target_len]
    return extended

def expand_columns(data):
    df = data.copy()

    # Expland fields with multiple parent companies
    nested_columns = [
        "parent_company_name_orbis",
        "parent_company_country",
        "GUO",
        "GUO_country",
        "parent_company_ownership_years",
    ]
    # Step 1: make sure all are lists
    for col in nested_columns:
        df[col] = df[col].apply(ensure_list)
    # Step 2: find max length of lists per row
    max_lengths = df[nested_columns].map(len).max(axis=1)
    # Step 3: duplicate shorter lists
    for col in nested_columns:
        df[col] = [
            repeat_to_length(lst, max_len)
            for lst, max_len in zip(df[col], max_lengths)
        ]
    # Step 4: explode safely
    df = df.explode(nested_columns, ignore_index=True)

    return df

def map_ids(data, company_id_map, BVD_ID, ORBIS_COMPANY_NAME):
    df = data.copy()

    df["BVD_ID"] = BVD_ID
    df["orbis_company_name"] = ORBIS_COMPANY_NAME
    df["parent_BVD_ID"] = df["parent_company_name_orbis"].map(company_id_map)
    df["GUO_BVD_ID"] = df["GUO"].map(company_id_map)

    return df

def create_guo_india_columns(data):
    df = data.copy()

    guo_india_map = df[df["GUO_country"] == "India"].set_index("year").to_dict()["GUO"]
    df["GUO_only_India"] = df["year"].map(guo_india_map)
    df["GUO_only_India"] = np.where(df["GUO_only_India"].isna(), np.nan, df["GUO_only_India"])
    df["GUO_only_India_BVD_ID"] = df["GUO_only_India"].map(guo_india_map)

    return df

def create_jv_with_india_column(data):
    df = data.copy()

    has_india = df.groupby('year')['parent_company_country'].transform(lambda x: 'India' in x.values)
    has_non_india = df.groupby('year')['parent_company_country'].transform(lambda x: any(c != 'India' for c in x.values))

    df['JV_with_india'] = np.where(has_india & has_non_india, 1, 0)

    return df

def create_foreign_controlled_dummy(data):
  df = data.copy()

  # If only one GUO from a Indian country, then 0, otherwise 1.
  # If there is only one foreign GUO means that is the mayor stakeholder.
  foreign_controlled_map = df[df["GUO_country"] == "India"].set_index("year").to_dict()["GUO_country"]
  df["foreign_controlled"] = df["year"].map(foreign_controlled_map)
  df["foreign_controlled"] = np.where(df["foreign_controlled"] == "India", 0, 1)

  # Fix: correctly handle missing GUO_country values
  df["foreign_controlled"] = np.where(
      pd.isna(df["GUO_country"]),
      np.nan,
      df["foreign_controlled"]
  )

  return df

def order_columns(data):
    df = data.copy()

    df = df[[
        'BVD_ID',
        'year',
        'establishment_year',
        'orbis_company_name',
        'company_international_name',
        'parent_company_name_orbis',
        'parent_BVD_ID',
        'parent_company_ownership_years',
        'parent_company_country',
        'JV',
        'JV_with_india',
        'GUO',
        'GUO_BVD_ID',
        'GUO_country',
        'foreign_controlled',
        'GUO_only_India',
        'GUO_only_India_BVD_ID',
        'IBG',
        'sources']]

    return df

def clean_nans(data):
    df = data.copy()

    # NaN all data before the establishment_year
    mask = df["year"] < df["establishment_year"]
    cols_to_nan = df.columns.difference(["BVD_ID", "year", "sources"])
    df.loc[mask, cols_to_nan] = np.nan

    # Format NaNs
    nan_values = ["", "None", None, "NA (independent)", "NA", "N/A", "N/A (not yet incorporated)", "[]", "<NA>", "Not applicable (standalone)"]
    df = df.where(~df.isin(nan_values), np.nan)

    return df

def clean_formats(data):
  df = data.copy()

  # Ints showing as floats
  df['JV'] = df['JV'].astype('Int64')
  df['JV_with_india'] = df['JV_with_india'].astype('Int64')
  df['IBG'] = df['IBG'].astype('Int64')
  df['foreign_controlled'] = df['foreign_controlled'].astype('Int64')
  df['establishment_year'] = df['establishment_year'].astype('Int64')

  # Country Names
  df['parent_company_country'] = df['parent_company_country'].replace({"USA": "United States"})
  df['GUO_country'] = df['GUO_country'].replace({"USA": "United States"})

  return df

def main(argv=None):

  parser = argparse.ArgumentParser(description="LLM company call.")
  parser.add_argument("--bvd_id", type=str, required=True, help="Bureau van Dijk company ID")
  parser.add_argument("--model", type=str, default="gpt-5", help="LLM model used to process the data (default: gpt-5)")
  args = parser.parse_args(argv)

  BVD_ID = args.bvd_id
  MODEL = args.model

  load_dotenv()

  RAW_OWNERSHIP_DATA_PATH = os.getenv("RAW_OWNERSHIP_DATA_PATH")
  MASTER_DATA_PATH = os.getenv("MASTER_DATA_PATH")
  LLM_RESPONSES_DATA_PATH = os.getenv("LLM_RESPONSES_DATA_PATH")
  COMPANY_FOLDER_PATH = os.getenv("COMPANY_FOLDER_PATH")

  orbis_company_name = get_orbis_company_name(MASTER_DATA_PATH=MASTER_DATA_PATH, BVD_ID=BVD_ID)
  company_id_map = create_bvd_id_map_dicts(RAW_OWNERSHIP_DATA_PATH)

  print(f"Cleaning panel data of {orbis_company_name} ({BVD_ID})...")
  data = load_llm_json_response_text(LLM_RESPONSES_DATA_PATH=LLM_RESPONSES_DATA_PATH,
                              BVD_ID=BVD_ID,
                              MODEL=MODEL)
  df = (
      data
      .pipe(expand_columns)
      .pipe(map_ids,
          company_id_map=company_id_map,
          BVD_ID=BVD_ID,
          ORBIS_COMPANY_NAME=orbis_company_name)
      .pipe(create_guo_india_columns)
      .pipe(create_jv_with_india_column)
      .pipe(create_foreign_controlled_dummy)
      .pipe(order_columns)
      .pipe(clean_nans)
      .pipe(clean_formats)
  )

  # Save clean file
  file_name = f"{COMPANY_FOLDER_PATH}/{BVD_ID}_{MODEL}_panel.csv"
  df.to_csv(file_name, index=False)
  print(f"Done! Saved as {file_name}")

  return df


if __name__ == "__main__":
  main()
