import os
import dotenv
import pandas as pd

def load_dotenv():
    # Ref: https://stackoverflow.com/a/78972639/
    dotenv.load_dotenv()
    dotenv.load_dotenv(dotenv.find_dotenv(usecwd=True))


def create_raw_master_file(
    RAW_DATA_PATH,
    FIRMS_STATA_FILENAME,
    ORBIS_STATA_FILENAME,
    MASTER_DATA_PATH):

    data_all_firms = (
        pd.read_stata(os.path.join(RAW_DATA_PATH, FIRMS_STATA_FILENAME))
        .replace("", pd.NA)
        .sort_values(by=["bvd_id_number", "year"])
        .filter([
            "bvd_id_number", "old_bvdidnumber", "CompanyCode", "year",
            "CompanyName", "name_internat", "type_of_entity", "size_category",
            "listed_delisted_unlisted"
                ])
        .rename({
            "bvd_id_number": "BVD_ID",
            "old_bvdidnumber": "BVD_ID_old",
            "CompanyCode": "company_code",
            "year": "year",
            "CompanyName": "company_name",
            "name_internat": "company_international_name",
            "type_of_entity": "type_of_entity",
            "size_category": "category_size",
            "listed_delisted_unlisted": "category_public",
        }, axis=1)
    )

    data_orbis = (
        pd.read_stata(os.path.join(RAW_DATA_PATH, ORBIS_STATA_FILENAME))
        .replace("",pd.NA)
        .filter(["bvd_id_number",
                "controlling_bvd_id",
                "year_of_control",
                "Orbis_controlling_name",
                "controlling_firm_name",
                "start_year",
                "end_year"])
        .dropna(subset="Orbis_controlling_name")
        .rename({"bvd_id_number": "BVD_ID",
                "controlling_bvd_id": "parent_BVD_ID",
                "year_of_control": "year",
                "Orbis_controlling_name": "parent_company_name_orbis",
                "controlling_firm_name": "parent_company_name",
                "start_year": "parent_company_start_year_ownership",
                "end_year": "parent_company_end_year_ownership"}, axis=1)
        .sort_values(by=["BVD_ID", "year"])

    )


    df = (pd.merge(data_all_firms, data_orbis,
                how="left",
                on=["BVD_ID", "year"])
        .drop(["BVD_ID_old", "company_code", "category_size", ], axis=1)
        )

    df.to_csv(MASTER_DATA_PATH, index=False)

    return df

if __name__=="__main__":

    load_dotenv()

    MASTER_DATA_PATH = os.getenv("MASTER_DATA_PATH")
    RAW_DATA_PATH = os.getenv("RAW_DATA_PATH")

    create_raw_master_file(
        RAW_DATA_PATH = RAW_DATA_PATH,
        FIRMS_STATA_FILENAME = "ALL_BvDID_all_firms_update.dta",
        ORBIS_STATA_FILENAME = "PANEL_controlling_firms_orbis.dta",
        MASTER_DATA_PATH = MASTER_DATA_PATH
    )
    print("Raw master file created successfully.")
