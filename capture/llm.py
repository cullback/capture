"""LLM interaction functions for capture pipeline."""

import json
import subprocess
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
LLM_SCRIPT = Path.home() / "repos/dotfiles/scripts/llm.py"


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


def cleanup_markdown(markdown: str, pandoc_md: str | None = None) -> str:
    """Clean up markdown with LLM, optionally merging two versions."""
    rules = load_prompt("cleanup")

    if pandoc_md:
        print("Merging with LLM...")
        merge_intro = load_prompt("merge")
        prompt = (
            f"{merge_intro}\n{rules}\n"
            f"VERSION A (from Reducto - has accurate math equations and tables):\n{markdown}\n\n"
            f"VERSION B (from Pandoc - has image references and hyperlinks):\n{pandoc_md}"
        )
    else:
        print("Cleaning up with LLM...")
        prompt = (
            f"You are cleaning up raw Markdown into polished, idiomatic Markdown.\n\n"
            f"{rules}\n{markdown}"
        )

    result = subprocess.run(
        ["python", str(LLM_SCRIPT)],
        input=prompt,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def extract_metadata(markdown: str) -> dict:
    """Use llm.py to extract metadata from the markdown."""
    print("Extracting metadata...")

    template = load_prompt("metadata")
    prompt = template.format(markdown=markdown[:8000])  # Limit context size
    schema_path = PROMPTS_DIR / "metadata_schema.json"

    result = subprocess.run(
        ["python", str(LLM_SCRIPT), "--schema", str(schema_path)],
        input=prompt,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)
