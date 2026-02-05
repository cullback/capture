# Display available recipes
default:
    just --list --unsorted

# Install dependencies and set up the development environment
bootstrap:
    uv sync

# Format code
format:
    dprint fmt
    fd -e nix | xargs -r nixfmt
    rg -l '[^\n]\z' --multiline | xargs -r sed -i -e '$a\\'

# Run linters and static analysis
check:
    #!/usr/bin/env fish
    set status_flag 0
    dprint check; or set status_flag 1
    ruff check .; or set status_flag 1
    pyright .; or set status_flag 1
    fd -e nix | xargs -r nixfmt --check; or set status_flag 1
    ! rg -l '[^\n]\z' --multiline; or set status_flag 1
    exit $status_flag

# Run the capture tool
run *ARGS:
    uv run python capture.py {{ ARGS }}
