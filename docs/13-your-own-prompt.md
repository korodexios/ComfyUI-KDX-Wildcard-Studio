# Your own prompt on the node

Sometimes you want one image from a prompt of your own without building a template. The Studio node takes your
text in two ways. In both, wildcards work (`__auto/car_color__`, `{sunny|foggy}`) with a new pick every run, and the
template counter waits, so the Studio carries on where it stopped when you go back.

## 1. Type it into the node

![The user_text box and the use_user_text switch](images/node-user-text.webp)

1. Type your prompt into the node's text box (`user_text`).
2. Turn the **use_user_text** switch on. It then reads **user text**, and the node body shows
   "✍ user text · the template counter waits".
3. Run. Switch it off (it reads **templates**) and the templates are back.

The text is saved with the workflow, so you can keep a favourite prompt in the box and flip the switch when you need it.

## 2. Connect a text node to `user_prompt`

![A text node connected to user_prompt](images/node-user-prompt.webp)

Connect any node that outputs text (for example **Text (Multiline)**, a String node, or the output of another node)
to the `user_prompt` input. While it sends text, that text is the `prompt` output. No switch is needed:

- **Mute** (Ctrl+M) or **bypass** (Ctrl+B) the text node, or leave it empty, and the template prompt comes back.

  ![The text node muted: the Studio prompt is used again](images/node-user-prompt-muted.webp)

- A connected `user_prompt` wins over the `user_text` box.

## Which text is used

The Studio node takes the first of these that has text:

1. **`user_prompt`**, a text wired into this socket (no switch; mute or bypass the source to stop it);
2. **`user_text`** while **use_user_text** is on. The newer ComfyUI frontend also shows a socket on the `user_text`
   box. If you wire a text node there, the wired text is used instead of what is typed in the box, and the switch
   still has to be on;
3. the template from the panel.

**Keep parts › Use on node** follows the same order. It writes into the text node wired to `user_prompt` or to
`user_text`, or into the `user_text` box, and it asks before it replaces text (see [Keep parts](16-keep-parts.md)).

## Your own prompt through the LLM

The **LLM** button on the node is the same switch as the LLM pill in the panel (an `llm=on|off` override still
wins).

- **Off**: your text is the final prompt, KDX-LLM Chat passes it on unchanged.
- **On**: KDX-LLM Chat rewrites your text. Pick the instructions in **`user_system_prompt`** on the node: it
  lists your KDX-LLM system prompts (press **R** after adding one). Your own text belongs to no category, so the
  category system prompts are not used; with `(no system prompt)` none is sent.

Connect `prompt`, `system_prompt` and `llm_enabled` to the Chat as in the
[quick start](01-quick-start.md), and use the Chat's `response` as the final prompt.

## What the outputs say

While your own text is used:

| Output | Value |
|---|---|
| `prompt` | your text with its wildcards expanded |
| `category` | `user` |
| `template` | `user_prompt` (handy in **KDX • Filename** and in the [Gallery](10-gallery.md)) |
| `system_prompt` | the profile picked in `user_system_prompt` while LLM is on, else empty |
| `llm_enabled` | the LLM switch (node, panel or `overrides`), the same as for templates |

The image records the text, the expanded prompt and the seed, so dragging it back onto the canvas repeats the same
prompt (see [Reproducible images](04-reproducible-images.md)). If the text node is gone by then, the node simply runs
the Studio.
