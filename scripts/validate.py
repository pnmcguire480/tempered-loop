"""Strict, dependency-free public-release validation for Tempered Loop v2."""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
import stat
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
APPROVAL_BINDING = "tempered-loop-sha256-nonce-v2"
TRUSTED_PYTHON_PLACEHOLDER = "<trusted-absolute-python>"
TRUSTED_HELPER_PLACEHOLDER = "<canonical-absolute-helper-path>"
LEGACY_WORD = "gaunt" + "let"
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

PUBLIC_FILE_MANIFEST = frozenset(
    {
        ".gitattributes",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/dependabot.yml",
        ".github/workflows/validate.yml",
        ".gitignore",
        "00-START-HERE.txt",
        "CHANGELOG.md",
        "COMMON-TEMPERED-CONTRACT.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "MIGRATION.md",
        "NOTICE.md",
        "PYTHON-SETUP.md",
        "README.md",
        "SECURITY.md",
        "THREAT-MODEL.md",
        "VALIDATION.md",
        "claude/.claude/skills/tempered-compile/SKILL.md",
        "claude/.claude/skills/tempered-compile/reference.md",
        "claude/.claude/skills/tempered-intake/SKILL.md",
        "claude/.claude/tempered-tools/tempered_receipt.py",
        "claude/README.md",
        "codex/.agents/skills/tempered-compile/SKILL.md",
        "codex/.agents/skills/tempered-compile/agents/openai.yaml",
        "codex/.agents/skills/tempered-intake/SKILL.md",
        "codex/.agents/skills/tempered-intake/agents/openai.yaml",
        "codex/.agents/tempered-tools/tempered_receipt.py",
        "codex/README.md",
        "cursor/.cursor/skills/tempered-compile/SKILL.md",
        "cursor/.cursor/skills/tempered-intake/SKILL.md",
        "cursor/.cursor/tempered-tools/tempered_receipt.py",
        "cursor/README.md",
        "qwen/.qwen/commands/tempered/compile.md",
        "qwen/.qwen/commands/tempered/intake.md",
        "qwen/.qwen/tempered-tools/tempered_receipt.py",
        "qwen/README.md",
        "scripts/validate.py",
        "tests/test_guardrails.py",
    }
)
PUBLIC_DIRECTORY_MANIFEST = frozenset(
    str(parent)
    for name in PUBLIC_FILE_MANIFEST
    for parent in PurePosixPath(name).parents
    if str(parent) != "."
)

HELPER_FILES = (
    "claude/.claude/tempered-tools/tempered_receipt.py",
    "codex/.agents/tempered-tools/tempered_receipt.py",
    "cursor/.cursor/tempered-tools/tempered_receipt.py",
    "qwen/.qwen/tempered-tools/tempered_receipt.py",
)

SKILL_FILES = {
    "claude/.claude/skills/tempered-intake/SKILL.md": "tempered-intake",
    "claude/.claude/skills/tempered-compile/SKILL.md": "tempered-compile",
    "cursor/.cursor/skills/tempered-intake/SKILL.md": "tempered-intake",
    "cursor/.cursor/skills/tempered-compile/SKILL.md": "tempered-compile",
    "codex/.agents/skills/tempered-intake/SKILL.md": "tempered-intake",
    "codex/.agents/skills/tempered-compile/SKILL.md": "tempered-compile",
}

QWEN_COMMANDS = {
    "qwen/.qwen/commands/tempered/intake.md",
    "qwen/.qwen/commands/tempered/compile.md",
}

PROTOCOL_FILES = frozenset(SKILL_FILES) | QWEN_COMMANDS

ADAPTERS = {
    "claude": {
        "intake": ("claude/.claude/skills/tempered-intake/SKILL.md",),
        "compile": (
            "claude/.claude/skills/tempered-compile/SKILL.md",
            "claude/.claude/skills/tempered-compile/reference.md",
        ),
        "helper": ".claude/tempered-tools/tempered_receipt.py",
    },
    "cursor": {
        "intake": ("cursor/.cursor/skills/tempered-intake/SKILL.md",),
        "compile": ("cursor/.cursor/skills/tempered-compile/SKILL.md",),
        "helper": ".cursor/tempered-tools/tempered_receipt.py",
    },
    "codex": {
        "intake": ("codex/.agents/skills/tempered-intake/SKILL.md",),
        "compile": ("codex/.agents/skills/tempered-compile/SKILL.md",),
        "helper": ".agents/tempered-tools/tempered_receipt.py",
    },
    "qwen": {
        "intake": ("qwen/.qwen/commands/tempered/intake.md",),
        "compile": ("qwen/.qwen/commands/tempered/compile.md",),
        "helper": ".qwen/tempered-tools/tempered_receipt.py",
    },
}

CANONICAL_APPROVALS = {
    phase: f"APPROVE TEMPERED {phase} <id> R<n> SHA256:<64hex> NONCE:<32hex>"
    for phase in ("BRIEF", "SETUP", "PLAN", "ACTION")
}
CANONICAL_RECEIPTS = {
    "BRIEF": (
        "TEMPERED BRIEF RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> "
        "HELPER_SHA256:<64hex>"
    ),
    "SETUP": (
        "TEMPERED SETUP RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> "
        "HELPER_SHA256:<64hex> CONTROL_SHA256:<64hex>"
    ),
    "PLAN": (
        "TEMPERED PLAN RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> "
        "HELPER_SHA256:<64hex> CONTROL_SHA256:<64hex> ARTIFACT_SHA:<64hex> "
        "GIT:<40-or-64hex-or-NOT_GIT>"
    ),
}

