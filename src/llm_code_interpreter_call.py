import os
import time
import json
import dotenv
import argparse
import warnings
import numpy as np
import pandas as pd
from openai import OpenAI
from functools import wraps
from datetime import datetime

# Suppress Pydantic serialization warnings from OpenAI SDK
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic.main")

def load_dotenv():
    # Ref: https://stackoverflow.com/a/78972639/
    dotenv.load_dotenv()
    dotenv.load_dotenv(dotenv.find_dotenv(usecwd=True))

def timeit(func):
    @wraps(func)
    def timeit_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        print(f"Function {func.__name__} took {total_time:.1f} seconds")
        return result
    return timeit_wrapper

def filter_company(RAW_DATA_PATH, BVD_ID):

    # Selected company
    df = pd.read_csv(RAW_DATA_PATH)
    df = df[df["BVD_ID"] == BVD_ID]

    df.loc[:, "parent_company_ownership_years"] = (
        df["parent_company_start_year_ownership"].fillna(0).astype(int).astype(str)
        + " - " +
        df["parent_company_end_year_ownership"].fillna(0).astype(int).astype(str)
    )

    df["parent_company_ownership_years"] = df["parent_company_ownership_years"].replace({"0 - 0": ""})

    df = df.drop(["type_of_entity",
                  "category_public",
                  "parent_company_name",
                  #"parent_company_start_year_ownership",
                  #"parent_company_end_year_ownership",
                  "BVD_ID",
                  "parent_BVD_ID"], axis=1)

    return df

def print_openai_cost_from_response(MODEL, response):
    """
    Args:
        model (str): One of "gpt-5", "gpt-5-mini", "gpt-5-nano".
        response: The API response object (must include response.usage).

    """

    # Pricing per 1M tokens
    pricing = {
        "gpt-5": {"input": 1.250, "cached": 0.125, "output": 10.000},
        "gpt-5-mini": {"input": 0.250, "cached": 0.025, "output": 2.000},
        "gpt-5-nano": {"input": 0.050, "cached": 0.005, "output": 0.400},
    }

    if MODEL not in pricing:
        raise ValueError(f"Unknown model '{MODEL}'. Choose from: {list(pricing.keys())}")

    # Extract token usage from the response
    usage = response.usage
    input_tokens = getattr(usage, "input_tokens", 0)
    cached_tokens = getattr(usage, "cached_tokens", 0)
    output_tokens = getattr(usage, "output_tokens", 0)

    # Compute cost
    cost = (
        (input_tokens / 1_000_000) * pricing[MODEL]["input"] +
        (cached_tokens / 1_000_000) * pricing[MODEL]["cached"] +
        (output_tokens / 1_000_000) * pricing[MODEL]["output"]
    )

    return print(f"API call estimated cost: ${cost:.2f}")


def load_llm_web_response_text(LLM_RESPONSES_DATA_PATH, BVD_ID, MODEL):
    response_web = f"{LLM_RESPONSES_DATA_PATH}/{BVD_ID}_{MODEL}_websearch.json"

    with open(response_web, "r", encoding="utf-8") as f:
        raw_json = f.read()

    json_parsed = json.loads(raw_json)

    # Search through the output array for content
    for item in json_parsed['response']['output']:
        if isinstance(item, dict) and 'content' in item:
            if isinstance(item['content'], list) and len(item['content']) > 0:
                if 'text' in item['content'][0]:
                    return item['content'][0]['text']

    raise ValueError("Could not find response text in expected format")


