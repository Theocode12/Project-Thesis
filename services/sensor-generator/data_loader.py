from pathlib import Path

import pandas as pd

class DataLoader:

    def __init__(
        self,
        runtime_directory: str
    ) -> None:
        self.runtime_directory: Path = Path(
            runtime_directory
        )

    def load_fault_run(
        self,
        fault: int,
        run: int
    ) -> pd.DataFrame:

        file_path = (
            self.runtime_directory
            / f"fault_{fault}"
            / f"run_{run}.parquet"
        )

        if not file_path.exists():

            raise FileNotFoundError(
                f"Dataset not found: {file_path}"
            )

        return pd.read_parquet(
            file_path
        )
