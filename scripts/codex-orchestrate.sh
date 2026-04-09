#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly REPO_ROOT
readonly STATE_DIR="${REPO_ROOT}/.codex"
readonly PLAN_FILE="${STATE_DIR}/plan.txt"
readonly REVIEW_FILE="${STATE_DIR}/review.txt"
readonly STATUS_FILE="${STATE_DIR}/status.txt"
readonly WORKTREE_DIR="${STATE_DIR}/worktree"
readonly NO_CASE_EXIT=20
readonly REVIEW_LIMIT_EXIT=10
readonly HARD_ERROR_EXIT=30

init_state() {
	mkdir -p "${STATE_DIR}"
	: >"${PLAN_FILE}"
	: >"${REVIEW_FILE}"
}

write_status() {
	printf '%s\n' "$1" >"${STATUS_FILE}"
}

ensure_clean_main_worktree() {
	if ! git -C "${REPO_ROOT}" diff --quiet || ! git -C "${REPO_ROOT}" diff --cached --quiet; then
		echo "codex-orchestrate requires a clean main worktree" >&2
		return "${HARD_ERROR_EXIT}"
	fi

	if [[ -n "$(git -C "${REPO_ROOT}" ls-files --others --exclude-standard)" ]]; then
		echo "codex-orchestrate requires a clean main worktree" >&2
		return "${HARD_ERROR_EXIT}"
	fi
}

codex_exec_to_file() {
	local sandbox="$1"
	local workdir="$2"
	local outfile="$3"
	local prompt="$4"

	printf '%s\n' "${prompt}" |
		codex -a never exec \
			--sandbox "${sandbox}" \
			--cd "${workdir}" \
			--output-last-message "${outfile}" \
			-
}

codex_exec() {
	local sandbox="$1"
	local workdir="$2"
	local prompt="$3"
	shift 3

	printf '%s\n' "${prompt}" |
		codex -a never exec \
			--sandbox "${sandbox}" \
			--cd "${workdir}" \
			"$@" \
			-
}

planner_prompt() {
	cat <<'EOF'
You are the planner for this repository.

Inspect the repository and choose exactly one deterministic candidate from tests/cases that still needs implementation work in the generator. Prefer the earliest case name in lexical order among plausible unsupported or failing cases. Do not edit any files.

Write one of the following outputs:

1. If no suitable case exists, output exactly:
NO_CASE

2. Otherwise, output a decision-complete implementation plan in plain text with this exact first line:
CASE: <case_name>

Then include short sections:
- Why
- Implementation
- Verification

The plan must be sufficient for an implementer to act without making decisions. Refer to concrete repo paths when needed. Keep it concise.
EOF
}

implementer_prompt() {
	local plan_text="$1"
	local review_text="$2"

	cat <<EOF
You are the implementer for this repository.

Follow the plan below exactly. Make the required code changes in this worktree, run focused verification, and stop without creating a git commit.

Plan:
${plan_text}

Current review feedback:
${review_text}

Requirements:
- Work only in this git worktree.
- Make the smallest practical change that satisfies the plan.
- Run focused verification relevant to the change and fix issues you find.
- Do not ask for additional review in your final message; just finish the implementation pass.
EOF
}

reviewer_prompt() {
	local plan_text="$1"

	cat <<EOF
Review the current uncommitted changes in /review style against this plan:

${plan_text}

Focus on bugs, regressions, missing tests, and mismatches with the plan.

Output contract:
- If there are no findings, output exactly NO_FINDINGS
- Otherwise output only the review findings, with the most important issues first
EOF
}

parse_case_name() {
	awk -F': ' 'NR == 1 && $1 == "CASE" { print $2 }' "${PLAN_FILE}"
}

create_worktree() {
	local branch_name="$1"

	rm -rf "${WORKTREE_DIR}"
	git -C "${REPO_ROOT}" worktree add --detach "${WORKTREE_DIR}" HEAD >/dev/null
	git -C "${WORKTREE_DIR}" switch -c "${branch_name}" >/dev/null
}

remove_worktree() {
	if [[ -d "${WORKTREE_DIR}" ]]; then
		git -C "${REPO_ROOT}" worktree remove --force "${WORKTREE_DIR}" >/dev/null || true
	fi
}

delete_branch_if_exists() {
	local branch_name="$1"

	if git -C "${REPO_ROOT}" show-ref --verify --quiet "refs/heads/${branch_name}"; then
		git -C "${REPO_ROOT}" branch -D "${branch_name}" >/dev/null || true
	fi
}

keep_failed_worktree() {
	local branch_name="$1"

	write_status "failed review_limit ${branch_name} ${WORKTREE_DIR}"
	trap - INT TERM
}

