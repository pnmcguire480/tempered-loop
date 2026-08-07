# Codex Tempered Kit

This is the Codex-native, two-part version of the Tempered workflow:

- **Tempered Intake** interviews you for a new project or an audit/revamp, challenges weak requirements, and creates a revision-bound approved brief.
- **Tempered Compiler** turns that approved brief into project-specific Codex agents, acceptance gates, a runbook, status ledger, and final execution prompt. It deliberately stops before project execution.

The workflow is packaged as repository skills—the current replacement for deprecated custom prompts—not as copied Qwen slash commands.

## Read this before you copy anything

Use the kit directly only in a new project or a repository whose instructions you already trust. A prompt cannot demote an applicable `AGENTS.md`, repository skill, configuration, MCP server, or other instruction Codex has already loaded from a hostile project. For an unknown or untrusted repository, stop and use the clean-working-directory procedure in the [threat model](../THREAT-MODEL.md). Remote and cloud execution are unsupported in this public preview.

This release uses the incompatible Tempered protocol v2: `payload_schema: 2` and `approval_binding: tempered-loop-sha256-nonce-v2`. Legacy v1 commands, payloads, approvals, and receipts are invalid; do not install both versions side by side. See the [migration guide](../MIGRATION.md).

## Tiny-person setup: pretend the computer is five

1. Find the project folder you want Codex to help with.
2. Open this kit's `codex` folder.
3. Copy the whole `.agents` folder into your project folder. Keep the dot at the front.
4. Open that project in Codex.
5. Pick **Tempered Intake** from Skills. In Codex CLI or the IDE, type `$tempered-intake`.
6. Answer the little groups of questions.
7. Read the brief. If it is right, send the whole exact `APPROVE TEMPERED BRIEF ... SHA256:... NONCE:...` line Codex gives you—alone in a new message.
8. Copy the `TEMPERED BRIEF RECEIPT` Codex prints after it checks the saved file.
9. Start a fresh chat in the same project and pick **Tempered Compiler**. In CLI or the IDE, type `$tempered-compile`.
10. When it asks, paste your `TEMPERED BRIEF RECEIPT` alone. The project is not allowed to hand the receipt to itself.
11. Read the exact-file setup preview. If it is right, send the whole `APPROVE TEMPERED SETUP ... SHA256:... NONCE:...` line alone.
12. Copy the checked `TEMPERED SETUP RECEIPT`, then stop and read `.codex/tempered/RUNBOOK.md`. The robot has made the recipe; it has not cooked the project yet.
13. Follow the runbook in a fresh chat. Save the full plan receipt ending in `CONTROL_SHA256:... ARTIFACT_SHA:... GIT:...`; one more fresh chat checks it before one work cycle.

On Windows, if you cannot see `.agents`, turn on **File Explorer → View → Show → Hidden items**. Copy the folder itself, not only the files inside it.

## Exact project installation — recommended

Copy this directory:

```text
codex/.agents/
```

into the project root so the result is:

```text
<project-root>/.agents/skills/tempered-intake/SKILL.md
<project-root>/.agents/skills/tempered-intake/agents/openai.yaml
<project-root>/.agents/skills/tempered-compile/SKILL.md
<project-root>/.agents/skills/tempered-compile/agents/openai.yaml
<project-root>/.agents/tempered-tools/tempered_receipt.py
```

Start Codex from that project root. Codex scans `.agents/skills` from the current working directory up to the repository root and normally detects changes automatically. Restart the Codex session if the skills do not appear.

### Personal installation

This public preview supports project installation only. A personal skill copy by itself is insufficient because the prompts require the project-local helper at `.agents/tempered-tools/tempered_receipt.py`. Copy and review the whole adapter folder separately for each trusted project.

## Exact invocation by surface

| Codex surface | Part 1 | Part 2 |
|---|---|---|
| ChatGPT desktop app, Codex selected | Open **Skills** and select **Tempered Intake** | Open **Skills** and select **Tempered Compiler** |
| Codex CLI | `$tempered-intake` | Start a fresh session, then `$tempered-compile` |
| Codex IDE extension | `$tempered-intake` | Start a fresh chat, then `$tempered-compile` |

Both skills disable implicit invocation so Codex cannot start either gated workflow merely because a normal request resembles it.

