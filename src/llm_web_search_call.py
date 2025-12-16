import os
import time
import json
import dotenv
import argparse
import warnings
import numpy as np
import pandas as pd
import asyncio
from openai import OpenAI
from functools import wraps
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Semaphore

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

@timeit
def create_websearch_llm_response(data, CHATGPT_KEY, MODEL, print_cost=False, rate_limiter=None, max_retries=3):

    company = data.orbis_company_name.unique()[0]
    international_name = data.company_international_name.unique()[0]

    prompt = f"""
        Research in the web the history of ownership of the indian company "{company}", internationally known as "{international_name}"

        Task:
        Web search the following infomation by year, from the year 1995 to 2015:

        - 'orbis_company_name': Legal firm name. Track if the company name changed, and change it according to year.
        - 'company_international_name': The company international name.
        - 'establishment_year': The establishment year of the company.
        - 'parent_company_name_orbis': The name of the direct parent company if it's a subsidiary. Consider that parent companies can be part of Joint ventures. List all the direct parent companies for a given adquisition.
        - 'parent_company_ownership_years': Ownership Dates in years. From which year to which year the parent company had ownership of the subsidiary. The range years can go before 1995 and beyond 2015. Only the years, no text. Format examples: 1992-2021, 1995-2010, 2000-2015+, 2000-2000.
        - 'parent_company_country': The country of the headquarters of the parent company.
        - 'JV': 1 if it's Joint Venture, 0 if not.
        - 'GUO': The name of the Global Ultimate Owner if it's a subsidiary. In case of a Joint Venture, the part with more ownership. In case of 50:50 ownership, return the 2 parent companies with 50 percent share, write both.
        - 'GUO_country': The country of the headquarters of the GUO company or companies.
        - 'IBG': 1 if the company is part of a "Indian Business Group", 0 otherwise. "IBG" is 1 when the company is part of a recognized Indian business group (IBG) — i.e. a multi-firm group with identifiable common control, typically listed among India's known industrial groups (e.g., Tata, Mahindra, Reliance, Birla, Bajaj, TVS, L&T, Kalyani, Murugappa, etc.).
        - 'sources': the full url of the online sources that you used to extract the information. It cannot be formated as "S1,S2,S3"

        Output:
        - Return a markdown text file with the information.
        """

    client = OpenAI(api_key=CHATGPT_KEY)

    # Retry logic for rate limit errors
    for attempt in range(max_retries):
        try:
            # Acquire semaphore if rate limiter is provided
            if rate_limiter:
                rate_limiter.acquire()

            try:
                response = client.responses.create(
                    model=MODEL,
                    tools=[{"type": "web_search"}],
                    input=prompt
                )

                if print_cost:
                    print_openai_cost_from_response(MODEL, response)

                return response
            finally:
                # Release semaphore after request completes
                if rate_limiter:
                    rate_limiter.release()

        except Exception as e:
            error_msg = str(e)
            if "rate_limit" in error_msg.lower() and attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 5  # Exponential backoff: 5s, 10s, 20s
                print(f"Rate limit hit for {company}. Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                raise

def process_single_company(BVD_ID, MODEL, MASTER_DATA_PATH, LLM_RESPONSES_DATA_PATH, CHATGPT_KEY, rate_limiter=None):
    """Process a single company web search"""

    file_name = f"{LLM_RESPONSES_DATA_PATH}/{BVD_ID}_{MODEL}_websearch.json"

    # Check if already exists
    if os.path.exists(file_name):
        print(f"✓ [{BVD_ID}] Already exists, skipping")
        return {"bvd_id": BVD_ID, "status": "skipped", "file": file_name}

    try:
        print(f"⚙ [{BVD_ID}] Starting web search...")

        df_company = filter_company(
            RAW_DATA_PATH=MASTER_DATA_PATH,
            BVD_ID=BVD_ID
        )

        response_web = create_websearch_llm_response(
            data=df_company,
            CHATGPT_KEY=CHATGPT_KEY,
            MODEL=MODEL,
            print_cost=True,
            rate_limiter=rate_limiter
        )

        # Save response
        with open(file_name, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "response": response_web.model_dump()
            }, f, ensure_ascii=False, indent=2)

        print(f"✓ [{BVD_ID}] Completed successfully")
        return {"bvd_id": BVD_ID, "status": "success", "file": file_name}

    except Exception as e:
        print(f"✗ [{BVD_ID}] Failed: {str(e)}")
        return {"bvd_id": BVD_ID, "status": "failed", "error": str(e)}

