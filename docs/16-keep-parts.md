# Keep parts

You like the pose, the clothes or the place in one image and want more images like it, with a different face or a
different light. **🔒 Keep parts** takes the image's prompt apart into the wildcard picks that made it. You click the
parts you want to keep, and the result is a new template: the kept parts are fixed text and everything else is
still wildcards.

It opens from two places, and both open the same window:

- **Gallery**: open an image, then click **🔒 Keep parts** in the viewer's header.
- **Template builder**: click **🔒 Keep parts** on one of the random samples.

It works for template images and for images made from your own text with wildcards (`user_text` / `user_prompt`).

## The window

**Left: the prompt in parts.** Each pick is underlined with dots. Hover over a part to see which wildcard it came
from. Click a part to keep it (blue) and click it again to let it vary. When parts sit inside each other, a click
keeps the innermost one. The **Keep** row above the prompt lists the parts around your last click, from the whole
value down to the small part, so you can keep the whole value or just one part of it.

**Quick choices** keep a whole group in one click: *Whole person*, *Face & hair*, *Body & age*, *Clothing*,
*Pose & action*, *Camera*, *Environment & light*, *Style & mood*, *Other people*, *Subject*. Only the groups that
this prompt has are shown. The groups follow the pool names (`person/hair` belongs to Face & hair, `core/light_sky`
to Environment & light). **⇄ Invert** keeps what varies now and lets vary what is kept now, so "keep the place,
change the people" takes two clicks. **Clear** lets everything vary again.

**Right: the result.** A few variants made with the current choices update as you click. The kept text is marked,
**⟳ Again** draws new variants, and **Template line** shows the line that will be used.

## Other wildcards in place of a part

Sometimes you want to keep some parts and take others from other pools, for example keep the pose but make the
picture a painting. Click the part, then **⇄ Replace…** in the Keep row. Search the pools of your library and click
one, or type wildcards or words (`{oil|ink} painting`, `__art/style__`) and press **Use as typed**. An empty text
removes the part. The part then shows with a dashed border; **↺ Original** brings it back. The choices around a
replaced part are kept, the same as for a kept part.

**Plain text can be replaced too.** Text that is not a pick (the fixed words of the template line, or a prompt
you made from kept parts before, where the kept parts are plain text now) is split into pieces at `, . ; : ! ?`.
Hover over a piece to see it, click it, then **⇄ Replace…** puts wildcards or other words in its place; the commas
and full stops around it stay. A number like `4:5` or `1.5` stays one piece. Words inside a pick (an option of a
`{…|…}` group) are not split: a click there keeps the pick, as before. This also works for a prompt with no
wildcards at all.

**＋ Add at the end** puts text or wildcards after the prompt (**＋ Pool…** picks a pool). Use it for what the
prompt has no place for yet, such as `in the style of __art/style__`.

**Clear** lets everything vary again and undoes the replacements.

## Choices around a kept part

A template often makes a choice that holds several parts, for example
`{her expression is __person/expression_positive__. The mood is __core/mood__|her expression is __person/expression_negative__. The mood is __core/mood_somber__}`.
When you keep the expression, that whole option is kept too. Without it, the next image could take the other
option, and the kept expression would drop out. The mood is still picked again, from the pool of the kept option
(`core/mood`, not `core/mood_somber`). In the prompt, a dashed outline marks a choice that is kept because a part
inside it is kept.

The same applies to a pool value that has wildcards inside it: keeping its inner part keeps the value it sits in.
The template line that the image's seed picked is kept too.

## Actions

- **Use on node** writes the template where the KDX Wildcard Studio node reads it. From then on, every run picks
  the parts that are not kept again. When the workflow has several Studio nodes, select one first.
  - Without a connection it goes into `user_text` and switches `use_user_text` on.
  - With a text node connected to `user_prompt` or to the `user_text` socket, a small window lets you choose where
    it goes: into that text node (the box's typed value is ignored while its socket is wired) or into the
    `user_text` box. A text on `user_prompt` wins over `user_text` (see [Your own prompt](13-your-own-prompt.md)).
  - When the chosen place already holds other text, the window shows it and the button says **Replace**; nothing
    is overwritten without that click. Afterwards **↶ Restore previous text** (or Ctrl+Z in ComfyUI) puts the old
    text back.
- **Save as template…** writes `templates/<name>.txt`. **Save into** can add the template to a category of the
  panel. An existing file is replaced only after you confirm, and the old one is kept as `.bak`. A template is one
  line; a prompt of several lines can only be used on the node.
- **Open in Builder** loads the line into the [Template builder](11-template-builder.md) as a new, unsaved
  template, ready for further changes. The builder's **Use on node** sends it to the node from there, without
  saving a template.

If you like the images made this way, open one in the [Gallery](10-gallery.md) and use **Save as template…** to keep
its prompt as a template.

## When the prompt does not match

The window runs the image's template and seed again and compares the result with the prompt stored in the image.
When a wildcard file has changed since the image was made, they differ. The window then says so, shows the stored
prompt, and keeps nothing until you click **Use today's picks anyway**, because the parts would come from today's
picks, not the image's.

Older images (before 0.6.9) stored no prompt text. For these, the window says that the parts are today's expansion.
If a wildcard value cuts through another one (an unbalanced brace in a pool, for example), its parts cannot be told
apart reliably, and the window does not keep any of them.

## LLM

With the LLM on, the image's final prompt is the LLM's rewrite. The image still stores the prompt from the Studio,
and Keep parts works on that prompt. Your kept template therefore goes through the LLM again on the next run, as
before.

## NSFW

Images of NSFW templates open only while the panel's **NSFW** switch is on, the same rule as in the Gallery and the
Builder.
