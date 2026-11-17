// Finding the Markdown files a terminal mentions: paths in its recent text,
// newest (lowest on screen) first, kept only if the file is really there.
// The approach follows jgrecoarroyo/herdr-markdown (MIT).
import { exec } from "herdr";

// A path-like run ending in .md / .markdown / .mdx. Stops at whitespace,
// quotes, brackets and the box-drawing marks agents print around paths.
const TOKEN = /[^\s`'"<>()[\]{}|│⎿●✻*,;]+?\.(?:md|markdown|mdx)(?![\w-])/giu;

function tokens(line) {
  const out = [];
  for (const [match] of line.matchAll(TOKEN)) {
    if (/^[a-z][\w+.-]*:\/\//i.test(match) && !match.startsWith("file://")) continue;
    let path = match.replace(/^file:\/\//, "").replace(/^@/, "");
    try {
      path = decodeURIComponent(path);
    } catch {}
    if (path.length > 1) out.push(path);
  }
  return out;
}

// Candidates, newest first, each once. A path the terminal wrapped is also
// tried as one line's last word joined to the next line's first; a wrong
// join won't exist on disk, so existing() drops it.
export function mentions(text) {
  const lines = text.split("\n");
  const seen = new Set();
  const out = [];
  const add = (paths) => {
    for (const p of paths) {
      if (!seen.has(p)) {
        seen.add(p);
        out.push(p);
      }
    }
  };
  for (let i = lines.length - 1; i >= 0; i--) {
    const tail = lines[i].match(/\S+$/)?.[0];
    const head = lines[i + 1]?.match(/^\s*(\S+)/)?.[1];
    if (tail && head) add(tokens(tail + head));
    add(tokens(lines[i]).reverse());
  }
  return out;
}

// The candidates that are files, as absolute paths, in order. Relative ones
// are from `cwd`; `~/` is home. Runs where the terminal runs (`on`).
export async function existing(candidates, cwd, on) {
  if (!candidates.length) return [];
  const script =
    'cd "$1" 2>/dev/null; shift; for p; do case $p in "~/"*) p="$HOME/${p#??}";; esac; ' +
    '[ -f "$p" ] && printf "%s/%s\\n" "$(cd "$(dirname "$p")" && pwd)" "$(basename "$p")"; done';
  const r = await exec("sh", ["-c", script, "sh", cwd || "/", ...candidates.slice(0, 80)], { on });
  return [...new Set(r.stdout.split("\n").filter(Boolean))];
}
