import os
import dotenv
import pandas as pd

def load_dotenv():
    # Ref: https://stackoverflow.com/a/78972639/
    dotenv.load_dotenv()
    dotenv.load_dotenv(dotenv.find_dotenv(usecwd=True))

def create_master_file(COMPANY_FOLDER_PATH, PROCESSED_DATA_PATH, output_name):

    # Collect all CSV files in the folder
    csv_files = [f for f in os.listdir(COMPANY_FOLDER_PATH) if f.endswith(".csv")]

    # Read and merge all CSVs
    df_list = [pd.read_csv(os.path.join(COMPANY_FOLDER_PATH, f)) for f in csv_files]
    merged_df = pd.concat(df_list, ignore_index=True)

    # Save to CSV (preserve original format with lists)
    merged_df.to_csv(f"{PROCESSED_DATA_PATH}/{output_name}.csv", index=False)

    # Prepare for Stata: convert all problematic types to strings
    stata_df = merged_df.copy()

    # Convert all object columns to strings for Stata compatibility
    for col in stata_df.select_dtypes(include=['object']).columns:
        # Convert entire column to string, handling NaN values
        stata_df[col] = stata_df[col].astype(str)
        # Replace 'nan' string with empty string
        stata_df[col] = stata_df[col].replace('nan', '')

    # Save to Stata
    stata_df.to_stata(f"{PROCESSED_DATA_PATH}/{output_name}.dta", version=118)

    print(f"Merged {len(csv_files)} CSV files into {output_name} CSV and dta")

    return merged_df

def main():
  load_dotenv()

  COMPANY_FOLDER_PATH =  os.getenv("COMPANY_FOLDER_PATH")
  PROCESSED_DATA_PATH = os.getenv("PROCESSED_DATA_PATH")

  if not os.path.exists(COMPANY_FOLDER_PATH):
    os.makedirs(COMPANY_FOLDER_PATH)

  output_name = "processed_master_file"

  master_file = create_master_file(COMPANY_FOLDER_PATH, PROCESSED_DATA_PATH, output_name)
  print(f"Done! saved at: {PROCESSED_DATA_PATH}/{output_name}")

  return master_file

if __name__=="__main__":
    main()