@timeit
def create_json_llm_response(llm_text, data, CHATGPT_KEY, MODEL, print_cost=False):
    json_sample = data.to_json()

    prompt = f"""
        You are given:
        1. The company data: {llm_text}
        2. A pandas DataFrame in JSON format: {json_sample}

        Task:
        - Insert the information from the string into the DataFrame.
        - The years covered are from 1995 to 2015.
        - Keep and populate these columns:
          ['year', 'orbis_company_name', 'company_international_name', 'establishment_year',
          'parent_company_name_orbis', 'parent_company_country', 'JV', 'GUO',
          'GUO_country', 'parent_company_ownership_years', 'IBG' ,'sources'].

        Formatting rules:
        - If multiple values exist for the following fields use list notation: 'parent_company_name_orbis', 'parent_company_country', 'GUO', 'GUO_country', 'parent_company_ownership_years'. Examples: ["Parent Company 1", "Parent Company 2"], [India, USA], [1992-2021, 1995-2010].
        - 'orbis_company_name', 'company_international_name', and 'parent_company_name' company and parent company naming of the output have to match the naming of the pandas DataFrame in JSON format.
        - Output a valid and readable JSON — not code.
        - Make sure that the following fields have the same number of elements if they are in a list: 'parent_company_name_orbis', 'parent_company_country', 'GUO','GUO_country', 'parent_company_ownership_years'.

        Output:
        - Only the final JSON with the updated columns and years, from 1995 to 2015.
        - No comments, the output should be a readable JSON file.
        """

    client = OpenAI(api_key=CHATGPT_KEY)

    response = client.responses.create(
        model=MODEL,
        tools=[{"type": "code_interpreter","container": {"type": "auto"}}],
        input=[{"role": "user", "content": prompt}]
    )

    if print_cost:
        print_openai_cost_from_response(MODEL, response)

    return response

def create_batch_requests(bvd_ids, MODEL, MASTER_DATA_PATH, LLM_RESPONSES_DATA_PATH):
    """
    Create batch request objects for multiple companies.
    Returns a list of request objects in JSONL format for OpenAI Batch API.
    Only creates requests for companies that don't already have responses.
    """
    batch_requests = []
    skipped_count = 0

    for bvd_id in bvd_ids:
        # Check if response already exists
        file_name = f"{LLM_RESPONSES_DATA_PATH}/{bvd_id}_{MODEL}_json.json"
        if os.path.exists(file_name):
            print(f"⊘ Skipped {bvd_id} (already exists)")
            skipped_count += 1
            continue

        try:
            # Load the web search response
            llm_text = load_llm_web_response_text(
                LLM_RESPONSES_DATA_PATH=LLM_RESPONSES_DATA_PATH,
                BVD_ID=bvd_id,
                MODEL=MODEL
            )

            # Get company data
            df_company = filter_company(
                RAW_DATA_PATH=MASTER_DATA_PATH,
                BVD_ID=bvd_id
            )

            json_sample = df_company.to_json()

            prompt = f"""
        You are given:
        1. The company data: {llm_text}
        2. A pandas DataFrame in JSON format: {json_sample}

        Task:
        - Insert the information from the string into the DataFrame.
        - The years covered are from 1995 to 2015.
        - Keep and populate these columns:
          ['year', 'orbis_company_name', 'company_international_name', 'establishment_year',
          'parent_company_name_orbis', 'parent_company_country', 'JV', 'GUO',
          'GUO_country', 'parent_company_ownership_years', 'IBG' ,'sources'].

        Formatting rules:
        - If multiple values exist for the following fields use list notation: 'parent_company_name_orbis', 'parent_company_country', 'GUO', 'GUO_country', 'parent_company_ownership_years'. Examples: ["Parent Company 1", "Parent Company 2"], [India, USA], [1992-2021, 1995-2010].
        - 'orbis_company_name', 'company_international_name', and 'parent_company_name' company and parent company naming of the output have to match the naming of the pandas DataFrame in JSON format.
        - Output a valid and readable JSON — not code.
        - Make sure that the following fields have the same number of elements if they are in a list: 'parent_company_name_orbis', 'parent_company_country', 'GUO','GUO_country', 'parent_company_ownership_years'.

        Output:
        - Only the final JSON with the updated columns and years, from 1995 to 2015.
        - No comments, the output should be a readable JSON file.
        """

            # Create batch request object
            batch_request = {
                "custom_id": bvd_id,
                "method": "POST",
                "url": "/v1/responses",
                "body": {
                    "model": MODEL,
                    "tools": [{"type": "code_interpreter", "container": {"type": "auto"}}],
                    "input": [{"role": "user", "content": prompt}]
                }
            }

            batch_requests.append(batch_request)
            print(f"✓ Created batch request for {bvd_id}")

        except Exception as e:
            print(f"✗ Failed to create batch request for {bvd_id}: {str(e)}")

    # Print summary
    print(f"\n{'='*60}")
    print("BATCH REQUEST SUMMARY")
    print(f"{'='*60}")
    print(f"Total companies provided: {len(bvd_ids)}")
    print(f"⊘ Skipped (already exist): {skipped_count}")
    print(f"✓ New requests created: {len(batch_requests)}")
    print(f"{'='*60}\n")

    return batch_requests