run_reviewer() {
	local plan_text="$1"

	write_status "reviewing"
	codex_exec_to_file \
		"read-only" \
		"${WORKTREE_DIR}" \
		"${REVIEW_FILE}" \
		"$(reviewer_prompt "${plan_text}")"
}

run_implementer() {
	local plan_text review_text branch_name case_name round commit_sha

	if [[ ! -s "${PLAN_FILE}" ]]; then
		echo "missing plan: ${PLAN_FILE}" >&2
		return "${HARD_ERROR_EXIT}"
	fi

	plan_text="$(cat "${PLAN_FILE}")"
	case_name="$(parse_case_name)"
	if [[ -z "${case_name}" ]]; then
		echo "planner output is missing CASE header" >&2
		return "${HARD_ERROR_EXIT}"
	fi

	branch_name="codex-orchestrate-${case_name//\//-}-$(date +%s)"
	create_worktree "${branch_name}"
	trap 'remove_worktree; delete_branch_if_exists "${branch_name}"' INT TERM

	review_text="Initial pass. No prior review findings."
	for round in 1 2 3 4 5; do
		write_status "implementing"
		codex_exec \
			"workspace-write" \
			"${WORKTREE_DIR}" \
			"$(implementer_prompt "${plan_text}" "Review round ${round}.\n${review_text}")" \
			--add-dir "${STATE_DIR}" >/dev/null

		run_reviewer "${plan_text}"
		if grep -qx 'NO_FINDINGS' "${REVIEW_FILE}"; then
			git -C "${WORKTREE_DIR}" add -A
			if git -C "${WORKTREE_DIR}" diff --cached --quiet; then
				write_status "failed no_changes ${branch_name} ${WORKTREE_DIR}"
				trap - INT TERM
				return "${HARD_ERROR_EXIT}"
			fi
			git -C "${WORKTREE_DIR}" commit -m "Implement ${case_name}" >/dev/null
			commit_sha="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
			write_status "done ${commit_sha} ${branch_name}"
			remove_worktree
			trap - INT TERM
			return 0
		fi

		review_text="$(cat "${REVIEW_FILE}")"
	done

	keep_failed_worktree "${branch_name}"
	return "${REVIEW_LIMIT_EXIT}"
}

planner() {
	local case_name implementer_status commit_sha branch_name

	init_state
	ensure_clean_main_worktree
	write_status "planning"
	codex_exec_to_file \
		"read-only" \
		"${REPO_ROOT}" \
		"${PLAN_FILE}" \
		"$(planner_prompt)"

	if grep -qx 'NO_CASE' "${PLAN_FILE}"; then
		write_status "no_case"
		return "${NO_CASE_EXIT}"
	fi

	case_name="$(parse_case_name)"
	if [[ -z "${case_name}" ]]; then
		echo "planner did not return a CASE header" >&2
		write_status "failed planner_output"
		return "${HARD_ERROR_EXIT}"
	fi

	if ! run_implementer; then
		return $?
	fi

	implementer_status="$(cat "${STATUS_FILE}")"
	commit_sha="$(awk '{print $2}' <<<"${implementer_status}")"
	branch_name="$(awk '{print $3}' <<<"${implementer_status}")"
	if [[ -z "${commit_sha}" || -z "${branch_name}" ]]; then
		echo "implementer did not report a commit sha and branch" >&2
		write_status "failed implementer_output"
		return "${HARD_ERROR_EXIT}"
	fi

	git -C "${REPO_ROOT}" cherry-pick "${commit_sha}" >/dev/null
	delete_branch_if_exists "${branch_name}"
	write_status "integrated ${case_name} ${commit_sha}"
}

run() {
	local rc

	if planner; then
		return 0
	fi

	rc=$?
	if [[ "${rc}" -eq "${NO_CASE_EXIT}" ]]; then
		return 0
	fi

	return "${rc}"
}

usage() {
	cat <<'EOF'
Usage: scripts/codex-orchestrate.sh <run|planner|implementer|reviewer>
EOF
}

reviewer() {
	if [[ ! -s "${PLAN_FILE}" ]]; then
		echo "missing plan: ${PLAN_FILE}" >&2
		return "${HARD_ERROR_EXIT}"
	fi

	run_reviewer "$(cat "${PLAN_FILE}")"
}

main() {
	local command="${1:-}"

	case "${command}" in
	run)
		run
		;;
	planner)
		planner
		;;
	implementer)
		run_implementer
		;;
	reviewer)
		reviewer
		;;
	*)
		usage >&2
		exit 1
		;;
	esac
}

main "$@"
