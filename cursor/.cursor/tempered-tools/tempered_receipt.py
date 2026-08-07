"""Scoped cryptographic, staging, and portable-path helper for Tempered Loop v2.

The command-line interface is intentionally small and dependency-free:

* ``self-test``
* ``nonce``
* ``sha256 --root <root> [<stage-file> | --relative <path>]``
* ``verify-payload --root <root> [<stage-file> | --relative <path>] --field <field>``
* ``verify-setup --root <root> --relative <approved_setup>``
* ``verify-bundle --root <root> --relative <control_bundle>``
* ``snapshot --root <root> --paths-file <file>``
* ``validate-paths --root <root> --paths-file <file>``
* ``preview-create --root <root> --phase <phase> --nonce <nonce>``
* ``preview-metrics <file> --root <root>``
* ``preview-finalize <file> --field <digest_field> --root <root>``
* ``preview-consume <file> --root <root>`` (finalized ACTION stages only)
* ``preview-remove <file> --root <root>``

Snapshot v2 hashes this exact byte grammar, with entries sorted by the UTF-8
bytes of their validated NFC repository-relative paths::

    TEMPERED-SNAPSHOT-V2\n
    PATH <decimal-path-byte-length>\n
    <path-utf8>\n
    TYPE REGULAR\n
    MODE <100644-or-100755>\n
    BYTES <decimal-content-byte-length>\n
    <exact-content-bytes>\n
    END\n

Lengths, rather than sentinel search, delimit variable fields. Preview commands
mutate only a nonce-bound private directory directly under the resolved OS temp
root. Snapshot and path-list inputs must be the correctly named member of that
active root-bound stage. All other commands are read-only. Digests and nonces
are calculated here from real bytes and OS entropy, never in model reasoning.
For ACTION, finalization replaces one zero-valued ``preview_stage_token`` with
the stage's random token before hashing, so ordinary duplicate or recreated
stages made through this helper do not share one approval digest. Consumption
is only a best-effort single-delivery state transition for a compliant,
untampered helper lifecycle. It is not durable replay protection: the same OS
principal can reverse the sentinel rename or recreate the exact stage. Human
idempotency and replay controls remain required.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import re
import secrets
import stat
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


APPROVAL_BINDING = "tempered-loop-sha256-nonce-v2"
NONCE_RE = re.compile(r"[0-9a-f]{32}\Z")
FIELD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
ID_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
DRIVE_RE = re.compile(r"[A-Za-z]:")
DEVICE_RE = re.compile(
    r"(?:CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9\u00b9\u00b2\u00b3]|LPT[1-9\u00b9\u00b2\u00b3])\Z",
    re.IGNORECASE,
)
HEX64_RE = re.compile(rb"[0-9a-f]{64}\Z")
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
SNAPSHOT_PREFIX = b"TEMPERED-SNAPSHOT-V2\n"
PAYLOAD_PHASES = rb"(?:BRIEF|SETUP|PLAN|ACTION)"
PREVIEW_PHASES = ("BRIEF", "SETUP", "PLAN", "ACTION")
PREVIEW_SENTINEL = ".tempered-preview-v2"
PREVIEW_CONSUMED_SENTINEL = ".tempered-preview-consumed-v2"
PREVIEW_CANDIDATE = "candidate.payload"
PREVIEW_AUXILIARIES = frozenset(
    {"proposed-paths.txt", "snapshot-paths.txt", "digest-input.bin"}
)
PREVIEW_ALLOWED = (
    frozenset(
        {PREVIEW_SENTINEL, PREVIEW_CONSUMED_SENTINEL, PREVIEW_CANDIDATE}
    )
    | PREVIEW_AUXILIARIES
)
MAX_PREVIEW_STAGE_ENTRIES = len(PREVIEW_ALLOWED)
PREVIEW_DIR_RE = re.compile(
    r"tempered-preview-v2-(brief|setup|plan|action)-([0-9a-f]{32})-"
    r"([0-9a-f]{64})-([0-9a-f]{32})\Z"
)
ZERO_DIGEST = b"0" * 64
ZERO_STAGE_TOKEN = b"0" * 32
ACTION_STAGE_TOKEN_FIELD = b"preview_stage_token"
READ_CHUNK_BYTES = 1024 * 1024
MAX_READ_BYTES = 64 * 1024 * 1024
MAX_PAYLOAD_BYTES = 32 * 1024 * 1024
MAX_PAYLOAD_LINES = 500_000
MAX_MANIFEST_BYTES = 32 * 1024 * 1024
MAX_PATHS_FILE_BYTES = 8 * 1024 * 1024
MAX_HASH_FILE_BYTES = 1024 * 1024 * 1024
MAX_SNAPSHOT_FILE_BYTES = 1024 * 1024 * 1024
MAX_SNAPSHOT_TOTAL_BYTES = 16 * 1024 * 1024 * 1024
MAX_PATH_ENTRIES = 100_000
MAX_MANIFEST_BLOCKS = 100_000
MAX_PATH_UTF8_BYTES = 4096
MAX_PATH_DEPTH = 128
MAX_TOTAL_PATH_COMPONENTS = 500_000
MAX_SCANNED_DIRECTORY_ENTRIES = 100_000
MAX_SCANNED_DIRECTORY_NAME_BYTES = 16 * 1024 * 1024
MAX_MOUNTINFO_BYTES = 8 * 1024 * 1024


class HelperError(ValueError):
    """A safe, user-facing validation failure."""


@dataclass(frozen=True)
class SafePath:
    """A validated repository-relative path and its resolved filesystem path."""

    relative: str
    collision_key: str
    absolute: Path


class _CollisionTrieNode:
    """Memory-bounded prefix-collision node; strings are stored per component."""

    __slots__ = ("children", "terminal", "representative_descendant")

    def __init__(self) -> None:
        self.children: dict[str, _CollisionTrieNode] = {}
        self.terminal: str | None = None
        self.representative_descendant: str | None = None


@dataclass
class _DirectoryScanBudget:
    entries: int = 0
    name_bytes: int = 0


def _is_link_or_reparse(st: os.stat_result) -> bool:
    """Return true for POSIX links and Windows reparse points/junctions."""

    return stat.S_ISLNK(st.st_mode) or bool(
        getattr(st, "st_file_attributes", 0) & REPARSE_POINT
    )


def _lstat(path: Path) -> os.stat_result:
    try:
        return os.lstat(path)
    except OSError as exc:
        raise HelperError(f"cannot inspect path: {path}: {exc.strerror or exc}") from exc


def _require_real_root(root: Path) -> Path:
    if not root.is_absolute():
        raise HelperError("root must be an absolute canonical path")
    if str(root) != unicodedata.normalize("NFC", str(root)):
        raise HelperError("root must use Unicode NFC")
    if any(
        unicodedata.category(character) in {"Cc", "Cf"}
        for character in str(root)
    ):
        raise HelperError("root contains a control or invisible-format character")
    normalized = Path(os.path.abspath(os.path.normpath(str(root))))
    if os.path.normcase(str(root)) != os.path.normcase(str(normalized)):
        raise HelperError("root must not contain lexical aliases such as dot segments")
    st = _lstat(root)
    if _is_link_or_reparse(st):
        raise HelperError("root must not be a symlink, junction, or reparse point")
    if not stat.S_ISDIR(st.st_mode):
        raise HelperError("root must be an existing directory")
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise HelperError(f"cannot resolve root: {exc.strerror or exc}") from exc
    if os.path.normcase(str(normalized)) != os.path.normcase(str(resolved)):
        raise HelperError("root must be canonical and free of filesystem aliases")
    return resolved


def _root_fingerprint(root: Path) -> str:
    """Bind a canonical root path to its current filesystem object identity."""

    resolved = _require_real_root(root)
    st = _lstat(resolved)
    path_bytes = resolved.as_posix().encode("utf-8")
    preimage = (
        b"TEMPERED-ROOT-IDENTITY-V2\nPATH-BYTES "
        + str(len(path_bytes)).encode("ascii")
        + b"\n"
        + path_bytes
        + b"\nDEV "
        + str(st.st_dev).encode("ascii")
        + b"\nINO "
        + str(st.st_ino).encode("ascii")
        + b"\n"
    )
    return hashlib.sha256(preimage).hexdigest()


def _portable_components(raw: str) -> tuple[str, ...]:
    if not isinstance(raw, str):
        raise HelperError("path entries must be text")
    if not raw:
        raise HelperError("path is empty")
    try:
        raw_bytes = raw.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise HelperError(f"path is not valid Unicode text: {raw!r}") from exc
    if len(raw_bytes) > MAX_PATH_UTF8_BYTES:
        raise HelperError(
            f"path exceeds {MAX_PATH_UTF8_BYTES} UTF-8 bytes: {raw[:80]!r}"
        )
    if raw != unicodedata.normalize("NFC", raw):
        raise HelperError(f"path is not Unicode NFC: {raw!r}")
    if "\\" in raw:
        raise HelperError(f"backslashes are forbidden in portable paths: {raw!r}")
    if raw.startswith("/") or raw.startswith("//") or DRIVE_RE.match(raw):
        raise HelperError(f"absolute, UNC, and drive paths are forbidden: {raw!r}")
    if any(unicodedata.category(char) in {"Cc", "Cf"} for char in raw):
        raise HelperError(
            f"control and invisible-format characters are forbidden in paths: {raw!r}"
        )
    if "~" in raw or any(char in raw for char in '*?[]{}$%<>"|'):
        raise HelperError(f"shell expansion or nonportable characters are forbidden: {raw!r}")

    parts = tuple(raw.split("/"))
    if len(parts) > MAX_PATH_DEPTH:
        raise HelperError(f"path exceeds {MAX_PATH_DEPTH} component depth: {raw[:80]!r}")
    for component in parts:
        if component == "":
            raise HelperError(f"empty path components are forbidden: {raw!r}")
        if component in {".", ".."}:
            raise HelperError(f"dot path components are forbidden: {raw!r}")
        if component.endswith((".", " ")):
            raise HelperError(f"trailing dot/space is forbidden: {raw!r}")
        if ":" in component:
            raise HelperError(f"alternate data stream syntax is forbidden: {raw!r}")
        if len(component.encode("utf-8")) > 255:
            raise HelperError(f"path component exceeds 255 UTF-8 bytes: {raw!r}")
        device_base = component.split(".", 1)[0].rstrip(" .")
        if DEVICE_RE.fullmatch(device_base):
            raise HelperError(f"Windows device name is forbidden: {raw!r}")
    return parts


def _collision_components(parts: Sequence[str]) -> tuple[str, ...]:
    return tuple(unicodedata.normalize("NFC", part).casefold() for part in parts)


def _collision_key(parts: Sequence[str]) -> str:
    return "/".join(_collision_components(parts))


def _assert_contained(root: Path, candidate: Path, raw: str) -> None:
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise HelperError(f"path escapes the declared root: {raw!r}") from exc


def _register_collision_components(
    components: Sequence[str],
    raw: str,
    trie: _CollisionTrieNode,
    *,
    duplicate_message: str,
    prefix_message: str,
) -> None:
    """Register one path in O(component count) time and storage."""

    node = trie
    ancestors: list[_CollisionTrieNode] = []
    for component in components:
        if node.terminal is not None:
            raise HelperError(
                prefix_message.format(previous=node.terminal, raw=raw)
            )
        ancestors.append(node)
        node = node.children.setdefault(component, _CollisionTrieNode())
    if node.terminal is not None:
        raise HelperError(
            duplicate_message.format(previous=node.terminal, raw=raw)
        )
    if node.representative_descendant is not None:
        raise HelperError(
            prefix_message.format(
                previous=node.representative_descendant,
                raw=raw,
            )
        )
    node.terminal = raw
    for ancestor in ancestors:
        if ancestor.representative_descendant is None:
            ancestor.representative_descendant = raw


def _decode_mountinfo_path(value: bytes) -> str:
    """Decode Linux mountinfo's octal path escapes without shell parsing."""

    decoded = re.sub(
        rb"\\([0-7]{3})",
        lambda match: bytes((int(match.group(1), 8),)),
        value,
    )
    return os.fsdecode(decoded)


