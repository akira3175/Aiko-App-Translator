import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from "react";
import { markdown } from "@codemirror/lang-markdown";
import { EditorState, StateEffect, StateField } from "@codemirror/state";
import { Decoration, EditorView, keymap, lineNumbers, type DecorationSet } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { openSearchPanel, search, searchKeymap } from "@codemirror/search";

export interface MarkdownEditorHandle {
  focusLine: (line: number) => void;
  openFind: () => void;
  wrapSelection: (marker: "*" | "**") => void;
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  label: string;
  readOnly?: boolean;
  streaming?: boolean;
  activeLine?: number | null;
}

const setActiveStreamLine = StateEffect.define<number | null>();
const activeStreamLineField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(value, transaction) {
    let next = value.map(transaction.changes);
    for (const effect of transaction.effects) {
      if (!effect.is(setActiveStreamLine)) continue;
      if (effect.value === null || !transaction.state.doc.lines) next = Decoration.none;
      else {
        const line = transaction.state.doc.line(Math.min(Math.max(1, effect.value + 1), transaction.state.doc.lines));
        next = Decoration.set([Decoration.line({ class: "ai-stream-line" }).range(line.from)]);
      }
    }
    return next;
  },
  provide: (field) => EditorView.decorations.from(field),
});

function wrapMarker(view: EditorView, marker: "*" | "**") {
  const selection = view.state.selection.main;
  const selected = view.state.sliceDoc(selection.from, selection.to);
  const insert = `${marker}${selected}${marker}`;
  const anchor = selection.from + marker.length;
  view.dispatch({ changes: { from: selection.from, to: selection.to, insert }, selection: selected ? { anchor, head: anchor + selected.length } : { anchor }, scrollIntoView: true });
  view.focus();
}

