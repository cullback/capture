You are merging two markdown versions of the same webpage.

Create a final merged markdown that:

1. Uses VERSION A's math equations (LaTeX format) and table formatting
2. Inserts image references from VERSION B in the appropriate locations
3. Preserves hyperlinks from VERSION B
4. Preserves the document structure and flow
5. Removes any duplicate content
6. Does NOT include any YAML frontmatter (metadata will be added separately)

Output ONLY the merged markdown, no explanations.

VERSION A (from Reducto - has accurate math equations and tables):
{reducto_md}

VERSION B (from Pandoc - has image references and hyperlinks):
{pandoc_md}
