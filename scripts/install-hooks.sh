#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "🔧 Configuring Git hooks to use .githooks/ directory..."
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit .githooks/pre-push

echo "✅ Git hooks configured successfully!"
echo "   - pre-commit: Auto-updates and stages README.md specs & validates links"
echo "   - pre-push:   Enforces documentation validity and spec synchronization"
