---
name: buildskill
description: Scaffolds a new slash-command skill named NAME so it can be added to this agent. Use when the user runs /buildskill NAME.
---

# Buildskill

## Steps

1. Confirm the intended behavior of the new skill if it isn't already
   clear from context: what `/NAME` should do, and what argument(s) (if
   any) it takes.
2. Create `.claude/skills/NAME/SKILL.md` with YAML frontmatter (`name`,
   `description`) and a body following this project's established
   pattern: a `## Steps` section and, where relevant, an `## Output` or
   `## Notes` section restating this agent's core objective —
   informational market context, not investment advice.
3. Keep the `description` to one line, phrased so it reads naturally in
   the `/skills` listing.
4. Commit the new file so the skill becomes available to the agent.
