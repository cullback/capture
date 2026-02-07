You are converting a webpage PDF into clean, well-structured Markdown. You have access to:

1. **The PDF attachment** — use this for visual layout, math equations, tables, and reading order
2. **Pandoc Markdown below** (if provided) — use this for image references (`images/...`) and hyperlinks

## Output Format

Output ONLY valid Markdown starting with YAML frontmatter in this exact format:

```markdown
---
title: "The Article Title"
publish_date: YYYY-MM-DD
tags:
  - tag1
  - tag2
---

# The Article Title

Article content...
```

The article content MUST start with a first-level header (`# Title`) matching the frontmatter title.

## Frontmatter Fields

- **title**: The article's title (in quotes to handle special characters)
- **publish_date**: Extract from the article in YYYY-MM-DD format. Omit the line if not found.
- **tags**: 2-8 relevant topic tags (see taxonomy below)

## Content Cleanup Rules

- **Headers**: Use `#` for main title, `##` for sections, `###` for subsections
- **Math**: Use `$...$` for inline math, `$$...$$` for display math. Preserve LaTeX notation.
- **Citations**: Convert numeric citations ([1], (1), superscripts) to Markdown footnotes `[^1]` with definitions
- **Code**: Use fenced code blocks with language tags (`python`, `js`, etc.)
- **Formatting**: Preserve emphasis (_italics_, **bold**) and blockquotes
- **Hyphenation**: Rejoin words broken across line breaks (e.g., "compu-\ntation" → "computation")
- **Layout**: Linearize multi-column layouts into single-column reading order
- **Figures**: ALWAYS include a detailed caption for every image that fully describes its content. Write as if for a blind reader—someone should be able to understand or roughly recreate the image from your description alone. For charts/graphs: describe the data, axes, trends, and key values. For diagrams: describe the components, relationships, and flow. For screenshots: describe the UI elements and their state. For photos: describe the subject, composition, and relevant details. Use image references from Pandoc Markdown if available.
- **Comments**: If user comments exist, include under `## Comments` heading. Format as blockquotes with author in bold. Use nested blockquotes for reply threading.
- **Artifacts**: Remove navigation elements, share buttons, cookie notices, page numbers, repeated headers/footers

## When Pandoc Markdown is Provided

- Insert image references from Pandoc in appropriate locations (matching by context/caption)
- Preserve hyperlinks from Pandoc
- Use PDF for accurate math equations, tables, and visual formatting
- Remove duplicate content

## Tag Taxonomy

Format: lowercase kebab-case. Prefer existing tags, but invent specific tags if needed.

### Topic tags

- CS: algorithms, data-structures, compilers, graphics, complexity-theory, type-theory, concurrency, formal-methods, encryption, solver, data-visualization, floating-point, unicode, parsing, compression, information-theory, automata
- Systems: operating-systems, distributed, networking, hardware, assembly, instruction-sets, nixos, macos, self-hosting, linux, containers, virtualization
- Programming: functional-programming, oop, design-patterns, code-golf, rust, python, c, html, plt, javascript, cpp, metaprogramming, regex
- Practices: performance, security, reversing, debugging, devtools, testing, observability, database, sqlite, git, ci-cd, profiling, logging
- Math: math, probability, statistics, linear-algebra, optimization, numerical-analysis, graph-theory, combinatorics, set-theory
- Finance: finance, quant, market-microstructure, market-manipulation, prediction-markets, forecasting, kelly-criterion, derivatives, risk-management, options, backtesting, portfolio-theory
- AI: llm, reinforcement-learning, interpretability, agents, computer-vision, nlp, fine-tuning
- Epistemics: rationalism, bayesian, decision-theory, cognitive-biases, game-theory, calibration
- Games: chess, puzzle, board-games, catan, poker, go, geoguessr
- Policy: policy, climate-change, copyright, privacy, regulation
- Life: employment, parenting, taxes, startup, productivity, conversation, philosophy, psychology, writing, humor, spaced-repetition, health, negotiation, reading, education

### Content type tags

- implementation — article describes building a concrete thing
- walkthrough — step-by-step explanation

Output ONLY the final Markdown document with frontmatter. No explanations or commentary.
