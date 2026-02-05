"""LLM interaction functions for capture pipeline."""

import json
import subprocess
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
LLM_SCRIPT = Path.home() / "repos/dotfiles/scripts/llm.py"


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


def merge_with_llm(reducto_md: str, pandoc_md: str) -> str:
    """Use llm.py to merge the two markdown versions."""
    print("Merging with LLM...")

    template = load_prompt("merge")
    prompt = template.format(reducto_md=reducto_md, pandoc_md=pandoc_md)

    result = subprocess.run(
        ["python", str(LLM_SCRIPT), prompt],
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
        ["python", str(LLM_SCRIPT), "--schema", str(schema_path), prompt],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)
