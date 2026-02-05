Cleanup and normalization:

- **Headers:** Normalize to `#` for main title, `##` for sections, `###` for subsections
- **Math:** Use `$...$` for inline math, `$$...$$` for display math. Preserve Greek letters and mathematical symbols in LaTeX.
- **Citations:** Convert numeric citations ([1], (1), superscripts) to Markdown footnotes `[^1]` with corresponding definitions
- **Code:** Use fenced code blocks with language tags (`python`, `js`, etc.)
- **Formatting:** Preserve emphasis (_italics_, **bold**) and blockquotes consistently
- **Hyphenation:** Rejoin words broken across line breaks or page boundaries (e.g., "compu-\ntation" → "computation", "ex- actly" → "exactly")
- **Layout:** Linearize multi-column layouts into single-column reading order
- **Figures:** Preserve figure/table captions. Use `[Figure X: Caption text]` if the image cannot be referenced.
- **Comments:** If user comments/discussion exist, include them at the end under a `## Comments` heading. Format each as a blockquote with the author in bold. Use nested blockquotes to preserve reply threading: `>` for top-level, `>>` for replies, `>>>` for deeper replies, etc.
- **Artifacts:** Remove navigation elements, share buttons, cookie notices, page numbers, repeated headers/footers, and other cruft

Do NOT include any YAML frontmatter (metadata will be added separately).
Output ONLY the cleaned Markdown, no explanations.