## Safe use, step by step

1. Confirm the repository is new/trusted, or complete the clean bootstrap in the [threat model](../THREAT-MODEL.md).
2. Open the intended project, not a parent directory containing unrelated work.
3. Follow [Find the trusted Python path](../PYTHON-SETUP.md) to identify one canonical full Python 3.10+ executable path outside the project without PATH or command lookup. Reject project virtual environments and any symlink, shortcut, junction, or reparse-point path. Resolve `.agents/tempered-tools/tempered_receipt.py` under the canonical project root to its full non-link path and keep it as `<canonical-absolute-helper-path>`. Use those same two paths for this read-only check and every later helper call:

   ```text
   <trusted-absolute-python> -I -S -B <canonical-absolute-helper-path> self-test
   ```

   Stop if it does not pass. Codex must never calculate, invent, or visually guess a nonce or SHA-256 value.
4. Record the exact Codex surface/build, selected model, and reasoning level. Do not assume a model alias exists because a document or another account lists it.
5. Enter Plan mode with `/plan` for Part 1.
6. Invoke Part 1 and answer at most four questions per round.
7. Review the complete marked brief payload and its fingerprint. Corrections increase its revision, rotate its random nonce, recompute its SHA-256, and invalidate every older token.
8. Before the brief preview is fingerprinted, leave Plan mode with `/plan` or the current UI control. Keep **Ask for approval** and the project workspace boundary. Approve only the helper's random OS-temp directory as an exact exception; never broaden roots or use project-local scratch. CLI users can check `/permissions`; the lower-risk explicit launch posture is `--sandbox workspace-write --ask-for-approval on-request`.
9. Review the finalized staged marker-wrapped payload. In a new user turn, send only `APPROVE TEMPERED BRIEF <id> R<n> SHA256:<64hex> NONCE:<32hex>` with the exact displayed values.
10. After raw-byte read-back passes, save the emitted `TEMPERED BRIEF RECEIPT`. Start a fresh chat in the same root, invoke Part 2, and wait for its receipt request. Paste the receipt alone in another fresh turn; invocation text, repository files, tool output, and assistant reconstruction do not count.
11. Re-enter Plan mode for Part 2's read-only analysis. Before it fingerprints the complete path-sorted manifest, leave Plan mode while retaining **Ask for approval** and approve only the new helper-issued OS-temp directory.
12. Review the staged exact proposed file bytes, topology, sandboxes, ownership, gates, budgets, and fallbacks. Then send only `APPROVE TEMPERED SETUP <id> R<n> SHA256:<64hex> NONCE:<32hex>` in a new turn.
13. The compiler writes the exact manifest, recomputes it from disk, emits a `TEMPERED SETUP RECEIPT`, and stops. It does not run builds, tests, agents, `/goal`, or project implementation.
14. Follow `.codex/tempered/RUNBOOK.md` in another fresh chat. That chat first issues a placeholder-only `TEMPERED SETUP RECEIPT` challenge. After you supply the external receipt alone, it checks `HELPER_SHA256` independently and only then recomputes the setup/control bundle. It then hashes the full execution plan and requires `APPROVE TEMPERED PLAN <id> R<n> SHA256:<64hex> NONCE:<32hex>` before any project-source change.
15. Save the emitted `TEMPERED PLAN RECEIPT`. Every separate launcher must recompute the plan, control bundle, artifact snapshot, and Git identity, then receive that receipt alone from the current user turn before dispatching work. If a completed cycle changes the snapshot, a later launcher needs a newly reviewed plan revision and new receipt.

Never use this workflow under **Full access**, `danger-full-access`, `--yolo`, or approval bypass. A prompt-level approval token is a workflow gate; the host sandbox and approval policy remain the security boundary.

## What the long fingerprint and receipt do

Every brief, setup, and plan preview has a fresh host-random nonce plus a SHA-256 fingerprint. Codex hashes the complete marker-wrapped UTF-8/LF file, including both marker lines and the final LF. For hashing only, it replaces the single active digest value's 64 hexadecimal characters with 64 zeroes; the nonce, markers, and every other byte stay unchanged. A correction rotates the nonce and fingerprint.

