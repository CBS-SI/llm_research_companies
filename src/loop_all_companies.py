import os
import dotenv
import argparse
import subprocess
import pandas as pd
from tqdm import tqdm

def load_dotenv():
    # Ref: https://stackoverflow.com/a/78972639/
    dotenv.load_dotenv()
    dotenv.load_dotenv(dotenv.find_dotenv(usecwd=True))

def process_company(MASTER_DATA_PATH, COMPANY_FOLDER_PATH,LLM_RESPONSES_DATA_PATH, MODEL):

    ids = pd.read_csv(MASTER_DATA_PATH).BVD_ID.dropna().unique()

    processed = [
        bvd_id for bvd_id in ids
        if os.path.exists(os.path.join(COMPANY_FOLDER_PATH, f"{bvd_id}_{MODEL}_panel.csv"))
    ]
    unprocessed = [bvd_id for bvd_id in ids if bvd_id not in processed]

    print(f"Already processed: {len(processed)}/{len(ids)} companies")

    # Apply limit to unprocessed companies
    if args.limit is not None:
        unprocessed = unprocessed[:args.limit]
        print(f"Limiting to {args.limit} new companies (skipping already processed ones).")

    # Main loop
    tqdm_count = processed + unprocessed
    for bvd_id in tqdm(tqdm_count, desc="Processing companies"):
        print(f"\n{'='*60}")
        print(f"Processing BVD_ID: {bvd_id}")
        print(f"{'='*60}")

        company_file_name = os.path.join(COMPANY_FOLDER_PATH, f"{bvd_id}_{MODEL}_panel.csv")

        # Skip if fully processed (but still count in tqdm)
        if os.path.exists(company_file_name):
            print("✓ Already processed. Skipping.")
            continue

        # Check if the web search LLM response already exists
        file_name = os.path.join(LLM_RESPONSES_DATA_PATH, f"{bvd_id}_{MODEL}_websearch.json")

        if os.path.exists(file_name):
            print("✓ Websearch LLM response already exists.")
        else:
            try:
                subprocess.run(
                    ["python", "src/llm_web_search_call.py", "--bvd_id", str(bvd_id)],
                    check=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                print("✗ Error running llm_web_search_call.py: {e.stderr}")
                continue

        # Check if json LLM response already exists
        file_name = os.path.join(LLM_RESPONSES_DATA_PATH, f"{bvd_id}_{MODEL}_json.json")

        if os.path.exists(file_name):
            print("✓ JSON LLM response already exists.")
        else:
            try:
                subprocess.run(
                    ["python", "src/llm_code_interpreter_call.py", "--bvd_id", str(bvd_id)],
                    check=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                print(f"✗ Error running llm_code_interpreter_call.py: {e.stderr}")
                continue

        # Format LLM output
        if os.path.exists(company_file_name):
            print("✓ Formatted output .csv file already exists.")
        else:
            print("Running post_llm_format.py...")
            try:
                subprocess.run(
                    ["python", "src/post_llm_format.py", "--bvd_id", str(bvd_id)],
                    check=True,
                    text=True
                )
                print("✓ post_llm_format.py completed successfully")
            except subprocess.CalledProcessError as e:
                print(f"✗ Error running post_llm_format.py: {e.stderr}")

    print(f"\n{'='*60}")
    print("All processing complete!")
    print(f"{'='*60}")


if __name__ == "__main__":

    load_dotenv()

    MASTER_DATA_PATH = os.getenv("MASTER_DATA_PATH")
    LLM_RESPONSES_DATA_PATH = os.getenv("LLM_RESPONSES_DATA_PATH")
    COMPANY_FOLDER_PATH = os.getenv("COMPANY_FOLDER_PATH")
    MODEL = "gpt-5"

    parser = argparse.ArgumentParser(description="Process companies with optional limit on number of new BVD_IDs.")
    parser.add_argument("--limit", type=int, default=None, help="Number of new BVD_IDs to process (excluding already processed ones).")
    args = parser.parse_args()

    process_company(
        MASTER_DATA_PATH=MASTER_DATA_PATH,
        COMPANY_FOLDER_PATH=COMPANY_FOLDER_PATH,
        LLM_RESPONSES_DATA_PATH=LLM_RESPONSES_DATA_PATH,
        MODEL=MODEL)
