import os
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

CGROUP_ROOT = Path("/sys/fs/cgroup")
PROC_SELF_CGROUP = Path("/proc/self/cgroup")
PROC_UPTIME = Path("/proc/uptime")

CPU_STALE_WINDOW_SECONDS = 10.0


def _read_int(path: Path) -> Optional[int]:
    try:
        return int(path.read_text().strip().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _resolve_cgroup(
    relative: str,
    controllers: tuple[str, ...],
) -> list[Path]:
    resolved = []

    try:
        for line in PROC_SELF_CGROUP.read_text().splitlines():
            parts = line.split(":", 2)
            if len(parts) != 3:
                continue

            _, controller_field, cgroup_path = parts
            cgroup_path = cgroup_path.strip().lstrip("/")

            if not cgroup_path:
                continue

            for controller in controller_field.split(","):
                if controller in controllers:
                    if controller:
                        candidate = (
                            CGROUP_ROOT
                            / controller
                            / cgroup_path
                            / relative
                        )
                    else:
                        candidate = (
                            CGROUP_ROOT
                            / cgroup_path
                            / relative
                        )
                    resolved.append(candidate)
    except OSError:
        pass

    root_candidate = CGROUP_ROOT / relative
    if root_candidate not in resolved:
        resolved.append(root_candidate)

    return resolved


@dataclass(slots=True)
class ContainerMetricsSnapshot:

    cgroup_version: Optional[int]

    cpu_percent: float

    cpu_time_seconds: float

    cpu_cores: Optional[float]

    memory_used_bytes: Optional[int]

    memory_limit_bytes: Optional[int]

    memory_percent: Optional[float]

    uptime_seconds: float

    process_count: Optional[int]

    def to_dict(self) -> dict:
        return asdict(self)


class ContainerMetricsCollector:

    def __init__(self) -> None:

        self._lock = threading.Lock()

        self._start_monotonic = time.monotonic()

        self._cgroup_version = self._detect_cgroup_version()

        self._cpu_usage_usec_path = self._find(
            "cpu.stat",
            ("cpu", ""),
            key="usage_usec",
        )
        self._cpuacct_usage_path = self._find(
            "cpuacct.usage",
            ("cpu", "cpuacct"),
        )
        self._cpu_max_path = self._find(
            "cpu.max",
            ("cpu", ""),
        )
        self._cfs_quota_path = self._find(
            "cpu.cfs_quota_us",
            ("cpu",),
        )
        self._cfs_period_path = self._find(
            "cpu.cfs_period_us",
            ("cpu",),
        )
        self._memory_current_path = self._find(
            "memory.current",
            ("memory", ""),
        )
        self._memory_usage_path = self._find(
            "memory.usage_in_bytes",
            ("memory",),
        )
        self._memory_max_path = self._find(
            "memory.max",
            ("memory", ""),
        )
        self._memory_limit_path = self._find(
            "memory.limit_in_bytes",
            ("memory",),
        )
        self._pids_current_path = self._find(
            "pids.current",
            ("pids", ""),
        )

        self._prev_cpu_usage_usec = (
            self._read_cpu_usage_usec() or 0
        )
        self._prev_wall = time.monotonic()

    def _detect_cgroup_version(self) -> Optional[int]:
        if (CGROUP_ROOT / "cgroup.controllers").exists():
            return 2
        if (CGROUP_ROOT / "cpu").exists() or (
            CGROUP_ROOT / "memory"
        ).exists():
            return 1
        return None

    def _find(
        self,
        relative: str,
        controllers: tuple[str, ...],
        key: Optional[str] = None,
    ) -> Optional[Path]:
        for candidate in _resolve_cgroup(
            relative,
            controllers,
        ):
            if not candidate.exists():
                continue
            if key is not None:
                content = _read_text(candidate)
                if content is None or key not in content:
                    continue
            return candidate
        return None

    def _read_cpu_usage_usec(self) -> Optional[int]:
        if self._cpu_usage_usec_path is not None:
            content = _read_text(
                self._cpu_usage_usec_path
            )
            if content is not None:
                for line in content.splitlines():
                    key, _, value = line.partition(" ")
                    if key == "usage_usec":
                        try:
                            return int(value)
                        except ValueError:
                            return None
                return None

        if self._cpuacct_usage_path is not None:
            nanoseconds = _read_int(
                self._cpuacct_usage_path
            )
            if nanoseconds is not None:
                return nanoseconds // 1000

        return self._read_proc_self_cpu_usec()

    def _read_proc_self_cpu_usec(self) -> Optional[int]:
        content = _read_text(Path("/proc/self/stat"))
        if content is None:
            return None
        try:
            rest = content[content.rfind(")") + 2 :]
            fields = rest.split()
            hz = float(
                os.sysconf("SC_CLK_TCK")
                or 100
            )
            utime = int(fields[11])
            stime = int(fields[12])
            return int((utime + stime) * 1_000_000 / hz)
        except (IndexError, ValueError, OSError):
            return None

    def _read_memory_used_bytes(self) -> Optional[int]:
        if self._memory_current_path is not None:
            return _read_int(
                self._memory_current_path
            )
        if self._memory_usage_path is not None:
            return _read_int(
                self._memory_usage_path
            )

        content = _read_text(Path("/proc/self/status"))
        if content is None:
            return None
        for line in content.splitlines():
            if line.startswith("VmRSS:"):
                try:
                    return int(
                        line.split()[1]
                    ) * 1024
                except (IndexError, ValueError):
                    return None
        return None

    def _read_memory_limit_bytes(self) -> Optional[int]:
        if self._memory_max_path is not None:
            content = _read_text(
                self._memory_max_path
            )
            if content is not None and content != "max":
                try:
                    return int(content)
                except ValueError:
                    return None
            return None
        if self._memory_limit_path is not None:
            limit = _read_int(
                self._memory_limit_path
            )
            if limit is not None and limit < (1 << 60):
                return limit
            return None
        return None

    def _read_cpu_quota_cores(self) -> Optional[float]:
        if self._cpu_max_path is not None:
            content = _read_text(self._cpu_max_path)
            if content is not None:
                parts = content.split()
                if len(parts) == 2 and parts[0] != "max":
                    try:
                        quota = int(parts[0])
                        period = int(parts[1])
                        if period > 0:
                            return quota / period
                    except ValueError:
                        pass
        elif self._cfs_quota_path is not None and (
            self._cfs_period_path is not None
        ):
            quota = _read_int(self._cfs_quota_path)
            period = _read_int(self._cfs_period_path)
            if (
                quota is not None
                and period is not None
                and quota > 0
                and period > 0
            ):
                return quota / period
        return None

    def _read_process_count(self) -> Optional[int]:
        if self._pids_current_path is not None:
            return _read_int(self._pids_current_path)
        return None

    def _read_container_uptime(self) -> Optional[float]:
        try:
            boot_seconds = float(
                PROC_UPTIME.read_text().split()[0]
            )
            content = _read_text(Path("/proc/1/stat"))
            if content is None:
                return None
            rest = content[content.rfind(")") + 2 :]
            fields = rest.split()
            start_ticks = int(fields[19])
            hz = float(
                os.sysconf("SC_CLK_TCK")
                or 100
            )
            return boot_seconds - (start_ticks / hz)
        except (
            OSError,
            IndexError,
            ValueError,
            TypeError,
        ):
            return None

    def snapshot(self) -> ContainerMetricsSnapshot:
        with self._lock:
            return self._snapshot()

    def _snapshot(self) -> ContainerMetricsSnapshot:

        now = time.monotonic()
        cpu_usage_usec = (
            self._read_cpu_usage_usec() or 0
        )

        delta_wall = now - self._prev_wall
        delta_usage = (
            cpu_usage_usec
            - self._prev_cpu_usage_usec
        )

        if (
            delta_wall > 0
            and delta_usage > 0
            and delta_wall <= CPU_STALE_WINDOW_SECONDS
        ):
            cores_used = (
                delta_usage
                / 1_000_000
                / delta_wall
            )
            quota_cores = self._read_cpu_quota_cores()
            denominator = (
                quota_cores
                if quota_cores
                else os.cpu_count() or 1
            )
            cpu_percent = (
                cores_used / denominator
            ) * 100.0
        else:
            cpu_percent = 0.0

        self._prev_cpu_usage_usec = cpu_usage_usec
        self._prev_wall = now

        cpu_time_usec = self._read_cpu_usage_usec()
        cpu_time_seconds = (
            (cpu_time_usec or 0) / 1_000_000
        )

        memory_used = self._read_memory_used_bytes()
        memory_limit = self._read_memory_limit_bytes()
        memory_percent = None
        if (
            memory_used is not None
            and memory_limit is not None
            and memory_limit > 0
        ):
            memory_percent = (
                memory_used / memory_limit
            ) * 100.0

        uptime = self._read_container_uptime()
        if uptime is None:
            uptime = (
                time.monotonic()
                - self._start_monotonic
            )

        return ContainerMetricsSnapshot(
            cgroup_version=self._cgroup_version,
            cpu_percent=round(cpu_percent, 3),
            cpu_time_seconds=round(
                cpu_time_seconds,
                6,
            ),
            cpu_cores=self._read_cpu_quota_cores(),
            memory_used_bytes=memory_used,
            memory_limit_bytes=memory_limit,
            memory_percent=(
                round(memory_percent, 3)
                if memory_percent is not None
                else None
            ),
            uptime_seconds=round(uptime, 3),
            process_count=self._read_process_count(),
        )