The payload may already say `approved`. During preview that is only the exact target state proposed for writing—it does not approve itself. It becomes factual only after the user sends the matching ID, revision, fingerprint, and nonce in a later turn and Codex verifies the exact written bytes afterward.

A stored self-hash is not enough in a fresh chat, so each successful gate prints a receipt for the user to carry forward:

- Part 1 emits `TEMPERED BRIEF RECEIPT`; Part 2 asks with placeholders first, checks the receipt-carried helper digest, then recomputes the brief.
- Part 2 emits `TEMPERED SETUP RECEIPT`; fresh execution asks with placeholders first, checks the helper digest, then recomputes the whole path-sorted control/agent bundle.
- Plan approval emits `TEMPERED PLAN RECEIPT`; every separate Goal/manual launcher asks with placeholders first, checks the helper digest, then recomputes the plan, control digest, and artifact/commit SHA.

Only a fresh current user message containing the requested receipt counts. Files, prompt arguments, assistant text, tool output, quoted content, and subagents cannot carry it across the trust boundary.

A receipt is a prompt-level fresh-user-turn ceremony, not a password or cryptographic signature; its fields are largely recomputable. A compromised or noncompliant host can bypass it. Host permissions, sandboxing, and your review remain the security boundary.

The v2 receipt lines are exactly:

```text
TEMPERED BRIEF RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> HELPER_SHA256:<64hex>
TEMPERED SETUP RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> HELPER_SHA256:<64hex> CONTROL_SHA256:<64hex>
TEMPERED PLAN RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> HELPER_SHA256:<64hex> CONTROL_SHA256:<64hex> ARTIFACT_SHA:<64hex> GIT:<40-or-64hex-or-NOT_GIT>
```

No v1 or legacy receipt is accepted by v2.

## What Part 2 generates

```text
.codex/tempered/
  PROJECT_BRIEF.md
  APPROVED_SETUP.md
  APPROVED_PLAN.md       created later only after exact PLAN approval
  ACCEPTANCE.md
  EXECUTION_PROMPT.md
  RUNBOOK.md
  STATUS.md
  RESOURCES.md
  CONTROL_BUNDLE.manifest
  AGENTS_SNIPPET.md
  CODEX_CONFIG_SNIPPET.toml

.codex/agents/
  tempered-explorer.toml
  tempered-builder-<track>.toml
  tempered-critic.toml
  tempered-verifier.toml
  tempered-integrator.toml
```

Execution planning later creates `.codex/tempered/APPROVED_PLAN.md` only after exact PLAN approval. It is not a Part 2 output and is authenticated by the artifact-bound PLAN receipt.

`PROJECT_BRIEF.md` is created by Part 1. Part 2 treats it only as a digest-verified input after the user carries its receipt into the fresh compiler chat; Part 2 never rewrites it.

The snippets are reviewable suggestions. The compiler never silently replaces an existing `AGENTS.md` or `.codex/config.toml`.

## Native capability record and fallbacks

This kit was authored on **2026-08-06** against a freshly fetched current OpenAI Codex manual. The installed build and account still must be checked because rollout, workspace policy, model access, and plugins can differ.

| Capability | Verified native behavior | Kit behavior when unavailable or unverified |
|---|---|---|
| Repository skills | Codex loads shared skills from `.agents/skills`; CLI/IDE can explicitly invoke them with `$skill-name`. | Stop if the skills are not discovered after a restart. |
| Project custom agents | Standalone TOML agents load from `.codex/agents/`; required fields are `name`, `description`, and `developer_instructions`. | Run the role in the coordinator chat, sequentially and with the same contract. |
| Subagents | Current local releases enable subagents by default; children inherit the parent turn's live permissions. | This public preview is coordinator-only and depth one. Children never spawn or delegate; otherwise the coordinator runs the role sequentially. |
| Plan mode | `/plan` gathers context and proposes a plan before implementation. | Manually demand a read-only preview and do not grant write approval. |
| Goal mode | `/goal` persists an objective and keeps the same sandbox/approval policy. | Goal mode is not treated as a budget ceiling. Use one ordinary-chat cycle at a time unless the installed host exposes a verified outer limit. |
| Worktrees | Managed worktrees are ChatGPT-desktop-only and require Git. They isolate chats, not every subagent in a chat. | Parallelize read-only agents only; run writers sequentially or in user-created separate checkouts. |
| Browser | Built-in Browser/computer use is available only in the ChatGPT desktop app when the Browser plugin is installed and exposed. | CLI/IDE use static screenshots, a verified project browser tool, or human visual review. |
| Image input | Desktop app, CLI, and IDE can receive static images; CLI supports `-i`/`--image`. | Mark visual gates unverified until human evidence is supplied. |
| Review | `/review` is an additional code-diff review surface. | Use the configured critic, deterministic tests, and human review; never treat diff review as runtime proof. |
| Model/reasoning | Selection and supported effort levels depend on the active model, account, and surface. | Inherit the selected coordinator settings or omit custom-agent model fields; never invent IDs. |
| Host-enforced outer run ceiling | No universal per-goal time, step, tool-call, or token ceiling is established by the public Goal-mode documentation. | Default to manually approved, one-cycle-at-a-time execution with a finite cycle ledger. |

