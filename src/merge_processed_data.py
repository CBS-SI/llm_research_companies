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

    # Save to one CSV
    merged_df.to_csv(f"{PROCESSED_DATA_PATH}/{output_name}.csv", index=False)
    merged_df.to_stata(f"{PROCESSED_DATA_PATH}/{output_name}.dta", version=118)

    print(f"Merged {len(csv_files)} CSV files into {output_name} CSV and dta")

    return merged_df

if __name__=="__main__":

    load_dotenv()

    COMPANY_FOLDER_PATH =  os.getenv("COMPANY_FOLDER_PATH")
    PROCESSED_DATA_PATH = os.getenv("PROCESSED_DATA_PATH")
    output_name = "processed_master_file"

    master_file = create_master_file(COMPANY_FOLDER_PATH, PROCESSED_DATA_PATH, output_name)
    print(f"Done! saved at: {PROCESSED_DATA_PATH}/{output_name}")
