"""Filesystem locations the orchestrator works with, all rooted at the repository."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    root: Path
    config: Path
    data: Path
    build: Path
    dist: Path

    @classmethod
    def from_root(
        cls, root: Path, *, config: Path | None = None, data: Path | None = None
    ) -> Paths:
        return cls(
            root=root,
            config=config or root / "config",
            data=data or root / "data",
            build=root / "build",
            dist=root / "dist",
        )

    @property
    def matches(self) -> Path:
        return self.config / "matches.yaml"

    @property
    def report(self) -> Path:
        return self.build / "report.json"

    @property
    def prices(self) -> Path:
        return self.data / "prices"
