import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

SERVICE_DIRS = [
    PROJECT_ROOT / "services",
    PROJECT_ROOT / "services" / "sensor-generator",
    PROJECT_ROOT / "services" / "edge-detector",
    PROJECT_ROOT / "services" / "data-management",
    PROJECT_ROOT / "services" / "orchestrator",
    PROJECT_ROOT / "services" / "classifier",
    PROJECT_ROOT / "services" / "shared",
]

for d in SERVICE_DIRS:
    if d.exists() and str(d) not in sys.path:
        sys.path.insert(0, str(d))
