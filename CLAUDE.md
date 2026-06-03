# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project State

This repository is currently empty (no commits, no source files). The project name suggests a trading/financial strategy focused on dry-run, stable, low-risk market entry signals, but no implementation exists yet.

# Git Safety Rules

Never run the following commands unless I explicitly approve them in the current message:

- git reset --hard
- git clean -fd
- git clean -fdx
- git checkout .
- rm -rf
- git restore .
- git restore --source
- git switch --discard-changes

Before making changes:

1. Run git status.
2. Explain which files will be modified.
3. Do not discard, reset, or clean local changes.
4. Never delete untracked files.
5. Never commit automatically unless I explicitly ask.

Any command that discards local changes is forbidden.
If you think reset/clean/restore is needed, stop and ask me first.
