"""LLM interaction functions for capture pipeline."""

import re
import subprocess
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"
LLM_SCRIPT = Path.home() / "repos/dotfiles/scripts/llm.py"


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


def strip_code_fences(text: str) -> str:
    """Strip markdown code fences from LLM output if present."""
    text = text.strip()
    # Match ```markdown, ```yaml, or just ``` at start
    text = re.sub(r"^```(?:markdown|yaml|md)?\s*\n", "", text)
    # Also strip fences after frontmatter (---\n...---\n```content```)
    text = re.sub(
        r"(^---\n.*?\n---\n)```(?:markdown|yaml|md)?\s*\n", r"\1", text, flags=re.DOTALL
    )
    # Remove trailing fence
    text = re.sub(r"\n```\s*$", "", text)
    return text


def inject_frontmatter_fields(
    markdown: str,
    domain: str,
    url: str,
    capture_date: str,
    hackernews: str | None = None,
) -> str:
    """Inject known metadata fields into frontmatter after title line."""
    lines = []
    if domain:
        lines.append(f"domain: {domain}")
    if url:
        lines.append(f"url: {url}")
    if hackernews:
        lines.append(f"hackernews: {hackernews}")
    lines.append(f"capture_date: {capture_date}")

    if not lines:
        return markdown

    inject = "\n".join(lines)
    # Insert after the title line in frontmatter
    return re.sub(
        r"(^---\n.*?title:[^\n]*\n)", rf"\1{inject}\n", markdown, flags=re.DOTALL
    )


def generate_markdown(
    pdf_path: Path,
    pandoc_md: str | None,
    domain: str,
    url: str,
    capture_date: str,
    hackernews: str | None = None,
) -> str:
    """Generate clean markdown with frontmatter from PDF and optional pandoc output."""
    print("Generating markdown with LLM...")

    prompt = load_prompt("generate")

    if pandoc_md:
        prompt = f"{prompt}\n\n## Pandoc Markdown (has image references and links)\n\n{pandoc_md}"

    result = subprocess.run(
        ["python", str(LLM_SCRIPT), "-a", str(pdf_path)],
        input=prompt,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"LLM error (exit {result.returncode}): {result.stderr}", flush=True)
        raise subprocess.CalledProcessError(result.returncode, result.args)

    markdown = strip_code_fences(result.stdout)
    return inject_frontmatter_fields(markdown, domain, url, capture_date, hackernews)