def submit_batch(batch_requests, CHATGPT_KEY, BATCH_DATA_PATH):
    """
    Submit batch requests to OpenAI Batch API.
    Returns the batch ID.
    """
    client = OpenAI(api_key=CHATGPT_KEY)

    # Create JSONL file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    input_file_path = f"{BATCH_DATA_PATH}/batch_input_{timestamp}.jsonl"

    with open(input_file_path, "w") as f:
        for request in batch_requests:
            f.write(json.dumps(request) + "\n")

    print(f"\n✓ Created batch input file: {input_file_path}")
    print(f"  Total requests: {len(batch_requests)}\n")

    # Upload file to OpenAI
    with open(input_file_path, "rb") as f:
        batch_input_file = client.files.create(file=f, purpose="batch")

    print(f"✓ Uploaded batch file to OpenAI: {batch_input_file.id}")

    # Create batch
    batch = client.batches.create(
        input_file_id=batch_input_file.id,
        endpoint="/v1/responses",
        completion_window="24h",
        metadata={
            "description": "Code interpreter formatting batch"
        }
    )

    print("✓ Batch submitted successfully!")
    print(f"  Batch ID: {batch.id}")
    print(f"  Status: {batch.status}")
    print("\n  Use this command to check status:")
    print(f"  python src/llm_code_interpreter_call.py --retrieve_batch {batch.id}\n")

    # Save batch metadata
    batch_metadata_file = f"{BATCH_DATA_PATH}/batch_metadata_{batch.id}.json"
    with open(batch_metadata_file, "w") as f:
        json.dump({
            "batch_id": batch.id,
            "timestamp": timestamp,
            "input_file": input_file_path,
            "input_file_id": batch_input_file.id,
            "total_requests": len(batch_requests),
            "bvd_ids": [req["custom_id"] for req in batch_requests]
        }, f, indent=2)

    return batch.id


