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

@timeit
def create_websearch_llm_response(data, CHATGPT_KEY, MODEL, print_cost=False):

    company = data.company_name.unique()[0]
    international_name = data.company_international_name.unique()[0]
    json_sample = data.to_json()

    prompt = f"""
        Research in the web the history of ownership of the indian company "{company}", internationally known as "{international_name}"

        Task:
        Web search the following infomation by year, from the year 1995 to 2015:

        - 'company_name'. Track if the company name changed, and change it according to year.
        - 'company_international_name'. The company international name.
        - 'establishment_year'. The establishment year of the company.
        - 'parent_company_name_orbis'. The name of the direct parent company if it's a subsidiary. Consider that parent companies can be part of Joint ventures. List all the direct parent companies for a given adquisition.
        - 'parent_company_ownership_years'. Ownership Dates in years. From which year to which year the parent company had ownership of the subsidiary. The range years can go before 1995 and beyond 2015. Only the years, no text. Format examples: 1992-2021, 1995-2010, 2000-2015+, 2000-2000.
        - 'parent_company_country'. The country of the headquarters of the parent company.
        - 'JV'. 1 if it's Joint Venture, 0 if not.
        - 'GUO'. The name of the Global Ultimate Owner if it's a subsidiary. In case of a Joint Venture, the part with more ownership. In case of 50:50 ownership, return the 2 parent companies with 50 percent share, write both.
        - 'GUO_country'. The country of the headquarters of the GUO company or companies.
        - 'sources'. the url of the online sources that you used to extract the information.

        Output:
        - Return a markdown text file with the information.


        """

    client = OpenAI(api_key=CHATGPT_KEY)

    response = client.responses.create(
        model=MODEL,
        tools=[{"type": "web_search"}],
        input=prompt
    )

    if print_cost:
        print_openai_cost_from_response(MODEL, response)

    return response

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="LLM company web search call.")
    parser.add_argument("--bvd_id", type=str, required=True, help="Bureau van Dijk company ID")
    parser.add_argument("--model", type=str, default="gpt-5", help="LLM model to use (default: gpt-5)")
    args = parser.parse_args()

    BVD_ID = args.bvd_id
    MODEL = args.model

    load_dotenv()
    MASTER_DATA_PATH =  ${MASTER_DATA_PATH}
    LLM_RESPONSES_DATA_PATH =  ${LLM_RESPONSES_DATA_PATH}


    # Check if LLM response already exists
    file_name = f"{LLM_RESPONSES_DATA_PATH}/{BVD_ID}_{MODEL}_websearch.json"
    if os.path.exists(file_name):
        print(f"✓ Web search LLM response already exists: {file_name}")
    else:
        # Step 1: Scrapping information using web_search
        print(f"✗ Websearch LLM response not found. Running llm_web_search_call.py...")

        df_company = filter_company(
            RAW_DATA_PATH=MASTER_DATA_PATH,
            BVD_ID=BVD_ID
        )
        response_web = create_websearch_llm_response(
            data=df_company,
            CHATGPT_KEY=os.getenv("CHATGPT_KEY"),
            MODEL=MODEL,
            print_cost=True
        )
        # Save response
        with open(file_name, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "response": response_web.model_dump()
            }, f, ensure_ascii=False, indent=2)

        print(f"✓ llm_web_search_call.py completed successfully")
