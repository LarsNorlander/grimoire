// md: Markdown files rendered in a Herdr tab or pane.
//
// One mod, two roles:
// - With props {file, on?}: a viewer. Renders the file, reloads it when it
//   changes, toggles Source/Preview, follows links to other Markdown files
//   in place (Back returns) and sends web links to the browser.
// - With no file (mod.open:md): a picker of the Markdown files mentioned in
//   the focused terminal's recent output. Enter opens a tab, cmd-Enter a
//   split beside the terminal. Typing filters, or names a path.
import { View, div } from "gpui-kit";
import { v_flex, h_flex, InputState, Input, Editor, EditorState, TextView } from "gpui-base";
import {
  focused,
  panes,
  hc,
  exec,
  run,
  theme,
  settings,
  props,
  closeOverlay,
  home,
  readTextFile,
  watchFolder,
  nextCommand,
} from "herdr";
import { mentions, existing } from "./paths.js";

const MOD = "md";
const base = (p) => p.slice(p.lastIndexOf("/") + 1);
const dir = (p) => p.slice(0, p.lastIndexOf("/")) || "/";
const pretty = (p) => {
  const h = home();
  return p === h || p.startsWith(h + "/") ? "~" + p.slice(h.length) : p;
};
const isMarkdown = (p) => /\.(md|markdown|mdx)$/i.test(p);
// Front matter is metadata, not part of what a reader sees.
const body = (text) => text.replace(/^---\n[\s\S]*?\n---\n/, "");

export default class Md extends View {
  init(_props, cx) {
    const p = props() ?? {};
    this.role = p.file ? new Viewer(p.file, p.on ?? null, cx) : new Picker(p.overlay, cx);
  }

  render(cx) {
    return this.role.render(cx);
  }
}

// A new tab named after the file, or a split beside `pane`.
function open(file, on, split, pane) {
  const p = on ? { file, on } : { file };
  if (split && pane) run("pane.split", { direction: "right", pane, mod: MOD, props: p });
  else run("tab.new", { mod: MOD, props: p, name: base(file) });
}

class Picker {
  constructor(overlay, cx) {
    const f = focused();
    this.overlay = overlay;
    this.pane = f?.pane ?? null;
    this.terminal = f?.terminal ?? null;
    // Relative paths are from the pane's live folder, where the agent works.
    this.cwd = (f?.pane && panes().find((p) => p.pane === f.pane)?.cwd) || f?.cwd || null;
    this.on = this.terminal?.includes("/") ? this.terminal.split("/")[0] : null;
    this.files = null;
    this.at = 0;
    this.filter = "";
    this.error = null;
    this.input = InputState.new({ placeholder: "Filter, or type a path…" });
    this.input.on("change", (_e, cx) => {
      this.filter = this.input.value();
      this.at = 0;
      cx.notify();
    });
    this.input.on("submit", (e, cx) => this.choose(this.shown()[this.at], Boolean(e?.secondary), cx));
    this.input.focus();
    cx.spawn(async (cx) => {
      try {
        if (!this.terminal) throw new Error("No terminal has focus.");
        const r = await hc(["read", this.terminal, "--json", "--lines", "400"]);
        if (r.code !== 0) throw new Error((r.stderr || "Can't read the terminal.").trim());
        this.files = await existing(mentions(JSON.parse(r.stdout).text ?? ""), this.cwd, this.on);
        if (this.files.length === 1) return this.choose(this.files[0], false, cx);
      } catch (e) {
        this.error = String(e?.message ?? e);
        this.files = [];
      }
      cx.notify();
    });
  }

  shown() {
    const q = this.filter.trim().toLowerCase();
    return (this.files ?? []).filter((f) => !q || pretty(f).toLowerCase().includes(q));
  }

  choose(file, split, cx) {
    const typed = this.filter.trim();
    if (!file && typed) {
      cx.spawn(async (cx) => {
        const [found] = await existing([typed], this.cwd, this.on).catch(() => []);
        if (found) {
          open(found, this.on, split, this.pane);
          closeOverlay(this.overlay);
        } else {
          this.error = `No file at ${typed}`;
          cx.notify();
        }
      });
      return;
    }
    if (!file) return;
    open(file, this.on, split, this.pane);
    closeOverlay(this.overlay);
  }