HIGH_IMPACT_ACTION_GROUPS = (
    (("high-impact", "high impact")),
    (("manual-only", "manual only", "manual handoffs only")),
    (("zero agent", "agent makes no", "agent may make no", "agent never executes")),
    (("process",)),
    (("shell",)),
    (("network",)),
    (("secret-provider", "secret provider", "no secrets")),
    (("credential",)),
    (("preflight",)),
    (("side effect", "side-effect", "never executes")),
    (("rollback",)),
    (("reconciliation",)),
    (("digest-bound handoff", "digest-bound")),
    (("approval authorizes only", "approval only authorizes")),
    (("stage-bound", "stage bound")),
    (("not executed", "not_executed")),
    (("handed_off",)),
    (("execution_unknown",)),
    (("human",)),
    ((
        "outside kit enforcement",
        "outside the kit's enforcement",
        "outside tempered loop observation and enforcement",
    )),
    (("duplicate",)),
    (("retry",)),
    (("never infer completion", "completion is never inferred")),
    (("human-attested", "human attested")),
    (("preview-consume",)),
    (("immediately before",)),
    (("best-effort single-delivery", "best effort single delivery")),
    (("crash",)),
    (("ambiguous delivery",)),
    (("new revision",)),
    (("stop",)),
)

LOW_IMPACT_ACTION_GROUPS = (
    (("low-impact", "low impact")),
    (("bounded",)),
    (("reversible",)),
    (("structured argv",)),
    (("strict",)),
    (("literal quoting",)),
    (("canonical cwd", "canonical absolute working directory")),
    (("exact stdin",)),
    (("none",)),
    (("scrubbed", "empty environment")),
    (("finite timeout", "finite deadline")),
    (("host-enforced", "host enforced", "host actually enforces")),
    (("no-network", "no network")),
    (("no-secrets", "no secrets")),
    (("out-of-root", "out of root")),
    (("external-service", "external service")),
    (("uncertain", "uncertainty")),
    (("reclassify", "reclassified", "classify it as high-impact")),
    (("manual action",)),
)

ACTION_LIFECYCLE_LIMITATION_GROUPS = (
    (("best-effort single-delivery", "best effort single delivery")),
    (("compliant",)),
    (("untampered",)),
    (("helper lifecycle",)),
    (("not a security guarantee", "not durable replay protection")),
    (("same principal", "same os principal")),
    (("reverse", "rename back")),
    (("recreate",)),
    (("human idempotency",)),
    (("replay control", "replay controls")),
    (("duplicate risk", "duplicate execution", "may duplicate")),
)

GUIDE_HIGH_IMPACT_GROUPS = (
    (("high-impact", "high impact")),
    (("manual handoff", "manual-only", "manual only")),
    (("agent never executes", "no agent process", "agent makes no process")),
    (("not executed", "not_executed")),
    (("handed_off",)),
    (("execution_unknown",)),
    (("preview-consume",)),
    (("human",)),
    (("out-of-agent", "outside the agent", "outside kit enforcement")),
    (("no cleanup", "without cleanup", "must not clean")),
    (("new revision",)),
    (("plan never", "plan does not", "plan cannot")),
)

STALE_ACTION_AUTOEXEC_PATTERNS = (
    r"\bone exact attempt\b",
    r"\bone attempt only\b",
    r"\bone structured process call\b",
    r"\baction authorizes one exact attempt\b",
    r"\baction permits one exact attempt\b",
)

MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
HOME_PATH_PATTERNS = (
    re.compile(r"(?i)\b[A-Z]:[\\/](?:Users|Documents and Settings)[\\/][^<>{}\s]+"),
    re.compile(r"(?i)(?<![\w.-])/(?:Users|home)/[^/<>{}\s]+/"),
)
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "OpenAI-style secret": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "Stripe live key": re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"),
}


@dataclass
class Scan:
    files: dict[str, Path]
    entries: list[str]


