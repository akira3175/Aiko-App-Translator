// @vitest-environment jsdom
import { fireEvent, render } from "@testing-library/react";
import { createRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { MarkdownEditor } from "./MarkdownEditor";
import type { MarkdownEditorHandle } from "./MarkdownEditor";

describe("MarkdownEditor", () => {
  it("allows editing the translated text", () => {
    const { container } = render(<MarkdownEditor label="Bản dịch" value="Nội dung" onChange={vi.fn()} />);
    expect(container.querySelector("textarea")?.readOnly).toBe(false);
  });

  it("keeps the source editor read-only", () => {
    const { container } = render(<MarkdownEditor readOnly label="Bản gốc" value="Nguyên văn" onChange={vi.fn()} />);
    expect(container.querySelector(".cm-content")?.getAttribute("contenteditable")).toBe("false");
  });

  it("reports text typed into the translated editor", () => {
    const onChange = vi.fn();
    const { container } = render(<MarkdownEditor label="Bản dịch" value="Nội dung" onChange={onChange} />);
    fireEvent.change(container.querySelector("textarea")!, { target: { value: "Nội dung đã sửa" } });
    expect(onChange).toHaveBeenCalledWith("Nội dung đã sửa");
  });

  it("wraps the current selection without moving it to the document end", () => {
    const onChange = vi.fn();
    const ref = createRef<MarkdownEditorHandle>();
    const { container } = render(<MarkdownEditor ref={ref} label="Bản dịch" value="Đầu Nội dung Cuối" onChange={onChange} />);
    const textarea = container.querySelector("textarea")!;
    textarea.focus();
    textarea.setSelectionRange(4, 12);
    ref.current?.wrapSelection("*");
    expect(onChange).toHaveBeenCalledWith("Đầu *Nội dung* Cuối");
  });

  it("focuses the requested line with the cursor at its end", () => {
    const ref = createRef<MarkdownEditorHandle>();
    const { container } = render(<MarkdownEditor ref={ref} label="Bản dịch" value={"Dòng một\nDòng hai\nDòng ba"} onChange={vi.fn()} />);
    const textarea = container.querySelector("textarea")!;
    ref.current?.focusLine(2);
    expect(document.activeElement).toBe(textarea);
    expect(textarea.selectionStart).toBe("Dòng một\nDòng hai".length);
    expect(textarea.selectionEnd).toBe("Dòng một\nDòng hai".length);
  });

  it("supports undo and redo in the controlled textarea", () => {
    function EditorHarness() {
      const [value, setValue] = useState("Một");
      return <MarkdownEditor label="Bản dịch" value={value} onChange={setValue} />;
    }
    const { container } = render(<EditorHarness />);
    const textarea = container.querySelector("textarea")!;
    fireEvent.change(textarea, { target: { value: "Một hai" } });
    fireEvent.keyDown(textarea, { key: "z", ctrlKey: true });
    expect(textarea.value).toBe("Một");
    fireEvent.keyDown(textarea, { key: "y", ctrlKey: true });
    expect(textarea.value).toBe("Một hai");
  });

  it("locks the editor and highlights the active streaming line", () => {
    const onChange = vi.fn();
    const { container, rerender } = render(<MarkdownEditor streaming activeLine={0} label="Bản dịch" value="Dòng một" onChange={onChange} />);
    expect(container.querySelector(".cm-content")?.getAttribute("contenteditable")).toBe("false");
    expect(container.querySelector(".ai-stream-line")?.textContent).toBe("Dòng một");
    rerender(<MarkdownEditor streaming activeLine={1} label="Bản dịch" value={'Dòng một\nDòng hai'} onChange={onChange} />);
    expect(container.querySelector(".ai-stream-line")?.textContent).toBe("Dòng hai");
    expect(onChange).not.toHaveBeenCalled();
  });
});
