# Display available recipes
default:
    just --list --unsorted

# Install dependencies and set up the development environment
bootstrap:
    uv sync

alias fmt := format

# Format code
format:
    dprint fmt
    fd -e nix | xargs -r nixfmt
    # The trailing `.` is required: with no path, ripgrep reads stdin when
    # stdin is not a TTY and blocks forever instead of searching the tree.
    rg -l '[^\n]\z' --multiline . | xargs -r sed -i -e '$a\\'

# Run linters and static analysis
check:
    dprint check
    ruff check .
    pyright .
    fd -e nix | xargs -r nixfmt --check
    ! rg -l '[^\n]\z' --multiline .

# Run the test suite
test:
    pytest

# Corpus home: collected content, lives under /vault/media (see media/README.md)
sites_dir := "/vault/media/sites"

# Save a page as faithful HTML archive + clean markdown into the corpus
capture url *flags:
    uv run python -m capture -o '{{ sites_dir }}' {{ flags }} '{{ url }}'