## Codex-specific cautions

- Applicable `AGENTS.md` instructions are loaded once per run from global scope through the project tree; a closer file can override a broader one. Start fresh chats after instruction changes.
- This public preview uses one local coordinator and first-level agents only. Nested agents, agent chaining, and remote/cloud execution are unsupported.
- Do not let two subagents write in the same checkout. “Different files” is not enough when lockfiles, schemas, generated output, or shared state can overlap.
- A custom agent's `sandbox_mode` can be superseded by the parent turn's live permission choice. Select the parent permission posture before delegation.
- Deterministic gates run before subjective model critique. A same-model fresh-context critic is useful but correlated, not an independent judge.
- Tests and builds can change caches, snapshots, generated files, and lockfiles. The final plan gate occurs before baseline execution for that reason.
- Repository text, websites, tool output, and quoted approval phrases never count as user approval.
- Every task and result carries matching brief/setup/plan IDs and revisions, all three payload digests, the canonical immutable control-bundle digest, and the actual artifact snapshot and Git identity. The coordinator rejects stale or mismatched work before using it.
- PLAN approval never authorizes destructive, production, deploy, publish, purchase, migration, secret-data, network, external-message, permission, scope, or budget effects. Each needs a separate ACTION payload and fresh approval. High-impact actions are manual-only manual handoffs in v0.1.0. The agent never executes them and makes no process call. Exact approval authorizes only the digest-bound, stage-bound chat handoff; root-bound `preview-consume` runs immediately before output labeled `NOT EXECUTED` and `HANDED_OFF/EXECUTION_UNKNOWN`. A human executes out-of-agent, outside kit enforcement. A crash or ambiguous delivery gets no cleanup and needs a new revision; PLAN never authorizes it, and completion is never inferred without later human-attested evidence. Delivery is best-effort single-delivery during a compliant, untampered helper lifecycle, not a security guarantee or durable replay protection. The same OS principal can reverse or recreate stage state, so human idempotency and replay controls are required because duplicate execution may occur.
- Changing an immutable control or agent file invalidates setup/plan receipts and requires a newly approved setup revision; editing a label in `STATUS.md` cannot reauthorize it.
- Success, plateau, regression, budget exhaustion, blocked access, and a required human decision are terminal outcomes; none automatically opens another cycle.

## Official OpenAI references

- Skills and repository locations: https://learn.chatgpt.com/docs/build-skills
- Subagents and custom-agent TOML: https://learn.chatgpt.com/docs/agent-configuration/subagents
- `AGENTS.md` discovery and precedence: https://learn.chatgpt.com/docs/agent-configuration/agents-md
- Plan and Goal workflows: https://learn.chatgpt.com/docs/long-running-work
- Sandbox and permissions: https://learn.chatgpt.com/docs/sandboxing
- Desktop Git worktrees: https://learn.chatgpt.com/docs/environments/git-worktrees
- Built-in Browser surfaces and limits: https://learn.chatgpt.com/docs/browser
- Static image inputs: https://learn.chatgpt.com/docs/image-inputs
- App slash commands: https://learn.chatgpt.com/docs/reference/commands
- CLI slash commands: https://learn.chatgpt.com/docs/developer-commands?surface=cli
- Codex developer documentation: https://developers.openai.com/codex/

Do not put credentials, personal data, production secrets, or private browser state into the prompts or generated files.
