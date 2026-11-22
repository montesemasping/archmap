"""The problem type reported by the loader and the guard rules."""

import re
from dataclasses import dataclass

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")


def _escape(text: str) -> str:
    return _CONTROL.sub(lambda m: "\\u%04x" % ord(m.group()), text)


@dataclass(frozen=True)
class Problem:
    code: str
    where: str
    message: str

    def __str__(self) -> str:
        # Escape control characters so one problem always prints as one line.
        return _escape(f"{self.where}: {self.message} [{self.code}]")
