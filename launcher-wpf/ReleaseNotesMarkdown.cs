using System;
using System.Diagnostics;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Documents;
using System.Windows.Media;

namespace AikoLauncher
{
    // Render release-note Markdown as native WPF text; never interpret HTML or XAML.
    internal static class ReleaseNotesMarkdown
    {
        private static readonly Regex InlineTokens = new Regex(@"(`[^`\n]+`|\*\*.+?\*\*|__.+?__|~~.+?~~|\[[^\]\n]+\]\([^\s)]+\)|\*[^*\n]+\*|_[^_\n]+_)");

        internal static FlowDocument Render(string markdown)
        {
            var document = new FlowDocument { PagePadding = new Thickness(0), FontFamily = new FontFamily("Segoe UI"), FontSize = 13, TextAlignment = TextAlignment.Left,
                Foreground = new SolidColorBrush(Color.FromRgb(230, 237, 245)), Background = Brushes.Transparent };
            var paragraph = new StringBuilder(); var code = new StringBuilder(); bool fenced = false;
            Action flush = () => { if (paragraph.Length > 0) { document.Blocks.Add(Paragraph(paragraph.ToString())); paragraph.Clear(); } };
            foreach (string raw in (markdown ?? "").Replace("\r\n", "\n").Replace('\r', '\n').Split('\n'))
            {
                string line = raw.TrimEnd();
                if (line.TrimStart().StartsWith("```"))
                {
                    flush();
                    if (fenced) { document.Blocks.Add(Code(code.ToString().TrimEnd('\n'))); code.Clear(); }
                    fenced = !fenced; continue;
                }
                if (fenced) { code.AppendLine(raw); continue; }
                if (string.IsNullOrWhiteSpace(line)) { flush(); continue; }
                var heading = Regex.Match(line, @"^\s{0,3}(#{1,6})\s+(.+?)(?:\s+#+)?$");
                var list = Regex.Match(line, @"^\s*(?:([-+*])|(\d+)[.)])\s+(.+)$");
                if (heading.Success)
                {
                    flush(); var block = Paragraph(heading.Groups[2].Value); block.FontWeight = FontWeights.SemiBold;
                    block.FontSize = heading.Groups[1].Length <= 2 ? 18 : 15;
                    block.Margin = new Thickness(0, document.Blocks.Count == 0 ? 0 : 12, 0, 10); document.Blocks.Add(block);
                }
                else if (list.Success)
                {
                    flush(); var block = Paragraph(list.Groups[3].Value);
                    block.Inlines.InsertBefore(block.Inlines.FirstInline, new Run(list.Groups[2].Success ? list.Groups[2].Value + ". " : "• "));
                    block.Margin = new Thickness(14, 0, 0, 8); block.TextIndent = -14; document.Blocks.Add(block);
                }
                else if (line.StartsWith("> "))
                {
                    flush(); var block = Paragraph(line.Substring(2)); block.FontStyle = FontStyles.Italic; block.Margin = new Thickness(12, 0, 0, 8); document.Blocks.Add(block);
                }
                else { if (paragraph.Length > 0) paragraph.Append(' '); paragraph.Append(line); }
            }
            flush(); if (fenced) document.Blocks.Add(Code(code.ToString().TrimEnd('\n')));
            return document;
        }

        private static Paragraph Paragraph(string text)
        {
            var paragraph = new Paragraph { Margin = new Thickness(0, 0, 0, 10), LineHeight = 21 };
            AddInline(paragraph.Inlines, text, 0); return paragraph;
        }

        private static Paragraph Code(string text)
        { return new Paragraph(new Run(text)) { FontFamily = new FontFamily("Consolas"), FontSize = 12, Margin = new Thickness(0, 0, 0, 10) }; }

        private static void AddInline(InlineCollection target, string text, int depth)
        {
            if (depth > 8) { target.Add(new Run(text)); return; }
            int previous = 0;
            foreach (Match match in InlineTokens.Matches(text))
            {
                if (match.Index > previous) target.Add(new Run(text.Substring(previous, match.Index - previous)));
                string token = match.Value;
                if (token.StartsWith("`")) target.Add(new Run(token.Substring(1, token.Length - 2)) { FontFamily = new FontFamily("Consolas") });
                else if (token.StartsWith("["))
                {
                    int split = token.IndexOf("](", StringComparison.Ordinal); string label = token.Substring(1, split - 1); Uri uri;
                    if (Uri.TryCreate(token.Substring(split + 2, token.Length - split - 3), UriKind.Absolute, out uri) && (uri.Scheme == "https" || uri.Scheme == "http"))
                    {
                        var link = new Hyperlink { NavigateUri = uri, Foreground = new SolidColorBrush(Color.FromRgb(114, 199, 255)), ToolTip = uri.AbsoluteUri };
                        AddInline(link.Inlines, label, depth + 1);
                        link.RequestNavigate += (s, e) => { try { Process.Start(new ProcessStartInfo(e.Uri.AbsoluteUri) { UseShellExecute = true }); } catch (Exception) { } e.Handled = true; };
                        target.Add(link);
                    }
                    else AddInline(target, label, depth + 1);
                }
                else
                {
                    bool doubled = token.StartsWith("**") || token.StartsWith("__") || token.StartsWith("~~"); int trim = doubled ? 2 : 1;
                    Span span = token.StartsWith("~~") ? new Span { TextDecorations = TextDecorations.Strikethrough } : doubled ? (Span)new Bold() : new Italic();
                    AddInline(span.Inlines, token.Substring(trim, token.Length - trim * 2), depth + 1); target.Add(span);
                }
                previous = match.Index + match.Length;
            }
            if (previous < text.Length) target.Add(new Run(text.Substring(previous)));
        }
    }
}