def _linux_mount_points() -> set[str]:
    """Return the current process mount points or fail closed if unavailable."""

    mountinfo = Path("/proc/self/mountinfo")
    try:
        with open(mountinfo, "rb") as stream:
            data = stream.read(MAX_MOUNTINFO_BYTES + 1)
    except OSError as exc:
        raise HelperError(
            "mount-boundary status is UNKNOWN because /proc/self/mountinfo "
            f"cannot be read: {exc.strerror or exc}"
        ) from exc
    if len(data) > MAX_MOUNTINFO_BYTES:
        raise HelperError("mount-boundary status is UNKNOWN because mountinfo is oversized")
    points: set[str] = set()
    for line in data.splitlines():
        fields = line.split(b" ")
        if len(fields) < 6 or b"-" not in fields:
            raise HelperError("mount-boundary status is UNKNOWN due to malformed mountinfo")
        point = _decode_mountinfo_path(fields[4])
        points.add(os.path.normcase(os.path.normpath(point)))
    return points


def _mount_security_context(root: Path) -> tuple[os.stat_result, set[str]]:
    """Build a fail-closed context for device and nested-mount checks."""

    root_stat = _lstat(root)
    if os.name == "nt":
        # Windows mount points and junctions are reparse points, checked per component.
        return root_stat, set()
    if sys.platform.startswith("linux"):
        return root_stat, _linux_mount_points()
    if sys.platform == "darwin":
        # Darwin has no native Linux-style same-device bind mount. Mounted APFS/FUSE
        # trees are caught by st_dev and/or the per-component os.path.ismount check.
        return root_stat, set()
    raise HelperError(
        "mount-boundary status is UNKNOWN on this platform; use manual high-impact handoff"
    )


def _assert_no_mount_or_device_traversal(
    root: Path,
    current: Path,
    st: os.stat_result,
    root_stat: os.stat_result,
    mount_points: set[str],
    raw: str,
) -> None:
    if st.st_dev != root_stat.st_dev:
        raise HelperError(f"cross-device traversal is forbidden: {raw!r}")
    if current != root and os.name != "nt":
        normalized = os.path.normcase(os.path.normpath(str(current)))
        if normalized in mount_points or os.path.ismount(current):
            raise HelperError(f"nested mount traversal is forbidden: {raw!r}")


def _assert_single_link(st: os.stat_result, path: Path | str) -> None:
    if stat.S_ISREG(st.st_mode) and getattr(st, "st_nlink", 1) > 1:
        raise HelperError(f"multi-link regular files are forbidden: {path}")


def _inspect_existing_components(
    root: Path,
    parts: Sequence[str],
    raw: str,
    *,
    mount_context: tuple[os.stat_result, set[str]] | None = None,
    directory_cache: dict[
        Path, tuple[os.stat_result, dict[str, tuple[str, ...]]]
    ] | None = None,
    scan_budget: _DirectoryScanBudget | None = None,
) -> os.stat_result | None:
    if mount_context is None:
        mount_context = _mount_security_context(root)
    if scan_budget is None:
        scan_budget = _DirectoryScanBudget()
    root_stat, mount_points = mount_context
    current = root
    final_stat: os.stat_result | None = None
    missing = False
    for index, component in enumerate(parts):
        if missing:
            current = current / component
            continue
        directory_before = _lstat(current)
        if _is_link_or_reparse(directory_before) or not stat.S_ISDIR(
            directory_before.st_mode
        ):
            raise HelperError(f"path parent is not a real directory: {raw!r}")
        _assert_no_mount_or_device_traversal(
            root, current, directory_before, root_stat, mount_points, raw
        )
        cached = directory_cache.get(current) if directory_cache is not None else None
        if cached is None:
            alias_index: dict[str, list[str]] = {}
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        scan_budget.entries += 1
                        try:
                            entry_name_bytes = len(
                                entry.name.encode("utf-8", errors="strict")
                            )
                        except UnicodeEncodeError as exc:
                            raise HelperError(
                                "directory contains a name that is not valid Unicode text"
                            ) from exc
                        scan_budget.name_bytes += entry_name_bytes
                        if scan_budget.entries > MAX_SCANNED_DIRECTORY_ENTRIES:
                            raise HelperError(
                                "directory scan exceeds "
                                f"{MAX_SCANNED_DIRECTORY_ENTRIES} entries"
                            )
                        if (
                            scan_budget.name_bytes
                            > MAX_SCANNED_DIRECTORY_NAME_BYTES
                        ):
                            raise HelperError(
                                "directory scan exceeds "
                                f"{MAX_SCANNED_DIRECTORY_NAME_BYTES} name bytes"
                            )
                        folded = unicodedata.normalize("NFC", entry.name).casefold()
                        alias_index.setdefault(folded, []).append(entry.name)
            except OSError as exc:
                raise HelperError(
                    f"cannot inspect directory entries for {raw!r}: {exc.strerror or exc}"
                ) from exc
            directory_after = _lstat(current)
            stable_directory_fields = ("st_dev", "st_ino", "st_mtime_ns")
            if any(
                getattr(directory_before, field) != getattr(directory_after, field)
                for field in stable_directory_fields
            ):
                raise HelperError(f"directory changed while paths were inspected: {raw!r}")
            frozen_index = {
                key: tuple(values) for key, values in alias_index.items()
            }
            cached = (directory_after, frozen_index)
            if directory_cache is not None:
                directory_cache[current] = cached
        else:
            cached_stat, _ = cached
            stable_directory_fields = ("st_dev", "st_ino", "st_mtime_ns")
            if any(
                getattr(cached_stat, field) != getattr(directory_before, field)
                for field in stable_directory_fields
            ):
                raise HelperError(f"directory changed during path validation: {raw!r}")
        aliases = list(
            cached[1].get(unicodedata.normalize("NFC", component).casefold(), ())
        )
        if len(aliases) > 1:
            raise HelperError(
                f"existing NFC/casefold aliases make path ambiguous: {raw!r}"
            )
        if aliases and aliases[0] != component:
            raise HelperError(
                f"path aliases existing name {aliases[0]!r}: {raw!r}"
            )
        current = current / component
        if not aliases:
            try:
                unenumerated = os.lstat(current)
            except FileNotFoundError:
                missing = True
                continue
            except OSError as exc:
                raise HelperError(
                    f"cannot inspect unresolved path component for {raw!r}: "
                    f"{exc.strerror or exc}"
                ) from exc
            if _is_link_or_reparse(unenumerated):
                raise HelperError(
                    f"symlink, junction, or reparse traversal is forbidden: {raw!r}"
                )
            raise HelperError(
                f"path resolves through an unenumerated filesystem alias: {raw!r}"
            )
        try:
            st = os.lstat(current)
        except OSError as exc:
            raise HelperError(
                f"cannot inspect existing path component for {raw!r}: {exc.strerror or exc}"
            ) from exc
        if _is_link_or_reparse(st):
            raise HelperError(
                f"symlink, junction, or reparse traversal is forbidden: {raw!r}"
            )
        _assert_no_mount_or_device_traversal(
            root, current, st, root_stat, mount_points, raw
        )
        if index < len(parts) - 1 and not stat.S_ISDIR(st.st_mode):
            raise HelperError(f"non-directory path component: {raw!r}")
        if index == len(parts) - 1:
            _assert_single_link(st, current)
            final_stat = st
    return final_stat


def validate_relative_paths(
    root: Path | str,
    paths: Iterable[str],
    *,
    require_regular_files: bool = False,
    _mount_context_override: tuple[os.stat_result, set[str]] | None = None,
    _directory_cache_override: dict[
        Path, tuple[os.stat_result, dict[str, tuple[str, ...]]]
    ] | None = None,
    _scan_budget_override: _DirectoryScanBudget | None = None,
) -> list[SafePath]:
    """Validate explicit paths without following filesystem aliases."""

    root_resolved = _require_real_root(Path(root))
    mount_context = _mount_context_override or _mount_security_context(root_resolved)
    directory_cache = (
        _directory_cache_override
        if _directory_cache_override is not None
        else {}
    )
    scan_budget = _scan_budget_override or _DirectoryScanBudget()
    collision_trie = _CollisionTrieNode()
    validated: list[SafePath] = []
    total_components = 0

    for count, raw in enumerate(paths, start=1):
        if count > MAX_PATH_ENTRIES:
            raise HelperError(f"path list exceeds {MAX_PATH_ENTRIES} entries")
        parts = _portable_components(raw)
        total_components += len(parts)
        if total_components > MAX_TOTAL_PATH_COMPONENTS:
            raise HelperError(
                "path list exceeds "
                f"{MAX_TOTAL_PATH_COMPONENTS} total components"
            )
        collision_components = _collision_components(parts)
        key = "/".join(collision_components)
        _register_collision_components(
            collision_components,
            raw,
            collision_trie,
            duplicate_message="NFC/casefold path collision: {previous!r} aliases {raw!r}",
            prefix_message="file/directory prefix collision: {previous!r} vs {raw!r}",
        )

        candidate = root_resolved.joinpath(*parts)
        _assert_contained(root_resolved, candidate, raw)
        final_stat = _inspect_existing_components(
            root_resolved,
            parts,
            raw,
            mount_context=mount_context,
            directory_cache=directory_cache,
            scan_budget=scan_budget,
        )
        if require_regular_files:
            if final_stat is None:
                raise HelperError(f"snapshot path does not exist: {raw!r}")
            if not stat.S_ISREG(final_stat.st_mode):
                raise HelperError(f"snapshot path is not a regular file: {raw!r}")
        elif final_stat is not None:
            raise HelperError(f"proposed path already exists: {raw!r}")

        validated.append(SafePath(raw, key, candidate))

    if not validated:
        raise HelperError("path list must contain at least one path")
    for directory, (cached_stat, _) in directory_cache.items():
        current_stat = _lstat(directory)
        if _is_link_or_reparse(current_stat) or not stat.S_ISDIR(current_stat.st_mode):
            raise HelperError("directory identity changed during path validation")
        if any(
            getattr(cached_stat, field) != getattr(current_stat, field)
            for field in ("st_dev", "st_ino", "st_mtime_ns")
        ):
            raise HelperError("directory changed during path validation")
    return validated


