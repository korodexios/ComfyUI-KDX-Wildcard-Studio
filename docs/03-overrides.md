# Overrides

`overrides` is an optional STRING input. It changes **this run only** and never writes to the config, so a
workflow (or another part of it) can steer the console without touching the panel.

Because it is a plain STRING, it works through Set/Get nodes (for example KJNodes SetNode/GetNode): those are
replaced by a direct link when the prompt is queued.

## Grammar

Items are separated by `,`, `;` or a new line and applied left to right. Each item is `key=value`
(`key:value` works too). Case does not matter. `#` starts a comment.

| Item | Effect |
|---|---|
| `art=off` | switch category `art` off (`on` to switch it on) |
| `portrait.selfie=on` | switch one template; switching a template on also switches its category on |
| `*=off` | all categories |
| `art.*=off` | all templates of a category |
| `select=art.cubism` | fixed template; implies `mode=manual` unless `mode` is given |
| `mode=sequential` / `manual` / `pin` | mode for this run |
| `seed=123` | wildcard seed for this run |
| `llm=on` / `off` | LLM switch for this run |

On/off values: `on off 1 0 true false yes no`.

## Examples

```
*=off, art=on                 only the art category
portrait.selfie=off           skip one template
select=art.cubism, seed=42    one fixed prompt
```

An unknown category or template stops the run with a message that lists the valid names.
