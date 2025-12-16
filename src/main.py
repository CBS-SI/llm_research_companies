import pandas as pd
import sys

SRC_PATH = "/Users/pg/Documents/GitHub/llm_research_companies/src"
sys.path.append(SRC_PATH)


# Imports for scripts from src
import llm_web_search_call #1
import llm_code_interpreter_call #2
import post_llm_format #3
import merge_processed_data #4


# Read companies data to get a list
df = pd.read_stata("/Users/pg/Library/CloudStorage/Dropbox-CBS/Pipe Galera/llm_research_companies_data/raw_data/ALL_BvDID_all_firms_update.dta")
companies = list(df["bvd_id_number"].unique())
companies = ["IN*110190685171" if x == "IN0000248276" else x for x in companies]
companies.remove("IN0000231333") # It has no company name in the "original raw file"
companies = list(filter(None, companies)) # 1844 companies


# Step 1: Run web search on all companies
print("\n" + "="*60)
print("STEP 1: WEB SEARCH")
print("="*60 + "\n")

llm_web_search_call.main([
    "--bvd_ids", *companies,
    "--model", "gpt-5",
    "--batch_size", "500",
    "--max_concurrent", "5"
])


# Step 2: Submit batch for code interpreter formatting (50% cost savings!)
print("\n" + "="*60)
print("STEP 2: CODE INTERPRETER FORMATTING (BATCH MODE)")
print("="*60 + "\n")

llm_code_interpreter_call.main([
    "--bvd_ids", *companies,
    "--model", "gpt-5",
    "--batch_mode"
])

print("\n" + "="*60)
print("IMPORTANT: Step 2 submitted as batch job!")
print("="*60)
print("Batch processing will complete within 24 hours.")
print("After completion, retrieve results with the command shown above,")
print("then run Step 3 (post-processing) manually for each company.")
print("\nTo process Step 3 after batch completes:")
print("Run: python src/post_llm_format.py --bvd_id <company_id>")
print("="*60 + "\n")