def retrieve_batch(batch_id, CHATGPT_KEY, LLM_RESPONSES_DATA_PATH, BATCH_DATA_PATH, MODEL):
    """
    Retrieve and process completed batch results.
    """
    client = OpenAI(api_key=CHATGPT_KEY)

    # Get batch status
    batch = client.batches.retrieve(batch_id)

    print(f"\n{'='*60}")
    print(f"BATCH STATUS: {batch_id}")
    print(f"{'='*60}")
    print(f"Status: {batch.status}")
    print(f"Total requests: {batch.request_counts.total}")
    print(f"Completed: {batch.request_counts.completed}")
    print(f"Failed: {batch.request_counts.failed}")

    if batch.status != "completed":
        print(f"\n⚠ Batch is not completed yet. Current status: {batch.status}")
        print("  Check again later using:")
        print(f"  python src/llm_code_interpreter_call.py --retrieve_batch {batch_id}\n")
        return

    print("\n✓ Batch completed! Downloading results...")

    # Download output file
    output_file_id = batch.output_file_id
    file_response = client.files.content(output_file_id)

    # Save raw output
    output_file_path = f"{BATCH_DATA_PATH}/batch_output_{batch_id}.jsonl"
    with open(output_file_path, "w") as f:
        f.write(file_response.text)

    print(f"✓ Downloaded batch output: {output_file_path}")

    # Process results and save individual responses
    # Also calculate total cost
    results = []
    total_input_tokens = 0
    total_cached_tokens = 0
    total_output_tokens = 0

    with open(output_file_path, "r") as f:
        for line in f:
            result = json.loads(line)
            results.append(result)

            bvd_id = result["custom_id"]

            # Save individual response
            if result.get("response") and result["response"].get("status_code") == 200:
                # Extract token usage for cost calculation
                usage = result["response"]["body"].get("usage", {})
                total_input_tokens += usage.get("input_tokens", 0)
                total_cached_tokens += usage.get("cached_tokens", 0)
                total_output_tokens += usage.get("output_tokens", 0)

                file_name = f"{LLM_RESPONSES_DATA_PATH}/{bvd_id}_{MODEL}_json.json"
                with open(file_name, "w", encoding="utf-8") as f:
                    json.dump({
                        "timestamp": datetime.now().isoformat(),
                        "response": result["response"]["body"]
                    }, f, ensure_ascii=False, indent=2)
                print(f"✓ Saved {bvd_id}")
            else:
                print(f"✗ Failed {bvd_id}: {result.get('error', 'Unknown error')}")

    # Calculate cost
    pricing = {
        "gpt-5": {"input": 1.250, "cached": 0.125, "output": 10.000},
        "gpt-5-mini": {"input": 0.250, "cached": 0.025, "output": 2.000},
        "gpt-5-nano": {"input": 0.050, "cached": 0.005, "output": 0.400},
    }

    if MODEL in pricing:
        # Batch API provides 50% discount
        batch_discount = 0.5

        regular_cost = (
            (total_input_tokens / 1_000_000) * pricing[MODEL]["input"] +
            (total_cached_tokens / 1_000_000) * pricing[MODEL]["cached"] +
            (total_output_tokens / 1_000_000) * pricing[MODEL]["output"]
        )

        batch_cost = regular_cost * batch_discount
        savings = regular_cost - batch_cost

        print(f"\n{'='*60}")
        print("COST ANALYSIS")
        print(f"{'='*60}")
        print(f"Model: {MODEL}")
        print(f"Input tokens: {total_input_tokens:,}")
        print(f"Cached tokens: {total_cached_tokens:,}")
        print(f"Output tokens: {total_output_tokens:,}")
        print(f"Total tokens: {total_input_tokens + total_cached_tokens + total_output_tokens:,}")
        print(f"\nRegular API cost: ${regular_cost:.2f}")
        print(f"Batch API cost (50% off): ${batch_cost:.2f}")
        print(f"💰 Total savings: ${savings:.2f}")
        print(f"{'='*60}\n")

    print(f"\n{'='*60}")
    print("PROCESSING COMPLETE")
    print(f"{'='*60}")
    print(f"Total processed: {len(results)}")
    print(f"✓ Success: {sum(1 for r in results if r.get('response', {}).get('status_code') == 200)}")
    print(f"✗ Failed: {sum(1 for r in results if r.get('response', {}).get('status_code') != 200)}")
    print(f"{'='*60}\n")


