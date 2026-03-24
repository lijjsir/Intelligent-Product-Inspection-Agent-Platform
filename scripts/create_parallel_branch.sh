#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 <branch-name> <base-branch> [worktree-dir]"
  echo "Example: $0 feature/analytics-drilldown develop ../piap-feature-analytics"
  exit 1
fi

branch_name="$1"
base_branch="$2"
worktree_dir="${3:-../$(basename "$(pwd)")-$(echo "$branch_name" | tr '/' '-')}"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "Error: current directory is not a git repository"
  exit 1
}

if git show-ref --verify --quiet "refs/heads/$branch_name"; then
  echo "Error: branch already exists: $branch_name"
  exit 1
fi

if [[ -e "$worktree_dir" ]]; then
  echo "Error: target worktree path already exists: $worktree_dir"
  exit 1
fi

echo "Fetching latest refs..."
git fetch --all --prune

echo "Creating worktree..."
git worktree add "$worktree_dir" -b "$branch_name" "$base_branch"

cat <<EOF

Created:
  branch:   $branch_name
  base:     $base_branch
  worktree: $worktree_dir

Next steps:
  cd $worktree_dir
  git status
EOF