def process_companies_concurrent(bvd_ids, MODEL, MASTER_DATA_PATH, LLM_RESPONSES_DATA_PATH, CHATGPT_KEY, max_concurrent=5):
    """Process multiple companies concurrently with rate limiting"""

    print(f"\n{'='*60}")
    print(f"Processing {len(bvd_ids)} companies with max {max_concurrent} concurrent requests")
    print(f"Model: {MODEL}")
    print(f"{'='*60}\n")

    # Create rate limiter (semaphore to limit concurrent requests)
    rate_limiter = Semaphore(max_concurrent)

    start_time = time.perf_counter()
    results = []

    # Use ThreadPoolExecutor for concurrent execution
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {
            executor.submit(
                process_single_company,
                bvd_id,
                MODEL,
                MASTER_DATA_PATH,
                LLM_RESPONSES_DATA_PATH,
                CHATGPT_KEY,
                rate_limiter
            ): bvd_id for bvd_id in bvd_ids
        }

        # Collect results as they complete
        from concurrent.futures import as_completed
        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    end_time = time.perf_counter()
    total_time = end_time - start_time

    # Print summary
    print(f"\n{'='*60}")
    print(f"SUMMARY - Total time: {total_time:.1f}s")
    print(f"{'='*60}")

    success = sum(1 for r in results if r["status"] == "success")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "failed")

    print(f"✓ Success: {success}")
    print(f"⊘ Skipped: {skipped}")
    print(f"✗ Failed: {failed}")

    if failed > 0:
        print("\nFailed companies:")
        for r in results:
            if r["status"] == "failed":
                print(f"  - {r['bvd_id']}: {r['error']}")

    print(f"{'='*60}\n")

    return results

def main(argv=None):

    parser = argparse.ArgumentParser(description="LLM company web search call.")
    parser.add_argument("--bvd_id", type=str, help="Single Bureau van Dijk company ID")
    parser.add_argument("--bvd_ids", type=str, nargs='+', help="Multiple Bureau van Dijk company IDs")
    parser.add_argument("--model", type=str, default="gpt-5", help="LLM model to use (default: gpt-5)")
    parser.add_argument("--max_concurrent", type=int, default=5, help="Maximum concurrent requests (default: 5)")
    parser.add_argument("--batch_size", type=int, default=None, help="Process companies in batches of this size (default: process all at once)")
    args = parser.parse_args(argv)

    # Validate input
    if not args.bvd_id and not args.bvd_ids:
        parser.error("Either --bvd_id or --bvd_ids must be provided")

    if args.bvd_id and args.bvd_ids:
        parser.error("Cannot use both --bvd_id and --bvd_ids at the same time")

    MODEL = args.model

    load_dotenv()
    MASTER_DATA_PATH = os.getenv("MASTER_DATA_PATH")
    LLM_RESPONSES_DATA_PATH = os.getenv("LLM_RESPONSES_DATA_PATH")
    CHATGPT_KEY = os.getenv("CHATGPT_KEY")

    if not os.path.exists(LLM_RESPONSES_DATA_PATH):
        os.makedirs(LLM_RESPONSES_DATA_PATH)

    # Process single company (backward compatible)
    if args.bvd_id:
        result = process_single_company(
            BVD_ID=args.bvd_id,
            MODEL=MODEL,
            MASTER_DATA_PATH=MASTER_DATA_PATH,
            LLM_RESPONSES_DATA_PATH=LLM_RESPONSES_DATA_PATH,
            CHATGPT_KEY=CHATGPT_KEY
        )
        return result

    # Process multiple companies concurrently
    else:
        bvd_ids = args.bvd_ids

        # If batch_size is specified, process in batches
        if args.batch_size:
            total_batches = (len(bvd_ids) + args.batch_size - 1) // args.batch_size
            all_results = []

            print(f"\n{'='*60}")
            print(f"BATCH PROCESSING MODE")
            print(f"Total companies: {len(bvd_ids)}")
            print(f"Batch size: {args.batch_size}")
            print(f"Total batches: {total_batches}")
            print(f"{'='*60}\n")

            for batch_num in range(total_batches):
                start_idx = batch_num * args.batch_size
                end_idx = min(start_idx + args.batch_size, len(bvd_ids))
                batch_companies = bvd_ids[start_idx:end_idx]

                print(f"\n{'='*60}")
                print(f"BATCH {batch_num + 1}/{total_batches}")
                print(f"Processing companies {start_idx + 1} to {end_idx} of {len(bvd_ids)}")
                print(f"{'='*60}\n")

                # Process this batch
                batch_results = process_companies_concurrent(
                    bvd_ids=batch_companies,
                    MODEL=MODEL,
                    MASTER_DATA_PATH=MASTER_DATA_PATH,
                    LLM_RESPONSES_DATA_PATH=LLM_RESPONSES_DATA_PATH,
                    CHATGPT_KEY=CHATGPT_KEY,
                    max_concurrent=args.max_concurrent
                )
                all_results.extend(batch_results)

            # Print final summary
            print(f"\n{'='*60}")
            print(f"FINAL SUMMARY - ALL BATCHES")
            print(f"{'='*60}")
            success = sum(1 for r in all_results if r["status"] == "success")
            skipped = sum(1 for r in all_results if r["status"] == "skipped")
            failed = sum(1 for r in all_results if r["status"] == "failed")
            print(f"Total companies: {len(all_results)}")
            print(f"✓ Success: {success}")
            print(f"⊘ Skipped: {skipped}")
            print(f"✗ Failed: {failed}")
            print(f"{'='*60}\n")

            return all_results

        # No batching - process all at once
        else:
            results = process_companies_concurrent(
                bvd_ids=bvd_ids,
                MODEL=MODEL,
                MASTER_DATA_PATH=MASTER_DATA_PATH,
                LLM_RESPONSES_DATA_PATH=LLM_RESPONSES_DATA_PATH,
                CHATGPT_KEY=CHATGPT_KEY,
                max_concurrent=args.max_concurrent
            )
            return results

if __name__ == "__main__":
  main()
