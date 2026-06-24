import json
from pathlib import Path
from typing import Any

class Catalog:

    def __init__(self, catalog_path: str) -> None:
        self.catalog_path: Path = Path(catalog_path)
        self.catalog: dict[str, Any]

        with open(
            self.catalog_path,
            "r",
            encoding="utf-8"
        ) as f:
            self.catalog = json.load(f)

    def get_faults(self) -> list[int]:

        faults = []

        for key in self.catalog.keys():
            fault = int(
                key.replace("fault_", "")
            )
            faults.append(fault)

        return sorted(faults)

    def get_runs(
        self,
        fault: int
    ) -> list[int]:

        key = f"fault_{fault}"

        if key not in self.catalog:
            raise ValueError(
                f"Unknown fault: {fault}"
            )

        return self.catalog[key]["runs"]

    def get_run_count(
        self,
        fault: int
    ) -> int:

        key = f"fault_{fault}"

        return self.catalog[key]["run_count"]

    def fault_exists(
        self,
        fault: int
    ) -> bool:

        return f"fault_{fault}" in self.catalog