def main(argv=None):
  parser = argparse.ArgumentParser(description="LLM company call.")
  parser.add_argument("--bvd_id", type=str, help="Bureau van Dijk company ID (single company mode)")
  parser.add_argument("--bvd_ids", type=str, nargs='+', help="Multiple Bureau van Dijk company IDs (batch mode)")
  parser.add_argument("--model", type=str, default="gpt-5", help="LLM model to use (default: gpt-5)")
  parser.add_argument("--batch_mode", action="store_true", help="Use OpenAI Batch API (50%% cost savings)")
  parser.add_argument("--retrieve_batch", type=str, help="Retrieve results from a batch ID")
  parser.add_argument("--test_limit", type=int, help="Limit number of companies for testing (e.g., 10)")
  args = parser.parse_args(argv)

  MODEL = args.model

  load_dotenv()

  MASTER_DATA_PATH = os.getenv("MASTER_DATA_PATH")
  LLM_RESPONSES_DATA_PATH = os.getenv("LLM_RESPONSES_DATA_PATH")
  CHATGPT_KEY = os.getenv("CHATGPT_KEY")

  # Create batch data directory if using batch mode
  BATCH_DATA_PATH = os.getenv("BATCH_DATA_PATH", f"{LLM_RESPONSES_DATA_PATH}/batches")
  if not os.path.exists(BATCH_DATA_PATH):
    os.makedirs(BATCH_DATA_PATH)

  # Mode 1: Retrieve batch results
  if args.retrieve_batch:
      retrieve_batch(
          batch_id=args.retrieve_batch,
          CHATGPT_KEY=CHATGPT_KEY,
          LLM_RESPONSES_DATA_PATH=LLM_RESPONSES_DATA_PATH,
          BATCH_DATA_PATH=BATCH_DATA_PATH,
          MODEL=MODEL
      )
      return

  # Mode 2: Batch processing mode
  if args.batch_mode:
      if not args.bvd_ids:
          parser.error("--batch_mode requires --bvd_ids")

      bvd_ids = args.bvd_ids

      # Apply test limit if specified
      if args.test_limit:
          bvd_ids = bvd_ids[:args.test_limit]
          print(f"\n⚠ TEST MODE: Processing only first {len(bvd_ids)} companies\n")

      print(f"\n{'='*60}")
      print("BATCH MODE - 50% COST SAVINGS")
      print(f"{'='*60}")
      print(f"Total companies to process: {len(bvd_ids)}")
      print(f"Model: {MODEL}")
      print(f"{'='*60}\n")

      # Create batch requests
      batch_requests = create_batch_requests(
          bvd_ids=bvd_ids,
          MODEL=MODEL,
          MASTER_DATA_PATH=MASTER_DATA_PATH,
          LLM_RESPONSES_DATA_PATH=LLM_RESPONSES_DATA_PATH
      )

      if not batch_requests:
          print("✗ No valid batch requests created. Exiting.")
          return

      # Submit batch
      batch_id = submit_batch(
          batch_requests=batch_requests,
          CHATGPT_KEY=CHATGPT_KEY,
          BATCH_DATA_PATH=BATCH_DATA_PATH
      )

      print(f"✓ Batch processing initiated. Batch ID: {batch_id}")
      print("\nNote: Batch processing typically completes within 24 hours.")
      print(f"Check status with: python src/llm_code_interpreter_call.py --retrieve_batch {batch_id}")
      return

  # Mode 3: Single company mode
  if args.bvd_id:
      BVD_ID = args.bvd_id

      # Check if LLM response already exists
      file_name = f"{LLM_RESPONSES_DATA_PATH}/{BVD_ID}_{MODEL}_json.json"
      if os.path.exists(file_name):
          print(f"✓ JSON LLM response already exists: {file_name}")
      else:
          # Step 2: Creating a valid panel data from the info using code_interpreter
          print(f"✗ {BVD_ID} JSON LLM response not found. Running llm_code_interpreter_call.py...")
          llm_text = load_llm_web_response_text(
                          LLM_RESPONSES_DATA_PATH=LLM_RESPONSES_DATA_PATH,
                          BVD_ID=BVD_ID,
                          MODEL=MODEL)

          df_company = filter_company(
              RAW_DATA_PATH=MASTER_DATA_PATH,
              BVD_ID=BVD_ID
          )

          response_json = create_json_llm_response(
              llm_text=llm_text,
              data=df_company,
              CHATGPT_KEY=CHATGPT_KEY,
              MODEL=MODEL,
              print_cost=True
          )

          # Save response
          file_name = f"{LLM_RESPONSES_DATA_PATH}/{BVD_ID}_{MODEL}_json.json"
          with open(file_name, "w", encoding="utf-8") as f:
              json.dump({
                  "timestamp": datetime.now().isoformat(),
                  "response": response_json.model_dump()
              }, f, ensure_ascii=False, indent=2)

      print("✓ llm_code_interpreter_call.py completed successfully")
      return

  # No valid mode specified
  parser.error("Must specify either --bvd_id (single mode) or --bvd_ids with --batch_mode")

if __name__ == "__main__":
  main()
