from pathlib import Path
import json

import pyreadr

RAW_FILE = Path("datasets/raw/TEP_Faulty_Training.RData")
RUNTIME_DIR = Path("datasets/runtime")


def main():
    result = pyreadr.read_r(str(RAW_FILE))
    df = next(iter(result.values()))

    catalog = {}

    faults = sorted(int(f) for f in df["faultNumber"].unique())

    for fault in faults:
        print(f"Extracting fault {fault}...")

        fault_df = df[df["faultNumber"] == fault]

        runs = sorted(
            int(r) for r in fault_df["simulationRun"].unique()
        )

        fault_dir = RUNTIME_DIR / f"fault_{fault}"
        fault_dir.mkdir(parents=True, exist_ok=True)

        for run in runs:
            run_df = (
                fault_df[fault_df["simulationRun"] == run]
                .sort_values("sample")
                .reset_index(drop=True)
            )

            run_df.to_parquet(
                fault_dir / f"run_{run}.parquet",
                index=False
            )

        catalog[f"fault_{fault}"] = {
            "run_count": len(runs),
            "runs": runs
        }

        print(f"  -> {len(runs)} runs, {len(fault_df)} samples")

    # Merge into existing catalog (preserve fault_0)
    catalog_path = RUNTIME_DIR / "catalog.json"

    if catalog_path.exists():
        with open(catalog_path, encoding="utf-8") as f:
            existing = json.load(f)

        existing.update(catalog)
        catalog = existing

    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)

    print(f"\nDone. Catalog has {len(catalog)} fault types:")
    for key in sorted(catalog):
        print(f"  {key}: {catalog[key]['run_count']} runs")


if __name__ == "__main__":
    main()