  render(_cx) {
    const t = theme();
    const list = this.shown();
    if (this.at >= list.length) this.at = Math.max(0, list.length - 1);
    const row = (f, i) =>
      h_flex()
        .id(`md-row-${i}`)
        .h(44)
        .px(12)
        .gap(10)
        .flex_none()
        .items_center()
        .rounded(7)
        .cursor_pointer()
        .bg(i === this.at ? t.selected : t.popover)
        .hover((s) => s.bg(i === this.at ? t.selected : t.hover))
        .on_click((e, cx) => this.choose(f, Boolean(e?.modifiers?.platform), cx))
        .child(
          v_flex()
            .flex_1()
            .min_w(0)
            .child(div().text_size(13).font_semibold().truncate().child(base(f)))
            .child(div().text_size(11).text_color(t.dim).truncate().child(pretty(dir(f)))),
        );
    const note =
      this.error ??
      (this.files === null
        ? "Reading the terminal…"
        : !this.files.length
          ? "No Markdown files in this terminal's recent output. Type a path."
          : !list.length
            ? "No match. Enter tries it as a path."
            : null);
    return v_flex()
      .id("md-picker")
      .size_full()
      .bg(t.popover)
      .text_color(t.foreground)
      .text_size(13)
      .on_key_down((e, cx) => {
        const n = list.length;
        if (e.key === "escape") {
          closeOverlay(this.overlay);
          return;
        }
        if (e.key === "down" && n) this.at = (this.at + 1) % n;
        else if (e.key === "up" && n) this.at = (this.at + n - 1) % n;
        else return;
        cx.stop_propagation();
        cx.notify();
      })
      .child(
        h_flex()
          .h(46)
          .flex_none()
          .px(14)
          .items_center()
          .border_b(1)
          .border_color(t.border)
          .child(Input.new(this.input).w_full().text_size(14).text_color(t.foreground)),
      )
      .child(
        v_flex()
          .id("md-list")
          // A popup sizes to its content, so the list needs its own height.
          .h(330)
          .flex_none()
          .overflow_y_scrollbar()
          .p(6)
          .gap(1)
          .children(list.map(row))
          .when(Boolean(note), (e) =>
            e.child(
              div()
                .px(12)
                .py(16)
                .text_size(12)
                .text_color(this.error ? t.ansi1 : t.dim)
                .child(note),
            ),
          ),
      )
      .child(
        h_flex()
          .h(30)
          .flex_none()
          .px(14)
          .gap(14)
          .items_center()
          .border_t(1)
          .border_color(t.border)
          .text_size(11)
          .text_color(t.dim)
          .child("↵ new tab")
          .child("⌘↵ split beside")
          .child("↑↓ choose")
          .child("esc close"),
      );
  }
}

class Viewer {
  constructor(file, on, cx) {
    this.file = file;
    this.on = on;
    this.history = [];
    this.text = null;
    this.error = null;
    this.editor = null;
    this.gen = 0;
    this.source = false;
    try {
      this.source = localStorage.getItem("source") === "1";
    } catch {}
    this.load(cx);
    // A local file is also watched; this is the backstop. A remote file
    // can't be watched, so it is polled.
    cx.timer.every(on ? 3000 : 15000, (cx) => this.reload(cx));
    this.listen(cx);
  }

  // Commands for keys.json (`"mod:md": {"cmd-e": "md.source"}`) or
  // `herdr-app do md.source`. They reach shown copies only.
  listen(cx) {
    cx.spawn(async (cx) => {
      for (;;) {
        const command = await nextCommand();
        if (command === "source") this.toggleSource(cx);
        else if (command === "back") this.back(cx);
      }
    });
  }

  load(cx) {
    const gen = ++this.gen;
    this.text = null;
    this.error = null;
    this.editor?.release();
    this.editor = null;
    cx.spawn(async (cx) => {
      try {
        const text = await readTextFile(this.file, { on: this.on });
        if (gen !== this.gen) return;
        if (text === null) this.error = "This file isn't there (anymore).";
        else this.set(text);
      } catch (e) {
        if (gen === this.gen) this.error = String(e?.message ?? e);
      }
      cx.notify();
      if (!this.on && gen === this.gen) this.watch(gen, cx);
    });
  }

  set(text) {
    this.text = text;
    // An editor can't be created while drawing, so Source's is made here.
    if (this.editor) this.editor.set_value(text);
    else if (this.source) this.editor = this.makeEditor(text);
  }

  reload(cx) {
    const gen = this.gen;
    cx.spawn(async (cx) => {
      const text = await readTextFile(this.file, { on: this.on }).catch(() => undefined);
      if (gen !== this.gen || text === undefined || text === this.text) return;
      if (text === null) this.error = "This file isn't there (anymore).";
      else {
        this.error = null;
        this.set(text);
      }
      cx.notify();
    });
  }

  watch(gen, cx) {
    const folder = dir(this.file);
    cx.spawn(async (cx) => {
      while (gen === this.gen) {
        try {
          await watchFolder(folder);
        } catch {
          return;
        }
        if (gen === this.gen) this.reload(cx);
      }
    });
  }

