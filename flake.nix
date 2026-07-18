{
  description = "Python project";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          # PyPI wheels (torch, numpy for marker-pdf) link against
          # libstdc++ and zlib, which NixOS doesn't expose by default.
          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
            pkgs.stdenv.cc.cc.lib
            pkgs.zlib
          ];
          # yt-dlp (a python3.13 app) leaks its dependency closure into
          # PYTHONPATH, which poisons the project's python3.12 venv;
          # its own wrapper re-adds what it needs.
          shellHook = ''
            unset PYTHONPATH
          '';
          packages = with pkgs; [
            python312
            uv
            ruff
            pyright
            dprint
            fd
            ripgrep
            nixfmt-rfc-style
            single-file-cli
            chromium
            pandoc
            yt-dlp
            ffmpeg
            git
            poppler-utils
          ];
        };
      }
    );
}
