You are merging two Markdown versions of the same webpage into clean, idiomatic Markdown.

Create a final merged Markdown that:

1. Uses VERSION A's math equations and table formatting
2. Inserts image references from VERSION B in the appropriate locations
3. Preserves hyperlinks from VERSION B
4. Removes any duplicate content
5. Does NOT include any YAML frontmatter (metadata will be added separately)

Cleanup and normalization:

- **Headers:** Normalize to `#` for main title, `##` for sections, `###` for subsections
- **Math:** Use `$...$` for inline math, `$$...$$` for display math
- **Citations:** Convert numeric citations ([1], (1), superscripts) to Markdown footnotes [^1]
- **Code:** Use fenced code blocks with language tags (`python,`js, etc.)
- **Formatting:** Preserve emphasis (_italics_, **bold**) and blockquotes consistently
- **Artifacts:** Remove navigation elements, share buttons, cookie notices, and footer cruft

Output ONLY the merged Markdown, no explanations.

VERSION A (from Reducto - has accurate math equations and tables):
{reducto_md}

VERSION B (from Pandoc - has image references and hyperlinks):
{pandoc_md}
