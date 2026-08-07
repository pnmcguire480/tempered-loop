"""Adversarial, dependency-free tests for Tempered Loop v2 guardrails."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path


sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "scripts" / "validate.py"
HELPER_PATHS = (
    REPO_ROOT / "claude" / ".claude" / "tempered-tools" / "tempered_receipt.py",
    REPO_ROOT / "codex" / ".agents" / "tempered-tools" / "tempered_receipt.py",
    REPO_ROOT / "cursor" / ".cursor" / "tempered-tools" / "tempered_receipt.py",
    REPO_ROOT / "qwen" / ".qwen" / "tempered-tools" / "tempered_receipt.py",
)


def _load_helper() -> types.ModuleType:
    name = "tempered_receipt_test_copy"
    spec = importlib.util.spec_from_file_location(name, HELPER_PATHS[0])
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load helper test copy")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


HELPER = _load_helper()


def _load_validator() -> types.ModuleType:
    name = "tempered_validator_test_copy"
    spec = importlib.util.spec_from_file_location(name, VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load validator test copy")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR_MODULE = _load_validator()


def _copy_repository(destination: Path) -> Path:
    root = destination / "tempered-loop"
    shutil.copytree(
        REPO_ROOT,
        root,
        symlinks=True,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
    )
    return root


def _run_validator(root: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(root / "scripts" / "validate.py")],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _run_helper(
    arguments: list[str],
    *,
    cwd: Path | None = None,
    environment_updates: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if environment_updates:
        environment.update(environment_updates)
    return subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(HELPER_PATHS[0]), *arguments],
        cwd=cwd or REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _marker_pair(style: str, phase: str, nonce: str) -> tuple[bytes, bytes]:
    pairs = {
        "angled": (
            f"<<<BEGIN TEMPERED PAYLOAD phase={phase} nonce={nonce}>>>",
            f"<<<END TEMPERED PAYLOAD phase={phase} nonce={nonce}>>>",
        ),
        "html": (
            f"<!-- BEGIN TEMPERED {phase} PAYLOAD -->",
            f"<!-- END TEMPERED {phase} PAYLOAD -->",
        ),
        "dashed": (
            f"-----BEGIN TEMPERED {phase} PAYLOAD-----",
            f"-----END TEMPERED {phase} PAYLOAD-----",
        ),
        "plain": (
            f"BEGIN TEMPERED {phase} PAYLOAD",
            f"END TEMPERED {phase} PAYLOAD",
        ),
    }
    begin, end = pairs[style]
    return begin.encode("ascii"), end.encode("ascii")


def _zero_payload(
    *, phase: str, nonce: str, field: str, style: str, body: bytes
) -> bytes:
    begin, end = _marker_pair(style, phase, nonce)
    scope = (
        f"payload_type: {phase.lower()}\n".encode("ascii")
        + b"payload_schema: 2\n"
        + b"approval_binding: tempered-loop-sha256-nonce-v2\n"
        + f"{phase.lower()}_id: {phase.lower()}-test\n".encode("ascii")
        + f"{phase.lower()}_revision: 1\n".encode("ascii")
        + f"approval_nonce: {nonce}\n".encode("ascii")
        + (
            b"preview_stage_token: " + (b"0" * 32) + b"\n"
            if phase == "ACTION"
            else b""
        )
        + f"{field}: ".encode("ascii")
        + (b"0" * 64)
        + b"\n\n"
        + body
    )
    return begin + b"\n" + scope + end + b"\n"


def _signed_payload(
    *, phase: str, nonce: str, field: str, style: str, body: bytes
) -> tuple[bytes, str]:
    zero = _zero_payload(
        phase=phase, nonce=nonce, field=field, style=style, body=body
    )
    digest = HELPER.payload_digest(zero, field)
    return zero.replace(b"0" * 64, digest.encode("ascii"), 1), digest


def _manifest_block(path: str, content: bytes, verb: str = "WRITE_NEW") -> bytes:
    declaration = f"@@FILE {verb} {path}\n"
    return (
        declaration.encode("utf-8")
        + f"@@BYTES {len(content)}\n".encode("ascii")
        + content
        + f"@@END {path}\n".encode("utf-8")
    )


class HelperTests(unittest.TestCase):
    def test_four_helpers_are_byte_identical_and_self_test(self) -> None:
        copies = [path.read_bytes() for path in HELPER_PATHS]
        self.assertTrue(all(copy == copies[0] for copy in copies[1:]))
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        for path in HELPER_PATHS:
            result = subprocess.run(
                [sys.executable, "-I", "-S", "-B", str(path), "self-test"],
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "SELF-TEST: PASS\n")

    def test_nonce_is_128_bit_os_csprng_shape(self) -> None:
        values = {HELPER.generate_nonce() for _ in range(32)}
        self.assertEqual(len(values), 32)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{32}", value) for value in values))

    def test_exact_cli_is_read_only(self) -> None:
        payload_bytes, digest = _signed_payload(
            phase="BRIEF",
            nonce="0123456789abcdef0123456789abcdef",
            field="payload_sha256",
            style="html",
            body=b"cli: exact\n",
        )
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = root / "payload.md"
            artifact = root / "artifact.bin"
            payload.write_bytes(payload_bytes)
            artifact.write_bytes(b"artifact\x00bytes")
            candidate = HELPER.preview_create(root, "PLAN", "a" * 32)
            snapshot_paths = candidate.parent / "snapshot-paths.txt"
            proposed_paths = candidate.parent / "proposed-paths.txt"
            snapshot_paths.write_bytes(b"artifact.bin\npayload.md\n")
            proposed_paths.write_bytes(b"new/file.txt\n")
            before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in root.iterdir()}

            commands = (
                (["nonce"], r"[0-9a-f]{32}\n"),
                (
                    ["sha256", "--root", str(root), "--relative", "artifact.bin"],
                    r"[0-9a-f]{64}\n",
                ),
                (
                    [
                        "verify-payload",
                        "--root",
                        str(root),
                        "--relative",
                        "payload.md",
                        "--field",
                        "payload_sha256",
                    ],
                    re.escape(digest) + r"\n",
                ),
                (
                    ["snapshot", "--root", str(root), "--paths-file", str(snapshot_paths)],
                    r"[0-9a-f]{64}\n",
                ),
                (
                    ["validate-paths", "--root", str(root), "--paths-file", str(proposed_paths)],
                    r"VALID 1\n",
                ),
            )
            for arguments, output_pattern in commands:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        "-S",
                        "-B",
                        str(HELPER_PATHS[0]),
                        *arguments,
                    ],
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertRegex(result.stdout, rf"\A{output_pattern}\Z")

            after = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in root.iterdir()}
            self.assertEqual(before, after)
            HELPER.preview_remove(candidate, root)

    def test_path_list_cli_requires_correct_active_preview_member(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "artifact.txt").write_bytes(b"artifact\n")
            outside_snapshot = root / "snapshot-paths.txt"
            outside_proposed = root / "proposed-paths.txt"
            outside_snapshot.write_bytes(b"artifact.txt\n")
            outside_proposed.write_bytes(b"new.txt\n")
            for command, paths_file in (
                ("snapshot", outside_snapshot),
                ("validate-paths", outside_proposed),
            ):
                refused = _run_helper(
                    [command, "--root", str(root), "--paths-file", str(paths_file)]
                )
                self.assertNotEqual(refused.returncode, 0)

            candidate = HELPER.preview_create(root, "ACTION", "b" * 32)
            snapshot_paths = candidate.parent / "snapshot-paths.txt"
            proposed_paths = candidate.parent / "proposed-paths.txt"
            snapshot_paths.write_bytes(b"artifact.txt\n")
            proposed_paths.write_bytes(b"new.txt\n")
            wrong_snapshot = _run_helper(
                [
                    "snapshot",
                    "--root",
                    str(root),
                    "--paths-file",
                    str(proposed_paths),
                ]
            )
            wrong_proposed = _run_helper(
                [
                    "validate-paths",
                    "--root",
                    str(root),
                    "--paths-file",
                    str(snapshot_paths),
                ]
            )
            self.assertNotEqual(wrong_snapshot.returncode, 0)
            self.assertNotEqual(wrong_proposed.returncode, 0)

            other_root = root / "other"
            other_root.mkdir()
            root_mismatch = _run_helper(
                [
                    "snapshot",
                    "--root",
                    str(other_root),
                    "--paths-file",
                    str(snapshot_paths),
                ]
            )
            self.assertNotEqual(root_mismatch.returncode, 0)
            self.assertIn("different project root", root_mismatch.stderr)

            candidate.write_bytes(
                _zero_payload(
                    phase="ACTION",
                    nonce="b" * 32,
                    field="action_payload_sha256",
                    style="plain",
                    body=b"operation: no-op test\n",
                )
            )
            self.assertEqual(
                _run_helper(
                    [
                        "preview-finalize",
                        str(candidate),
                        "--field",
                        "action_payload_sha256",
                        "--root",
                        str(root),
                    ]
                ).returncode,
                0,
            )
            self.assertEqual(
                _run_helper(
                    ["preview-consume", str(candidate), "--root", str(root)]
                ).returncode,
                0,
            )
            for command, paths_file in (
                ("snapshot", snapshot_paths),
                ("validate-paths", proposed_paths),
            ):
                refused = _run_helper(
                    [command, "--root", str(root), "--paths-file", str(paths_file)]
                )
                self.assertNotEqual(refused.returncode, 0)
            HELPER.preview_remove(candidate, root)

    def test_preview_lifecycle_all_phases_markers_fields_and_auxiliaries(self) -> None:
        cases = (
            ("BRIEF", "angled", "payload_sha256"),
            ("SETUP", "html", "setup_payload_sha256"),
            ("PLAN", "dashed", "plan_payload_sha256"),
            ("ACTION", "plain", "action_payload_sha256"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            keep = project / "keep.txt"
            keep.write_bytes(b"workspace stays unchanged\n")
            before = (keep.read_bytes(), keep.stat().st_mtime_ns, sorted(project.iterdir()))

            for index, (phase, style, field) in enumerate(cases, start=1):
                with self.subTest(phase=phase, style=style, field=field):
                    nonce = f"{index:032x}"
                    created = _run_helper(
                        [
                            "preview-create",
                            "--root",
                            str(project),
                            "--phase",
                            phase,
                            "--nonce",
                            nonce,
                        ]
                    )
                    self.assertEqual(created.returncode, 0, created.stderr)
                    self.assertRegex(created.stdout, r"\A[^\r\n]+candidate\.payload\n\Z")
                    candidate = Path(created.stdout.strip())
                    self.assertTrue(candidate.is_absolute())
                    self.assertTrue(candidate.exists())
                    with self.assertRaises(ValueError):
                        candidate.relative_to(project)

                    for auxiliary, content in (
                        ("proposed-paths.txt", b"new/file.txt\n"),
                        ("snapshot-paths.txt", b"keep.txt\n"),
                        ("digest-input.bin", b"bundle preimage\n"),
                    ):
                        (candidate.parent / auxiliary).write_bytes(content)

                    if phase == "SETUP":
                        embedded = (
                            b"BEGIN TEMPERED PLAN PAYLOAD\n"
                            b"prefix BEGIN TEMPERED is inert file content\n"
                            b"payload_sha256: " + (b"a" * 64) + b"\n"
                        )
                        body = _manifest_block("nested.txt", embedded)
                    else:
                        body = f"body: {phase.lower()}\n".encode("ascii")
                    candidate.write_bytes(
                        _zero_payload(
                            phase=phase,
                            nonce=nonce,
                            field=field,
                            style=style,
                            body=body,
                        )
                    )

                    finalized = _run_helper(
                        [
                            "preview-finalize",
                            str(candidate),
                            "--field",
                            field,
                            "--root",
                            str(project),
                        ]
                    )
                    self.assertEqual(finalized.returncode, 0, finalized.stderr)
                    digest = finalized.stdout.strip()
                    self.assertRegex(digest, r"\A[0-9a-f]{64}\Z")

                    verified = _run_helper(
                        [
                            "verify-payload",
                            str(candidate),
                            "--field",
                            field,
                            "--root",
                            str(project),
                        ]
                    )
                    self.assertEqual(verified.returncode, 0, verified.stderr)
                    self.assertEqual(verified.stdout, digest + "\n")
                    staged_sha = _run_helper(
                        [
                            "sha256",
                            str(candidate.parent / "digest-input.bin"),
                            "--root",
                            str(project),
                        ]
                    )
                    self.assertEqual(staged_sha.returncode, 0, staged_sha.stderr)
                    self.assertRegex(staged_sha.stdout, r"\A[0-9a-f]{64}\n\Z")

                    second_finalize = _run_helper(
                        [
                            "preview-finalize",
                            str(candidate),
                            "--field",
                            field,
                            "--root",
                            str(project),
                        ]
                    )
                    self.assertNotEqual(second_finalize.returncode, 0)
                    self.assertIn("64 zeroes", second_finalize.stderr)

                    removed = _run_helper(
                        ["preview-remove", str(candidate), "--root", str(project)]
                    )
                    self.assertEqual(removed.returncode, 0, removed.stderr)
                    self.assertEqual(removed.stdout, "REMOVED\n")
                    self.assertFalse(candidate.parent.exists())

            after = (keep.read_bytes(), keep.stat().st_mtime_ns, sorted(project.iterdir()))
            self.assertEqual(before, after)

    def test_preview_rejects_stale_sentinel_unknown_entries_and_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            nonce = "1" * 32
            created = _run_helper(
                [
                    "preview-create",
                    "--root",
                    str(project),
                    "--phase",
                    "BRIEF",
                    "--nonce",
                    nonce,
                ]
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            candidate = Path(created.stdout.strip())
            sentinel = candidate.parent / HELPER.PREVIEW_SENTINEL
            original_sentinel = sentinel.read_bytes()
            candidate.write_bytes(
                _zero_payload(
                    phase="BRIEF",
                    nonce="2" * 32,
                    field="payload_sha256",
                    style="plain",
                    body=b"stale: true\n",
                )
            )
            stale = _run_helper(
                [
                    "preview-finalize",
                    str(candidate),
                    "--field",
                    "payload_sha256",
                    "--root",
                    str(project),
                ]
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("phase/nonce", stale.stderr)

            candidate.write_bytes(
                _zero_payload(
                    phase="BRIEF",
                    nonce=nonce,
                    field="payload_sha256",
                    style="plain",
                    body=b"stale: false\n",
                )
            )
            sentinel.write_bytes(original_sentinel.replace(b"phase: BRIEF", b"phase: PLAN "))
            tampered = _run_helper(
                [
                    "preview-finalize",
                    str(candidate),
                    "--field",
                    "payload_sha256",
                    "--root",
                    str(project),
                ]
            )
            self.assertNotEqual(tampered.returncode, 0)
            self.assertIn("sentinel", tampered.stderr)
            sentinel.write_bytes(original_sentinel)

            overflow_entries = []
            for index in range(5):
                overflow = candidate.parent / f"overflow-{index}.txt"
                overflow.write_bytes(b"bounded\n")
                overflow_entries.append(overflow)
            with self.assertRaisesRegex(HELPER.HelperError, "entry-count limit"):
                HELPER._validate_preview_stage(candidate, root=project)
            for overflow in overflow_entries:
                overflow.unlink()

            unknown = candidate.parent / "unexpected.txt"
            unknown.write_bytes(b"not allowed\n")
            refused = _run_helper(
                ["preview-remove", str(candidate), "--root", str(project)]
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("unexpected", refused.stderr)
            self.assertTrue(candidate.exists())
            unknown.unlink()
            removed = _run_helper(
                ["preview-remove", str(candidate), "--root", str(project)]
            )
            self.assertEqual(removed.returncode, 0, removed.stderr)

            arbitrary = project / "candidate.payload"
            arbitrary.write_bytes(b"must survive\n")
            outside = _run_helper(
                ["preview-remove", str(arbitrary.resolve()), "--root", str(project)]
            )
            self.assertNotEqual(outside.returncode, 0)
            self.assertTrue(arbitrary.exists())

    def test_action_preview_consume_is_atomic_lifecycle_state_and_crash_persistent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            nonce = "7" * 32
            created = _run_helper(
                [
                    "preview-create",
                    "--root",
                    str(project),
                    "--phase",
                    "ACTION",
                    "--nonce",
                    nonce,
                ]
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            candidate = Path(created.stdout.strip())
            candidate.write_bytes(
                _zero_payload(
                    phase="ACTION",
                    nonce=nonce,
                    field="action_payload_sha256",
                    style="plain",
                    body=b"operation: single delivery\n",
                )
            )
            finalized = _run_helper(
                [
                    "preview-finalize",
                    str(candidate),
                    "--field",
                    "action_payload_sha256",
                    "--root",
                    str(project),
                ]
            )
            self.assertEqual(finalized.returncode, 0, finalized.stderr)
            digest = finalized.stdout.strip()
            consumed = _run_helper(
                ["preview-consume", str(candidate), "--root", str(project)]
            )
            self.assertEqual(consumed.returncode, 0, consumed.stderr)
            self.assertEqual(consumed.stdout, f"CONSUMED {digest}\n")
            self.assertTrue(candidate.exists())
            self.assertTrue(
                (candidate.parent / HELPER.PREVIEW_CONSUMED_SENTINEL).exists()
            )
            self.assertFalse((candidate.parent / HELPER.PREVIEW_SENTINEL).exists())

            for arguments in (
                [
                    "verify-payload",
                    str(candidate),
                    "--field",
                    "action_payload_sha256",
                    "--root",
                    str(project),
                ],
                [
                    "preview-finalize",
                    str(candidate),
                    "--field",
                    "action_payload_sha256",
                    "--root",
                    str(project),
                ],
                ["preview-consume", str(candidate), "--root", str(project)],
            ):
                reused = _run_helper(arguments)
                self.assertNotEqual(reused.returncode, 0, arguments)

            removed = _run_helper(
                ["preview-remove", str(candidate), "--root", str(project)]
            )
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertFalse(candidate.parent.exists())

            brief = _run_helper(
                [
                    "preview-create",
                    "--root",
                    str(project),
                    "--phase",
                    "BRIEF",
                    "--nonce",
                    "8" * 32,
                ]
            )
            self.assertEqual(brief.returncode, 0, brief.stderr)
            brief_candidate = Path(brief.stdout.strip())
            brief_candidate.write_bytes(
                _zero_payload(
                    phase="BRIEF",
                    nonce="8" * 32,
                    field="payload_sha256",
                    style="plain",
                    body=b"not-an-action: true\n",
                )
            )
            brief_finalize = _run_helper(
                [
                    "preview-finalize",
                    str(brief_candidate),
                    "--field",
                    "payload_sha256",
                    "--root",
                    str(project),
                ]
            )
            self.assertEqual(brief_finalize.returncode, 0, brief_finalize.stderr)
            refused = _run_helper(
                ["preview-consume", str(brief_candidate), "--root", str(project)]
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("ACTION", refused.stderr)
            self.assertEqual(
                _run_helper(
                    ["preview-remove", str(brief_candidate), "--root", str(project)]
                ).returncode,
                0,
            )

    def test_action_stage_token_rejects_other_helper_created_same_nonce_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            nonce = "c" * 32
            stage_a = HELPER.preview_create(project, "ACTION", nonce)
            stage_b = HELPER.preview_create(project, "ACTION", nonce)
            token_a = HELPER._validate_preview_stage(stage_a).token
            token_b = HELPER._validate_preview_stage(stage_b).token
            self.assertNotEqual(token_a, token_b)

            stage_a.write_bytes(
                _zero_payload(
                    phase="ACTION",
                    nonce=nonce,
                    field="action_payload_sha256",
                    style="plain",
                    body=b"operation: exactly one\n",
                )
            )
            finalized = _run_helper(
                [
                    "preview-finalize",
                    str(stage_a),
                    "--field",
                    "action_payload_sha256",
                    "--root",
                    str(project),
                ]
            )
            self.assertEqual(finalized.returncode, 0, finalized.stderr)
            digest_a = finalized.stdout.strip()
            signed_a = stage_a.read_bytes()
            self.assertIn(
                f"preview_stage_token: {token_a}\n".encode("ascii"), signed_a
            )
            self.assertNotIn(
                b"preview_stage_token: " + (b"0" * 32) + b"\n", signed_a
            )

            stage_b.write_bytes(signed_a)
            for arguments in (
                [
                    "preview-finalize",
                    str(stage_b),
                    "--field",
                    "action_payload_sha256",
                    "--root",
                    str(project),
                ],
                [
                    "verify-payload",
                    str(stage_b),
                    "--field",
                    "action_payload_sha256",
                    "--root",
                    str(project),
                ],
                ["preview-consume", str(stage_b), "--root", str(project)],
            ):
                refused = _run_helper(arguments)
                self.assertNotEqual(refused.returncode, 0, arguments)
                self.assertIn("token does not match", refused.stderr)
            HELPER.preview_remove(stage_b, project)

            consumed = _run_helper(
                ["preview-consume", str(stage_a), "--root", str(project)]
            )
            self.assertEqual(consumed.returncode, 0, consumed.stderr)
            self.assertEqual(consumed.stdout, f"CONSUMED {digest_a}\n")
            HELPER.preview_remove(stage_a, project)

            recreated = HELPER.preview_create(project, "ACTION", nonce)
            recreated_token = HELPER._validate_preview_stage(recreated).token
            self.assertNotEqual(token_a, recreated_token)
            recreated.write_bytes(signed_a)
            for arguments in (
                [
                    "preview-finalize",
                    str(recreated),
                    "--field",
                    "action_payload_sha256",
                    "--root",
                    str(project),
                ],
                [
                    "verify-payload",
                    str(recreated),
                    "--field",
                    "action_payload_sha256",
                    "--root",
                    str(project),
                ],
                ["preview-consume", str(recreated), "--root", str(project)],
            ):
                refused = _run_helper(arguments)
                self.assertNotEqual(refused.returncode, 0, arguments)
                self.assertIn("token does not match", refused.stderr)
            HELPER.preview_remove(recreated, project)

    def test_same_principal_can_reverse_or_recreate_consumed_stage_expected_limit(self) -> None:
        """Consumption is a compliant-lifecycle guard, not durable replay protection."""

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            nonce = "e" * 32
            candidate = HELPER.preview_create(project, "ACTION", nonce)
            candidate.write_bytes(
                _zero_payload(
                    phase="ACTION",
                    nonce=nonce,
                    field="action_payload_sha256",
                    style="plain",
                    body=b"operation: manual handoff\n",
                )
            )
            digest = HELPER.preview_finalize(
                candidate,
                "action_payload_sha256",
                project,
            )
            stage = HELPER._validate_preview_stage(candidate)
            signed_payload = candidate.read_bytes()
            active_sentinel = stage.sentinel.read_bytes()
            directory = stage.directory
            sentinel = stage.sentinel
            consumed_sentinel = directory / HELPER.PREVIEW_CONSUMED_SENTINEL

            self.assertEqual(HELPER.preview_consume(candidate, project), digest)
            os.replace(consumed_sentinel, sentinel)
            self.assertEqual(HELPER.preview_consume(candidate, project), digest)
            HELPER.preview_remove(candidate, project)

            os.mkdir(directory, 0o700)
            candidate.write_bytes(signed_payload)
            sentinel.write_bytes(active_sentinel)
            if os.name != "nt":
                os.chmod(directory, 0o700)
                os.chmod(candidate, 0o600)
                os.chmod(sentinel, 0o600)
            self.assertEqual(HELPER.preview_consume(candidate, project), digest)
            HELPER.preview_remove(candidate, project)

    def test_every_stage_operation_requires_and_revalidates_exact_root_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project_a = base / "project-a"
            project_b = base / "project-b"
            project_a.mkdir()
            project_b.mkdir()
            nonce = "f" * 32
            candidate = HELPER.preview_create(project_a, "ACTION", nonce)
            candidate.write_bytes(
                _zero_payload(
                    phase="ACTION",
                    nonce=nonce,
                    field="action_payload_sha256",
                    style="plain",
                    body=b"operation: root-bound handoff\n",
                )
            )
            digest_input = candidate.parent / "digest-input.bin"
            digest_input.write_bytes(b"root-bound digest input\n")
            if os.name != "nt":
                os.chmod(candidate, 0o600)
                os.chmod(digest_input, 0o600)

            missing_root_commands = (
                ["sha256", str(candidate)],
                ["sha256", str(digest_input)],
                [
                    "verify-payload",
                    str(candidate),
                    "--field",
                    "action_payload_sha256",
                ],
                ["preview-metrics", str(candidate)],
                [
                    "preview-finalize",
                    str(candidate),
                    "--field",
                    "action_payload_sha256",
                ],
                ["preview-consume", str(candidate)],
                ["preview-remove", str(candidate)],
            )
            for arguments in missing_root_commands:
                with self.subTest(missing_root=arguments[0]):
                    refused = _run_helper(arguments)
                    self.assertNotEqual(refused.returncode, 0)
                    self.assertIn("--root", refused.stderr)

            cross_root_commands = (
                ["sha256", str(candidate), "--root", str(project_b)],
                ["sha256", str(digest_input), "--root", str(project_b)],
                [
                    "verify-payload",
                    str(candidate),
                    "--field",
                    "action_payload_sha256",
                    "--root",
                    str(project_b),
                ],
                ["preview-metrics", str(candidate), "--root", str(project_b)],
                [
                    "preview-finalize",
                    str(candidate),
                    "--field",
                    "action_payload_sha256",
                    "--root",
                    str(project_b),
                ],
                ["preview-consume", str(candidate), "--root", str(project_b)],
                ["preview-remove", str(candidate), "--root", str(project_b)],
            )
            for arguments in cross_root_commands:
                with self.subTest(cross_root=arguments[0]):
                    refused = _run_helper(arguments)
                    self.assertNotEqual(refused.returncode, 0)
                    self.assertIn("different project root", refused.stderr)

            finalized = _run_helper(
                [
                    "preview-finalize",
                    str(candidate),
                    "--field",
                    "action_payload_sha256",
                    "--root",
                    str(project_a),
                ]
            )
            self.assertEqual(finalized.returncode, 0, finalized.stderr)
            digest = finalized.stdout.strip()
            verified = _run_helper(
                [
                    "verify-payload",
                    str(candidate),
                    "--field",
                    "action_payload_sha256",
                    "--root",
                    str(project_a),
                ]
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(verified.stdout, digest + "\n")

            backup = base / "project-a-original"
            project_a.rename(backup)
            project_a.mkdir()
            try:
                replacement_root_commands = (
                    ["sha256", str(candidate), "--root", str(project_a)],
                    ["sha256", str(digest_input), "--root", str(project_a)],
                    [
                        "verify-payload",
                        str(candidate),
                        "--field",
                        "action_payload_sha256",
                        "--root",
                        str(project_a),
                    ],
                    ["preview-metrics", str(candidate), "--root", str(project_a)],
                    [
                        "preview-finalize",
                        str(candidate),
                        "--field",
                        "action_payload_sha256",
                        "--root",
                        str(project_a),
                    ],
                    ["preview-consume", str(candidate), "--root", str(project_a)],
                    ["preview-remove", str(candidate), "--root", str(project_a)],
                )
                for arguments in replacement_root_commands:
                    with self.subTest(replaced_root=arguments[0]):
                        refused = _run_helper(arguments)
                        self.assertNotEqual(refused.returncode, 0)
                        self.assertIn("different project root", refused.stderr)
            finally:
                project_a.rmdir()
                backup.rename(project_a)

            consumed = _run_helper(
                ["preview-consume", str(candidate), "--root", str(project_a)]
            )
            self.assertEqual(consumed.returncode, 0, consumed.stderr)
            cross_remove = _run_helper(
                ["preview-remove", str(candidate), "--root", str(project_b)]
            )
            self.assertNotEqual(cross_remove.returncode, 0)
            removed = _run_helper(
                ["preview-remove", str(candidate), "--root", str(project_a)]
            )
            self.assertEqual(removed.returncode, 0, removed.stderr)

    def test_preview_metrics_is_root_bound_exact_and_byte_count_aware(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            other = base / "other"
            project.mkdir()
            other.mkdir()
            nonce = "1" * 32
            candidate = HELPER.preview_create(project, "SETUP", nonce)
            marker_like_content = (
                b"BEGIN TEMPERED ACTION PAYLOAD\n"
                b"@@FILE WRITE_NEW smuggled.txt\n"
                b"@@END smuggled.txt\n"
            )
            status_content = b"status: pending\n"
            body = (
                _manifest_block(
                    ".claude/tempered/STATUS.md", status_content, "WRITE_NEW"
                )
                + _manifest_block(
                    "artifact.txt", marker_like_content, "WRITE_NEW"
                )
            )
            payload = _zero_payload(
                phase="SETUP",
                nonce=nonce,
                field="setup_payload_sha256",
                style="dashed",
                body=body,
            )
            candidate.write_bytes(payload)

            direct = HELPER.preview_metrics(candidate, project)
            cli = _run_helper(
                ["preview-metrics", str(candidate), "--root", str(project)]
            )
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertEqual(cli.stdout, direct)
            self.assertIn("PHASE SETUP\n", direct)
            self.assertIn(f"BYTES {len(payload)}\n", direct)
            self.assertIn(f"LF {payload.count(bytes((10,)))}\n", direct)
            self.assertIn("BLOCKS 2\n", direct)
            self.assertRegex(direct, r"PATH-INDEX-SHA256 [0-9a-f]{64}\n")
            self.assertIn(
                "PATH 000001 WRITE_NEW 26 .claude/tempered/STATUS.md\n",
                direct,
            )
            self.assertIn("PATH 000002 WRITE_NEW 12 artifact.txt\n", direct)
            self.assertNotIn("smuggled.txt\nPATH", direct)

            cross_root = _run_helper(
                ["preview-metrics", str(candidate), "--root", str(other)]
            )
            self.assertNotEqual(cross_root.returncode, 0)
            self.assertIn("different project root", cross_root.stderr)
            candidate.write_bytes(payload[:-5])
            with self.assertRaises(HELPER.HelperError):
                HELPER.preview_metrics(candidate, project)
            candidate.write_bytes(payload)
            HELPER.preview_remove(candidate, project)

    def test_action_stage_token_shape_uniqueness_and_phase_scope(self) -> None:
        valid_action = _zero_payload(
            phase="ACTION",
            nonce="d" * 32,
            field="action_payload_sha256",
            style="plain",
            body=b"operation: bounded\n",
        )
        token_line = b"preview_stage_token: " + (b"0" * 32) + b"\n"
        HELPER.payload_digest(valid_action, "action_payload_sha256")
        malformed = (
            valid_action.replace(token_line, b"", 1),
            valid_action.replace(token_line, token_line + token_line, 1),
            valid_action.replace(b"0" * 32, b"A" * 32, 1),
            valid_action.replace(b"0" * 32, b"0" * 31, 1),
        )
        for payload in malformed:
            with self.subTest(payload=payload[:120]):
                with self.assertRaisesRegex(HELPER.HelperError, "stage token"):
                    HELPER.payload_digest(payload, "action_payload_sha256")

        brief = _zero_payload(
            phase="BRIEF",
            nonce="e" * 32,
            field="brief_payload_sha256",
            style="plain",
            body=b"scope: brief\n",
        ).replace(
            b"brief_payload_sha256:", token_line + b"brief_payload_sha256:", 1
        )
        with self.assertRaisesRegex(HELPER.HelperError, "reserved for ACTION"):
            HELPER.payload_digest(brief, "brief_payload_sha256")

    def test_preview_rejects_temp_root_inside_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            hostile_temp = project / "temp"
            hostile_temp.mkdir(parents=True)
            result = _run_helper(
                [
                    "preview-create",
                    "--root",
                    str(project),
                    "--phase",
                    "PLAN",
                    "--nonce",
                    "3" * 32,
                ],
                environment_updates={
                    "TMPDIR": str(hostile_temp),
                    "TMP": str(hostile_temp),
                    "TEMP": str(hostile_temp),
                },
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertRegex(
                result.stderr,
                r"inside the project root|Windows TEMP privacy is UNKNOWN",
            )
            self.assertEqual(list(hostile_temp.iterdir()), [])

    def test_preview_cleanup_rejects_symlinked_entries_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            outside = project / "outside.txt"
            outside.write_bytes(b"must survive\n")
            created = _run_helper(
                [
                    "preview-create",
                    "--root",
                    str(project),
                    "--phase",
                    "ACTION",
                    "--nonce",
                    "6" * 32,
                ]
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            candidate = Path(created.stdout.strip())
            auxiliary = candidate.parent / "digest-input.bin"
            try:
                os.symlink(outside, auxiliary)
            except (NotImplementedError, OSError) as exc:
                _run_helper(
                    ["preview-remove", str(candidate), "--root", str(project)]
                )
                self.skipTest(f"filesystem cannot create preview symlink: {exc}")
            refused_aux = _run_helper(
                ["preview-remove", str(candidate), "--root", str(project)]
            )
            self.assertNotEqual(refused_aux.returncode, 0)
            self.assertRegex(refused_aux.stderr, r"link|reparse|regular")
            self.assertEqual(outside.read_bytes(), b"must survive\n")
            auxiliary.unlink()

            candidate.unlink()
            os.symlink(outside, candidate)
            refused_candidate = _run_helper(
                ["preview-remove", str(candidate), "--root", str(project)]
            )
            self.assertNotEqual(refused_candidate.returncode, 0)
            self.assertRegex(refused_candidate.stderr, r"link|reparse|regular")
            self.assertEqual(outside.read_bytes(), b"must survive\n")
            candidate.unlink()
            candidate.write_bytes(b"")
            os.chmod(candidate, 0o600)
            removed = _run_helper(
                ["preview-remove", str(candidate), "--root", str(project)]
            )
            self.assertEqual(removed.returncode, 0, removed.stderr)

    def test_isolated_helper_ignores_shadow_stdlib_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for directory in (root / "project", root / "helper"):
                directory.mkdir()
                (directory / "hashlib.py").write_text(
                    "raise RuntimeError('shadow hashlib imported')\n", encoding="utf-8"
                )
                (directory / "secrets.py").write_text(
                    "raise RuntimeError('shadow secrets imported')\n", encoding="utf-8"
                )
            copied_helper = root / "helper" / "tempered_receipt.py"
            shutil.copyfile(HELPER_PATHS[0], copied_helper)
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            for helper, cwd in (
                (HELPER_PATHS[0], root / "project"),
                (copied_helper, root / "project"),
            ):
                result = subprocess.run(
                    [sys.executable, "-I", "-S", "-B", str(helper), "self-test"],
                    cwd=cwd,
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "SELF-TEST: PASS\n")

    def test_payload_digest_rejects_mutation_and_duplicate_field(self) -> None:
        nonce = "0123456789abcdef0123456789abcdef"
        styles = ("angled", "html", "dashed", "plain")
        signed_by_style: dict[str, tuple[bytes, str]] = {}
        for style in styles:
            signed_by_style[style] = _signed_payload(
                phase="BRIEF",
                nonce=nonce,
                field="payload_sha256",
                style=style,
                body=b"artifact: exact\n",
            )
        self.assertEqual(len({digest for _, digest in signed_by_style.values()}), 4)

        with tempfile.TemporaryDirectory() as temporary:
            payload = Path(temporary) / "payload.md"
            for style, (signed, digest) in signed_by_style.items():
                with self.subTest(style=style):
                    payload.write_bytes(signed)
                    self.assertEqual(
                        HELPER.verify_payload_file(payload, "payload_sha256"), digest
                    )

            signed, digest = signed_by_style["html"]
            payload.write_bytes(signed.replace(b"artifact: exact", b"artifact: drift"))
            with self.assertRaisesRegex(HELPER.HelperError, "digest mismatch"):
                HELPER.verify_payload_file(payload, "payload_sha256")

            duplicate = signed.replace(
                b"\n\nartifact",
                b"\npayload_sha256: " + digest.encode("ascii") + b"\n\nartifact",
            )
            payload.write_bytes(duplicate)
            with self.assertRaisesRegex(HELPER.HelperError, "exactly one"):
                HELPER.verify_payload_file(payload, "payload_sha256")

            html_begin, html_end = _marker_pair("html", "BRIEF", nonce)
            dashed_begin, dashed_end = _marker_pair("dashed", "BRIEF", nonce)
            substituted = signed.replace(html_begin, dashed_begin, 1).replace(
                html_end, dashed_end, 1
            )
            payload.write_bytes(substituted)
            with self.assertRaisesRegex(HELPER.HelperError, "digest mismatch"):
                HELPER.verify_payload_file(payload, "payload_sha256")

            lines = signed.splitlines(keepends=True)
            payload.write_bytes(b"".join(lines[1:-1]))
            with self.assertRaisesRegex(HELPER.HelperError, "outer marker pair"):
                HELPER.verify_payload_file(payload, "payload_sha256")
            payload.write_bytes(signed.replace(b"BRIEF PAYLOAD -->", b"PLAN PAYLOAD -->", 1))
            with self.assertRaisesRegex(HELPER.HelperError, "markers|phase"):
                HELPER.verify_payload_file(payload, "payload_sha256")
            payload.write_bytes(b"prefix " + signed)
            with self.assertRaisesRegex(HELPER.HelperError, "marker"):
                HELPER.verify_payload_file(payload, "payload_sha256")
            payload.write_bytes(signed[:-1] + b" suffix\n")
            with self.assertRaisesRegex(HELPER.HelperError, "marker"):
                HELPER.verify_payload_file(payload, "payload_sha256")
            payload.write_bytes(
                dashed_begin
                + b"\n"
                + signed
                + dashed_end
                + b"\n"
            )
            with self.assertRaises(HELPER.HelperError):
                HELPER.verify_payload_file(payload, "payload_sha256")
            payload.write_bytes(signed.replace(b"\n", b"\r\n"))
            with self.assertRaisesRegex(HELPER.HelperError, "LF line endings"):
                HELPER.verify_payload_file(payload, "payload_sha256")
            payload.write_bytes(signed[:-1])
            with self.assertRaisesRegex(HELPER.HelperError, "end in LF"):
                HELPER.verify_payload_file(payload, "payload_sha256")
            for before, after, expected in (
                (b"payload_schema: 2", b"payload_schema: 1", "payload schema"),
                (
                    b"approval_binding: tempered-loop-sha256-nonce-v2",
                    b"approval_binding: tempered-loop-sha256-nonce-v1",
                    "approval binding",
                ),
                (b"artifact: exact", "artifact: ex\u202eact".encode("utf-8"), "invisible-format"),
            ):
                payload.write_bytes(signed.replace(before, after, 1))
                with self.assertRaisesRegex(HELPER.HelperError, expected):
                    HELPER.verify_payload_file(payload, "payload_sha256")

            wrong_field = _zero_payload(
                phase="BRIEF",
                nonce=nonce,
                field="unexpected_sha256",
                style="plain",
                body=b"artifact: exact\n",
            )
            with self.assertRaisesRegex(HELPER.HelperError, "exactly one active"):
                HELPER.payload_digest(wrong_field, "unexpected_sha256")
            duplicate_alias = _zero_payload(
                phase="BRIEF",
                nonce=nonce,
                field="payload_sha256",
                style="plain",
                body=b"artifact: exact\n",
            ).replace(
                b"payload_sha256: " + (b"0" * 64) + b"\n",
                b"payload_sha256: " + (b"0" * 64) + b"\n"
                + b"brief_payload_sha256: " + (b"0" * 64) + b"\n",
                1,
            )
            with self.assertRaisesRegex(HELPER.HelperError, "exactly one active"):
                HELPER.payload_digest(duplicate_alias, "payload_sha256")

            embedded_file = (
                b"payload_sha256: " + (b"a" * 64) + b"\n"
                b"BEGIN TEMPERED PLAN PAYLOAD\n"
                b"prefix BEGIN TEMPERED marker-like file content\n"
                b"-----END TEMPERED PLAN PAYLOAD-----\n"
            )
            body = _manifest_block("nested-brief.md", embedded_file)
            for style in styles:
                with self.subTest(setup_style=style):
                    signed_setup, setup_digest = _signed_payload(
                        phase="SETUP",
                        nonce=nonce,
                        field="payload_sha256",
                        style=style,
                        body=body,
                    )
                    payload.write_bytes(signed_setup)
                    self.assertEqual(
                        HELPER.verify_payload_file(payload, "payload_sha256"),
                        setup_digest,
                    )

            structural = _zero_payload(
                phase="SETUP",
                nonce=nonce,
                field="payload_sha256",
                style="dashed",
                body=b"BEGIN TEMPERED PLAN PAYLOAD\n" + body,
            )
            with self.assertRaisesRegex(
                HELPER.HelperError, "structural content|only as one exact"
            ):
                HELPER.payload_digest(structural, "payload_sha256")
            bad_count = _zero_payload(
                phase="SETUP",
                nonce=nonce,
                field="payload_sha256",
                style="dashed",
                body=body.replace(
                    f"@@BYTES {len(embedded_file)}".encode("ascii"), b"@@BYTES 1"
                ),
            )
            with self.assertRaisesRegex(HELPER.HelperError, "file content|@@END path"):
                HELPER.payload_digest(bad_count, "payload_sha256")

    def test_root_bound_authority_reads_and_direct_path_restriction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, phase in enumerate(("BRIEF", "SETUP", "PLAN"), start=1):
                signed, digest = _signed_payload(
                    phase=phase,
                    nonce=f"{index:032x}",
                    field="payload_sha256",
                    style="plain",
                    body=f"authority: {phase.lower()}\n".encode("ascii"),
                )
                relative = f"{phase.lower()}.md"
                path = root / relative
                path.write_bytes(signed)
                verified = _run_helper(
                    [
                        "verify-payload",
                        "--root",
                        str(root),
                        "--relative",
                        relative,
                        "--field",
                        "payload_sha256",
                    ]
                )
                self.assertEqual(verified.returncode, 0, verified.stderr)
                self.assertEqual(verified.stdout, digest + "\n")

            missing_root = _run_helper(
                ["verify-payload", str(root / "brief.md"), "--field", "payload_sha256"]
            )
            self.assertNotEqual(missing_root.returncode, 0)
            self.assertIn("--root", missing_root.stderr)
            direct = _run_helper(
                [
                    "verify-payload",
                    str(root / "brief.md"),
                    "--field",
                    "payload_sha256",
                    "--root",
                    str(root),
                ]
            )
            self.assertNotEqual(direct.returncode, 0)
            self.assertIn("preview-stage", direct.stderr)
            direct_sha_missing_root = _run_helper(["sha256", str(root / "brief.md")])
            self.assertNotEqual(direct_sha_missing_root.returncode, 0)
            self.assertIn("--root", direct_sha_missing_root.stderr)
            direct_sha = _run_helper(
                ["sha256", str(root / "brief.md"), "--root", str(root)]
            )
            self.assertNotEqual(direct_sha.returncode, 0)
            paired = _run_helper(
                ["sha256", "--root", str(root), "--relative", "brief.md"]
            )
            self.assertEqual(paired.returncode, 0, paired.stderr)
            missing_pair = _run_helper(["sha256", "--root", str(root)])
            self.assertNotEqual(missing_pair.returncode, 0)
            self.assertIn("supply", missing_pair.stderr)

    def test_primary_payload_ids_are_mechanically_validated_without_argv_data(self) -> None:
        valid = _zero_payload(
            phase="BRIEF",
            nonce="5" * 32,
            field="payload_sha256",
            style="plain",
            body=b"identity: checked\n",
        )
        self.assertEqual(HELPER._validate_primary_payload_id(valid, "BRIEF"), "brief-test")
        invalid_values = (
            b" brief-test",
            b"brief:test",
            "br\u00eef".encode("utf-8"),
            b"APPROVE TEMPERED BRIEF x R1",
            b"a" + (b"b" * 64),
        )
        for value in invalid_values:
            with self.subTest(value=value):
                malformed = valid.replace(b"brief_id: brief-test", b"brief_id: " + value)
                with self.assertRaises(HELPER.HelperError):
                    HELPER._validate_primary_payload_id(malformed, "BRIEF")

    def test_phase_revision_is_exact_positive_canonical_decimal(self) -> None:
        nonce = "9" * 32
        for phase in ("BRIEF", "SETUP", "PLAN", "ACTION"):
            with self.subTest(phase=phase):
                valid = _zero_payload(
                    phase=phase,
                    nonce=nonce,
                    field=f"{phase.lower()}_payload_sha256",
                    style="plain",
                    body=b"revision: bound\n",
                )
                revision_line = f"{phase.lower()}_revision: 1\n".encode("ascii")
                HELPER.payload_digest(valid, f"{phase.lower()}_payload_sha256")
                malformed_values = (b"", b"0", b"+1", b"01")
                for value in malformed_values:
                    if value:
                        malformed = valid.replace(
                            revision_line,
                            f"{phase.lower()}_revision: ".encode("ascii")
                            + value
                            + b"\n",
                            1,
                        )
                    else:
                        malformed = valid.replace(revision_line, b"", 1)
                    with self.assertRaisesRegex(HELPER.HelperError, "revision"):
                        HELPER.payload_digest(
                            malformed, f"{phase.lower()}_payload_sha256"
                        )
                duplicated = valid.replace(
                    revision_line, revision_line + revision_line, 1
                )
                with self.assertRaisesRegex(HELPER.HelperError, "revision"):
                    HELPER.payload_digest(
                        duplicated, f"{phase.lower()}_payload_sha256"
                    )

    def test_root_bound_authority_rejects_intermediate_link_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            signed, _ = _signed_payload(
                phase="PLAN",
                nonce="4" * 32,
                field="payload_sha256",
                style="plain",
                body=b"linked: false\n",
            )
            (real / "plan.md").write_bytes(signed)
            alias = root / "alias"
            try:
                os.symlink(real, alias, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"filesystem cannot create authority symlink: {exc}")
            result = _run_helper(
                [
                    "verify-payload",
                    "--root",
                    str(root),
                    "--relative",
                    "alias/plan.md",
                    "--field",
                    "payload_sha256",
                ]
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertRegex(result.stderr, r"symlink|junction|reparse")

    def test_verify_setup_all_marker_styles_status_prefix_and_tamper(self) -> None:
        cases = (
            ("angled", ".claude"),
            ("html", ".cursor"),
            ("dashed", ".codex"),
            ("plain", ".qwen"),
        )
        for index, (style, host_dir) in enumerate(cases, start=1):
            with self.subTest(style=style), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                status_relative = f"{host_dir}/tempered/STATUS.md"
                setup_relative = f"{host_dir}/tempered/APPROVED_SETUP.md"
                status_initial = b"status: approved-initial\n"
                status_path = root / status_relative
                status_path.parent.mkdir(parents=True)
                status_path.write_bytes(status_initial + b"UNTRUSTED_AUDIT_COPY: allowed\n")
                artifact_content = (
                    b"BEGIN TEMPERED PLAN PAYLOAD\n"
                    b"payload_sha256: " + (b"b" * 64) + b"\n"
                )
                (root / "artifact.txt").write_bytes(artifact_content)
                body = (
                    _manifest_block(status_relative, status_initial, "WRITE_NEW")
                    + _manifest_block("artifact.txt", artifact_content, "WRITE_NEW")
                )
                signed, digest = _signed_payload(
                    phase="SETUP",
                    nonce=f"{index + 10:032x}",
                    field="setup_payload_sha256",
                    style=style,
                    body=body,
                )
                setup_path = root / setup_relative
                setup_path.write_bytes(signed)

                verified_digest, count = HELPER.verify_setup(root, setup_relative)
                self.assertEqual((verified_digest, count), (digest, 2))
                cli = _run_helper(
                    [
                        "verify-setup",
                        "--root",
                        str(root),
                        "--relative",
                        setup_relative,
                    ]
                )
                self.assertEqual(cli.returncode, 0, cli.stderr)
                self.assertEqual(cli.stdout, digest + "\n")

                (root / "artifact.txt").write_bytes(b"tampered\n")
                with self.assertRaisesRegex(HELPER.HelperError, "differs"):
                    HELPER.verify_setup(root, setup_relative)
                (root / "artifact.txt").write_bytes(artifact_content)
                status_path.write_bytes(b"status: TAMPERED\n")
                with self.assertRaisesRegex(HELPER.HelperError, "STATUS prefix"):
                    HELPER.verify_setup(root, setup_relative)
                status_path.write_bytes(status_initial + b"arbitrary untrusted suffix\n")
                self.assertEqual(HELPER.verify_setup(root, setup_relative)[0], digest)
                wrong_status_verb, _ = _signed_payload(
                    phase="SETUP",
                    nonce=f"{index + 20:032x}",
                    field="setup_payload_sha256",
                    style=style,
                    body=body.replace(
                        f"@@FILE WRITE_NEW {status_relative}".encode("utf-8"),
                        f"@@FILE VERIFY_EXISTING {status_relative}".encode("utf-8"),
                        1,
                    ),
                )
                setup_path.write_bytes(wrong_status_verb)
                with self.assertRaisesRegex(HELPER.HelperError, "WRITE_NEW STATUS"):
                    HELPER.verify_setup(root, setup_relative)

    def test_verify_bundle_exact_blocks_and_materialized_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.txt").write_bytes(b"alpha\n")
            (root / "b.txt").write_bytes(b"beta\n")
            bundle = (
                _manifest_block("a.txt", b"alpha\n", "VERIFY_EXISTING")
                + _manifest_block("b.txt", b"beta\n", "VERIFY_EXISTING")
            )
            manifest = root / "CONTROL_BUNDLE.manifest"
            manifest.write_bytes(bundle)
            expected = hashlib.sha256(bundle).hexdigest()
            self.assertEqual(
                HELPER.verify_bundle(root, "CONTROL_BUNDLE.manifest"), (expected, 2)
            )
            cli = _run_helper(
                [
                    "verify-bundle",
                    "--root",
                    str(root),
                    "--relative",
                    "CONTROL_BUNDLE.manifest",
                ]
            )
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertEqual(cli.stdout, expected + "\n")
            (root / "b.txt").write_bytes(b"drift\n")
            with self.assertRaisesRegex(HELPER.HelperError, "differs"):
                HELPER.verify_bundle(root, "CONTROL_BUNDLE.manifest")

            bad = _manifest_block("a.txt", b"alpha\n", "WRITE_NEW")
            manifest.write_bytes(bad)
            with self.assertRaisesRegex(HELPER.HelperError, "VERIFY_EXISTING"):
                HELPER.verify_bundle(root, "CONTROL_BUNDLE.manifest")

    def test_manifest_parser_rejects_duplicate_end_count_and_structural_smuggling(self) -> None:
        good = _manifest_block("a.txt", b"alpha\n")
        bad_cases = (
            good.replace(b"@@FILE WRITE_NEW ", b"@@FILE ", 1),
            good + good,
            good.replace(b"@@END a.txt", b"@@END b.txt"),
            good.replace(b"@@BYTES 6", b"@@BYTES 1"),
            good + b"outside: true\n",
        )
        for bad in bad_cases:
            with self.subTest(bad=bad[:40]):
                with self.assertRaises(HELPER.HelperError):
                    HELPER._parse_file_blocks(bad)

    def test_snapshot_is_order_independent_and_detects_artifact_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.txt").write_bytes(b"alpha\n")
            (root / "b.bin").write_bytes(b"\x00beta\xff")
            forward = HELPER.snapshot_digest(root, ["a.txt", "b.bin"])
            reverse = HELPER.snapshot_digest(root, ["b.bin", "a.txt"])
            self.assertEqual(forward, reverse)
            (root / "b.bin").write_bytes(b"\x00BETA\xff")
            self.assertNotEqual(forward, HELPER.snapshot_digest(root, ["a.txt", "b.bin"]))

    def test_snapshot_detects_portable_executable_mode_drift_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "tool.sh"
            artifact.write_bytes(b"#!/bin/sh\nexit 0\n")
            os.chmod(artifact, 0o644)
            before_mode = stat.S_IMODE(os.lstat(artifact).st_mode)
            before = HELPER.snapshot_digest(root, ["tool.sh"])
            os.chmod(artifact, 0o755)
            after_mode = stat.S_IMODE(os.lstat(artifact).st_mode)
            if bool(before_mode & 0o111) == bool(after_mode & 0o111):
                self.skipTest("filesystem does not expose portable executable-bit changes")
            after = HELPER.snapshot_digest(root, ["tool.sh"])
            self.assertNotEqual(before, after)

    def test_manual_save_comparison_is_exact_raw_byte_equality(self) -> None:
        approved = b"line one\nline two\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "approved.txt"
            exact = root / "manual-exact.txt"
            crlf = root / "manual-crlf.txt"
            bom = root / "manual-bom.txt"
            truncated = root / "manual-no-final-lf.txt"
            source.write_bytes(approved)
            exact.write_bytes(approved)
            crlf.write_bytes(approved.replace(b"\n", b"\r\n"))
            bom.write_bytes(b"\xef\xbb\xbf" + approved)
            truncated.write_bytes(approved[:-1])

            self.assertTrue(HELPER.exact_bytes_equal(source, exact))
            self.assertFalse(HELPER.exact_bytes_equal(source, crlf))
            self.assertFalse(HELPER.exact_bytes_equal(source, bom))
            self.assertFalse(HELPER.exact_bytes_equal(source, truncated))
            self.assertEqual(HELPER.sha256_file(source), hashlib.sha256(approved).hexdigest())

    def test_hash_and_snapshot_stream_files_and_enforce_bounded_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "artifact.bin"
            artifact.write_bytes(b"streamed bytes\n")
            expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
            with mock.patch.object(
                HELPER,
                "_read_regular_bytes",
                side_effect=AssertionError("streaming path buffered the file"),
            ):
                self.assertEqual(HELPER.sha256_file(artifact), expected)
                self.assertRegex(
                    HELPER.snapshot_digest(root, ["artifact.bin"]),
                    r"^[0-9a-f]{64}$",
                )

            with mock.patch.object(HELPER, "MAX_HASH_FILE_BYTES", 4):
                with self.assertRaisesRegex(HELPER.HelperError, "hash limit"):
                    HELPER.sha256_file(artifact)
            with mock.patch.object(HELPER, "MAX_SNAPSHOT_FILE_BYTES", 4):
                with self.assertRaisesRegex(HELPER.HelperError, "snapshot file exceeds"):
                    HELPER.snapshot_digest(root, ["artifact.bin"])
            with mock.patch.object(HELPER, "MAX_PAYLOAD_BYTES", 8):
                with self.assertRaisesRegex(HELPER.HelperError, "payload exceeds"):
                    HELPER.payload_digest(b"x" * 9, "payload_sha256")
            with mock.patch.object(HELPER, "MAX_PAYLOAD_LINES", 3):
                with self.assertRaisesRegex(HELPER.HelperError, "LF line limit"):
                    HELPER._payload_scope(b"x\n" * 4)
            with mock.patch.object(HELPER, "MAX_MANIFEST_BYTES", 8):
                with self.assertRaisesRegex(HELPER.HelperError, "manifest exceeds"):
                    HELPER._parse_file_blocks(b"x" * 9)
            paths_file = root / "paths.txt"
            paths_file.write_bytes(b"a.txt\nb.txt\n")
            with mock.patch.object(HELPER, "MAX_PATHS_FILE_BYTES", 4):
                with self.assertRaisesRegex(HELPER.HelperError, "byte limit"):
                    HELPER._paths_from_file(paths_file)
            with mock.patch.object(HELPER, "MAX_PATH_ENTRIES", 2):
                with self.assertRaisesRegex(HELPER.HelperError, "exceeds 2 entries"):
                    HELPER.validate_relative_paths(root, ["a", "b", "c"])
                paths_file.write_bytes(b"a\nb\nc\n")
                with self.assertRaisesRegex(HELPER.HelperError, "exceeds 2 entries"):
                    HELPER._paths_from_file(paths_file)
            with mock.patch.object(HELPER, "MAX_PATH_DEPTH", 2):
                with self.assertRaisesRegex(HELPER.HelperError, "component depth"):
                    HELPER.validate_relative_paths(root, ["a/b/c"])
            with mock.patch.object(HELPER, "MAX_TOTAL_PATH_COMPONENTS", 3):
                with self.assertRaisesRegex(HELPER.HelperError, "total components"):
                    HELPER.validate_relative_paths(root, ["a/b", "c/d"])
            three_blocks = b"".join(
                _manifest_block(f"{index}.txt", b"x\n") for index in range(3)
            )
            with mock.patch.object(HELPER, "MAX_MANIFEST_BLOCKS", 2):
                with self.assertRaisesRegex(HELPER.HelperError, "exceeds 2 file blocks"):
                    HELPER._parse_file_blocks(three_blocks)

            for index in range(3):
                (root / f"scan-{index}.txt").write_bytes(b"x\n")
            with mock.patch.object(
                HELPER, "MAX_SCANNED_DIRECTORY_ENTRIES", 2
            ):
                with self.assertRaisesRegex(HELPER.HelperError, "scan exceeds 2 entries"):
                    HELPER.validate_relative_paths(root, ["new.txt"])
            with mock.patch.object(
                HELPER, "MAX_SCANNED_DIRECTORY_NAME_BYTES", 1
            ):
                with self.assertRaisesRegex(HELPER.HelperError, "name bytes"):
                    HELPER.validate_relative_paths(root, ["new.txt"])

    def test_large_flat_path_and_manifest_sets_use_bounded_directory_scans(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_scandir = os.scandir
            paths = [f"generated/{index:05d}.txt" for index in range(10_000)]
            with mock.patch.object(
                HELPER.os, "scandir", side_effect=real_scandir
            ) as scanned:
                validated = HELPER.validate_relative_paths(root, paths)
            self.assertEqual(len(validated), 10_000)
            self.assertLessEqual(scanned.call_count, 1)

            manifest = b"".join(
                _manifest_block(f"files/{index:05d}.txt", b"x\n")
                for index in range(5_000)
            )
            blocks, _ = HELPER._parse_file_blocks(manifest)
            self.assertEqual(len(blocks), 5_000)

            snapshot_directory = root / "snapshot"
            snapshot_directory.mkdir()
            snapshot_paths = []
            for index in range(128):
                relative = f"snapshot/{index:04d}.txt"
                (root / relative).write_bytes(b"x\n")
                snapshot_paths.append(relative)
            with mock.patch.object(
                HELPER.os, "scandir", side_effect=real_scandir
            ) as snapshot_scans:
                HELPER.snapshot_digest(root, snapshot_paths)
            self.assertLessEqual(snapshot_scans.call_count, 4)

    def test_multi_link_regular_files_are_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            alias = root / "alias.txt"
            source.write_bytes(b"single identity required\n")
            try:
                os.link(source, alias)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"filesystem cannot create hard links: {exc}")
            with self.assertRaisesRegex(HELPER.HelperError, "multi-link"):
                HELPER.validate_relative_paths(
                    root, ["source.txt"], require_regular_files=True
                )
            with self.assertRaisesRegex(HELPER.HelperError, "multi-link"):
                HELPER.sha256_file(source)
            alias.unlink()

            project = root / "project"
            project.mkdir()
            candidate = HELPER.preview_create(project, "BRIEF", "2" * 32)
            external_link = root / "candidate-hardlink"
            os.link(candidate, external_link)
            with self.assertRaisesRegex(HELPER.HelperError, "multi-link"):
                HELPER._validate_preview_stage(candidate, root=project)
            external_link.unlink()
            HELPER.preview_remove(candidate, project)

    def test_nested_mount_and_unknown_mount_status_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mounted = root / "mounted"
            mounted.mkdir()
            (mounted / "file.txt").write_bytes(b"mounted\n")
            root_stat = os.lstat(root)
            mount_key = os.path.normcase(os.path.normpath(str(mounted)))
            with mock.patch.object(HELPER.os, "name", "posix"):
                with self.assertRaisesRegex(HELPER.HelperError, "mount traversal"):
                    HELPER._assert_no_mount_or_device_traversal(
                        root,
                        mounted,
                        os.lstat(mounted),
                        root_stat,
                        {mount_key},
                        "mounted/file.txt",
                    )

            with mock.patch.object(HELPER.os, "name", "posix"), mock.patch.object(
                HELPER.sys, "platform", "darwin"
            ):
                context = HELPER._mount_security_context(root)
                self.assertEqual(context[0].st_ino, root_stat.st_ino)
            with mock.patch.object(HELPER.os, "name", "posix"), mock.patch.object(
                HELPER.sys, "platform", "freebsd-test"
            ):
                with self.assertRaisesRegex(HELPER.HelperError, "UNKNOWN"):
                    HELPER._mount_security_context(root)

    def test_temp_root_rejects_control_and_non_nfc_paths_before_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(
                HELPER.tempfile, "gettempdir", return_value=str(root) + "\n"
            ):
                with self.assertRaisesRegex(HELPER.HelperError, "control"):
                    HELPER._resolved_temp_root()
            decomposed = str(root / "cafe\u0301")
            with mock.patch.object(
                HELPER.tempfile, "gettempdir", return_value=decomposed
            ):
                with self.assertRaisesRegex(HELPER.HelperError, "NFC"):
                    HELPER._resolved_temp_root()

    @unittest.skipIf(os.name == "nt", "POSIX permission semantics")
    def test_preview_auxiliary_0644_is_safe_inside_0700_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            candidate = HELPER.preview_create(project, "PLAN", "3" * 32)
            auxiliary = candidate.parent / "digest-input.bin"
            auxiliary.write_bytes(b"review bytes\n")
            os.chmod(auxiliary, 0o644)
            HELPER._validate_preview_stage(candidate, root=project)
            os.chmod(candidate, 0o644)
            with self.assertRaisesRegex(HELPER.HelperError, "permissions"):
                HELPER._validate_preview_stage(candidate, root=project)
            os.chmod(candidate, 0o600)
            HELPER.preview_remove(candidate, project)

    def test_path_escape_case_alias_unicode_alias_and_devices_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            unsafe_lists = (
                ["../escape"],
                ["/absolute"],
                ["C:/drive"],
                ["server\\share"],
                ["a//b"],
                ["a/../b"],
                ["name."],
                ["name "],
                ["file:stream"],
                ["NUL.txt"],
                ["dir/FILE~1.TXT"],
                ["safe/bi\u202edi.txt"],
                ["safe/zero\u200bwidth.txt"],
                ["Alpha.txt", "alpha.txt"],
                ["caf\u00e9.txt", "cafe\u0301.txt"],
            )
            for paths in unsafe_lists:
                with self.subTest(paths=paths):
                    with self.assertRaises(HELPER.HelperError):
                        HELPER.validate_relative_paths(root, paths)
            with self.assertRaisesRegex(HELPER.HelperError, "absolute canonical"):
                HELPER.validate_relative_paths(Path("relative-root"), ["safe.txt"])
            aliased_root = root / "missing" / ".."
            with self.assertRaisesRegex(HELPER.HelperError, "lexical aliases"):
                HELPER.validate_relative_paths(aliased_root, ["safe.txt"])
            self.assertEqual(
                HELPER._collision_key(("caf\u00e9.txt",)),
                HELPER._collision_key(("cafe\u0301.txt",)),
            )

        alias_errors: list[str] = []
        VALIDATOR_MODULE.validate_path_aliases(
            ["Alpha/file.txt", "alpha/FILE.txt", "caf\u00e9", "cafe\u0301"],
            alias_errors,
        )
        self.assertTrue(
            any("casefold release-path collision" in error for error in alias_errors),
            alias_errors,
        )
        self.assertTrue(
            any("not Unicode NFC" in error for error in alias_errors), alias_errors
        )

    def test_unenumerated_filesystem_alias_is_rejected(self) -> None:
        fake_stat = types.SimpleNamespace(
            st_mode=stat.S_IFREG | 0o600,
            st_file_attributes=0,
            st_dev=1,
            st_ino=1,
            st_mtime_ns=0,
            st_nlink=1,
        )
        fake_directory_stat = types.SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o700,
            st_file_attributes=0,
            st_dev=1,
            st_ino=2,
            st_mtime_ns=0,
            st_nlink=1,
        )
        fake_root = Path("C:/root")

        def fake_lstat(path: Path | str) -> object:
            return fake_directory_stat if Path(path) == fake_root else fake_stat

        scandir_context = mock.MagicMock()
        scandir_context.__enter__.return_value = iter(())
        scandir_context.__exit__.return_value = False
        with mock.patch.object(
            HELPER.os, "scandir", return_value=scandir_context
        ), mock.patch.object(HELPER.os, "lstat", side_effect=fake_lstat):
            with self.assertRaisesRegex(
                HELPER.HelperError, "unenumerated filesystem alias"
            ):
                HELPER._inspect_existing_components(
                    fake_root,
                    ("VERYLO~1.TXT",),
                    "VERYLO~1.TXT",
                    mount_context=(fake_directory_stat, set()),
                )

    def test_proposed_existing_target_and_existing_case_alias_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "existing.txt").write_text("owned\n", encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(HELPER.HelperError, "already exists"):
                HELPER.validate_relative_paths(root, ["existing.txt"])

            (root / "lower").mkdir()
            with self.assertRaisesRegex(HELPER.HelperError, "aliases existing name"):
                HELPER.validate_relative_paths(root, ["LOWER/new.txt"])

            (root / "Mixed.txt").write_text("owned\n", encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(HELPER.HelperError, "aliases existing name"):
                HELPER.validate_relative_paths(root, ["mixed.txt"])

    def test_symlink_or_junction_traversal_is_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "real"
            target.mkdir()
            (target / "artifact.txt").write_text("safe\n", encoding="utf-8", newline="\n")
            alias = root / "alias"
            try:
                os.symlink(target, alias, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("filesystem does not permit creating a test symlink")
            with self.assertRaisesRegex(HELPER.HelperError, "symlink|junction|reparse"):
                HELPER.validate_relative_paths(
                    root, ["alias/artifact.txt"], require_regular_files=True
                )

    @unittest.skipUnless(os.name == "nt", "Windows junction coverage")
    def test_windows_junction_traversal_is_rejected_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "real"
            target.mkdir()
            (target / "artifact.txt").write_bytes(b"safe\n")
            alias = root / "junction"
            created = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(alias), str(target)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if created.returncode != 0 or not alias.exists():
                reason = (created.stderr or created.stdout or "unknown error").strip()
                self.skipTest(f"Windows junction creation unavailable: {reason}")
            try:
                with self.assertRaisesRegex(
                    HELPER.HelperError, "symlink|junction|reparse"
                ):
                    HELPER.validate_relative_paths(
                        root,
                        ["junction/artifact.txt"],
                        require_regular_files=True,
                    )
            finally:
                os.rmdir(alias)


class ValidatorTests(unittest.TestCase):
    def test_repository_validates(self) -> None:
        result = _run_validator(REPO_ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("VALIDATION: PASS", result.stdout)
        self.assertIn("Public-manifest digest:", result.stdout)

    def test_unexpected_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = _copy_repository(Path(temporary))
            (root / "unexpected.txt").write_text("surprise\n", encoding="utf-8", newline="\n")
            result = _run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unexpected public file: unexpected.txt", result.stderr)

    def test_invisible_unicode_is_rejected_from_public_release_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = _copy_repository(Path(temporary))
            target = root / "README.md"
            text = target.read_text(encoding="utf-8")
            target.write_text(
                text.replace("Tempered", "Tem\u202epered", 1),
                encoding="utf-8",
                newline="\n",
            )
            result = _run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invisible-format Unicode", result.stderr)

    def test_python_path_resolving_shebang_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = _copy_repository(Path(temporary))
            target = root / "scripts/validate.py"
            target.write_bytes(b"#!/usr/bin/env python3\n" + target.read_bytes())
            result = _run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PATH-resolved shebang", result.stderr)

    def test_legacy_v1_schema_binding_and_name_are_rejected_in_executable_prompts(self) -> None:
        target_name = "codex/.agents/skills/tempered-intake/SKILL.md"
        cases = (
            ("payload_schema: 2", "payload_schema: 1", "unsupported payload_schema"),
            (
                "tempered-loop-sha256-nonce-v2",
                "tempered-loop-sha256-nonce-v1",
                "unsupported approval_binding",
            ),
            ("Tempered", "Gaunt" + "let", "Legacy v1 identifier"),
        )
        for before, after, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                root = _copy_repository(Path(temporary))
                target = root / target_name
                text = target.read_text(encoding="utf-8")
                self.assertIn(before, text)
                target.write_text(
                    text.replace(before, after, 1), encoding="utf-8", newline="\n"
                )
                result = _run_validator(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)

    def test_release_symlink_is_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = _copy_repository(Path(temporary))
            target = root / "README.md"
            alias = root / "readme-alias.md"
            try:
                os.symlink(target, alias)
            except (NotImplementedError, OSError):
                self.skipTest("filesystem does not permit creating a test symlink")
            result = _run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertRegex(result.stderr, r"Symlink, junction, or reparse point")

    @unittest.skipUnless(os.name == "nt", "Windows junction coverage")
    def test_release_junction_is_rejected_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            root = _copy_repository(temporary_root)
            target = temporary_root / "junction-target"
            target.mkdir()
            (target / "outside.txt").write_bytes(b"outside\n")
            alias = root / "junction-alias"
            created = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(alias), str(target)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if created.returncode != 0 or not alias.exists():
                reason = (created.stderr or created.stdout or "unknown error").strip()
                self.skipTest(f"Windows junction creation unavailable: {reason}")
            try:
                result = _run_validator(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertRegex(
                    result.stderr, r"Symlink, junction, or reparse point"
                )
            finally:
                os.rmdir(alias)

    def test_semantic_negative_fixtures_are_rejected(self) -> None:
        target_name = "qwen/.qwen/commands/tempered/compile.md"
        fixtures = (
            (
                "APPROVE TEMPERED ACTION <id> R<n> SHA256:<64hex> NONCE:<32hex>",
                "ACTION APPROVAL REMOVED",
                "qwen ACTION approval grammar",
            ),
            ("APPROVED_SETUP", "REMOVED_SETUP_ARTIFACT", "immutable approved setup"),
            ("brief_payload_sha256", "removed_brief_digest", "task/result binding"),
            ("maxSubagentDepth: 1", "maxSubagentDepth: 5", "Qwen depth ceiling"),
            ("modelFallbacks", "removed_fallback_control", "controlled model fallbacks"),
            ("instruction_trust_mode", "removed_trust_mode", "trusted-instruction threat model"),
            (
                "git_status_baseline",
                "removed_dirty_baseline",
                "advisory Git dirty-state coverage",
            ),
            (
                "preview_stage_token",
                "removed_stage_binding_field",
                "ACTION preview-stage replay binding",
            ),
            (
                "subsequent current user turn",
                "same assistant turn",
                "external helper bootstrap trust",
            ),
            ("non-file resource", "removed external state", "exclusive non-file resource ledger"),
        )
        for before, after, expected in fixtures:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                root = _copy_repository(Path(temporary))
                target = root / target_name
                text = target.read_text(encoding="utf-8")
                self.assertIn(before, text)
                target.write_text(text.replace(before, after), encoding="utf-8", newline="\n")
                result = _run_validator(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)

    def test_numeric_ceiling_and_one_cycle_fallback_cannot_both_disappear(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = _copy_repository(Path(temporary))
            target = root / "qwen/.qwen/commands/tempered/compile.md"
            text = target.read_text(encoding="utf-8")
            text = re.sub(r"(?i)numeric", "measured", text)
            text = re.sub(
                r"(?i)one[- ](?:authenticated )?(?:manual )?(?:approved )?cycle(?:-at-a-time| at a time)?",
                "multiple cycles",
                text,
            )
            text = re.sub(r"(?i)exactly one numbered", "several numbered", text)
            target.write_text(text, encoding="utf-8", newline="\n")
            result = _run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("numeric ceiling proof or one-cycle fallback", result.stderr)

    def test_ci_permissions_pins_isolation_and_trigger_are_enforced(self) -> None:
        target_name = ".github/workflows/validate.yml"
        cases = (
            (
                "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd",
                "actions/checkout@v4",
                "not pinned to a full commit SHA",
            ),
            (
                "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405",
                "actions/setup-python@v6",
                "not pinned to a full commit SHA",
            ),
            (
                "Invoke-TrustedPython -I -S -B scripts/validate.py",
                "python scripts/validate.py",
                "CI hardening",
            ),
            (
                'python: ["3.10", "3.12"]',
                'python: ["3.12"]',
                "CI hardening",
            ),
            ("macos-latest", "macos-disabled", "CI hardening"),
            (
                "persist-credentials: false",
                "persist-credentials: true",
                "CI hardening",
            ),
            ("contents: read", "contents: write", "permissions must remain read-only"),
            ("pull_request:\n", "pull_request_target:\n", "must not use pull_request_target"),
        )
        for before, after, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                root = _copy_repository(Path(temporary))
                target = root / target_name
                text = target.read_text(encoding="utf-8")
                self.assertIn(before, text)
                target.write_text(
                    text.replace(before, after, 1), encoding="utf-8", newline="\n"
                )
                result = _run_validator(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)

    def test_intake_partial_state_and_terminal_receipt_semantics_are_enforced(self) -> None:
        target_name = "qwen/.qwen/commands/tempered/intake.md"
        cases = (
            (
                "Successful removal is a BRIEF receipt precondition",
                "Preview removal is attempted after verification",
            ),
            ("INVALID/PARTIAL", "PARTIAL_STATE"),
            ("human reconciliation", "later review"),
            ("After emitting a receipt", "After the workflow completes"),
        )
        for before, after in cases:
            with self.subTest(removed=before), tempfile.TemporaryDirectory() as temporary:
                root = _copy_repository(Path(temporary))
                target = root / target_name
                text = target.read_text(encoding="utf-8")
                self.assertIn(before, text)
                target.write_text(
                    text.replace(before, after), encoding="utf-8", newline="\n"
                )
                result = _run_validator(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "qwen intake terminal receipt and partial-state quarantine",
                    result.stderr,
                )

    def test_external_receipt_helper_hash_field_and_order_are_enforced(self) -> None:
        target_name = "qwen/.qwen/commands/tempered/compile.md"
        cases = (
            (
                "TEMPERED BRIEF RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> "
                "HELPER_SHA256:<64hex>",
                "TEMPERED BRIEF RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex>",
                "qwen BRIEF receipt grammar",
            ),
            (
                "TEMPERED SETUP RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> "
                "HELPER_SHA256:<64hex> CONTROL_SHA256:<64hex>",
                "TEMPERED SETUP RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> "
                "CONTROL_SHA256:<64hex> HELPER_SHA256:<64hex>",
                "qwen SETUP receipt grammar",
            ),
            (
                "TEMPERED PLAN RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> "
                "HELPER_SHA256:<64hex> CONTROL_SHA256:<64hex> "
                "ARTIFACT_SHA:<64hex> GIT:<40-or-64hex-or-NOT_GIT>",
                "TEMPERED PLAN RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> "
                "CONTROL_SHA256:<64hex> HELPER_SHA256:<64hex> "
                "ARTIFACT_SHA:<64hex> GIT:<40-or-64hex-or-NOT_GIT>",
                "qwen PLAN receipt grammar",
            ),
        )
        for before, after, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                root = _copy_repository(Path(temporary))
                target = root / target_name
                text = target.read_text(encoding="utf-8")
                self.assertEqual(text.count(before), 1)
                target.write_text(
                    text.replace(before, after, 1), encoding="utf-8", newline="\n"
                )
                result = _run_validator(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