def _read_regular_bytes(path: Path, *, max_bytes: int = MAX_READ_BYTES) -> bytes:
    """Read exact bytes while rejecting final-component aliases and basic drift."""

    before = _lstat(path)
    if _is_link_or_reparse(before):
        raise HelperError(f"refusing to read a symlink, junction, or reparse point: {path}")
    if not stat.S_ISREG(before.st_mode):
        raise HelperError(f"not a regular file: {path}")
    _assert_single_link(before, path)
    if before.st_size > max_bytes:
        raise HelperError(f"file exceeds {max_bytes} byte limit: {path}")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise HelperError(f"cannot open file: {path}: {exc.strerror or exc}") from exc

    try:
        opened = os.fstat(descriptor)
        if _is_link_or_reparse(opened) or not stat.S_ISREG(opened.st_mode):
            raise HelperError(f"opened path is not a real regular file: {path}")
        _assert_single_link(opened, path)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise HelperError(f"file identity changed while opening: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HelperError(f"file exceeds {max_bytes} byte limit: {path}")
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(opened, field) != getattr(after, field) for field in stable_fields):
        raise HelperError(f"file changed while being read: {path}")
    _assert_single_link(after, path)
    data = b"".join(chunks)
    if len(data) != after.st_size:
        raise HelperError(f"file length changed while being read: {path}")
    return data


def _update_digest_from_regular_file(
    digest: object,
    path: Path,
    *,
    max_bytes: int,
    emit_snapshot_length: bool = False,
) -> tuple[int, os.stat_result]:
    """Stream one stable single-link file into a hashlib-compatible digest."""

    before = _lstat(path)
    if _is_link_or_reparse(before) or not stat.S_ISREG(before.st_mode):
        raise HelperError(f"refusing to hash a linked or non-regular file: {path}")
    _assert_single_link(before, path)
    if before.st_size > max_bytes:
        raise HelperError(f"file exceeds {max_bytes} byte hash limit: {path}")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise HelperError(f"cannot open file for hashing: {path}: {exc.strerror or exc}") from exc

    try:
        opened = os.fstat(descriptor)
        if _is_link_or_reparse(opened) or not stat.S_ISREG(opened.st_mode):
            raise HelperError(f"opened hash path is not a real regular file: {path}")
        _assert_single_link(opened, path)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise HelperError(f"file identity changed while opening for hash: {path}")
        if opened.st_size > max_bytes:
            raise HelperError(f"file exceeds {max_bytes} byte hash limit: {path}")
        if emit_snapshot_length:
            digest.update(b"BYTES ")
            digest.update(str(opened.st_size).encode("ascii"))
            digest.update(b"\n")
        total = 0
        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HelperError(f"file exceeds {max_bytes} byte hash limit: {path}")
            digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(opened, field) != getattr(after, field) for field in stable_fields):
        raise HelperError(f"file changed while being hashed: {path}")
    _assert_single_link(after, path)
    if total != after.st_size:
        raise HelperError(f"file length changed while being hashed: {path}")
    return total, after


def sha256_file(path: Path | str) -> str:
    """Return SHA-256 of exact on-disk bytes."""

    digest = hashlib.sha256()
    _update_digest_from_regular_file(
        digest, Path(path), max_bytes=MAX_HASH_FILE_BYTES
    )
    return digest.hexdigest()


def exact_bytes_equal(left: Path | str, right: Path | str) -> bool:
    """Compare two manual-save candidates byte-for-byte, without normalization."""

    left_bytes = _read_regular_bytes(Path(left))
    right_bytes = _read_regular_bytes(Path(right))
    return len(left_bytes) == len(right_bytes) and hmac.compare_digest(
        left_bytes, right_bytes
    )


def _parse_marker(line: bytes) -> tuple[str, str, bytes, bytes | None] | None:
    """Parse one exact supported marker line without accepting prefix/suffix text."""

    patterns = (
        (
            "angled",
            re.compile(
                rb"<<<(BEGIN|END) TEMPERED PAYLOAD phase=("
                + PAYLOAD_PHASES
                + rb") nonce=([0-9a-f]{32})>>>"
            ),
        ),
        (
            "html",
            re.compile(
                rb"<!-- (BEGIN|END) TEMPERED (" + PAYLOAD_PHASES + rb") PAYLOAD -->"
            ),
        ),
        (
            "dashed",
            re.compile(
                rb"-----(BEGIN|END) TEMPERED (" + PAYLOAD_PHASES + rb") PAYLOAD-----"
            ),
        ),
        (
            "plain",
            re.compile(rb"(BEGIN|END) TEMPERED (" + PAYLOAD_PHASES + rb") PAYLOAD"),
        ),
    )
    for style, pattern in patterns:
        match = pattern.fullmatch(line)
        if match:
            nonce = match.group(3) if style == "angled" else None
            return style, match.group(1).decode("ascii"), match.group(2), nonce
    return None


@dataclass(frozen=True)
class ManifestBlock:
    """One exact length-prefixed setup or control-bundle file block."""

    verb: str
    path: str
    content: bytes


def _setup_body_start(scope: bytes) -> int:
    header_start, header_end = _active_header(scope)
    del header_start
    if scope.startswith(b"---\n"):
        closing_end = scope.find(b"\n", header_end)
        if closing_end < 0:
            raise HelperError("frontmatter header is not closed")
        return closing_end + 1
    if scope[header_end : header_end + 1] == b"\n":
        return header_end + 1
    return header_end


def _parse_file_blocks(data: bytes) -> tuple[list[ManifestBlock], list[bytes]]:
    """Parse an exact block stream and return blocks plus structural lines."""

    if len(data) > MAX_MANIFEST_BYTES:
        raise HelperError(f"manifest exceeds {MAX_MANIFEST_BYTES} byte limit")
    blocks: list[ManifestBlock] = []
    structural: list[bytes] = []
    collision_trie = _CollisionTrieNode()
    total_components = 0
    previous_path_bytes: bytes | None = None
    cursor = 0
    while cursor < len(data):
        line_end = data.find(b"\n", cursor)
        if line_end < 0:
            raise HelperError("manifest contains an unterminated @@FILE line")
        file_line = data[cursor:line_end]
        structural.append(file_line)
        if not file_line.startswith(b"@@FILE "):
            raise HelperError("manifest contains structural content outside @@FILE blocks")
        declaration = file_line[len(b"@@FILE ") :]
        if declaration.startswith(b"VERIFY_EXISTING "):
            verb = "VERIFY_EXISTING"
            path_bytes = declaration[len(b"VERIFY_EXISTING ") :]
        elif declaration.startswith(b"WRITE_NEW "):
            verb = "WRITE_NEW"
            path_bytes = declaration[len(b"WRITE_NEW ") :]
        else:
            raise HelperError(
                "manifest @@FILE requires explicit VERIFY_EXISTING or WRITE_NEW verb"
            )
        if not path_bytes or path_bytes != path_bytes.strip():
            raise HelperError("manifest @@FILE path is empty or padded")
        try:
            path = path_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise HelperError(f"manifest path is not valid UTF-8: {exc}") from exc
        parts = _portable_components(path)
        total_components += len(parts)
        if total_components > MAX_TOTAL_PATH_COMPONENTS:
            raise HelperError(
                "manifest paths exceed "
                f"{MAX_TOTAL_PATH_COMPONENTS} total components"
            )
        collision_components = _collision_components(parts)
        _register_collision_components(
            collision_components,
            path,
            collision_trie,
            duplicate_message="manifest contains a duplicate/alias path: {raw!r}",
            prefix_message=(
                "manifest file/directory prefix collision: {previous!r} vs {raw!r}"
            ),
        )
        if previous_path_bytes is not None and path_bytes <= previous_path_bytes:
            raise HelperError("manifest paths are not in strict ordinal UTF-8 order")
        previous_path_bytes = path_bytes
        cursor = line_end + 1

        bytes_end = data.find(b"\n", cursor)
        if bytes_end < 0:
            raise HelperError("manifest @@BYTES line is missing")
        bytes_line = data[cursor:bytes_end]
        structural.append(bytes_line)
        count_match = re.fullmatch(rb"@@BYTES (0|[1-9][0-9]*)", bytes_line)
        if count_match is None:
            raise HelperError("manifest @@FILE must be followed by exact @@BYTES count")
        count_bytes = count_match.group(1)
        if len(count_bytes) > 20:
            raise HelperError("manifest @@BYTES count exceeds supported decimal range")
        try:
            byte_count = int(count_bytes)
        except ValueError as exc:
            raise HelperError("manifest @@BYTES count is not supported") from exc
        if byte_count > MAX_MANIFEST_BYTES:
            raise HelperError(
                f"manifest file content exceeds {MAX_MANIFEST_BYTES} byte limit"
            )
        cursor = bytes_end + 1
        content_end = cursor + byte_count
        if content_end > len(data):
            raise HelperError("manifest file content is shorter than its @@BYTES count")
        content = data[cursor:content_end]
        if not content.endswith(b"\n"):
            raise HelperError("manifest file content must end in LF")
        cursor = content_end

        end_line_end = data.find(b"\n", cursor)
        if end_line_end < 0:
            raise HelperError("manifest @@END line is missing")
        end_line = data[cursor:end_line_end]
        structural.append(end_line)
        if end_line != b"@@END " + path_bytes:
            raise HelperError("manifest @@END path does not match @@FILE path")
        cursor = end_line_end + 1
        blocks.append(ManifestBlock(verb, path, content))
        if len(blocks) > MAX_MANIFEST_BLOCKS:
            raise HelperError(
                f"manifest exceeds {MAX_MANIFEST_BLOCKS} file blocks"
            )
    if not blocks:
        raise HelperError("manifest must contain at least one @@FILE block")
    return blocks, structural


