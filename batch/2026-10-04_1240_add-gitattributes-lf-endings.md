# Batch: add-gitattributes-lf-endings

**Date:** 2026-10-04 12:40
**Type:** bugfix
**Command Used:** commands/fix-bug.md
**Standards Referenced:** standards/12-git-standards.md, standards/16-change-management-and-workflow.md
**Requirements:** §18 (deployment)

## Summary
The owner cloned the repository on Windows to run it locally. Git for Windows converts text files to CRLF by default, and the shell scripts that run inside Linux containers fail with CRLF: the PostgreSQL init script (engine role), backup and restore, and the Alertmanager start script. A `.gitattributes` now keeps LF line endings on every operating system.

## Changes Made
- New `.gitattributes`: `* text=auto eol=lf`, `*.sh text eol=lf`, and the binary types (docx, png, ico, onnx) marked as binary.

## Files Changed
```
.gitattributes
```

## Database Changes
None.

## CPU / Performance Impact
N/A.

## Testing
`git add --renormalize .` changed no files, so every committed file is already LF and only checkouts are affected. Not tested on a Windows machine here. The owner's existing Windows clone needs one re-checkout to pick this up (`git rm -r --cached .` then `git reset --hard`).

## Notes
None.
