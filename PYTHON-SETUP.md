# Find the trusted Python path

Tempered Loop supports Python **3.10 or newer** and uses only the standard library. The release workflow tests the oldest supported minor, 3.10, and the current reference minor, 3.12.

The important part is not merely having Python. You must give the kit the full path to one Python executable you already trust, outside the project. The kit calls that path `<trusted-absolute-python>`.

Do not type only `python`, `python3`, or `py`. Do not use a project virtual environment, a Microsoft Store app alias, a shortcut, or a path containing a symlink, junction, or reparse point. If you cannot establish the path confidently, stop and ask a computer administrator; do not let the agent guess.

This procedure checks identity and path hygiene. It does not prove that a compromised operating system or malicious Python installation is safe.

## Windows

The simplest supported route is an organization-approved installation or the official installer from [python.org](https://www.python.org/downloads/windows/). Choose a fixed install directory outside every project. An all-users install such as `C:\Program Files\Python312\python.exe` is easy to recognize; your real path may differ.

1. Open **Settings > Apps > Installed apps** and locate the Python installation you trust. Use its installer/Modify screen or the Start-menu shortcut's **Properties > Target** to find the full `python.exe` target. Do not use a target under `WindowsApps`.
2. In PowerShell, replace the example with that literal full path and inspect the file plus every parent. `LinkType`/`Target` must be empty and `Attributes` must not contain `ReparsePoint`:

   ```powershell
   $TrustedPython = 'C:\Program Files\Python312\python.exe'
   $Item = Get-Item -LiteralPath $TrustedPython -Force
   while ($null -ne $Item) {
     $Item | Select-Object FullName, Attributes, LinkType, Target
     $Item = $Item.Parent
   }
   ```

3. Run the exact executable directly in isolated mode:

   ```powershell
   & 'C:\Program Files\Python312\python.exe' -I -S -B -c "import sys; assert sys.version_info >= (3, 10); print(sys.executable); print(sys.version)"
   ```

The printed executable must be the same trusted path and the version must be 3.10 or newer. Keep that full path and substitute it wherever a guide prints `<trusted-absolute-python>`.

## macOS

Use a Python installation you or your administrator deliberately installed, such as the signed installer from [python.org](https://www.python.org/downloads/macos/). Do not use an agent-suggested download or a project environment.

1. In Finder choose **Go > Go to Folder** and open `/Library/Frameworks/Python.framework/Versions/` for a standard python.org install.
2. Open a numeric version directory, then `bin`, and select the versioned executable such as `python3.12`. Do not use a `Current` alias or an unversioned convenience link. **Get Info** must describe a Unix executable, not an alias.
3. Use its literal full path and confirm the version:

   ```text
   /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -I -S -B -c "import sys; assert sys.version_info >= (3, 10); print(sys.executable); print(sys.version)"
   ```

If your trusted installation lives elsewhere, ask its administrator or installer for the fully resolved versioned binary. Do not discover it with `which`, `whereis`, or a shell PATH lookup.

## Linux

Use the system package your administrator trusts or an organization-managed installation. Ask for the versioned executable's full path. Starting from that known candidate, the operating system's fixed `readlink` tool can show the fully resolved path:

```text
/usr/bin/readlink -f -- /usr/bin/python3.12
```

Use the returned absolute path only after confirming it remains outside the project and comes from the expected system package. Then run it directly:

```text
/usr/bin/python3.12 -I -S -B -c "import sys; assert sys.version_info >= (3, 10); print(sys.executable); print(sys.version)"
```

Paths vary by distribution. If `/usr/bin/readlink`, the candidate, or the package identity is not known and trusted, stop and ask the administrator rather than substituting a PATH search.

## Final check

Run the adapter's `tempered_receipt.py self-test` with the same absolute executable and `-I -S -B`. Every later helper invocation must use that identical prefix. If the path, executable bytes, or version changes, stop and review the installation again.
