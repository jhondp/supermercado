"""Write approved matches into the head of matches.yaml without disturbing its layout.

The head (everything above the proposals marker) is edited as text, line by line, so
comments and formatting survive; only the new entry value is produced by yaml.safe_dump.
The generated proposals section below the marker is preserved byte for byte.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

from supermercado.config import ConfigError, load_config
from supermercado.pipeline.propose import MARKER

ConfirmReplace = Callable[[str, str], bool]
Pair = tuple[str, str]

_TOP_LEVEL = re.compile(r"^[^\s#]")
_CHILD = re.compile(r"^(?P<indent>[ ]+)(?P<key>[^\s:#][^:]*?):(?:\s|$)")
_DEFAULT_INDENT = "  "


class ApproveError(RuntimeError):
    """matches.yaml could not be updated; the file on disk is unchanged."""


@dataclass(frozen=True)
class NewMatch:
    item_id: str
    store: str
    sku: str
    size: float
    approved: date
    url: str | None = None


@dataclass
class ApplyResult:
    added: list[Pair] = field(default_factory=list)
    replaced: list[Pair] = field(default_factory=list)
    kept: list[Pair] = field(default_factory=list)


@dataclass
class WriteResult(ApplyResult):
    backup: Path | None = None


def format_entry(match: NewMatch) -> str:
    """Flow-style YAML value for one match: quoted SKU, then url (Lider), size, approved."""
    data: dict[str, object] = {"sku": match.sku}
    if match.url:
        data["url"] = match.url
    data["size"] = float(match.size)
    data["approved"] = match.approved
    dumped = yaml.safe_dump(
        data, default_flow_style=True, sort_keys=False, allow_unicode=True, width=1_000_000
    )
    return dumped.strip()


def _split(text: str) -> tuple[str, str]:
    at = text.find(MARKER)
    return (text, "") if at < 0 else (text[:at], text[at:])


def _item_line(body: list[str], item_id: str) -> int | None:
    key = re.compile(rf"^{re.escape(item_id)}:(?P<rest>.*)$")
    for index, line in enumerate(body):
        found = key.match(line.rstrip("\r\n"))
        if not found:
            continue
        rest = found["rest"].strip()
        if rest and not rest.startswith("#"):
            raise ApproveError(
                f"matches.yaml: {item_id!r} uses an inline mapping (line {index + 1}); "
                "edit it by hand into one store per line"
            )
        return index
    return None


def _region_end(body: list[str], start: int) -> int:
    for index in range(start + 1, len(body)):
        if _TOP_LEVEL.match(body[index]):
            return index
    return len(body)


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _merge(
    body: list[str], match: NewMatch, confirm_replace: ConfirmReplace, result: ApplyResult
) -> None:
    pair = (match.item_id, match.store)
    entry = format_entry(match)
    start = _item_line(body, match.item_id)
    if start is None:
        if body and body[-1].startswith("#"):
            body.append("\n")  # keep the leading comment block visually separate
        body += [f"{match.item_id}:\n", f"{_DEFAULT_INDENT}{match.store}: {entry}\n"]
        result.added.append(pair)
        return
    end = _region_end(body, start)
    children = [(i, _CHILD.match(body[i])) for i in range(start + 1, end)]
    children = [(i, m) for i, m in children if m]
    indent = min((m["indent"] for _, m in children), key=len, default=_DEFAULT_INDENT)
    existing = next(
        (i for i, m in children if m["indent"] == indent and m["key"] == match.store), None
    )
    if existing is None:
        content = [i for i in range(start + 1, end) if body[i].startswith(" ") and body[i].strip()]
        body.insert((content[-1] if content else start) + 1, f"{indent}{match.store}: {entry}\n")
        result.added.append(pair)
        return
    if not confirm_replace(*pair):
        result.kept.append(pair)
        return
    stop = existing + 1
    while stop < end and body[stop].strip() and _indent_width(body[stop]) > len(indent):
        stop += 1
    body[existing:stop] = [f"{indent}{match.store}: {entry}\n"]
    result.replaced.append(pair)


def apply_matches(
    text: str, matches: Iterable[NewMatch], confirm_replace: ConfirmReplace
) -> tuple[str, ApplyResult]:
    """Return `text` with `matches` merged into its head, plus what was added/replaced/kept."""
    head, tail = _split(text)
    lines = head.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    cut = len(lines)
    while cut and not lines[cut - 1].strip():
        cut -= 1
    body, trailing = lines[:cut], lines[cut:]
    unique: dict[Pair, NewMatch] = {}
    for match in matches:
        unique[(match.item_id, match.store)] = match
    result = ApplyResult()
    for match in unique.values():
        _merge(body, match, confirm_replace, result)
    if not result.added and not result.replaced:
        return text, result
    return "".join(body + trailing) + tail, result


def _atomic_write(path: Path, content: bytes) -> None:
    handle, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _backup_path(path: Path, now: datetime) -> Path:
    stem = f"{path.name}.{now:%Y%m%d-%H%M%S}"
    candidate = path.with_name(f"{stem}.bak")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{stem}-{counter}.bak")
        counter += 1
    return candidate


def write_matches(
    config_dir: Path,
    matches: Iterable[NewMatch],
    *,
    confirm_replace: ConfirmReplace,
    now: datetime,
) -> WriteResult:
    """Merge `matches` into config_dir/matches.yaml with a backup and atomic replace.

    The written configuration is validated with load_config; on failure the backup is
    restored and ApproveError is raised.
    """
    path = config_dir / "matches.yaml"
    original = path.read_bytes()
    text, applied = apply_matches(original.decode("utf-8"), matches, confirm_replace)
    result = WriteResult(added=applied.added, replaced=applied.replaced, kept=applied.kept)
    if not applied.added and not applied.replaced:
        return result
    backup = _backup_path(path, now)
    shutil.copy2(path, backup)
    _atomic_write(path, text.encode("utf-8"))
    try:
        load_config(config_dir)
    except ConfigError as exc:
        _atomic_write(path, backup.read_bytes())
        raise ApproveError(
            f"the updated matches.yaml did not validate, restored {backup.name}: {exc}"
        ) from exc
    result.backup = backup
    return result
