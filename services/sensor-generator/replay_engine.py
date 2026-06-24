import random
from typing import Optional

import pandas as pd

from catalog import Catalog
from data_loader import DataLoader

class ReplayEngine:

    def __init__(
        self,
        loader: DataLoader,
        catalog: Catalog
    ) -> None:

        self.loader = loader
        self.catalog = catalog
        self.running: bool = False
        self.current_fault: Optional[int] = None
        self.current_run: Optional[int] = None
        self.current_position: int = 0
        self.current_dataframe: Optional[pd.DataFrame] = None

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def reset(self) -> None:
        self.current_position = 0

    def set_fault(
        self,
        fault: int
    ) -> None:

        if not self.catalog.fault_exists(
            fault
        ):
            raise ValueError(
                f"Unknown fault: {fault}"
            )

        runs = self.catalog.get_runs(
            fault
        )

        selected_run = random.choice(
            runs
        )

        self.set_stream(
            fault=fault,
            run=selected_run
        )

    def set_stream(
        self,
        fault: int,
        run: int
    ) -> None:

        dataframe = (
            self.loader.load_fault_run(
                fault=fault,
                run=run
            )
        )

        self.current_fault = fault
        self.current_run = run

        self.current_dataframe = dataframe

        self.current_position = 0

    def next_sample(self) -> Optional[dict]:

        if not self.running:
            return None

        if self.current_dataframe is None:
            return None

        if (
            self.current_position
            >= len(
                self.current_dataframe
            )
        ):
            self._handle_end_of_run()

        row = self.current_dataframe.iloc[
            self.current_position
        ]

        self.current_position += 1

        payload = row.to_dict()

        payload["_stream"] = {
            "fault": self.current_fault,
            "run": self.current_run
        }

        return payload

    def _handle_end_of_run(self) -> None:

        runs = self.catalog.get_runs(
            self.current_fault
        )

        next_run = random.choice(
            runs
        )

        self.set_stream(
            fault=self.current_fault,
            run=next_run
        )

    def get_status(self) -> dict:

        return {
            "running": self.running,
            "fault": self.current_fault,
            "run": self.current_run,
            "position": self.current_position,
            "loaded": (
                self.current_dataframe
                is not None
            )
        }
