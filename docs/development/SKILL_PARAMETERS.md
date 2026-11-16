# Reviewed, text-only Skill parameters

Piko Skills are local, typed JSON plans. A saved Skill remains **DRAFT** even
after successful executions. Loading a Skill never automatically executes it.

## Authoring a reusable value

In a corrected or reviewed plan, put a token of the form `{{person}}` in the
literal text being entered and in its expected observable text result:

```json
{
  "objective": "Enter a reviewed name",
  "explanation": "Edit an existing field and check its value",
  "actions": [{
    "kind": "ui.set_text",
    "automation_id": "NameInput",
    "text": "{{person}}",
    "keys": [],
    "timeout_seconds": 5,
    "expected": {
      "automation_id": "NameInput",
      "property": "text_equals",
      "value": "{{person}}"
    }
  }]
}
```

Parameter names must use lowercase ASCII letters followed by letters, digits,
or underscores (up to 32 characters). Each Skill has at most 12 parameters.
Each supplied value is at most 1000 characters. The library stores the
**parameter names only**, not previous values.

## Safe replay

1. Open the Skill library and enter literal values into the named fields.
2. Explicitly consent to inspecting the *current foreground application*.
3. Select **Review procedure**. Piko substitutes values in memory only, checks
   the current UIA target and app grant, and shows the concrete plan.
4. Separately approve execution. Piko checks actions against permissions and
   verifies their outcomes by observing the UI again.

An omitted or unexpected parameter is refused; a value cannot change the
application executable, UIA automation ID, action kind, keyboard hotkey, or
permission scope. Substitution is **not recursive**: text that itself contains
`{{another}}` is treated literally. No template can run code or shell commands.

Imported Skill ZIPs are always drafts, never pre-authorized. Revisions record
which parameter names belong to each draft; rollback creates a fresh revision.
Treat outputs as unverified until controlled real-world replay succeeds.
