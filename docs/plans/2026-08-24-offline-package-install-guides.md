# Offline package installation helpers

**Status:** complete, 2026-08-24

## Goal

Make each unsigned offline test archive self-explanatory after extraction. The visible install
guide must be named `HOW TO INSTALL.txt`. macOS receives a narrowly scoped launcher that clears
extended attributes only from the sibling `Muta.app` before opening it; Linux receives a portable
launcher that restores the AppImage executable bit; Windows retains its existing installer helper.

## Package contract

- macOS: `Muta.command`, `Muta.app`, `model-pack/`, and `HOW TO INSTALL.txt` stay together.
  `Muta.command` resolves its own directory, refuses to target a missing sibling app, invokes the
  system `/usr/bin/xattr`, and opens only that app. The guide discloses that this is an unsigned
  private-test workaround and that a public build must be Developer ID signed and notarized.
- Linux: `Muta.sh`, `Muta.AppImage`, `model-pack/`, and `HOW TO INSTALL.txt` stay together.
  `Muta.sh` restores the executable bit and replaces itself with the AppImage process.
- Windows: `Install-Muta.cmd`, `Muta-Setup.exe`, `model-pack/`, and `HOW TO INSTALL.txt` stay
  together. The existing current-user install and model-pack import flow remains unchanged.

## Verification

- Unit-test filenames, helper contents, and executable modes for macOS, Linux, and Windows.
- Rebuild only the outer archives around the already-built application artifacts.
- Verify every generated checksum and inspect each archive's top-level installation files.

This task deliberately does not rebuild application binaries or change their embedded Git SHAs.

Completed with eight focused collector tests, Ruff, `zsh -n`/`sh -n`, archive-member and mode
inspection, Windows CRLF validation, and successful SHA-256 verification of all four refreshed
0.1.0 offline archives.
