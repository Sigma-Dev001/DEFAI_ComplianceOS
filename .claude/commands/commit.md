---
description: Stage and commit all changes with conventional message
allowed-tools: Bash(git*)
argument-hint: [message]
---
Run git add -A.
Write a conventional commit message with feat:, fix:, or chore: prefix.
If $ARGUMENTS is provided use it as the message body.
Commit then push to origin dev.
Print the commit hash when done.
