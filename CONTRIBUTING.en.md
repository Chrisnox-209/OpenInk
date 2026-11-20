# Contributing to OpenInk

[Français](CONTRIBUTING.md) · **English** · [Español](CONTRIBUTING.es.md)

## Scope

This repository contains the Linux application, experimental Windows port and
experimental macOS kit. Windows/macOS have not been tested on their native
operating systems: preserve this warning in guides and distributions. See
[DISCLAIMER.md](DISCLAIMER.md#english). Preserve the data paths and the `inkora`
alias for migration compatibility. Do not introduce dependencies
on the original research directory, real printer data, personal backups,
recovery executables or new experimental firmware.

Files in `commun/inkora/firmware_assets/` are pinned by SHA-256. Changing their
hashes is more than a routine resource update. Preserve explicit acceptance,
the mandatory USB connection, backup before writing, shared locks and the
absence of automatic reflashing.

## Validate a change

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning \
  python3 -m unittest discover -s linux/tests -v
python3 linux/build_deb.py
python3 linux/build_linux.py
git diff --check
```

For interface changes, run the isolated graphical checks:

```bash
python3 linux/tests/check_interface.py
python3 linux/tests/check_i18n.py
python3 linux/tests/check_appearance.py
dbus-run-session -- python3 linux/tests/check_tray.py
```

Hardware tests must not run implicitly as part of a test suite. Checks use
a temporary database and a fictional printer identity. Validation captures
and build outputs remain ignored by Git. Only the public illustrations in
`docs/images/` are versioned.

The `commun/inkora/locales/en.json` and `es.json` catalogues translate French
labels at display time. Preserve placeholders such as `{p0}` and `{p1}`, and
the canonical form values: never translate CUPS identifiers, hardware commands
or persistent data. French remains the default README; keep the English and
Spanish guides up to date. Also update all three versions of this contribution
guide whenever a rule changes.

To regenerate illustrations for all three guides without hardware access:

```bash
python3 linux/tests/capture_readme.py
```

Capturing requires an X11/XWayland display and `xwd` (`x11-apps`). The script
reads only the test window, not the desktop. Visually inspect the generated
images before publishing: three light views and the dark settings view per
language, for a total of twelve illustrations.

## Commit style

The format follows the author's `gchelp` terminal functions:

```text
<emoji> <type>(<scope>): <message in French>
```

| Emoji | Type | Purpose |
| --- | --- | --- |
| 🧩 | `feat` | New feature |
| 🐛 | `fix` | Bug fix |
| 📝 | `docs` | Documentation |
| 🛠 | `tweak` | Adjustment or renaming |
| 🔨 | `refactor` | Refactoring |
| 💄 | `style` | Formatting |
| ➕ | `add` | Adding files |
| 🚧 | `wip` | Work in progress |
| 🔧 | `chore` | Maintenance |
| ✅ | `test` | Tests |
| ⚡ | `perf` | Performance |
| 👷 | `ci` | Continuous integration |
| ⏪ | `build` | Builds and artefacts |
| ❌ | `remove` | Removal |
| 🎨 | `media` | Images and media |
| ⚙️ | `config` | Configuration |
| ⬆️ | `upgrade` | Dependency upgrade |
| ⬇️ | `downgrade` | Dependency downgrade |
| 🚑 | `hotfix` | Urgent fix |
| 🔀 | `merge` | Merge |

Examples retain the project's French commit messages:

```text
🧩 feat(linux): ajoute OpenInk et le suivi local de l’encre
✅ test(core): couvre les alertes et les reprises du contrôleur V2
📝 docs(README): documente l’installation Ubuntu et les limites du suivi
```

The `gcfeat`, `gcdocs` and similar functions are local terminal helpers;
they are not required to contribute.
