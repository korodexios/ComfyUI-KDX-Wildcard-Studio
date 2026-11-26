// KDX Wildcard Studio - the folder and name of a new pool, as the New pool window builds them (pure, no imports, so it can be
// tested on its own). The server checks the same rules again (kdx_console/pools.py check_key) before writing.

export const NEW_FOLDER = "__new__";
export const FOLDER_RE = /^[a-z0-9][a-z0-9_-]{0,63}(\/[a-z0-9][a-z0-9_-]{0,63})*$/;
export const NAME_RE = /^[a-z0-9][a-z0-9_]{0,63}$/;
const RESERVED = ["templates", "packs"];

/** The folder the window starts with: the one it was opened from when it exists, else none ("choose a folder"). */
export function startFolder(from, folders) {
  return from && folders.includes(from) ? from : "";
}

/**
 * `{choice, typed, name}` -> `{key, token, error}`. `choice` is a folder from the list, NEW_FOLDER (then `typed` is
 * the new folder, e.g. `auto` or `auto/motor`) or "" (nothing chosen yet). `error` says what is missing or wrong.
 */
export function newPoolKey({ choice = "", typed = "", name = "" }) {
  const folder = (choice === NEW_FOLDER ? typed : choice).trim().toLowerCase().replace(/^\/+|\/+$/g, "");
  const n = name.trim().toLowerCase().replace(/\.txt$/, "");
  const key = folder && n ? `${folder}/${n}` : "";
  const out = (error) => ({ key, token: key ? `__${key}__` : "", error });
  if (!choice) return out("Choose a folder.");
  if (!folder) return out("Type the name of the new folder.");
  if (!FOLDER_RE.test(folder)) return out("A folder name uses a-z, 0-9, _ and -; a / makes a subfolder (auto/motor).");
  if (RESERVED.includes(folder.split("/")[0])) return out(`${folder.split("/")[0]}/ is reserved: pick another folder.`);
  if (!n) return out("Give the pool a name.");
  if (!NAME_RE.test(n)) return out("A pool name uses a-z, 0-9 and _ (e.g. light_window).");
  return out("");
}
