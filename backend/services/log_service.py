from __future__ import annotations

from collections import deque
import re
from pathlib import Path


class LogService:
    def __init__(self, log_file: Path) -> None:
        self.log_file = log_file

    def tail(self, lines: int = 200) -> dict:
        if not self.log_file.exists():
            return {"logs": []}

        with self.log_file.open("r", encoding="utf-8", errors="ignore") as handle:
            content = list(deque(handle, maxlen=lines))

        payload = []
        for line in content:
            text = line.strip()
            if not text:
                continue
            parts = [segment.strip() for segment in text.split("|", 3)]
            if len(parts) >= 4:
                payload.append(
                    {
                        "time": parts[0],
                        "level": parts[1],
                        "source": parts[2],
                        "message": " | ".join(parts[3:]),
                        "raw": text,
                    }
                )
            else:
                runtime_match = re.match(r"^(INFO|WARNING|ERROR|DEBUG|CRITICAL):\s*(.*)$", text)
                if runtime_match:
                    payload.append(
                        {
                            "time": None,
                            "level": runtime_match.group(1),
                            "source": "runtime",
                            "message": runtime_match.group(2).strip(),
                            "raw": text,
                        }
                    )
                else:
                    payload.append({"time": None, "level": "INFO", "source": "runtime", "message": text, "raw": text})
        return {"logs": payload}
