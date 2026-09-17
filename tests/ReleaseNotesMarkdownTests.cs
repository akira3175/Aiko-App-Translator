using System;
using System.Linq;
using System.Windows;
using System.Windows.Documents;
using AikoLauncher;

internal static class ReleaseNotesMarkdownTests
{
    private static void Check(bool value, string label) { if (!value) throw new Exception(label); Console.WriteLine("PASS " + label); }
    [STAThread] public static int Main()
    {
        var doc = ReleaseNotesMarkdown.Render("## Có gì mới?\n\n- Cải thiện **ChatGPT Work**.\n- Thêm **icon thường** và *icon anime*.\n");
        var blocks = doc.Blocks.Cast<Paragraph>().ToArray();
        Check(blocks.Length == 3 && blocks[0].FontWeight == FontWeights.SemiBold, "heading and list blocks");
        Check(blocks[1].Inlines.OfType<Bold>().Any() && blocks[2].Inlines.OfType<Italic>().Any(), "bold and italic formatting");
        string text = new TextRange(doc.ContentStart, doc.ContentEnd).Text;
        Check(!text.Contains("##") && !text.Contains("**") && text.Contains("ChatGPT Work"), "Markdown markers removed while Vietnamese is preserved");
        var links = ReleaseNotesMarkdown.Render("[GitHub](https://github.com) [unsafe](file:///C:/test.exe)");
        Check(((Paragraph)links.Blocks.FirstBlock).Inlines.OfType<Hyperlink>().Count() == 1, "only web links are clickable");
        var code = ReleaseNotesMarkdown.Render("```\n**literal code**\n```");
        Check(new TextRange(code.ContentStart, code.ContentEnd).Text.Contains("**literal code**"), "fenced code remains literal");
        Check(ReleaseNotesMarkdown.Render(null).Blocks.Count == 0, "empty release notes");
        return 0;
    }
}
