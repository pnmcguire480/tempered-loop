# Migrating to Tempered Loop protocol v2

Tempered Loop is a breaking rename and protocol upgrade. It is not a compatible alias for the earlier Gauntlet-named kit.

Do not install both generations side by side. Back up your project, review the old control files, and move or remove the old adapter files yourself. The installer and prompts do not delete them for you.

The old spellings below are **migration-only inert text**. Do not invoke them, copy them into active configuration, or treat them as aliases.

## Name mapping

| Earlier name | Tempered Loop v2 |
|---|---|
| `gauntlet-intake` | `tempered-intake` |
| `gauntlet-compile` | `tempered-compile` |
| `/gauntlet:intake` | `/tempered:intake` |
| `/gauntlet:compile` | `/tempered:compile` |
| `.claude/gauntlet/` | `.claude/tempered/` |
| `.cursor/gauntlet/` | `.cursor/tempered/` |
| `.codex/gauntlet/` | `.codex/tempered/` |
| `.qwen/gauntlet/` | `.qwen/tempered/` |
| `APPROVE GAUNTLET ...` and legacy receipts | `APPROVE TEMPERED ...` and protocol-v2 receipts |

## Upgrade steps

1. Make a recoverable backup or source-control checkpoint.
2. Save any useful project work. Your source code remains yours; only the old generated control files and adapter instructions are being replaced.
3. Review and manually move or remove the earlier skills, commands, agents, and generated control folders. Do not leave duplicate old and new commands discoverable by the host.
4. Copy one complete Tempered Loop adapter into the project. Do not merge individual prompt fragments across generations.
5. Start a fresh host session.
6. Run the Tempered intake again and approve a new protocol-v2 project brief.
7. Start another fresh session and run the Tempered compiler again. Review and approve a new setup.
8. Discard every earlier approval token and receipt. Protocol-v1 IDs, nonces, digests, receipts, paths, and commands cannot authorize protocol v2.

If an old generated file contains decisions you still need, treat it as untrusted reference material and copy those decisions into your new intake answers. Do not present the old file or receipt as current authority.

The original Gauntlet Loop name remains in [NOTICE.md](NOTICE.md) and the README only to credit the source material that inspired this independent implementation.
