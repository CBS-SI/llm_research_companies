import os
import time
import json
import dotenv
import argparse
import numpy as np
import pandas as pd
from openai import OpenAI
from functools import wraps
from datetime import datetime

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
          ['year', 'company_name', 'company_international_name', 'establishment_year',
          'parent_company_name_orbis', 'parent_company_country', 'JV', 'GUO',
          'GUO_country', 'parent_company_ownership_years', 'sources'].

        Formatting rules:
        - If multiple values exist for the following fields use list notation: parent_company_name_orbis, parent_company_country, GUO, GUO_country, 'parent_company_ownership_years'. Examples: ["Parent Company 1", "Parent Company 2"], [India, USA], [1992-2021, 1995-2010].
        - 'company_name', 'company_international_name', and 'parent_company_name' company and parent company naming of the output have to match the naming of the pandas DataFrame in JSON format.
        - Output a valid and readable JSON — not code.


        Output:
        - Only the final JSON with the updated columns and years, from 1995 to 2015.
        - No comment, output should be a readable JSON file.
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

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="LLM company call.")
    parser.add_argument("--bvd_id", type=str, required=True, help="Bureau van Dijk company ID")
    parser.add_argument("--model", type=str, default="gpt-5", help="LLM model to use (default: gpt-5)")
    args = parser.parse_args()

    BVD_ID = args.bvd_id
    MODEL = args.model

    load_dotenv()

    RAW_OWNERSHIP_DATA_PATH = os.getenv("RAW_OWNERSHIP_DATA_PATH")
    MASTER_DATA_PATH = os.getenv("MASTER_DATA_PATH")
    LLM_RESPONSES_DATA_PATH = os.getenv("LLM_RESPONSES_DATA_PATH")
    COMPANY_FOLDER_PATH = os.getenv("COMPANY_FOLDER_PATH")

    # Check if LLM response already exists
    file_name = f"{LLM_RESPONSES_DATA_PATH}/{BVD_ID}_{MODEL}_json.json"
    if os.path.exists(file_name):
        print(f"✓ JSON LLM response already exists: {file_name}")
    else:
        # Step 2: Creating a valid panel data from the info using code_interpreter
        print(f"✗ JSON LLM response not found. Running llm_code_interpreter_call.py...")
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
            CHATGPT_KEY=os.getenv("CHATGPT_KEY"),
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

    print(f"✓ llm_code_interpreter_call.py completed successfully")
