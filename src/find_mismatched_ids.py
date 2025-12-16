from pathlib import Path

def find_mismatched_ids():
    """
    Find IDs that exist in one folder but not the other.
    Compares processed_data/company_files/*_panel with processed_data/responses/*_json.json
    """
    # Define the paths to your folders
    base_path = Path('/Users/pg/Library/CloudStorage/Dropbox-CBS/Pipe Galera/llm_research_companies_data/processed_data')
    company_files_dir = base_path / 'company_files'
    responses_dir = base_path / 'responses'

    # Extract IDs from company_files (files ending with _panel.csv)
    company_ids = set()
    for file in company_files_dir.glob('*_gpt-5_panel.csv'):
        # Extract ID from filename like "IN*1226255_gpt-5_panel.csv"
        filename = file.name
        # Remove the '_panel.csv' suffix
        id_part = filename.replace('_gpt-5_panel.csv', '')
        company_ids.add(id_part)

    # Extract IDs from responses (files ending with _websearch.json)
    response_ids = set()

    for file in responses_dir.glob('*_gpt-5_websearch.json'):
        # Extract ID from filename like "INA005609994_gpt-5_websearch.json"
        filename = file.name
        # Remove the '_websearch.json' suffix
        id_part = filename.replace('_gpt-5_websearch.json', '')
        response_ids.add(id_part)

    # Find IDs in company_files but not in responses
    only_in_company = company_ids - response_ids

    # Find IDs in responses but not in company_files
    only_in_responses = response_ids - company_ids

    # Print results
    print(f"Total IDs in company_files: {len(company_ids)}")
    print(f"Total IDs in responses: {len(response_ids)}")
    print(f"\nIDs only in company_files ({len(only_in_company)}):")
    for id in sorted(only_in_company):
        print(f"  {id}")

    print(f"\nIDs only in responses ({len(only_in_responses)}):")
    for id in sorted(only_in_responses):
        print(f"  {id}")

    # Optional: Save to files
    if only_in_company:
        with open('ids_missing_responses.txt', 'w') as f:
            f.write('\n'.join(sorted(only_in_company)))
        print("\nSaved IDs missing responses to: ids_missing_responses.txt")

    if only_in_responses:
        with open('ids_missing_company_files.txt', 'w') as f:
            f.write('\n'.join(sorted(only_in_responses)))
        print("\nSaved IDs missing company files to: ids_missing_company_files.txt")

    return only_in_company, only_in_responses


if __name__ == "__main__":
    find_mismatched_ids()