def _setup_file_block_structural_lines(scope: bytes) -> list[bytes]:
    """Return SETUP structural lines while skipping byte-counted file data."""

    body_start = _setup_body_start(scope)
    _, block_lines = _parse_file_blocks(scope[body_start:])
    header_lines = [
        line[:-1] if line.endswith(b"\n") else line
        for line in scope[:body_start].splitlines(keepends=True)
    ]
    return header_lines + block_lines


def _structural_marker_lines(scope: bytes) -> list[bytes]:
    """Return lines where marker syntax is structural rather than file data."""

    header_start, header_end = _active_header(scope)
    header = scope[header_start:header_end]
    setup_header = bool(
        re.search(rb"(?m)^payload_(?:type|kind): setup$", header)
    )
    if setup_header and b"@@FILE " in scope[header_end:]:
        return _setup_file_block_structural_lines(scope)
    return [line[:-1] if line.endswith(b"\n") else line for line in scope.splitlines(keepends=True)]


def _payload_scope(data: bytes) -> bytes:
    """Return inner payload bytes after requiring one exact outer marker pair."""

    if len(data) > MAX_PAYLOAD_BYTES:
        raise HelperError(f"canonical payload exceeds {MAX_PAYLOAD_BYTES} byte limit")
    if data.count(b"\n") > MAX_PAYLOAD_LINES:
        raise HelperError(
            f"canonical payload exceeds {MAX_PAYLOAD_LINES} LF line limit"
        )
    lines = data.splitlines(keepends=True)
    if not lines:
        raise HelperError("canonical payload is empty")
    contents = [line[:-1] if line.endswith(b"\n") else line for line in lines]
    begin = _parse_marker(contents[0])
    end = _parse_marker(contents[-1])
    if begin is None or end is None:
        raise HelperError(
            "canonical payload requires one supported exact first/last outer marker pair"
        )
    if begin[1] != "BEGIN" or end[1] != "END":
        raise HelperError("outer payload markers are reversed")
    if begin[0] != end[0] or begin[2] != end[2] or begin[3] != end[3]:
        raise HelperError("outer payload markers are missing or do not match")
    if len(lines) < 3:
        raise HelperError("marked canonical payload is empty")
    scope = b"".join(lines[1:-1])
    if not scope.endswith(b"\n"):
        raise HelperError("marked canonical payload must end in LF before END marker")
    if scope.endswith(b"\n\n"):
        raise HelperError("marked canonical payload must end in exactly one LF")
    if any(
        b"BEGIN TEMPERED" in line or b"END TEMPERED" in line
        for line in _structural_marker_lines(scope)
    ):
        raise HelperError(
            "recognized marker text is allowed only as one exact first/last outer pair"
        )
    return scope


def _active_header(scope: bytes) -> tuple[int, int]:
    """Locate the leading metadata header so embedded file fields stay inert."""

    lines = scope.splitlines(keepends=True)
    if not lines:
        raise HelperError("canonical payload scope is empty")
    if lines[0] == b"---\n":
        offset = len(lines[0])
        for line in lines[1:]:
            if line == b"---\n":
                return len(lines[0]), offset
            offset += len(line)
        raise HelperError("frontmatter header is not closed")

    block_prefixes = (
        b"@@FILE ",
        b"FILE ",
        b"VERIFY_EXISTING ",
        b"WRITE_NEW ",
        b"### ",
        b"# ",
    )
    offset = 0
    for index, line in enumerate(lines):
        content = line[:-1] if line.endswith(b"\n") else line
        if index > 0 and (content == b"" or content.startswith(block_prefixes)):
            return 0, offset
        offset += len(line)
    return 0, len(scope)


def _canonical_payload_details(
    data: bytes, field: str
) -> tuple[str, bytes, int, int]:
    if len(data) > MAX_PAYLOAD_BYTES:
        raise HelperError(f"canonical payload exceeds {MAX_PAYLOAD_BYTES} byte limit")
    if not FIELD_RE.fullmatch(field):
        raise HelperError("digest field must be an ASCII identifier")
    if data.startswith(b"\xef\xbb\xbf"):
        raise HelperError("canonical payload must not contain a UTF-8 BOM")
    if b"\r" in data:
        raise HelperError("canonical payload must use LF line endings")
    if not data.endswith(b"\n"):
        raise HelperError("canonical payload must end in LF")
    if data.endswith(b"\n\n"):
        raise HelperError("canonical payload must end in exactly one LF")
    forbidden_controls = set(range(0, 32)) - {9, 10}
    if any(byte in forbidden_controls or byte == 127 for byte in data):
        raise HelperError("canonical payload contains a forbidden control byte")
    try:
        decoded = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise HelperError(f"canonical payload is not valid UTF-8: {exc}") from exc
    if any(
        unicodedata.category(character) in {"Cc", "Cf"}
        for character in decoded
        if character not in {"\t", "\n"}
    ):
        raise HelperError(
            "canonical payload contains a control or invisible-format character"
        )

    scope = _payload_scope(data)
    phase, _ = _active_phase_nonce(data)
    _validate_primary_payload_id(data, phase)
    active_digest_field = _detect_phase_digest_field(data, phase)
    if active_digest_field != field:
        raise HelperError(
            f"{field} is not the unique active digest field for {phase}"
        )
    header_start, header_end = _active_header(scope)
    header = scope[header_start:header_end]
    field_bytes = field.encode("ascii")
    candidate_prefix = re.compile(re.escape(field_bytes) + rb"\s*:")
    prefix = field_bytes + b":"
    candidate_lines: list[tuple[int, bytes]] = []
    offset = 0
    for line in header.splitlines(keepends=True):
        content = line[:-1] if line.endswith(b"\n") else line
        if candidate_prefix.match(content):
            candidate_lines.append((header_start + offset, content))
        offset += len(line)
    if len(candidate_lines) != 1:
        raise HelperError(f"payload must contain exactly one active {field} field")

    line_offset, line = candidate_lines[0]
    unquoted = re.fullmatch(re.escape(prefix) + rb" ([0-9a-f]{64})", line)
    quoted = re.fullmatch(re.escape(prefix) + rb' "([0-9a-f]{64})"', line)
    match = unquoted or quoted
    if match is None:
        raise HelperError(
            f"{field} must contain exactly 64 lowercase hex characters"
        )
    stored_bytes = match.group(1)
    if not HEX64_RE.fullmatch(stored_bytes):
        raise HelperError(f"malformed {field}")
    digest_start = line_offset + match.start(1)
    digest_end = line_offset + match.end(1)
    first_line_end = data.find(b"\n") + 1
    first_line = data[: first_line_end - 1] if first_line_end else data
    scope_offset = first_line_end if _parse_marker(first_line) is not None else 0
    absolute_start = scope_offset + digest_start
    absolute_end = scope_offset + digest_end
    canonical = data[:absolute_start] + ZERO_DIGEST + data[absolute_end:]
    return (
        stored_bytes.decode("ascii"),
        canonical,
        absolute_start,
        absolute_end,
    )


def _canonical_payload(data: bytes, field: str) -> tuple[str, bytes]:
    stored, canonical, _, _ = _canonical_payload_details(data, field)
    return stored, canonical


def payload_digest(data: bytes, field: str) -> str:
    """Compute the canonical digest after zeroing exactly one active field."""

    _, canonical = _canonical_payload(data, field)
    return hashlib.sha256(canonical).hexdigest()


def verify_payload_file(
    path: Path | str,
    field: str,
    *,
    expected_preview_stage_token: str | None = None,
) -> str:
    """Verify a stored canonical payload digest and return it on success."""

    data = _read_regular_bytes(Path(path), max_bytes=MAX_PAYLOAD_BYTES)
    stored, canonical = _canonical_payload(data, field)
    phase, _ = _active_phase_nonce(data)
    if phase == "ACTION":
        if expected_preview_stage_token is None:
            raise HelperError(
                "ACTION payload verification requires its active preview-stage token"
            )
        stored_stage_token, _, _ = _action_stage_token_details(data)
        if not hmac.compare_digest(stored_stage_token, expected_preview_stage_token):
            raise HelperError("ACTION payload token does not match its preview stage")
    calculated = hashlib.sha256(canonical).hexdigest()
    if not hmac.compare_digest(stored, calculated):
        raise HelperError("payload digest mismatch")
    return calculated


@dataclass(frozen=True)
class PreviewStage:
    """A validated helper-issued preview stage."""

    directory: Path
    candidate: Path
    sentinel: Path
    phase: str
    nonce: str
    root_sha256: str
    token: str
    directory_stat: os.stat_result
    candidate_stat: os.stat_result
    consumed: bool


def _resolved_temp_root() -> Path:
    raw = tempfile.gettempdir()
    if raw != unicodedata.normalize("NFC", raw):
        raise HelperError("OS temp root must use Unicode NFC")
    if any(unicodedata.category(character) in {"Cc", "Cf"} for character in raw):
        raise HelperError("OS temp root contains a control or invisible-format character")
    raw_path = Path(raw)
    if not raw_path.is_absolute():
        raise HelperError("OS temp root must be absolute")
    normalized = Path(os.path.abspath(os.path.normpath(raw)))
    if os.path.normcase(raw) != os.path.normcase(str(normalized)):
        raise HelperError("OS temp root contains a lexical alias")
    try:
        root = raw_path.resolve(strict=True)
    except OSError as exc:
        raise HelperError(f"cannot resolve OS temp root: {exc.strerror or exc}") from exc
    st = _lstat(root)
    if _is_link_or_reparse(st) or not stat.S_ISDIR(st.st_mode):
        raise HelperError("resolved OS temp root is not a real directory")
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise HelperError(
                "Windows TEMP privacy is UNKNOWN because LOCALAPPDATA is unavailable"
            )
        trusted_raw = Path(local_app_data) / "Temp"
        try:
            trusted = trusted_raw.resolve(strict=True)
            same_temp = os.path.samefile(root, trusted)
        except OSError as exc:
            raise HelperError(
                "Windows TEMP privacy is UNKNOWN because the canonical per-user "
                f"LocalAppData/Temp cannot be verified: {exc.strerror or exc}"
            ) from exc
        if not same_temp:
            raise HelperError(
                "Windows TEMP privacy is UNKNOWN outside canonical per-user "
                "LocalAppData/Temp"
            )
    return root


