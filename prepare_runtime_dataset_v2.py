from pathlib import Path
import json

import pandas as pd
import pyreadr


RAW_DIR = Path("datasets/raw")
RUNTIME_DIR = Path("datasets/runtime")

FAULT_FREE_FILE = RAW_DIR / "TEP_FaultFree_Testing.RData"
FAULTY_FILE = RAW_DIR / "TEP_Faulty_Testing.RData"


def load_rdata(path: Path) -> pd.DataFrame:
    result = pyreadr.read_r(str(path))

    if len(result) != 1:
        raise ValueError(
            f"Expected exactly one object in {path}"
        )

    return next(iter(result.values()))


def save_run(
    df: pd.DataFrame,
    fault_number: int,
    run_number: int,
):
    fault_dir = RUNTIME_DIR / f"fault_{fault_number}"
    fault_dir.mkdir(parents=True, exist_ok=True)

    output_file = fault_dir / f"run_{run_number}.parquet"

    df.to_parquet(
        output_file,
        index=False
    )


def build_fault_free_catalog():

    print("\nProcessing fault-free dataset...")

    df = load_rdata(FAULT_FREE_FILE)

    runs = sorted(
        int(run)
        for run in df["simulationRun"].unique()
    )

    # for run in runs:

    #     run_df = (
    #         df[
    #             df["simulationRun"] == run
    #         ]
    #         .sort_values("sample")
    #         .reset_index(drop=True)
    #     )

    #     save_run(
    #         run_df,
    #         fault_number=0,
    #         run_number=run
    #     )

    return {
        "fault_0": {
            "run_count": len(runs),
            "runs": runs
        }
    }


def build_faulty_catalog():

    print("\nProcessing faulty dataset...")

    df = load_rdata(FAULTY_FILE)

    catalog = {}

    faults = sorted(
        int(fault)
        for fault in df["faultNumber"].unique()
    )

    for fault in faults:

        print(
            f"Processing fault {fault}"
        )

        fault_df = df[
            df["faultNumber"] == fault
        ]

        runs = sorted(
            int(run)
            for run in fault_df[
                "simulationRun"
            ].unique()
        )

        catalog[f"fault_{fault}"] = {
            "run_count": len(runs),
            "runs": runs
        }

        # for run in runs:

        #     run_df = (
        #         fault_df[
        #             fault_df[
        #                 "simulationRun"
        #             ] == run
        #         ]
        #         .sort_values("sample")
        #         .reset_index(drop=True)
        #     )

        #     save_run(
        #         run_df,
        #         fault_number=fault,
        #         run_number=run
        #     )

    return catalog


def save_catalog(catalog):

    catalog_path = (
        RUNTIME_DIR / "catalog.json"
    )

    with open(
        catalog_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            catalog,
            f,
            indent=2
        )

    print(
        f"\nCatalog saved to:"
        f"\n{catalog_path}"
    )


def main():

    RUNTIME_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    catalog = {}

    catalog.update(
        build_fault_free_catalog()
    )

    catalog.update(
        build_faulty_catalog()
    )

    save_catalog(catalog)

    print("\nDataset preparation complete.")


if __name__ == "__main__":
    main()