<!--
Thanks for the PR! A few asks to keep review fast:

- One logical change per PR. If you've bundled multiple fixes, split them.
- For UI changes, attach a before/after screenshot.
- For prompt/AI changes, paste an example of the model's output on a real
  log so a reviewer can sanity-check tone + structure.
-->

## What & why
<!--
Short paragraph describing what changes and why. Reference the issue if
there is one (e.g. "Closes #42").
-->

## How
<!--
Notable implementation choices, anything reviewers should pay extra
attention to, and any trade-offs you considered.
-->

## Test plan
- [ ] AST / type-check passes locally
- [ ] Manually exercised the affected flow (paste steps if non-obvious)
- [ ] CI green
<!--
For migrations / data-shape changes: re-import a real WCL report locally
and confirm the new fields land.
For UI changes: screenshots / short clip.
For prompt changes: a real AI output sample.
-->

## Notes for the reviewer
<!--
Anything else that doesn't fit above. Edge cases you punted on, follow-ups
you've already planned, etc.
-->