def _chmod_private(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError as exc:
        if os.name != "nt":
            raise HelperError(
                f"cannot apply private permissions to {path}: {exc.strerror or exc}"
            ) from exc


def _write_new_private(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise HelperError(f"cannot create private stage file: {exc.strerror or exc}") from exc
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise HelperError("short write while creating private stage file")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _chmod_private(path, 0o600)


def _preview_sentinel_bytes(
    phase: str, nonce: str, root_sha256: str, token: str
) -> bytes:
    return (
        b"TEMPERED-PREVIEW-STAGE-V2\n"
        + f"phase: {phase}\n".encode("ascii")
        + f"nonce: {nonce}\n".encode("ascii")
        + f"root_sha256: {root_sha256}\n".encode("ascii")
        + f"token: {token}\n".encode("ascii")
        + b"candidate: candidate.payload\n"
    )


def preview_create(root: Path | str, phase: str, nonce: str) -> Path:
    """Create one nonce-bound private stage directly under the OS temp root."""

    if phase not in PREVIEW_PHASES:
        raise HelperError("preview phase must be BRIEF, SETUP, PLAN, or ACTION")
    if not NONCE_RE.fullmatch(nonce):
        raise HelperError("preview nonce must be exactly 32 lowercase hex characters")
    project_root = _require_real_root(Path(root))
    temp_root = _resolved_temp_root()
    try:
        temp_root.relative_to(project_root)
    except ValueError:
        pass
    else:
        raise HelperError("OS temp root must not equal or fall inside the project root")
    root_sha256 = _root_fingerprint(project_root)
    for _ in range(16):
        token = secrets.token_hex(16)
        directory = temp_root / (
            f"tempered-preview-v2-{phase.lower()}-{nonce}-{root_sha256}-{token}"
        )
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            continue
        except OSError as exc:
            raise HelperError(
                f"cannot create private preview directory: {exc.strerror or exc}"
            ) from exc
        try:
            _chmod_private(directory, 0o700)
            candidate = directory / PREVIEW_CANDIDATE
            sentinel = directory / PREVIEW_SENTINEL
            try:
                candidate.resolve(strict=False).relative_to(project_root)
            except ValueError:
                pass
            else:
                raise HelperError("OS temp stage unexpectedly falls inside the project")
            _write_new_private(candidate, b"")
            _write_new_private(
                sentinel,
                _preview_sentinel_bytes(phase, nonce, root_sha256, token),
            )
            _validate_preview_stage(candidate, root=project_root)
            return candidate
        except Exception:
            for name in (PREVIEW_CANDIDATE, PREVIEW_SENTINEL):
                try:
                    os.unlink(directory / name)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
            try:
                os.rmdir(directory)
            except OSError:
                pass
            raise
    raise HelperError("could not allocate a unique private preview directory")


def _same_lexical_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(
        os.path.normpath(str(right))
    )


def _validate_preview_stage(
    candidate_path: Path | str,
    *,
    consumed: bool = False,
    root: Path | str | None = None,
) -> PreviewStage:
    candidate = Path(candidate_path)
    if not candidate.is_absolute():
        raise HelperError("preview candidate path must be absolute")
    if candidate.name != PREVIEW_CANDIDATE:
        raise HelperError("preview path must name candidate.payload")
    normalized = Path(os.path.abspath(os.path.normpath(str(candidate))))
    if not _same_lexical_path(candidate, normalized):
        raise HelperError("preview candidate path must be normalized")

    temp_root = _resolved_temp_root()
    directory = candidate.parent
    if not _same_lexical_path(directory.parent, temp_root):
        raise HelperError("preview stage must be a direct child of the OS temp root")
    match = PREVIEW_DIR_RE.fullmatch(directory.name)
    if match is None:
        raise HelperError("preview directory name is not helper-shaped")
    phase = match.group(1).upper()
    nonce = match.group(2)
    root_sha256 = match.group(3)
    token = match.group(4)

    directory_stat = _lstat(directory)
    if _is_link_or_reparse(directory_stat) or not stat.S_ISDIR(directory_stat.st_mode):
        raise HelperError("preview directory must not be a link or reparse point")
    if os.name != "nt" and stat.S_IMODE(directory_stat.st_mode) & 0o077:
        raise HelperError("preview directory permissions are not private")
    try:
        if not os.path.samefile(directory.parent, temp_root):
            raise HelperError("preview directory escaped the resolved OS temp root")
    except OSError as exc:
        raise HelperError(f"cannot validate preview temp root: {exc.strerror or exc}") from exc

    try:
        with os.scandir(directory) as entries:
            names = []
            entry_stats: dict[str, os.stat_result] = {}
            for entry in entries:
                names.append(entry.name)
                if len(names) > MAX_PREVIEW_STAGE_ENTRIES:
                    raise HelperError(
                        "preview stage exceeds its fixed entry-count limit"
                    )
                st = entry.stat(follow_symlinks=False)
                entry_stats[entry.name] = st
    except OSError as exc:
        raise HelperError(f"cannot inspect preview stage: {exc.strerror or exc}") from exc
    unknown = sorted(set(names) - PREVIEW_ALLOWED)
    if unknown:
        raise HelperError(f"preview stage contains unexpected entries: {unknown!r}")
    if len(names) != len(set(names)):
        raise HelperError("preview stage contains ambiguous duplicate names")
    sentinel_name = PREVIEW_CONSUMED_SENTINEL if consumed else PREVIEW_SENTINEL
    other_sentinel = PREVIEW_SENTINEL if consumed else PREVIEW_CONSUMED_SENTINEL
    for required in (PREVIEW_CANDIDATE, sentinel_name):
        if required not in entry_stats:
            raise HelperError(f"preview stage is missing {required}")
    if other_sentinel in entry_stats:
        raise HelperError("preview stage has conflicting active/consumed state")
    for name, st in entry_stats.items():
        if _is_link_or_reparse(st) or not stat.S_ISREG(st.st_mode):
            raise HelperError(f"preview stage entry must be a real regular file: {name}")
        _assert_single_link(st, directory / name)
    candidate_stat = _lstat(candidate)
    sentinel = directory / sentinel_name
    sentinel_stat = _lstat(sentinel)
    if _is_link_or_reparse(candidate_stat) or not stat.S_ISREG(candidate_stat.st_mode):
        raise HelperError("preview candidate must be a real regular file")
    if _is_link_or_reparse(sentinel_stat) or not stat.S_ISREG(sentinel_stat.st_mode):
        raise HelperError("preview sentinel must be a real regular file")
    _assert_single_link(candidate_stat, candidate)
    _assert_single_link(sentinel_stat, sentinel)
    if os.name != "nt":
        if stat.S_IMODE(candidate_stat.st_mode) & 0o077:
            raise HelperError("preview candidate permissions are not private")
        if stat.S_IMODE(sentinel_stat.st_mode) & 0o077:
            raise HelperError("preview sentinel permissions are not private")

    expected = _preview_sentinel_bytes(phase, nonce, root_sha256, token)
    actual = _read_regular_bytes(sentinel)
    if not hmac.compare_digest(actual, expected):
        raise HelperError("preview sentinel does not match directory phase/nonce")
    if root is not None:
        current_root = _require_real_root(Path(root))
        expected_root_sha256 = _root_fingerprint(current_root)
        if not hmac.compare_digest(root_sha256, expected_root_sha256):
            raise HelperError("preview stage is bound to a different project root")
    try:
        if not os.path.samefile(candidate, directory / PREVIEW_CANDIDATE):
            raise HelperError("preview candidate identity is ambiguous")
    except OSError as exc:
        raise HelperError(f"cannot validate preview candidate: {exc.strerror or exc}") from exc
    return PreviewStage(
        directory,
        candidate,
        sentinel,
        phase,
        nonce,
        root_sha256,
        token,
        directory_stat,
        candidate_stat,
        consumed,
    )


def _validate_preview_member(
    path: Path | str,
    allowed_names: set[str],
    *,
    root: Path | str | None = None,
) -> Path:
    member = Path(path)
    if not member.is_absolute() or member.name not in allowed_names:
        raise HelperError("direct file access is limited to an allowed preview-stage file")
    stage = _validate_preview_stage(
        member.parent / PREVIEW_CANDIDATE,
        root=root,
    )
    expected = stage.directory / member.name
    if not _same_lexical_path(member, expected):
        raise HelperError("preview member path must be normalized")
    st = _lstat(member)
    if _is_link_or_reparse(st) or not stat.S_ISREG(st.st_mode):
        raise HelperError("preview member must be a real regular file")
    _assert_single_link(st, member)
    return member


def _header_scalar(
    header: bytes, names: Sequence[bytes], value_pattern: bytes, label: str
) -> tuple[bytes, bytes]:
    name_pattern = rb"(?:" + b"|".join(re.escape(name) for name in names) + rb")"
    candidates = [
        line
        for line in header.splitlines()
        if re.match(rb"^" + name_pattern + rb"\s*:", line)
    ]
    if len(candidates) != 1:
        raise HelperError(f"payload must contain exactly one active {label} field")
    line = candidates[0]
    unquoted = re.fullmatch(
        rb"(" + name_pattern + rb"): (" + value_pattern + rb")", line
    )
    quoted = re.fullmatch(
        rb'(' + name_pattern + rb'): "(' + value_pattern + rb')"', line
    )
    match = unquoted or quoted
    if match is None:
        raise HelperError(f"payload {label} field has noncanonical syntax or value")
    return match.group(1), match.group(2)


def _active_phase_nonce(data: bytes) -> tuple[str, str]:
    scope = _payload_scope(data)
    header_start, header_end = _active_header(scope)
    header = scope[header_start:header_end]
    _, phase_bytes = _header_scalar(
        header,
        (b"payload_type", b"payload_kind"),
        rb"(?:brief|setup|plan|action)",
        "payload phase",
    )
    phase = phase_bytes.decode("ascii").upper()
    _header_scalar(
        header,
        (f"{phase.lower()}_revision".encode("ascii"),),
        rb"[1-9][0-9]*",
        f"{phase.lower()} revision",
    )
    _, nonce_bytes = _header_scalar(
        header,
        (
            b"approval_nonce",
            b"preview_nonce",
            b"brief_nonce",
            b"setup_nonce",
            b"plan_nonce",
            b"action_nonce",
        ),
        rb"[0-9a-f]{32}",
        "nonce",
    )
    _header_scalar(header, (b"payload_schema",), rb"2", "payload schema")
    _header_scalar(
        header,
        (b"approval_binding",),
        re.escape(APPROVAL_BINDING.encode("ascii")),
        "approval binding",
    )
    token_lines = [
        line
        for line in header.splitlines()
        if re.match(rb"^" + ACTION_STAGE_TOKEN_FIELD + rb"\s*:", line)
    ]
    if phase == "ACTION":
        _header_scalar(
            header,
            (ACTION_STAGE_TOKEN_FIELD,),
            rb"[0-9a-f]{32}",
            "preview stage token",
        )
    elif token_lines:
        raise HelperError("preview_stage_token is reserved for ACTION payloads")
    nonce = nonce_bytes.decode("ascii")

    first_line = data.split(b"\n", 1)[0]
    marker = _parse_marker(first_line)
    if marker is not None:
        marker_phase = marker[2].decode("ascii")
        if marker_phase != phase:
            raise HelperError("outer marker phase does not match payload header")
        if marker[3] is not None and marker[3].decode("ascii") != nonce:
            raise HelperError("outer marker nonce does not match payload header")
    return phase, nonce


def _validate_primary_payload_id(data: bytes, phase: str) -> str:
    scope = _payload_scope(data)
    header_start, header_end = _active_header(scope)
    header = scope[header_start:header_end]
    field = f"{phase.lower()}_id".encode("ascii")
    _, value = _header_scalar(
        header, (field,), rb"[a-z][a-z0-9_-]{0,63}", f"{phase.lower()} ID"
    )
    decoded = value.decode("ascii")
    if not ID_RE.fullmatch(decoded):
        raise HelperError(f"invalid primary {phase} ID")
    return decoded


def _action_stage_token_details(data: bytes) -> tuple[str, int, int]:
    """Return ACTION stage-token value and absolute value span."""

    scope = _payload_scope(data)
    header_start, header_end = _active_header(scope)
    header = scope[header_start:header_end]
    candidate_prefix = re.compile(ACTION_STAGE_TOKEN_FIELD + rb"\s*:")
    candidates: list[tuple[int, bytes]] = []
    offset = 0
    for line in header.splitlines(keepends=True):
        content = line[:-1] if line.endswith(b"\n") else line
        if candidate_prefix.match(content):
            candidates.append((header_start + offset, content))
        offset += len(line)
    if len(candidates) != 1:
        raise HelperError(
            "ACTION payload must contain exactly one active preview_stage_token field"
        )
    line_offset, line = candidates[0]
    prefix = ACTION_STAGE_TOKEN_FIELD + b":"
    unquoted = re.fullmatch(prefix + rb" ([0-9a-f]{32})", line)
    quoted = re.fullmatch(prefix + rb' "([0-9a-f]{32})"', line)
    match = unquoted or quoted
    if match is None:
        raise HelperError(
            "preview_stage_token must contain exactly 32 lowercase hex characters"
        )
    first_line_end = data.find(b"\n") + 1
    absolute_start = first_line_end + line_offset + match.start(1)
    absolute_end = first_line_end + line_offset + match.end(1)
    return match.group(1).decode("ascii"), absolute_start, absolute_end


def _write_atomic_private(path: Path, data: bytes) -> None:
    temporary = path.parent / f".candidate.payload.{secrets.token_hex(16)}.tmp"
    try:
        _write_new_private(temporary, data)
        os.replace(temporary, path)
        _chmod_private(path, 0o600)
    except OSError as exc:
        raise HelperError(f"cannot atomically finalize preview: {exc.strerror or exc}") from exc
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        except OSError:
            pass


def preview_finalize(path: Path | str, field: str, root: Path | str) -> str:
    """Sign exactly one zero-valued active field in a valid private stage."""

    stage = _validate_preview_stage(path, root=root)
    original_data = _read_regular_bytes(
        stage.candidate, max_bytes=MAX_PAYLOAD_BYTES
    )
    phase, nonce = _active_phase_nonce(original_data)
    _validate_primary_payload_id(original_data, phase)
    if phase != stage.phase or nonce != stage.nonce:
        raise HelperError("preview payload phase/nonce does not match its stage")
    data = original_data
    if phase == "ACTION":
        stored_token, token_start, token_end = _action_stage_token_details(data)
        if stored_token == ZERO_STAGE_TOKEN.decode("ascii"):
            data = (
                data[:token_start]
                + stage.token.encode("ascii")
                + data[token_end:]
            )
        elif not hmac.compare_digest(stored_token, stage.token):
            raise HelperError("ACTION payload token does not match its preview stage")
    stored, canonical, digest_start, digest_end = _canonical_payload_details(data, field)
    if stored != ZERO_DIGEST.decode("ascii"):
        raise HelperError("preview digest field must contain 64 zeroes before finalization")
    digest = hashlib.sha256(canonical).hexdigest()
    signed = data[:digest_start] + digest.encode("ascii") + data[digest_end:]

    current = _lstat(stage.candidate)
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    current_directory = _lstat(stage.directory)
    if _is_link_or_reparse(current) or _is_link_or_reparse(current_directory):
        raise HelperError("preview stage became a link or reparse point")
    if (stage.directory_stat.st_dev, stage.directory_stat.st_ino) != (
        current_directory.st_dev,
        current_directory.st_ino,
    ):
        raise HelperError("preview directory identity changed during finalization")
    if any(
        getattr(stage.candidate_stat, name) != getattr(current, name)
        for name in stable_fields
    ):
        raise HelperError("preview candidate changed during finalization")
    current_data = _read_regular_bytes(
        stage.candidate, max_bytes=MAX_PAYLOAD_BYTES
    )
    if not hmac.compare_digest(original_data, current_data):
        raise HelperError("preview candidate bytes changed during finalization")
    sentinel_now = _read_regular_bytes(stage.sentinel)
    if not hmac.compare_digest(
        sentinel_now,
        _preview_sentinel_bytes(
            stage.phase, stage.nonce, stage.root_sha256, stage.token
        ),
    ):
        raise HelperError("preview sentinel changed during finalization")

    _write_atomic_private(stage.candidate, signed)
    finalized = _validate_preview_stage(stage.candidate, root=root)
    final_phase, final_nonce = _active_phase_nonce(
        _read_regular_bytes(finalized.candidate, max_bytes=MAX_PAYLOAD_BYTES)
    )
    if (final_phase, final_nonce) != (stage.phase, stage.nonce):
        raise HelperError("finalized payload lost its stage binding")
    verified = verify_payload_file(
        finalized.candidate,
        field,
        expected_preview_stage_token=(stage.token if phase == "ACTION" else None),
    )
    if not hmac.compare_digest(verified, digest):
        raise HelperError("finalized payload failed digest verification")
    return digest


def _preview_path_index(blocks: Sequence[ManifestBlock]) -> tuple[str, list[str]]:
    """Return a domain-separated digest and deterministic length-prefixed index."""

    digest = hashlib.sha256()
    digest.update(b"TEMPERED-PREVIEW-PATH-INDEX-V2\n")
    lines: list[str] = []
    for index, block in enumerate(blocks, start=1):
        path_bytes = block.path.encode("utf-8")
        verb_bytes = block.verb.encode("ascii")
        digest.update(b"ENTRY ")
        digest.update(str(index).encode("ascii"))
        digest.update(b"\nVERB ")
        digest.update(verb_bytes)
        digest.update(b"\nPATH ")
        digest.update(str(len(path_bytes)).encode("ascii"))
        digest.update(b"\n")
        digest.update(path_bytes)
        digest.update(b"\n")
        lines.append(
            f"PATH {index:06d} {block.verb} {len(path_bytes)} {block.path}"
        )
    return digest.hexdigest(), lines


def preview_metrics(path: Path | str, root: Path | str) -> str:
    """Validate one active stage and return exact bounded review metrics."""

    stage = _validate_preview_stage(path, root=root)
    data = _read_regular_bytes(stage.candidate, max_bytes=MAX_PAYLOAD_BYTES)
    phase, nonce = _active_phase_nonce(data)
    if (phase, nonce) != (stage.phase, stage.nonce):
        raise HelperError("preview payload phase/nonce does not match its stage")
    _validate_primary_payload_id(data, phase)
    field = _detect_phase_digest_field(data, phase)
    stored, canonical = _canonical_payload(data, field)
    calculated = hashlib.sha256(canonical).hexdigest()
    if stored != ZERO_DIGEST.decode("ascii") and not hmac.compare_digest(
        stored, calculated
    ):
        raise HelperError("preview payload digest is neither zero nor valid")
    if phase == "ACTION":
        stored_token, _, _ = _action_stage_token_details(data)
        if stored_token != ZERO_STAGE_TOKEN.decode("ascii") and not hmac.compare_digest(
            stored_token, stage.token
        ):
            raise HelperError("ACTION payload token does not match its preview stage")

    blocks: list[ManifestBlock] = []
    if phase == "SETUP":
        scope = _payload_scope(data)
        body_start = _setup_body_start(scope)
        blocks, _ = _parse_file_blocks(scope[body_start:])
    path_digest, path_lines = _preview_path_index(blocks)
    lf_count = data.count(b"\n")
    metrics = [
        f"PHASE {phase}",
        f"BYTES {len(data)}",
        f"LF {lf_count}",
        f"BLOCKS {len(blocks)}",
        f"PATH-INDEX-SHA256 {path_digest}",
        *path_lines,
    ]
    return "\n".join(metrics) + "\n"


def _detect_phase_digest_field(data: bytes, phase: str) -> str:
    if phase not in PREVIEW_PHASES:
        raise HelperError("payload phase has no supported digest field")
    scope = _payload_scope(data)
    header_start, header_end = _active_header(scope)
    header = scope[header_start:header_end]
    matches: list[str] = []
    phase_field = f"{phase.lower()}_payload_sha256"
    for field in ("payload_sha256", phase_field):
        if re.search(rb"(?m)^" + field.encode("ascii") + rb"\s*:", header):
            matches.append(field)
    if len(matches) != 1:
        raise HelperError(
            f"{phase} must contain exactly one active payload_sha256 or {phase_field}"
        )
    return matches[0]


def _detect_action_digest_field(data: bytes) -> str:
    return _detect_phase_digest_field(data, "ACTION")


def preview_consume(path: Path | str, root: Path | str) -> str:
    """Atomically mark one finalized ACTION stage consumed before side effects."""

    stage = _validate_preview_stage(path, root=root)
    data = _read_regular_bytes(stage.candidate, max_bytes=MAX_PAYLOAD_BYTES)
    phase, nonce = _active_phase_nonce(data)
    if phase != "ACTION" or (phase, nonce) != (stage.phase, stage.nonce):
        raise HelperError("preview-consume accepts only its bound ACTION payload")
    _validate_primary_payload_id(data, phase)
    stored_stage_token, _, _ = _action_stage_token_details(data)
    if not hmac.compare_digest(stored_stage_token, stage.token):
        raise HelperError("ACTION payload token does not match its preview stage")
    field = _detect_action_digest_field(data)
    digest = verify_payload_file(
        stage.candidate,
        field,
        expected_preview_stage_token=stage.token,
    )

    current_candidate = _lstat(stage.candidate)
    current_directory = _lstat(stage.directory)
    if _is_link_or_reparse(current_candidate) or _is_link_or_reparse(current_directory):
        raise HelperError("ACTION stage became a link or reparse point")
    if (stage.directory_stat.st_dev, stage.directory_stat.st_ino) != (
        current_directory.st_dev,
        current_directory.st_ino,
    ):
        raise HelperError("ACTION stage directory identity changed before consume")
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(
        getattr(stage.candidate_stat, name) != getattr(current_candidate, name)
        for name in stable_fields
    ) or not hmac.compare_digest(
        data, _read_regular_bytes(stage.candidate, max_bytes=MAX_PAYLOAD_BYTES)
    ):
        raise HelperError("ACTION candidate changed before consume")

    consumed_sentinel = stage.directory / PREVIEW_CONSUMED_SENTINEL
    try:
        os.replace(stage.sentinel, consumed_sentinel)
    except OSError as exc:
        raise HelperError(f"cannot atomically consume ACTION stage: {exc.strerror or exc}") from exc
    consumed_stage = _validate_preview_stage(
        stage.candidate,
        consumed=True,
        root=root,
    )
    if not hmac.compare_digest(
        data,
        _read_regular_bytes(consumed_stage.candidate, max_bytes=MAX_PAYLOAD_BYTES),
    ):
        raise HelperError("consumed ACTION candidate bytes changed")
    return digest


def preview_remove(path: Path | str, root: Path | str) -> None:
    """Remove only the validated fixed files in one helper-issued stage."""

    try:
        stage = _validate_preview_stage(path, root=root)
    except HelperError as active_error:
        try:
            stage = _validate_preview_stage(path, consumed=True, root=root)
        except HelperError:
            raise active_error
    try:
        with os.scandir(stage.directory) as entries:
            names = []
            for entry in entries:
                names.append(entry.name)
                if len(names) > MAX_PREVIEW_STAGE_ENTRIES:
                    raise HelperError(
                        "preview cleanup refuses an oversized stage"
                    )
            names.sort()
    except OSError as exc:
        raise HelperError(f"cannot inspect preview stage for cleanup: {exc.strerror or exc}") from exc
    if any(name not in PREVIEW_ALLOWED for name in names):
        raise HelperError("preview cleanup refuses an unexpected stage entry")

    for name in sorted(PREVIEW_AUXILIARIES):
        auxiliary = stage.directory / name
        try:
            st = os.lstat(auxiliary)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise HelperError(f"cannot inspect preview auxiliary: {exc.strerror or exc}") from exc
        if _is_link_or_reparse(st) or not stat.S_ISREG(st.st_mode):
            raise HelperError("preview cleanup refuses a linked or non-file auxiliary")
        _assert_single_link(st, auxiliary)
        try:
            os.unlink(auxiliary)
        except OSError as exc:
            raise HelperError(f"cannot remove preview auxiliary: {exc.strerror or exc}") from exc

    _validate_preview_stage(
        stage.candidate,
        consumed=stage.consumed,
        root=root,
    )
    try:
        os.unlink(stage.candidate)
        os.unlink(stage.sentinel)
        os.rmdir(stage.directory)
    except OSError as exc:
        raise HelperError(f"could not finish preview cleanup: {exc.strerror or exc}") from exc


def _resolve_root_relative(root: Path | str, relative: str) -> Path:
    validated = validate_relative_paths(
        root, [relative], require_regular_files=True
    )
    return validated[0].absolute


def _detect_setup_digest_field(data: bytes) -> str:
    return _detect_phase_digest_field(data, "SETUP")


def _require_manifest_encoding(data: bytes) -> None:
    if data.startswith(b"\xef\xbb\xbf"):
        raise HelperError("manifest must not contain a UTF-8 BOM")
    if b"\r" in data:
        raise HelperError("manifest must use LF line endings")
    if not data.endswith(b"\n"):
        raise HelperError("manifest must end in LF")
    forbidden_controls = set(range(0, 32)) - {9, 10}
    if any(byte in forbidden_controls or byte == 127 for byte in data):
        raise HelperError("manifest contains a forbidden control byte")
    try:
        decoded = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise HelperError(f"manifest is not valid UTF-8: {exc}") from exc
    if any(
        unicodedata.category(character) in {"Cc", "Cf"}
        for character in decoded
        if character not in {"\t", "\n"}
    ):
        raise HelperError("manifest contains a control or invisible-format character")


def _verify_manifest_blocks(
    root: Path | str,
    blocks: Sequence[ManifestBlock],
    *,
    allow_status_prefix: bool,
) -> None:
    root_resolved = _require_real_root(Path(root))
    paths = [block.path for block in blocks]
    entries = validate_relative_paths(
        root_resolved, paths, require_regular_files=True
    )
    by_path = {entry.relative: entry.absolute for entry in entries}
    status_re = re.compile(
        r"\A\.(?:claude|cursor|codex|qwen)/tempered/STATUS\.md\Z"
    )
    status_count = 0
    for block in blocks:
        actual = _read_regular_bytes(by_path[block.path])
        if allow_status_prefix and status_re.fullmatch(block.path):
            status_count += 1
            if len(actual) < len(block.content) or not hmac.compare_digest(
                actual[: len(block.content)], block.content
            ):
                raise HelperError(
                    f"mutable STATUS prefix differs from approved setup block: {block.path}"
                )
        elif len(actual) != len(block.content) or not hmac.compare_digest(
            actual, block.content
        ):
            raise HelperError(f"materialized file differs from manifest block: {block.path}")
    if allow_status_prefix and status_count != 1:
        raise HelperError("setup manifest must contain exactly one recognized STATUS block")


def verify_setup(root: Path | str, relative: str) -> tuple[str, int]:
    """Verify a root-bound approved SETUP and all materialized file blocks."""

    setup_path = _resolve_root_relative(root, relative)
    data = _read_regular_bytes(setup_path, max_bytes=MAX_PAYLOAD_BYTES)
    phase, _ = _active_phase_nonce(data)
    if phase != "SETUP":
        raise HelperError("approved setup payload phase is not SETUP")
    field = _detect_setup_digest_field(data)
    digest = verify_payload_file(setup_path, field)
    scope = _payload_scope(data)
    body_start = _setup_body_start(scope)
    blocks, _ = _parse_file_blocks(scope[body_start:])
    if any(block.path == relative for block in blocks):
        raise HelperError("setup manifest must not contain its own APPROVED_SETUP file")
    status_re = re.compile(
        r"\A\.(?:claude|cursor|codex|qwen)/tempered/STATUS\.md\Z"
    )
    status_blocks = [block for block in blocks if status_re.fullmatch(block.path)]
    if len(status_blocks) != 1 or status_blocks[0].verb != "WRITE_NEW":
        raise HelperError(
            "setup manifest requires exactly one recognized WRITE_NEW STATUS block"
        )
    _verify_manifest_blocks(root, blocks, allow_status_prefix=True)
    return digest, len(blocks)


def verify_bundle(root: Path | str, relative: str) -> tuple[str, int]:
    """Verify a root-bound headerless CONTROL_BUNDLE.manifest and its files."""

    bundle_path = _resolve_root_relative(root, relative)
    data = _read_regular_bytes(bundle_path, max_bytes=MAX_MANIFEST_BYTES)
    _require_manifest_encoding(data)
    blocks, _ = _parse_file_blocks(data)
    if any(block.verb != "VERIFY_EXISTING" for block in blocks):
        raise HelperError("control bundle blocks must all use VERIFY_EXISTING")
    if any(block.path == relative for block in blocks):
        raise HelperError("control bundle manifest must not contain itself")
    forbidden = re.compile(
        r"\A\.(?:claude|cursor|codex|qwen)/tempered/"
        r"(?:STATUS|APPROVED_SETUP|APPROVED_PLAN|CONTROL_BUNDLE)\.(?:md|manifest)\Z"
    )
    if any(forbidden.fullmatch(block.path) for block in blocks):
        raise HelperError("control bundle contains a mutable or receipt-authenticated exclusion")
    _verify_manifest_blocks(root, blocks, allow_status_prefix=False)
    return hashlib.sha256(data).hexdigest(), len(blocks)


def _paths_from_file(path: Path | str) -> list[str]:
    data = _read_regular_bytes(Path(path), max_bytes=MAX_PATHS_FILE_BYTES)
    if data.startswith(b"\xef\xbb\xbf"):
        raise HelperError("paths file must not contain a UTF-8 BOM")
    if b"\r" in data:
        raise HelperError("paths file must use LF line endings")
    if not data.endswith(b"\n"):
        raise HelperError("paths file must end in LF")
    if data.count(b"\n") > MAX_PATH_ENTRIES:
        raise HelperError(f"paths file exceeds {MAX_PATH_ENTRIES} entries")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise HelperError(f"paths file is not valid UTF-8: {exc}") from exc
    paths = text[:-1].split("\n")
    if not paths or any(path == "" for path in paths):
        raise HelperError("paths file must contain one non-empty path per line")
    if len(paths) > MAX_PATH_ENTRIES:
        raise HelperError(f"paths file exceeds {MAX_PATH_ENTRIES} entries")
    return paths


def _portable_regular_mode(st: os.stat_result) -> bytes:
    """Map a regular file to the portable Git-style executable mode."""

    if not stat.S_ISREG(st.st_mode):
        raise HelperError("snapshot entry is not a regular file")
    return b"100755" if st.st_mode & 0o111 else b"100644"


def snapshot_digest(root: Path | str, paths: Iterable[str]) -> str:
    """Hash a canonical v2 snapshot of an explicit, validated path set."""

    root_resolved = _require_real_root(Path(root))
    mount_context = _mount_security_context(root_resolved)
    directory_cache: dict[
        Path, tuple[os.stat_result, dict[str, tuple[str, ...]]]
    ] = {}
    scan_budget = _DirectoryScanBudget()
    entries = validate_relative_paths(
        root_resolved,
        paths,
        require_regular_files=True,
        _mount_context_override=mount_context,
        _directory_cache_override=directory_cache,
        _scan_budget_override=scan_budget,
    )
    entries.sort(key=lambda entry: entry.relative.encode("utf-8"))
    digest = hashlib.sha256()
    digest.update(SNAPSHOT_PREFIX)
    total_bytes = 0
    for entry in entries:
        path_bytes = entry.relative.encode("utf-8")
        parts = tuple(entry.relative.split("/"))
        before = _inspect_existing_components(
            root_resolved,
            parts,
            entry.relative,
            mount_context=mount_context,
            directory_cache=directory_cache,
            scan_budget=scan_budget,
        )
        if before is None or not stat.S_ISREG(before.st_mode):
            raise HelperError(f"snapshot path drifted before read: {entry.relative!r}")
        if before.st_size > MAX_SNAPSHOT_FILE_BYTES:
            raise HelperError(
                f"snapshot file exceeds {MAX_SNAPSHOT_FILE_BYTES} byte limit: "
                f"{entry.relative!r}"
            )
        if total_bytes + before.st_size > MAX_SNAPSHOT_TOTAL_BYTES:
            raise HelperError(
                f"snapshot exceeds {MAX_SNAPSHOT_TOTAL_BYTES} total byte limit"
            )
        portable_mode = _portable_regular_mode(before)
        digest.update(b"PATH ")
        digest.update(str(len(path_bytes)).encode("ascii"))
        digest.update(b"\n")
        digest.update(path_bytes)
        digest.update(b"\nTYPE REGULAR\nMODE ")
        digest.update(portable_mode)
        digest.update(b"\n")
        content_bytes, streamed_after = _update_digest_from_regular_file(
            digest,
            entry.absolute,
            max_bytes=MAX_SNAPSHOT_FILE_BYTES,
            emit_snapshot_length=True,
        )
        digest.update(b"\nEND\n")
        total_bytes += content_bytes
        after = _inspect_existing_components(
            root_resolved,
            parts,
            entry.relative,
            mount_context=mount_context,
            directory_cache=directory_cache,
            scan_budget=scan_budget,
        )
        if after is None or not stat.S_ISREG(after.st_mode):
            raise HelperError(f"snapshot path drifted after read: {entry.relative!r}")
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise HelperError(f"snapshot path changed while hashing: {entry.relative!r}")
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            streamed_after.st_dev,
            streamed_after.st_ino,
            streamed_after.st_size,
            streamed_after.st_mtime_ns,
        ):
            raise HelperError(f"snapshot path changed after streamed hash: {entry.relative!r}")
        if portable_mode != _portable_regular_mode(after):
            raise HelperError(f"snapshot file mode changed while hashing: {entry.relative!r}")
    for directory, (cached_stat, _) in directory_cache.items():
        current_stat = _lstat(directory)
        if _is_link_or_reparse(current_stat) or not stat.S_ISDIR(current_stat.st_mode):
            raise HelperError("snapshot directory identity changed while hashing")
        if any(
            getattr(cached_stat, field) != getattr(current_stat, field)
            for field in ("st_dev", "st_ino", "st_mtime_ns")
        ):
            raise HelperError("snapshot directory changed while hashing")
    return digest.hexdigest()


def generate_nonce() -> str:
    """Return 128 bits from the operating-system CSPRNG as lowercase hex."""

    return secrets.token_hex(16)


def self_test() -> None:
    first = generate_nonce()
    second = generate_nonce()
    if not NONCE_RE.fullmatch(first) or not NONCE_RE.fullmatch(second) or first == second:
        raise HelperError("OS CSPRNG nonce self-test failed")
    if hashlib.sha256(b"abc").hexdigest() != (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    ):
        raise HelperError("SHA-256 self-test failed")

    zeroes = b"0" * 64
    template = (
        b"<!-- BEGIN TEMPERED BRIEF PAYLOAD -->\n"
        b"---\n"
        b"payload_type: brief\n"
        b"payload_schema: 2\n"
        b"approval_binding: tempered-loop-sha256-nonce-v2\n"
        b"brief_id: helper-self-test\n"
        b"brief_revision: 1\n"
        b"approval_nonce: 0123456789abcdef0123456789abcdef\n"
        b'payload_sha256: "' + zeroes + b'"\n'
        b"---\n"
        b"self_test: true\n"
        b"<!-- END TEMPERED BRIEF PAYLOAD -->\n"
    )
    calculated = payload_digest(template, "payload_sha256")
    signed = template.replace(zeroes, calculated.encode("ascii"), 1)
    stored, canonical = _canonical_payload(signed, "payload_sha256")
    if stored != calculated or hashlib.sha256(canonical).hexdigest() != calculated:
        raise HelperError("canonical payload self-test failed")
    phase, nonce = _active_phase_nonce(signed)
    if phase != "BRIEF" or nonce != "0123456789abcdef0123456789abcdef":
        raise HelperError("payload phase/nonce self-test failed")
    if _validate_primary_payload_id(signed, phase) != "helper-self-test":
        raise HelperError("payload ID self-test failed")
    mutated = signed.replace(b"self_test: true", b"self_test: false")
    mutated_stored, mutated_canonical = _canonical_payload(mutated, "payload_sha256")
    if hmac.compare_digest(
        mutated_stored, hashlib.sha256(mutated_canonical).hexdigest()
    ):
        raise HelperError("payload mutation self-test failed")

    helper = Path(__file__).resolve(strict=True)
    root = helper.parent
    validate_relative_paths(root, [helper.name], require_regular_files=True)
    if snapshot_digest(root, [helper.name]) != snapshot_digest(root, [helper.name]):
        raise HelperError("snapshot determinism self-test failed")
    for unsafe in (
        "../escape",
        "a\\b",
        "C:/drive",
        "NUL.txt",
        "a//b",
        "~/home",
        "*.txt",
        "$VARIABLE/file",
    ):
        try:
            validate_relative_paths(root, [unsafe])
        except HelperError:
            continue
        raise HelperError(f"unsafe path self-test failed: {unsafe!r}")
    try:
        validate_relative_paths(root, ["prefix", "prefix/child"])
    except HelperError:
        pass
    else:
        raise HelperError("file/directory prefix collision self-test failed")


def _cli_file_path(
    file: str | None,
    root: str | None,
    relative: str | None,
    *,
    direct_names: set[str],
) -> Path:
    if root is None:
        raise HelperError("--root is required for every file operation")
    if file is not None:
        if relative is not None:
            raise HelperError("positional stage file cannot be combined with --relative")
        return _validate_preview_member(file, direct_names, root=root)
    if relative is not None:
        resolved = _resolve_root_relative(root, relative)
        try:
            temp_root = _resolved_temp_root()
            is_preview = (
                resolved.name == PREVIEW_CANDIDATE
                and PREVIEW_DIR_RE.fullmatch(resolved.parent.name) is not None
                and os.path.samefile(resolved.parent.parent, temp_root)
            )
        except OSError:
            is_preview = False
        if is_preview:
            raise HelperError(
                "helper temp candidates must use direct active-stage validation"
            )
        return resolved
    raise HelperError("supply a helper-stage file or --relative with --root")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scoped Tempered Loop v2 receipt, staging, and path helper"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("self-test", help="run dependency-free internal checks")
    commands.add_parser("nonce", help="print a fresh 128-bit OS-CSPRNG nonce")

    sha = commands.add_parser("sha256", help="hash exact root-bound or staged bytes")
    sha.add_argument("file", nargs="?")
    sha.add_argument("--root", required=True)
    sha.add_argument("--relative")

    verify = commands.add_parser(
        "verify-payload", help="verify a canonical zero-field payload digest"
    )
    verify.add_argument("file", nargs="?")
    verify.add_argument("--field", required=True)
    verify.add_argument("--root", required=True)
    verify.add_argument("--relative")

    verify_setup_parser = commands.add_parser(
        "verify-setup", help="verify approved SETUP bytes and materialized files"
    )
    verify_setup_parser.add_argument("--root", required=True)
    verify_setup_parser.add_argument("--relative", required=True)

    verify_bundle_parser = commands.add_parser(
        "verify-bundle", help="verify a headerless control-bundle manifest"
    )
    verify_bundle_parser.add_argument("--root", required=True)
    verify_bundle_parser.add_argument("--relative", required=True)

    snapshot = commands.add_parser(
        "snapshot", help="hash a canonical snapshot of an explicit path list"
    )
    snapshot.add_argument("--root", required=True)
    snapshot.add_argument("--paths-file", required=True)

    paths = commands.add_parser(
        "validate-paths", help="validate an explicit portable path list"
    )
    paths.add_argument("--root", required=True)
    paths.add_argument("--paths-file", required=True)

    preview_create_parser = commands.add_parser(
        "preview-create", help="create one private nonce-bound OS-temp stage"
    )
    preview_create_parser.add_argument("--root", required=True)
    preview_create_parser.add_argument("--phase", required=True, choices=PREVIEW_PHASES)
    preview_create_parser.add_argument("--nonce", required=True)

    preview_metrics_parser = commands.add_parser(
        "preview-metrics",
        help="validate a staged payload and print exact bounded review metrics",
    )
    preview_metrics_parser.add_argument("file")
    preview_metrics_parser.add_argument("--root", required=True)

    preview_finalize_parser = commands.add_parser(
        "preview-finalize", help="atomically sign a zero-field staged payload"
    )
    preview_finalize_parser.add_argument("file")
    preview_finalize_parser.add_argument("--field", required=True)
    preview_finalize_parser.add_argument("--root", required=True)

    preview_consume_parser = commands.add_parser(
        "preview-consume",
        help="atomically mark a finalized ACTION stage consumed (best effort)",
    )
    preview_consume_parser.add_argument("file")
    preview_consume_parser.add_argument("--root", required=True)

    preview_remove_parser = commands.add_parser(
        "preview-remove", help="remove one validated helper-issued temp stage"
    )
    preview_remove_parser.add_argument("file")
    preview_remove_parser.add_argument("--root", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "self-test":
            self_test()
            print("SELF-TEST: PASS")
        elif args.command == "nonce":
            print(generate_nonce())
        elif args.command == "sha256":
            path = _cli_file_path(
                args.file,
                args.root,
                args.relative,
                direct_names={PREVIEW_CANDIDATE, "digest-input.bin"},
            )
            print(sha256_file(path))
        elif args.command == "verify-payload":
            path = _cli_file_path(
                args.file,
                args.root,
                args.relative,
                direct_names={PREVIEW_CANDIDATE},
            )
            expected_stage_token = None
            if args.file is not None:
                expected_stage_token = _validate_preview_stage(
                    path,
                    root=args.root,
                ).token
            print(
                verify_payload_file(
                    path,
                    args.field,
                    expected_preview_stage_token=expected_stage_token,
                )
            )
        elif args.command == "verify-setup":
            digest, _ = verify_setup(args.root, args.relative)
            print(digest)
        elif args.command == "verify-bundle":
            digest, _ = verify_bundle(args.root, args.relative)
            print(digest)
        elif args.command == "snapshot":
            paths_file = _validate_preview_member(
                args.paths_file, {"snapshot-paths.txt"}, root=args.root
            )
            paths = _paths_from_file(paths_file)
            print(snapshot_digest(args.root, paths))
        elif args.command == "validate-paths":
            paths_file = _validate_preview_member(
                args.paths_file, {"proposed-paths.txt"}, root=args.root
            )
            paths = _paths_from_file(paths_file)
            validated = validate_relative_paths(args.root, paths)
            print(f"VALID {len(validated)}")
        elif args.command == "preview-create":
            print(preview_create(args.root, args.phase, args.nonce))
        elif args.command == "preview-metrics":
            print(preview_metrics(args.file, args.root), end="")
        elif args.command == "preview-finalize":
            print(preview_finalize(args.file, args.field, args.root))
        elif args.command == "preview-consume":
            print(f"CONSUMED {preview_consume(args.file, args.root)}")
        elif args.command == "preview-remove":
            preview_remove(args.file, args.root)
            print("REMOVED")
        else:  # pragma: no cover - argparse guarantees a known command.
            raise HelperError("unknown command")
    except HelperError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