  makeEditor(value) {
    const t = theme();
    return EditorState.new({
      language: "markdown",
      value,
      readonly: true,
      soft_wrap: true,
      folding: false,
      font_family: settings().font_family,
      font_size: 13,
      syntax: {
        keyword: t.ansi5,
        string: t.ansi2,
        comment: t.dim,
        function: t.ansi4,
        type: t.ansi3,
        number: t.ansi1,
        constant: t.ansi6,
        punctuation: t.muted,
      },
    });
  }

  toggleSource(cx) {
    this.source = !this.source;
    if (this.source && !this.editor && this.text !== null) this.editor = this.makeEditor(this.text);
    try {
      localStorage.setItem("source", this.source ? "1" : "0");
    } catch {}
    cx.notify();
  }

  // Another Markdown file opens here (Back returns); web links go to the
  // browser. Any other local file is only revealed in Finder, never opened:
  // a link could point at something that runs.
  link(url, cx) {
    if (/^(https?|mailto):/i.test(url)) {
      exec("open", [url]).catch(() => null);
      return;
    }
    if (/^[a-z][\w+.-]*:/i.test(url) && !url.startsWith("file:")) return;
    let path = url.replace(/^file:\/\//, "").split("#")[0];
    try {
      path = decodeURIComponent(path);
    } catch {}
    if (!path) return;
    if (path.startsWith("~/")) path = home() + path.slice(1);
    else if (!path.startsWith("/")) path = `${dir(this.file)}/${path}`;
    const parts = [];
    for (const part of path.split("/")) {
      if (part === "..") parts.pop();
      else if (part && part !== ".") parts.push(part);
    }
    path = "/" + parts.join("/");
    if (isMarkdown(path)) {
      this.history.push(this.file);
      this.file = path;
      this.load(cx);
      cx.notify();
    } else if (!this.on) exec("open", ["-R", path]).catch(() => null);
  }

  back(cx) {
    const prev = this.history.pop();
    if (!prev) return;
    this.file = prev;
    this.load(cx);
    cx.notify();
  }

  render(_cx) {
    const t = theme();
    const button = (id, label, action) =>
      h_flex()
        .id(id)
        .h(26)
        .px(8)
        .flex_none()
        .items_center()
        .rounded(6)
        .text_size(12)
        .text_color(t.muted)
        .cursor_pointer()
        .hover((s) => s.bg(t.hover).text_color(t.foreground))
        .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
        .on_click((_e, cx) => action(cx))
        .child(label);
    const content = this.error
      ? div().p(20).text_color(t.ansi1).child(this.error)
      : this.text === null
        ? div().p(20).text_color(t.dim).child("Loading…")
        : this.source
          ? div()
              .flex_1()
              .min_h(0)
              .p(6)
              .when(Boolean(this.editor), (e) => e.child(Editor.new(this.editor).size_full()))
          : div()
              .id("md-scroll")
              .flex_1()
              .min_h(0)
              .overflow_y_scrollbar()
              .child(
                h_flex()
                  .w_full()
                  .justify_center()
                  .child(
                    v_flex()
                      .flex_1()
                      .min_w(0)
                      .max_w(860)
                      .px(28)
                      .py(24)
                      .text_size(14)
                      .child(
                        this.text.trim()
                          ? TextView.markdown(`md-${this.gen}`, body(this.text))
                              .selectable(true)
                              .on_link_click((url, cx) => this.link(url, cx))
                          : div().text_color(t.dim).child("This file is empty."),
                      ),
                  ),
              );
    return v_flex()
      .id("md-viewer")
      .size_full()
      .min_h(0)
      .bg(t.background)
      .text_color(t.foreground)
      .child(
        h_flex()
          .h(40)
          .flex_none()
          .px(10)
          .gap(6)
          .items_center()
          .border_b(1)
          .border_color(t.border)
          .when(this.history.length > 0, (e) => e.child(button("md-back", "← Back", (cx) => this.back(cx))))
          .child(div().flex_none().text_size(13).font_semibold().child(base(this.file)))
          .child(
            div()
              .flex_1()
              .min_w(0)
              .truncate()
              .text_size(11)
              .text_color(t.dim)
              .child((this.on ? `${this.on}:` : "") + pretty(dir(this.file))),
          )
          .child(button("md-mode", this.source ? "Preview" : "Source", (cx) => this.toggleSource(cx)))
          .when(!this.on, (e) =>
            e.child(button("md-reveal", "Reveal", () => exec("open", ["-R", this.file]).catch(() => null))),
          ),
      )
      .child(content);
  }
}
