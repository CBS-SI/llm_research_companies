"""
Step 3: Post-processing for all companies with completed code interpreter formatting.

This script processes all companies that have {BVD_ID}_{MODEL}_json.json files
and creates cleaned panel CSV files.
"""

import os
import sys
import dotenv

SRC_PATH = "/Users/pg/Documents/GitHub/llm_research_companies/src"
sys.path.append(SRC_PATH)

import post_llm_format


def load_dotenv():
    dotenv.load_dotenv()
    dotenv.load_dotenv(dotenv.find_dotenv(usecwd=True))

def get_companies_with_json_responses(LLM_RESPONSES_DATA_PATH, MODEL):
    """
    Find all companies that have completed code interpreter formatting.
    Returns list of BVD IDs.
    """
    if not os.path.exists(LLM_RESPONSES_DATA_PATH):
        print(f"Error: {LLM_RESPONSES_DATA_PATH} does not exist")
        return []

    companies_with_json = []

    # Find all *_json.json files
    for filename in os.listdir(LLM_RESPONSES_DATA_PATH):
        if filename.endswith(f"_{MODEL}_json.json"):
            # Extract BVD_ID from filename
            bvd_id = filename.replace(f"_{MODEL}_json.json", "")
            companies_with_json.append(bvd_id)

    return sorted(companies_with_json)


def get_companies_already_processed(COMPANY_FOLDER_PATH, MODEL):
    """
    Find all companies that already have panel CSV files.
    Returns set of BVD IDs.
    """
    if not os.path.exists(COMPANY_FOLDER_PATH):
        os.makedirs(COMPANY_FOLDER_PATH)
        return set()

    processed = set()

    # Find all *_panel.csv files
    for filename in os.listdir(COMPANY_FOLDER_PATH):
        if filename.endswith(f"_{MODEL}_panel.csv"):
            # Extract BVD_ID from filename
            bvd_id = filename.replace(f"_{MODEL}_panel.csv", "")
            processed.add(bvd_id)

    return processed


def main():
    print("\n" + "="*60)
    print("STEP 3: POST-PROCESSING")
    print("="*60 + "\n")

    load_dotenv()

    LLM_RESPONSES_DATA_PATH = os.getenv("LLM_RESPONSES_DATA_PATH")
    COMPANY_FOLDER_PATH = os.getenv("COMPANY_FOLDER_PATH")
    MODEL = "gpt-5"

    # Find companies with JSON responses
    companies_with_json = get_companies_with_json_responses(LLM_RESPONSES_DATA_PATH, MODEL)

    if not companies_with_json:
        print("✗ No companies found with JSON responses.")
        print(f"  Looking in: {LLM_RESPONSES_DATA_PATH}")
        print(f"  Pattern: *_{MODEL}_json.json")
        return

    # Find companies already processed
    already_processed = get_companies_already_processed(COMPANY_FOLDER_PATH, MODEL)

    # Filter to only unprocessed companies
    companies_to_process = [c for c in companies_with_json if c not in already_processed]

    # Summary
    print(f"Total companies with JSON responses: {len(companies_with_json)}")
    print(f"Already processed (skipping): {len(already_processed)}")
    print(f"To process: {len(companies_to_process)}\n")

    if not companies_to_process:
        print("✓ All companies already processed!")
        return

    print(f"{'='*60}")
    print("Processing companies...")
    print(f"{'='*60}\n")

    success_count = 0
    failed_count = 0
    failed_companies = []

    for idx, bvd_id in enumerate(companies_to_process, 1):
        try:
            print(f"[{idx}/{len(companies_to_process)}] Processing {bvd_id}...")

            # Run post_llm_format for this company
            post_llm_format.main(["--bvd_id", bvd_id, "--model", MODEL])

            success_count += 1

        except Exception as e:
            print(f"✗ Failed {bvd_id}: {str(e)}\n")
            failed_count += 1
            failed_companies.append({"bvd_id": bvd_id, "error": str(e)})

    # Final summary
    print(f"\n{'='*60}")
    print("STEP 3 COMPLETE")
    print(f"{'='*60}")
    print(f"Total processed: {len(companies_to_process)}")
    print(f"✓ Success: {success_count}")
    print(f"✗ Failed: {failed_count}")

    if failed_companies:
        print(f"\nFailed companies:")
        for item in failed_companies:
            print(f"  - {item['bvd_id']}: {item['error']}")

    print(f"{'='*60}\n")

    print(f"✓ Panel CSV files saved to: {COMPANY_FOLDER_PATH}")
    print(f"  Pattern: {{BVD_ID}}_{MODEL}_panel.csv\n")


if __name__ == "__main__":
    main()
