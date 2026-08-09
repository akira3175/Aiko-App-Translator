// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MarkdownPreview, markdownToClipboardHtml, markdownToPlainText } from "./MarkdownPreview";

describe("MarkdownPreview editing bridge", () => {
  it("renders bold and italic markers", () => {
    render(<MarkdownPreview value="Đây là **in đậm** và *in nghiêng*." assets={[]} label="Preview" />);
    expect(screen.getByText("in đậm").tagName).toBe("STRONG");
    expect(screen.getByText("in nghiêng").tagName).toBe("EM");
  });

  it("renders triple markers as bold and italic", () => {
    const { container } = render(<MarkdownPreview value="***vừa đậm vừa nghiêng***" assets={[]} label="Preview" />);
    expect(container.querySelector("strong > em")?.textContent).toBe("vừa đậm vừa nghiêng");
  });

  it("treats a spaced italic line as italic instead of a bullet", () => {
    const { container } = render(<MarkdownPreview value="* dòng in nghiêng *" assets={[]} label="Preview" />);
    expect(container.querySelector("em")?.textContent).toBe(" dòng in nghiêng ");
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("copies rendered text without markdown markers", () => {
    expect(markdownToPlainText("# Tiêu đề\n\nĐây là **đậm** và *nghiêng*."))
      .toBe("Tiêu đề\n\nĐây là đậm và nghiêng.");
  });

  it("builds formatted clipboard HTML", () => {
    expect(markdownToClipboardHtml("Đây là **đậm**, *nghiêng* và ***cả hai***."))
      .toBe("<p>Đây là <strong>đậm</strong>, <em>nghiêng</em> và <strong><em>cả hai</em></strong>.</p>");
  });

  it("returns the source line when a preview block is double-clicked", () => {
    const onEditLine = vi.fn();
    render(<MarkdownPreview value={"# Tiêu đề\n\nĐoạn thứ hai\nliên tục."} assets={[]} label="Preview" onEditLine={onEditLine} />);
    fireEvent.doubleClick(screen.getByText(/Đoạn thứ hai/));
    expect(onEditLine).toHaveBeenCalledWith(3);
  });

  it("keeps headings separate from adjacent character profile lists", () => {
    render(<MarkdownPreview value={"## Allister\n### Thông tin cơ bản\n- **Tên gốc**: 알리스터\n- **Giới tính**: Nam\n\n---"} assets={[]} label="Preview" />);
    expect(screen.getByRole("heading", { name: "Allister", level: 2 })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Thông tin cơ bản", level: 3 })).toBeTruthy();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("separator")).toBeTruthy();
  });
});