export const MarkdownEditor = forwardRef<MarkdownEditorHandle, Props>(function MarkdownEditor({ value, onChange, label, readOnly = false, streaming = false, activeLine = null }, ref) {
  const hostRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const selectionRef = useRef<{ start: number; end: number; direction: "forward" | "backward" | "none" } | null>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const historyRef = useRef({ entries: [value], index: 0 });
  const [findOpen, setFindOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [replacement, setReplacement] = useState("");
  const [matchCase, setMatchCase] = useState(false);
  const [wholeWord, setWholeWord] = useState(false);
  const [regexp, setRegexp] = useState(false);
  const [lineHeights, setLineHeights] = useState<number[]>([]);
  const changeRef = useRef(onChange);
  const locked = readOnly || streaming;
  changeRef.current = onChange;

  const commitValue = (next: string) => {
    const historyState = historyRef.current;
    if (historyState.entries[historyState.index] !== next) {
      historyState.entries = [...historyState.entries.slice(0, historyState.index + 1), next].slice(-200);
      historyState.index = historyState.entries.length - 1;
    }
    onChange(next);
  };

  const moveHistory = (textarea: HTMLTextAreaElement, direction: -1 | 1) => {
    const historyState = historyRef.current;
    const nextIndex = Math.min(historyState.entries.length - 1, Math.max(0, historyState.index + direction));
    if (nextIndex === historyState.index) return;
    const scrollTop = textarea.scrollTop;
    historyState.index = nextIndex;
    const next = historyState.entries[nextIndex];
    const cursor = Math.min(textarea.selectionStart, next.length);
    selectionRef.current = { start: cursor, end: cursor, direction: "none" };
    onChange(next);
    requestAnimationFrame(() => {
      textarea.focus({ preventScroll: true });
      textarea.setSelectionRange(cursor, cursor);
      textarea.scrollTop = scrollTop;
    });
  };

  const wrapNativeSelection = (textarea: HTMLTextAreaElement, marker: "*" | "**") => {
    const { selectionStart: from, selectionEnd: to, selectionDirection: direction } = textarea;
    const selected = value.slice(from, to);
    const start = from + marker.length;
    const end = start + selected.length;
    const scrollTop = textarea.scrollTop;
    selectionRef.current = { start, end, direction };
    commitValue(value.slice(0, from) + marker + selected + marker + value.slice(to));
    requestAnimationFrame(() => {
      textarea.focus({ preventScroll: true });
      textarea.setSelectionRange(start, end, direction);
      textarea.scrollTop = scrollTop;
    });
  };

  const matches = () => {
    if (!query) return [] as Array<{ from: number; to: number }>;
    try {
      const source = regexp ? query : query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const expression = new RegExp(source, `g${matchCase ? "" : "i"}u`);
      return [...value.matchAll(expression)].flatMap((match) => {
        const from = match.index ?? 0;
        const to = from + match[0].length;
        if (!match[0].length) return [];
        if (wholeWord) {
          const word = /[\p{L}\p{N}_]/u;
          if (word.test(value[from - 1] || "") || word.test(value[to] || "")) return [];
        }
        return [{ from, to }];
      });
    } catch { return []; }
  };

  const selectMatch = (direction: 1 | -1) => {
    const textarea = textareaRef.current;
    const found = matches();
    if (!textarea || !found.length) return;
    const cursor = direction === 1 ? textarea.selectionEnd : textarea.selectionStart;
    const match = direction === 1
      ? found.find((item) => item.from >= cursor) || found[0]
      : [...found].reverse().find((item) => item.to <= cursor) || found[found.length - 1];
    textarea.focus();
    textarea.setSelectionRange(match.from, match.to);
  };

  const replaceCurrent = () => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const found = matches();
    const current = found.find((item) => item.from === textarea.selectionStart && item.to === textarea.selectionEnd);
    if (!current) return selectMatch(1);
    const next = value.slice(0, current.from) + replacement + value.slice(current.to);
    commitValue(next);
    requestAnimationFrame(() => { textarea.focus(); textarea.setSelectionRange(current.from, current.from + replacement.length); });
  };

  const replaceAll = () => {
    const found = matches();
    if (!found.length) return;
    let next = value;
    for (const match of [...found].reverse()) next = next.slice(0, match.from) + replacement + next.slice(match.to);
    commitValue(next);
  };

  useImperativeHandle(ref, () => ({
    focusLine(lineNumber) {
      const textarea = textareaRef.current;
      if (textarea) {
        const lines = value.split("\n");
        const lineIndex = Math.min(Math.max(1, lineNumber), lines.length) - 1;
        const offset = lines.slice(0, lineIndex).reduce((total, line) => total + line.length + 1, 0) + lines[lineIndex].length;
        textarea.focus({ preventScroll: true });
        textarea.setSelectionRange(offset, offset);
        const lineHeight = lineHeights.slice(0, lineIndex).reduce((total, height) => total + height, 0);
        textarea.scrollTop = Math.max(0, lineHeight - textarea.clientHeight / 2);
        return;
      }
      const view = viewRef.current;
      if (!view) return;
      const line = view.state.doc.line(Math.min(Math.max(1, lineNumber), view.state.doc.lines));
      view.dispatch({ selection: { anchor: line.to }, scrollIntoView: true });
      view.focus();
    },
    openFind() {
      if (!readOnly) {
        setFindOpen(true);
        requestAnimationFrame(() => hostRef.current?.querySelector<HTMLInputElement>(".native-find-input")?.focus());
        return;
      }
      const view = viewRef.current;
      if (view) openSearchPanel(view);
    },
    wrapSelection(marker) {
      const textarea = textareaRef.current;
      if (textarea) {
        wrapNativeSelection(textarea, marker);
        return;
      }
      const view = viewRef.current;
      if (!view || readOnly) return;
      wrapMarker(view, marker);
    },
  }), [lineHeights, onChange, readOnly, value]);

  useEffect(() => {
    if (!locked || !hostRef.current) return;
    const view = new EditorView({
      parent: hostRef.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          lineNumbers(),
          history(),
          markdown(),
          search({ top: true }),
          EditorState.phrases.of({
            Find: "Tìm kiếm",
            Replace: "Thay bằng",
            next: "Tiếp",
            previous: "Trước",
            all: "Tất cả",
            "match case": "Aa",
            regexp: "Regex",
            "by word": "Nguyên từ",
            replace: "Thay",
            "replace all": "Thay tất cả",
            close: "Đóng",
          }),
          keymap.of([
            ...(!readOnly ? [
              { key: "Mod-b", run: (editor: EditorView) => { wrapMarker(editor, "**"); return true; } },
              { key: "Mod-i", run: (editor: EditorView) => { wrapMarker(editor, "*"); return true; } },
            ] : []),
            ...defaultKeymap,
            ...historyKeymap,
            ...searchKeymap,
          ]),
          EditorView.lineWrapping,
          activeStreamLineField,
          EditorState.readOnly.of(true),
          EditorView.editable.of(false),
          EditorView.updateListener.of((update) => {
            if (update.docChanged && !locked) changeRef.current(update.state.doc.toString());
          }),
        ],
      }),
    });
    viewRef.current = view;
    return () => view.destroy();
  }, [locked]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view || view.state.doc.toString() === value) return;
    const current = view.state.doc.toString();
    let prefix = 0;
    while (prefix < current.length && prefix < value.length && current[prefix] === value[prefix]) prefix += 1;
    let suffix = 0;
    while (suffix < current.length - prefix && suffix < value.length - prefix && current[current.length - 1 - suffix] === value[value.length - 1 - suffix]) suffix += 1;
    view.dispatch({ changes: { from: prefix, to: current.length - suffix, insert: value.slice(prefix, value.length - suffix) } });
  }, [value]);

  useEffect(() => {
    if (!streaming || !viewRef.current) return;
    viewRef.current.dispatch({ effects: setActiveStreamLine.of(activeLine) });
    if (activeLine !== null && typeof Range !== "undefined" && typeof Range.prototype.getClientRects === "function") {
      const line = viewRef.current.state.doc.line(Math.min(Math.max(1, activeLine + 1), viewRef.current.state.doc.lines));
      viewRef.current.dispatch({ effects: EditorView.scrollIntoView(line.from, { y: "center" }) });
    }
  }, [activeLine, streaming, value]);

  useLayoutEffect(() => {
    if (locked) return;
    const textarea = textareaRef.current;
    const mirror = mirrorRef.current;
    if (!textarea || !mirror) return;
    const measure = () => {
      mirror.style.width = `${textarea.clientWidth}px`;
      const next = [...mirror.children].map((line) => (line as HTMLElement).getBoundingClientRect().height);
      setLineHeights((current) => current.length === next.length && current.every((height, index) => height === next[index]) ? current : next);
    };
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(textarea);
    return () => observer.disconnect();
  }, [locked, value]);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    const selection = selectionRef.current;
    if (!textarea || !selection || document.activeElement !== textarea) return;
    textarea.setSelectionRange(selection.start, selection.end, selection.direction);
  }, [value]);

  useEffect(() => {
    const historyState = historyRef.current;
    if (historyState.entries[historyState.index] === value) return;
    historyState.entries = [value];
    historyState.index = 0;
  }, [value]);

  if (locked) return <div className={`editor${streaming ? " ai-stream-editor" : ""}`} aria-busy={streaming || undefined} aria-label={label} ref={hostRef} />;
  return <div className="editor native-markdown-editor" aria-label={label} ref={hostRef}>
    {findOpen && <div className="native-find-bar">
      <input className="native-find-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm kiếm" onKeyDown={(event) => { if (event.key === "Enter") selectMatch(event.shiftKey ? -1 : 1); if (event.key === "Escape") setFindOpen(false); }} />
      <button type="button" onClick={() => selectMatch(-1)}>Trước</button><button type="button" onClick={() => selectMatch(1)}>Tiếp</button>
      <label><input type="checkbox" checked={matchCase} onChange={(event) => setMatchCase(event.target.checked)} />Aa</label>
      <label><input type="checkbox" checked={regexp} onChange={(event) => setRegexp(event.target.checked)} />Regex</label>
      <label><input type="checkbox" checked={wholeWord} onChange={(event) => setWholeWord(event.target.checked)} />Nguyên từ</label>
      <button className="native-find-close" type="button" aria-label="Đóng" onClick={() => setFindOpen(false)}>×</button>
      <input className="native-replace-input" value={replacement} onChange={(event) => setReplacement(event.target.value)} placeholder="Thay bằng" onKeyDown={(event) => { if (event.key === "Enter") replaceCurrent(); }} />
      <button type="button" onClick={replaceCurrent}>Thay</button><button type="button" onClick={replaceAll}>Thay tất cả</button>
    </div>}
    <div className="native-editor-body">
      <div className="native-line-gutter" ref={gutterRef} aria-hidden="true">{value.split("\n").map((_line, index) => <span style={{ height: lineHeights[index] }} key={index}>{index + 1}</span>)}</div>
      <div className="native-editor-mirror" ref={mirrorRef} aria-hidden="true">{value.split("\n").map((line, index) => <div className="native-line-measure" key={index}>{line || "\u200b"}</div>)}</div>
      <textarea ref={textareaRef} value={value} onSelect={(event) => { selectionRef.current = { start: event.currentTarget.selectionStart, end: event.currentTarget.selectionEnd, direction: event.currentTarget.selectionDirection }; }} onChange={(event) => { selectionRef.current = { start: event.currentTarget.selectionStart, end: event.currentTarget.selectionEnd, direction: event.currentTarget.selectionDirection }; commitValue(event.target.value); }} onScroll={(event) => { if (gutterRef.current) gutterRef.current.scrollTop = event.currentTarget.scrollTop; }} aria-label={label} spellCheck={false} wrap="soft" onKeyDown={(event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") { event.preventDefault(); moveHistory(event.currentTarget, event.shiftKey ? 1 : -1); return; }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") { event.preventDefault(); moveHistory(event.currentTarget, 1); return; }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") { event.preventDefault(); setFindOpen(true); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "h") { event.preventDefault(); setFindOpen(true); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "b") { event.preventDefault(); wrapNativeSelection(event.currentTarget, "**"); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "i") { event.preventDefault(); wrapNativeSelection(event.currentTarget, "*"); }
      }} />
    </div>
  </div>;
});
