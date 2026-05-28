# Project Wiki Manager — working agreements

## UX review gate for all screen changes

Any request that **adds or modifies a screen, component, layout, or styling**
(anything under `frontend/src/`) MUST go through the **`ux-reviewer`** subagent
before it is considered done. Workflow:

1. Decide the change and implement it (or draft the plan for non-trivial ones).
2. Invoke the `ux-reviewer` agent (via the Agent tool, `subagent_type: ux-reviewer`)
   to review the proposed plan and/or the resulting diff.
3. Apply the 🔴/🟡 feedback it returns, then proceed. Surface the review summary to
   the user so they can see what was checked.

Backend-only or non-UI changes do not require this gate. Do not skip the review
for "small" UI tweaks — color, copy, spacing, and layout changes are exactly what
the reviewer exists to catch.

The reviewer is read-only and knows this project's design system
(`frontend/src/index.css` tokens, dark theme, Korean UI). Its definition lives in
`.claude/agents/ux-reviewer.md`.
