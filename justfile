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
    rg -l '[^\n]\z' --multiline | xargs -r sed -i -e '$a\\'

# Run linters and static analysis
check:
    dprint check
    ruff check .
    pyright .
    fd -e nix | xargs -r nixfmt --check
    ! rg -l '[^\n]\z' --multiline

# Run the test suite
test:
    pytest
