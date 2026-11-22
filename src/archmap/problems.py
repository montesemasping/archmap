"""The problem type reported by the loader and the guard rules."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Problem:
    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.where}: {self.message} [{self.code}]"