def _is_link_or_reparse(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(
        getattr(st, "st_file_attributes", 0) & REPARSE_POINT
    )


def collision_key(name: str) -> str:
    """Return the cross-platform alias key used for release paths."""

    return "/".join(
        unicodedata.normalize("NFC", part).casefold() for part in name.split("/")
    )


def scan_tree(errors: list[str]) -> Scan:
    files: dict[str, Path] = {}
    entries: list[str] = []
    stack: list[tuple[Path, str]] = [(ROOT, "")]

    while stack:
        directory, prefix = stack.pop()
        try:
            children = list(os.scandir(directory))
        except OSError as exc:
            errors.append(f"Cannot scan release directory {prefix or '.'}: {exc}")
            continue
        for entry in children:
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            relative = relative.replace("\\", "/")
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError as exc:
                errors.append(f"Cannot lstat release path {relative}: {exc}")
                continue
            if _is_link_or_reparse(st):
                errors.append(
                    f"Symlink, junction, or reparse point is forbidden: {relative}"
                )
                continue
            if relative == ".git":
                continue
            entries.append(relative)
            if stat.S_ISDIR(st.st_mode):
                stack.append((Path(entry.path), relative))
            elif stat.S_ISREG(st.st_mode):
                files[relative] = Path(entry.path)
            else:
                errors.append(f"Unsupported filesystem object in release: {relative}")
    return Scan(files, entries)


def validate_path_aliases(entries: list[str], errors: list[str]) -> None:
    seen: dict[str, str] = {}
    for name in sorted(entries, key=lambda value: value.encode("utf-8")):
        if unicodedata.normalize("NFC", name) != name:
            errors.append(f"Release path is not Unicode NFC: {name!r}")
        key = collision_key(name)
        previous = seen.get(key)
        if previous is not None and previous != name:
            errors.append(f"NFC/casefold release-path collision: {previous!r} vs {name!r}")
        else:
            seen[key] = name


def read_canonical_text(name: str, path: Path, errors: list[str]) -> tuple[str, bytes] | None:
    try:
        data = path.read_bytes()
    except OSError as exc:
        errors.append(f"Cannot read {name}: {exc}")
        return None
    if data.startswith(b"\xef\xbb\xbf"):
        errors.append(f"UTF-8 BOM is forbidden: {name}")
    if b"\r" in data:
        errors.append(f"Non-LF line ending: {name}")
    if not data.endswith(b"\n"):
        errors.append(f"Missing final LF: {name}")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        errors.append(f"Invalid UTF-8: {name}: {exc}")
        return None
    if "\x00" in text:
        errors.append(f"NUL byte is forbidden in public text: {name}")
    if any(
        unicodedata.category(character) in {"Cc", "Cf"}
        for character in text
        if character not in {"\t", "\n"}
    ):
        errors.append(f"Control or invisible-format Unicode is forbidden: {name}")
    return text, data


def validate_frontmatter(name: str, text: str, expected_name: str | None, errors: list[str]) -> None:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        errors.append(f"Missing frontmatter start: {name}")
        return
    try:
        end = lines.index("---", 1)
    except ValueError:
        errors.append(f"Missing frontmatter end: {name}")
        return
    if end > 30:
        errors.append(f"Frontmatter exceeds 30 lines: {name}")
    fields: dict[str, str] = {}
    for number, line in enumerate(lines[1:end], start=2):
        if not line or line.startswith((" ", "-", "#")):
            continue
        if ":" not in line:
            errors.append(f"Malformed frontmatter line: {name}:{number}")
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in fields:
            errors.append(f"Duplicate frontmatter key {key!r}: {name}")
        fields[key] = value.strip()
    if not fields.get("description"):
        errors.append(f"Frontmatter description is required: {name}")
    if expected_name is not None and fields.get("name") != expected_name:
        errors.append(
            f"Frontmatter name must be {expected_name!r}, got {fields.get('name')!r}: {name}"
        )


def _local_target(source_name: str, raw_target: str, errors: list[str]) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    elif " " in target:
        target = target.split(None, 1)[0]
    if target.startswith("#"):
        return source_name
    if target.startswith("//") or SCHEME_RE.match(target):
        return None
    target = unquote(target)
    parsed = urlsplit(target)
    path_part = parsed.path
    if not path_part:
        return source_name
    if "\\" in path_part or path_part.startswith("/"):
        errors.append(f"Unsafe local link: {source_name} -> {raw_target}")
        return None
    joined = posixpath.normpath(
        posixpath.join(str(PurePosixPath(source_name).parent), path_part)
    )
    if joined == ".." or joined.startswith("../"):
        errors.append(f"Local link escapes release: {source_name} -> {raw_target}")
        return None
    return joined


def validate_markdown(name: str, text: str, errors: list[str]) -> None:
    fences = {"```": 0, "~~~": 0}
    for line in text.splitlines():
        stripped = line.lstrip()
        for fence in fences:
            if stripped.startswith(fence):
                fences[fence] += 1
    for fence, count in fences.items():
        if count % 2:
            errors.append(f"Unbalanced Markdown fence {fence!r} ({count}): {name}")

    for match in MARKDOWN_LINK_RE.finditer(text):
        target = _local_target(name, match.group(1), errors)
        if target is not None and target not in PUBLIC_FILE_MANIFEST:
            errors.append(f"Broken or unmanifested local link: {name} -> {match.group(1)}")


def validate_public_text(name: str, text: str, errors: list[str]) -> None:
    for pattern in HOME_PATH_PATTERNS:
        if pattern.search(text):
            errors.append(f"Personal absolute path found: {name}")
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            errors.append(f"Possible {label} found: {name}")
    private_phrases = (
        "bull" + "shit",
        "make this " + "shit",
        "go " + "viral",
    )
    if any(phrase in text.casefold() for phrase in private_phrases):
        errors.append(f"Internal launch language found: {name}")


def validate_legacy_names(name: str, text: str, errors: list[str]) -> None:
    if LEGACY_WORD not in text.casefold():
        return
    if name in {"README.md", "NOTICE.md"}:
        allowed = (
            "[Gaunt"
            + "let Loop write-up](https://somethingbig.ai/"
            + LEGACY_WORD
            + "-loop)"
        )
        remainder = text.replace(allowed, "")
        if LEGACY_WORD in remainder.casefold():
            errors.append(f"Non-attribution legacy identifier found: {name}")
        return
    if name == "MIGRATION.md":
        lowered = text.casefold()
        required = ("migration-only", "inert", "do not invoke")
        if not all(phrase in lowered for phrase in required):
            errors.append(
                "MIGRATION.md legacy examples require migration-only, inert, and do-not-invoke warnings"
            )
        return
    errors.append(f"Legacy v1 identifier is forbidden: {name}")


def validate_protocol_file(name: str, text: str, errors: list[str]) -> None:
    if "payload_schema: 2" not in text:
        errors.append(f"Protocol v2 payload_schema is missing: {name}")
    for match in re.finditer(r"(?m)^payload_schema:\s*([^\s#]+)", text):
        if match.group(1).strip("\"'") != "2":
            errors.append(f"Legacy or unsupported payload_schema in {name}: {match.group(1)}")
    binding_line = f"approval_binding: {APPROVAL_BINDING}"
    if binding_line not in text:
        errors.append(f"Protocol v2 approval_binding is missing: {name}")
    for match in re.finditer(r"(?m)^approval_binding:\s*([^\s#]+)", text):
        if match.group(1).strip("\"'") != APPROVAL_BINDING:
            errors.append(f"Legacy or unsupported approval_binding in {name}")

    for line_number, line in enumerate(text.splitlines(), start=1):
        upper = line.upper()
        if "TEMPERED" not in upper or "RECEIPT" not in upper:
            continue
        if any(
            old in upper
            for old in (
                "CONTROL_BUNDLE_SHA256:",
                " BUNDLE:",
                "SETUP-SHA256:",
                "SETUP_SHA256:",
            )
        ):
            errors.append(f"Noncanonical v2 receipt label: {name}:{line_number}")


def _corpus(names: tuple[str, ...], texts: dict[str, str]) -> str:
    return "\n".join(texts.get(name, "") for name in names)


def _markdown_section(corpus: str, title: str) -> str:
    """Return one Markdown heading section through the next peer/parent heading."""

    heading = re.search(
        rf"(?im)^(?P<marks>#{{2,6}})[^\n]*{re.escape(title)}[^\n]*$",
        corpus,
    )
    if heading is None:
        return ""
    level = len(heading.group("marks"))
    body_start = heading.end()
    following = re.search(rf"(?m)^#{{1,{level}}}\s", corpus[body_start:])
    body_end = len(corpus) if following is None else body_start + following.start()
    return corpus[body_start:body_end]


def require_literal(label: str, literal: str, corpus: str, errors: list[str]) -> None:
    if literal not in corpus:
        errors.append(f"Semantic clause missing ({label}): {literal}")


def require_pattern(label: str, pattern: str, corpus: str, errors: list[str]) -> None:
    if re.search(pattern, corpus, flags=re.IGNORECASE | re.DOTALL) is None:
        errors.append(f"Semantic clause missing ({label})")


def require_term_groups(
    label: str,
    corpus: str,
    groups: tuple[tuple[str, ...], ...],
    errors: list[str],
) -> None:
    """Require one alternative from every semantic group, independent of prose order."""

    def semantic_fold(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        normalized = "".join(
            "-" if unicodedata.category(character) == "Pd" else character
            for character in normalized
        )
        return " ".join(normalized.split())

    lowered = semantic_fold(corpus)
    missing = [
        alternatives
        for alternatives in groups
        if not any(semantic_fold(term) in lowered for term in alternatives)
    ]
    if missing:
        readable = ", ".join("|".join(alternatives) for alternatives in missing)
        errors.append(f"Semantic clause missing ({label}; needs {readable})")


def validate_adapter_semantics(texts: dict[str, str], errors: list[str]) -> None:
    for host, config in ADAPTERS.items():
        intake = _corpus(config["intake"], texts)
        compile_text = _corpus(config["compile"], texts)
        guide = texts.get(f"{host}/README.md", "")
        helper = config["helper"]

        require_literal(f"{host} intake helper", helper, intake, errors)
        require_literal(
            f"{host} intake canonical absolute helper",
            TRUSTED_HELPER_PLACEHOLDER,
            intake,
            errors,
        )
        require_literal(
            f"{host} intake bound helper invocation",
            f"{TRUSTED_PYTHON_PLACEHOLDER} -I -S -B {TRUSTED_HELPER_PLACEHOLDER}",
            intake,
            errors,
        )
        require_literal(
            f"{host} intake trusted absolute interpreter",
            TRUSTED_PYTHON_PLACEHOLDER,
            intake,
            errors,
        )
        require_literal(f"{host} intake nonce command", " nonce", intake, errors)
        require_literal(
            f"{host} intake payload verification command", "verify-payload", intake, errors
        )
        require_literal(
            f"{host} intake BRIEF approval grammar",
            CANONICAL_APPROVALS["BRIEF"],
            intake,
            errors,
        )
        require_literal(
            f"{host} intake BRIEF receipt grammar",
            CANONICAL_RECEIPTS["BRIEF"],
            intake,
            errors,
        )
        require_term_groups(
            f"{host} manual-save raw-byte equality",
            intake,
            (
                (("manual saving", "manually saved", "manual-save")),
                (("raw bytes", "raw file", "byte-for-byte", "exact bytes")),
                (("approved candidate", "approved payload", "displayed candidate")),
                (("approval token", "original approval")),
                (("self-consistent", "self consistent")),
            ),
            errors,
        )
        require_term_groups(
            f"{host} intake terminal receipt and partial-state quarantine",
            intake,
            (
                (("preview-remove",)),
                (("receipt precondition", "before emitting", "before receipt")),
                (("invalid/partial",)),
                (("no receipt", "emit no receipt", "withhold the receipt")),
                (("no retry", "never retry", "must not retry")),
                (("no cleanup", "do not clean", "must not clean")),
                (("quarantine",)),
                (("human reconciliation",)),
                (("after emitting a receipt", "after receipt emission")),
                (("never mutate", "no further mutation", "must not mutate")),
                (("stop",)),
            ),
            errors,
        )
        require_term_groups(
            f"{host} intake single top-level session",
            intake,
            (
                (("concurrent", "simultaneous")),
                (("top-level", "top level")),
                (("canonical root", "canonical project root")),
                (("unsupported",)),
                (("exactly one", "one active")),
                (("chat",)),
                (("process",)),
                (("terminal stop",)),
                (("stage cleanup",)),
                (("stop",)),
                (("reconcile", "reconciliation")),
                (("depth-one", "depth one")),
                (("coordinator",)),
            ),
            errors,
        )
        require_term_groups(
            f"{host} intake helper path and argv binding",
            intake,
            (
                (("canonical absolute helper",)),
                (("canonical root", "canonical project root")),
                (("every component", "all components", "each path component")),
                (("symlink",)),
                (("junction",)),
                (("reparse",)),
                (("hash", "sha-256", "sha256")),
                (("same exact path", "exact same path", "identical absolute path")),
                (("every invocation", "all helper calls", "every helper command")),
                (("distinct argv", "separate argv")),
                (("cwd drift", "working-directory drift")),
                (("shell interpolation",)),
            ),
            errors,
        )

        require_term_groups(
            f"{host} compiler helper",
            compile_text,
            ((('helper',)), (('self-test',)), (('independent', 'bootstrap'))),
            errors,
        )
        require_literal(
            f"{host} compiler trusted absolute interpreter",
            TRUSTED_PYTHON_PLACEHOLDER,
            compile_text,
            errors,
        )
        require_literal(
            f"{host} compiler canonical absolute helper",
            TRUSTED_HELPER_PLACEHOLDER,
            compile_text,
            errors,
        )
        require_literal(
            f"{host} compiler bound helper invocation",
            f"{TRUSTED_PYTHON_PLACEHOLDER} -I -S -B {TRUSTED_HELPER_PLACEHOLDER}",
            compile_text,
            errors,
        )
        require_term_groups(
            f"{host} absolute interpreter trust",
            intake + "\n" + compile_text,
            (
                (("all helper calls", "every helper invocation", "every helper command")),
                (("same trusted absolute interpreter", "one trusted absolute interpreter")),
                ((
                    "user-known",
                    "host-known",
                    "user/host-known",
                    "user or trusted host",
                )),
                (("outside the project", "outside the project root")),
                (("path lookup", "path search", "path resolution", "command lookup")),
                (("symlink",)),
                (("reparse",)),
            ),
            errors,
        )
        for command in (
            "nonce",
            "sha256",
            "verify-payload",
            "snapshot",
            "validate-paths",
            "preview-create",
            "preview-metrics",
            "preview-finalize",
            "preview-consume",
            "preview-remove",
            "verify-setup",
            "verify-bundle",
        ):
            require_literal(f"{host} compiler helper command", command, compile_text, errors)
        for phase in ("SETUP", "PLAN", "ACTION"):
            require_literal(
                f"{host} {phase} approval grammar",
                CANONICAL_APPROVALS[phase],
                compile_text,
                errors,
            )
        for phase in ("BRIEF", "SETUP", "PLAN"):
            require_literal(
                f"{host} {phase} receipt grammar",
                CANONICAL_RECEIPTS[phase],
                compile_text,
                errors,
            )

        semantic_groups = {
            "external helper bootstrap trust": (
                (("helper_sha256",)),
                (("placeholder-only", "placeholder only", "placeholders only")),
                (("before any project-local read", "before reading any project-local")),
                (("subsequent current user turn", "later current-user turn")),
                (("independently hash", "independent hash")),
                (("compare directly", "directly compare")),
                (("only then",)),
            ),
            "helper path and argv binding": (
                (("canonical absolute helper",)),
                (("canonical root", "canonical project root")),
                (("every component", "all components", "each path component")),
                (("symlink",)),
                (("junction",)),
                (("reparse",)),
                (("hash", "sha-256", "sha256")),
                (("same exact path", "exact same path", "identical absolute path")),
                (("every invocation", "all helper calls", "every helper command")),
                (("distinct argv", "separate argv")),
                (("cwd drift", "working-directory drift")),
                (("shell interpolation",)),
            ),
            "receipt emission is terminal": (
                (("after emitting a receipt", "after receipt emission")),
                (("never mutate", "no further mutation", "must not mutate")),
            ),
            "partial action quarantine": (
                (("invalid/partial",)),
                (("no retry", "never retry", "must not retry")),
                (("no cleanup", "do not clean", "must not clean")),
                (("quarantine",)),
                (("human reconciliation",)),
            ),
            "crash-safe setup materialization order": (
                (("crash",)),
                (("inert",)),
                (("tempered/",)),
                (("first",)),
                (("host-active", "host active")),
                (("agent",)),
                (("rule",)),
                (("config", "snippet")),
                (("last",)),
            ),
            "ACTION preview-stage replay binding": (
                (("preview_stage_token",)),
                (("32 zeroes", "32 zeros")),
                (("replace", "inject")),
                (("stage token",)),
                (("digest",)),
                (("verify",)),
                (("consume",)),
                (("duplicate",)),
                (("recreate", "recreated", "re-created", "recreation")),
                (("helper-created", "helper created", "ordinary")),
                (("reject", "cannot reuse")),
            ),
            "ACTION lifecycle limitation": ACTION_LIFECYCLE_LIMITATION_GROUPS,
            "trusted-instruction threat model": (
                (("instruction_trust_mode",)),
                (("clean bootstrap",)),
                (("stop", "refuse", "block")),
                (("evidence",)),
            ),
            "launch snapshot recomputation": (
                (("launch", "launcher")),
                (("recompute", "recomputes")),
                (("artifact snapshot", "artifact_snapshot")),
                (("git state", "git identity", "git:")),
                (("drift", "mismatch")),
            ),
            "advisory Git dirty-state coverage": (
                (("git_status_baseline",)),
                (("porcelain",)),
                (("advisory",)),
                (("dirty regular",)),
                (("byte-bound", "byte bound")),
                (("unmerged",)),
                (("submodule",)),
                (("unparsed",)),
                (("uncovered",)),
                (("approved_plan",)),
                (("status",)),
                (("root-bound",)),
                (("ignored",)),
                (("omitted",)),
            ),
            "trusted Git executable identity": (
                (("git executable",)),
                ((
                    "user-known",
                    "host-known",
                    "user/host-known",
                    "user or trusted host",
                )),
                (("canonical absolute", "absolute git")),
                (("outside the project", "outside the project root")),
                (("path lookup", "path search", "command lookup")),
                (("fixed argv", "fixed argument vector")),
                (("symlink",)),
                (("reparse",)),
                (("version",)),
                (("digest", "sha-256", "sha256")),
                (("recheck", "rehash")),
                ((
                    "immediately before use",
                    "immediately before every use",
                    "immediately before each",
                    "immediately before every call",
                    "before each use",
                )),
                (("structured argv",)),
                (("does not authenticate", "cannot authenticate")),
                (("not_git",)),
                (("no git drift coverage",)),
            ),
            "ACTION executable identity": (
                ((
                    "action executable",
                    "approved executable",
                    "intended executable",
                    "exact executable identity",
                )),
                (("canonical absolute",)),
                (("symlink",)),
                (("reparse",)),
                (("executable-byte", "executable bytes", "exact executable")),
                (("sha-256", "sha256")),
                (("recheck", "rehash")),
                (("immediately before",)),
                (("preview-consume",)),
                (("process", "launch")),
                (("stop",)),
                (("manual",)),
            ),
            "high-impact ACTION manual-only handoff": HIGH_IMPACT_ACTION_GROUPS,
            "low-impact ACTION execution containment": LOW_IMPACT_ACTION_GROUPS,
            "bounded payload review metrics": (
                (("preview-metrics",)),
                (("byte count", "bytes")),
                (("lf count", "line-feed count", "line feed count")),
                (("embedded-block count", "embedded block count", "blocks")),
                (("deterministic path index", "path-index-sha256")),
                (("32 mib", "32 mebibytes")),
                (("100,000", "100000")),
                (("stop", "refuse", "reject")),
            ),
            "single top-level session": (
                (("concurrent", "simultaneous")),
                (("top-level", "top level")),
                (("canonical root", "canonical project root")),
                (("unsupported",)),
                (("exactly one", "one active")),
                (("chat",)),
                (("process",)),
                (("terminal stop",)),
                (("stage cleanup",)),
                (("stop",)),
                (("reconcile", "reconciliation")),
                (("depth-one", "depth one")),
                (("coordinator",)),
            ),
            "ACTION is separate from PLAN": (
                (("plan approval", "approved plan", "plan never")),
                (("cannot", "does not", "never satisfies", "never enough")),
                (("action",)),
            ),
            "task/result digest chain": (
                (("every task", "task envelope")),
                (("every result", "result envelope")),
                (("brief_payload_sha256",)),
                (("setup_payload_sha256",)),
                (("plan_payload_sha256",)),
                (("stale",)),
            ),
            "immutable approved setup": (
                (("approved_setup",)),
                (("immutable",)),
                (("status",)),
                (("reconstruct",)),
                (("never", "do not", "must not")),
            ),
            "remote/cloud v1 gate": (
                (("remote", "cloud")),
                (("unsupported", "local-only", "separately gated", "separate approval")),
                (("public v1", "this kit")),
            ),
            "coordinator-only depth one": (
                (("coordinator",)),
                (("depth-one", "depth one", "maxsubagentdepth: 1")),
                (("only", "sole")),
                (("dispatch", "delegation")),
            ),
            "exclusive non-file resource ledger": (
                (("exclusive",)),
                (("non-file resource",)),
                (("ledger", "resources.md")),
            ),
            "raw-evidence secret redaction": (
                (("raw evidence", "raw path", "raw bytes")),
                (("redact", "redacted", "redaction")),
                (("secret",)),
                (("restricted",)),
            ),
        }
        for label, groups in semantic_groups.items():
            require_term_groups(f"{host} {label}", compile_text, groups, errors)

        lowered_compile = compile_text.casefold()
        numeric_ceiling_proof = all(
            term in lowered_compile for term in ("numeric", "ceiling")
        ) and any(
            term in lowered_compile for term in ("observed", "smoke test", "proven")
        )
        one_cycle_fallback = any(
            term in lowered_compile
            for term in (
                "one-cycle",
                "one cycle",
                "one authenticated ordinary-chat cycle",
                "exactly one numbered",
            )
        ) and any(
            term in lowered_compile for term in ("manual", "ordinary chat", "ordinary-chat")
        )
        if not (numeric_ceiling_proof or one_cycle_fallback):
            errors.append(
                f"Semantic clause missing ({host} numeric ceiling proof or one-cycle fallback)"
            )

        for digest_field in (
            "brief_payload_sha256",
            "setup_payload_sha256",
            "plan_payload_sha256",
        ):
            require_literal(
                f"{host} task/result binding", digest_field, compile_text, errors
            )
        require_term_groups(
            f"{host} public guide high-impact manual handoff",
            guide,
            GUIDE_HIGH_IMPACT_GROUPS,
            errors,
        )
        require_term_groups(
            f"{host} public guide ACTION lifecycle limitation",
            guide,
            ACTION_LIFECYCLE_LIMITATION_GROUPS,
            errors,
        )
        for artifact in ("EXECUTION_PROMPT.md", "RUNBOOK.md"):
            section = _markdown_section(compile_text, artifact)
            if not section:
                errors.append(f"Required generated-artifact section missing: {host} {artifact}")
                continue
            require_term_groups(
                f"{host} generated {artifact} high-impact manual handoff",
                section,
                GUIDE_HIGH_IMPACT_GROUPS,
                errors,
            )
            require_term_groups(
                f"{host} generated {artifact} ACTION lifecycle limitation",
                section,
                ACTION_LIFECYCLE_LIMITATION_GROUPS,
                errors,
            )
        for pattern in STALE_ACTION_AUTOEXEC_PATTERNS:
            if re.search(pattern, compile_text + "\n" + guide, flags=re.IGNORECASE):
                errors.append(
                    f"Legacy high-impact ACTION auto-execution language: {host}: {pattern}"
                )

    qwen = _corpus(ADAPTERS["qwen"]["compile"], texts)
    require_literal("Qwen depth ceiling", "maxSubagentDepth: 1", qwen, errors)
    require_term_groups(
        "Qwen task denial",
        qwen,
        ((("task",)), (("deny", "denied", "denies"))),
        errors,
    )
    require_pattern(
        "Qwen controlled model fallbacks",
        r"modelFallbacks.{0,220}(?:empty|same-family|explicit(?:ly)? approved)",
        qwen,
        errors,
    )


def validate_root_semantics(texts: dict[str, str], errors: list[str]) -> None:
    common = texts.get("COMMON-TEMPERED-CONTRACT.md", "")
    threat = texts.get("THREAT-MODEL.md", "")
    migration = texts.get("MIGRATION.md", "")
    validation = texts.get("VALIDATION.md", "")
    python_setup = texts.get("PYTHON-SETUP.md", "")
    start_here = texts.get("00-START-HERE.txt", "")
    readme = texts.get("README.md", "")
    require_literal("common protocol schema", "payload_schema: 2", common, errors)
    require_literal(
        "common approval binding", f"approval_binding: {APPROVAL_BINDING}", common, errors
    )
    for phase, grammar in CANONICAL_APPROVALS.items():
        require_literal(f"common {phase} approval grammar", grammar, common, errors)
    for phase, grammar in CANONICAL_RECEIPTS.items():
        require_literal(f"common {phase} receipt grammar", grammar, common, errors)
    require_term_groups(
        "central trusted-instruction threat model",
        threat,
        (
            (("trusted instruction",)),
            (("untrusted repository", "unfamiliar or hostile")),
            (("cannot demote", "does not reliably make them inert")),
            (("clean bootstrap",)),
            (("stop", "unsupported")),
        ),
        errors,
    )
    for label, corpus in (
        ("common single top-level session", common),
        ("threat-model single top-level session", threat),
    ):
        require_term_groups(
            label,
            corpus,
            (
                (("concurrent", "simultaneous")),
                (("top-level", "top level")),
                (("canonical root", "canonical project root")),
                (("unsupported",)),
                (("exactly one", "one active")),
                (("chat",)),
                (("process",)),
                (("terminal stop",)),
                (("stage cleanup",)),
                (("stop",)),
                (("reconcile", "reconciliation")),
                (("depth-one", "depth one")),
                (("coordinator",)),
            ),
            errors,
        )
    require_term_groups(
        "migration examples are inert",
        migration,
        (
            (("migration-only",)),
            (("inert",)),
            (("do not invoke",)),
            (("protocol-v1",)),
        ),
        errors,
    )
    require_term_groups(
        "central ACTION preview-stage replay binding",
        common,
        (
            (("preview_stage_token",)),
            (("32 zeroes", "32 zeros")),
            (("replace", "inject")),
            (("digest",)),
            (("duplicate",)),
            (("recreate", "recreated", "re-created", "recreation")),
            (("helper-created", "helper created", "ordinary")),
            (("reject", "cannot reuse")),
        ),
        errors,
    )
    for label, corpus in (
        ("common ACTION safety boundary", common),
        ("threat-model ACTION safety boundary", threat),
    ):
        require_term_groups(
            f"{label} high-impact manual-only handoff",
            corpus,
            HIGH_IMPACT_ACTION_GROUPS,
            errors,
        )
        require_term_groups(
            f"{label} low-impact execution containment",
            corpus,
            LOW_IMPACT_ACTION_GROUPS,
            errors,
        )
        require_term_groups(
            f"{label} ACTION lifecycle limitation",
            corpus,
            ACTION_LIFECYCLE_LIMITATION_GROUPS,
            errors,
        )
    for label, corpus in (
        ("root README high-impact manual handoff", readme),
        ("start-here high-impact manual handoff", start_here),
    ):
        require_term_groups(label, corpus, GUIDE_HIGH_IMPACT_GROUPS, errors)
        require_term_groups(
            label.replace("high-impact manual handoff", "ACTION lifecycle limitation"),
            corpus,
            ACTION_LIFECYCLE_LIMITATION_GROUPS,
            errors,
        )
    for pattern in STALE_ACTION_AUTOEXEC_PATTERNS:
        for name, corpus in (
            ("COMMON-TEMPERED-CONTRACT.md", common),
            ("THREAT-MODEL.md", threat),
            ("README.md", readme),
            ("00-START-HERE.txt", start_here),
        ):
            if re.search(pattern, corpus, flags=re.IGNORECASE):
                errors.append(
                    f"Legacy high-impact ACTION auto-execution language: {name}: {pattern}"
                )
    require_literal(
        "local validation trusted absolute interpreter",
        TRUSTED_PYTHON_PLACEHOLDER,
        validation,
        errors,
    )
    require_term_groups(
        "local validation interpreter resolution",
        validation,
        (
            (("user-known", "host-known", "user/host-known")),
            (("outside the project", "outside the project root")),
            (("path lookup", "path search", "path resolution", "command lookup")),
            (("symlink",)),
            (("reparse",)),
        ),
        errors,
    )
    for label, corpus in (
        ("root README Python setup link", readme),
        ("start-here Python setup link", start_here),
    ):
        require_literal(label, "PYTHON-SETUP.md", corpus, errors)
    require_term_groups(
        "beginner Python setup compatibility and trust",
        python_setup,
        (
            ((
                "python 3.10+",
                "python 3.10 or newer",
                "python 3.10 and newer",
                "python **3.10 or newer**",
                "python >=3.10",
            )),
            (("windows",)),
            (("macos", "mac os")),
            (("linux",)),
            (("absolute",)),
            (("outside the project", "outside your project")),
            (("path lookup", "path search", "command lookup")),
            (("symlink",)),
            (("reparse",)),
            (("stop",)),
            (("ask",)),
        ),
        errors,
    )


def validate_ci_semantics(texts: dict[str, str], errors: list[str]) -> None:
    workflow = texts.get(".github/workflows/validate.yml", "")
    dependabot = texts.get(".github/dependabot.yml", "")

    uses_lines = re.findall(r"(?m)^\s*-?\s*uses:\s*([^\s#]+)", workflow)
    if not uses_lines:
        errors.append("CI workflow contains no actions to validate")
    for action in uses_lines:
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}", action) is None:
            errors.append(f"CI action is not pinned to a full commit SHA: {action}")
    for literal in (
        "permissions:\n  contents: read",
        "persist-credentials: false",
        "ubuntu-latest",
        "windows-latest",
        "macos-latest",
        'python: ["3.10", "3.12"]',
        "timeout-minutes:",
        "shell: pwsh",
        "$env:pythonLocation",
        "ResolveLinkTarget($true)",
        "[IO.Path]::GetRelativePath",
        "Invoke-TrustedPython -I -S -B scripts/validate.py",
        "Invoke-TrustedPython -I -S -B claude/.claude/tempered-tools/tempered_receipt.py self-test",
        "Invoke-TrustedPython -I -S -B cursor/.cursor/tempered-tools/tempered_receipt.py self-test",
        "Invoke-TrustedPython -I -S -B codex/.agents/tempered-tools/tempered_receipt.py self-test",
        "Invoke-TrustedPython -I -S -B qwen/.qwen/tempered-tools/tempered_receipt.py self-test",
        'Invoke-TrustedPython -I -S -B -m unittest discover -s tests -p "test_*.py" -v',
    ):
        require_literal("CI hardening", literal, workflow, errors)
    if re.search(r"(?m)^\s*pull_request_target\s*:", workflow):
        errors.append("CI must not use pull_request_target for untrusted contributions")
    if re.search(r"(?im)^\s*[A-Za-z_-]+:\s*write\s*$", workflow):
        errors.append("CI workflow permissions must remain read-only")
    if re.search(r"(?im)^\s*persist-credentials:\s*true\s*$", workflow):
        errors.append("CI checkout must not persist credentials for pull-request code")
    if re.search(r"(?m)^\s*(?:run:\s*)?python(?:3(?:\.\d+)?)?\s", workflow):
        errors.append("CI must not resolve Python through PATH")

    for literal in (
        "version: 2",
        "package-ecosystem: github-actions",
        "directory: /",
        "interval: monthly",
    ):
        require_literal("Dependabot GitHub Actions maintenance", literal, dependabot, errors)


def validate_helper_semantics(texts: dict[str, str], errors: list[str]) -> None:
    helper = texts.get(HELPER_FILES[0], "")
    for literal in (
        "preview-metrics",
        "MAX_PAYLOAD_BYTES = 32 * 1024 * 1024",
        "MAX_PAYLOAD_LINES = 500_000",
        "MAX_MANIFEST_BYTES = 32 * 1024 * 1024",
        "MAX_PATH_ENTRIES = 100_000",
        "MAX_MANIFEST_BLOCKS = 100_000",
        "MAX_PATH_UTF8_BYTES = 4096",
        "MAX_PATH_DEPTH = 128",
        "MAX_TOTAL_PATH_COMPONENTS = 500_000",
        "MAX_SCANNED_DIRECTORY_ENTRIES = 100_000",
        "MAX_SCANNED_DIRECTORY_NAME_BYTES = 16 * 1024 * 1024",
        "MAX_PREVIEW_STAGE_ENTRIES = len(PREVIEW_ALLOWED)",
        "multi-link regular files are forbidden",
        "nested mount traversal is forbidden",
        "mount-boundary status is UNKNOWN",
        "best-effort single-delivery",
        "PATH-INDEX-SHA256",
    ):
        require_literal("helper hardening", literal, helper, errors)


def manifest_digest(raw_files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    digest.update(b"TEMPERED-PUBLIC-MANIFEST-V2\n")
    for name in sorted(PUBLIC_FILE_MANIFEST, key=lambda value: value.encode("utf-8")):
        name_bytes = name.encode("utf-8")
        content = raw_files[name]
        digest.update(b"PATH ")
        digest.update(str(len(name_bytes)).encode("ascii"))
        digest.update(b"\n")
        digest.update(name_bytes)
        digest.update(b"\nBYTES ")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\n")
        digest.update(content)
        digest.update(b"\nEND\n")
    return digest.hexdigest()


def main() -> int:
    errors: list[str] = []
    scan = scan_tree(errors)
    validate_path_aliases(scan.entries, errors)

    actual = set(scan.files)
    actual_directories = set(scan.entries) - actual
    for name in sorted(PUBLIC_FILE_MANIFEST - actual):
        errors.append(f"Missing public-manifest file: {name}")
    for name in sorted(actual - PUBLIC_FILE_MANIFEST):
        errors.append(f"Unexpected public file: {name}")
    for name in sorted(actual_directories - PUBLIC_DIRECTORY_MANIFEST):
        errors.append(f"Unexpected public directory: {name}")

    texts: dict[str, str] = {}
    raw_files: dict[str, bytes] = {}
    for name in sorted(PUBLIC_FILE_MANIFEST & actual):
        result = read_canonical_text(name, scan.files[name], errors)
        if result is None:
            continue
        text, raw = result
        texts[name] = text
        raw_files[name] = raw
        if name.endswith(".py") and raw.startswith(b"#!"):
            errors.append(f"Python entry points must not use a PATH-resolved shebang: {name}")
        validate_public_text(name, text, errors)
        validate_legacy_names(name, text, errors)
        if name.endswith(".md"):
            validate_markdown(name, text, errors)

    for name, expected_name in SKILL_FILES.items():
        if name in texts:
            validate_frontmatter(name, texts[name], expected_name, errors)
    for name in QWEN_COMMANDS:
        if name in texts:
            validate_frontmatter(name, texts[name], None, errors)
    for name in PROTOCOL_FILES:
        if name in texts:
            validate_protocol_file(name, texts[name], errors)

    for name in (
        "codex/.agents/skills/tempered-intake/agents/openai.yaml",
        "codex/.agents/skills/tempered-compile/agents/openai.yaml",
    ):
        if name in texts and "allow_implicit_invocation: false" not in texts[name]:
            errors.append(f"Codex skill must disable implicit invocation: {name}")

    helper_blobs = [raw_files[name] for name in HELPER_FILES if name in raw_files]
    if len(helper_blobs) == len(HELPER_FILES) and any(
        blob != helper_blobs[0] for blob in helper_blobs[1:]
    ):
        errors.append("The four adapter helper copies are not byte-identical")

    validate_root_semantics(texts, errors)
    validate_adapter_semantics(texts, errors)
    validate_ci_semantics(texts, errors)
    validate_helper_semantics(texts, errors)

    if errors:
        print("VALIDATION: FAIL", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    if set(raw_files) != PUBLIC_FILE_MANIFEST:
        print("VALIDATION: FAIL", file=sys.stderr)
        print("- Cannot digest an incomplete public manifest", file=sys.stderr)
        return 1

    print("VALIDATION: PASS")
    print(f"Files inspected: {len(raw_files)}")
    print(f"Public-manifest digest: {manifest_digest(raw_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
