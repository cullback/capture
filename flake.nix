{
  description = "Save web pages and PDFs as self-contained archive folders";

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
        # Binaries the pipeline shells out to; wrapped onto PATH so an
        # installed capture works outside the devShell.
        runtime = with pkgs; [
          chromium
          single-file-cli
          pandoc
          dprint
          yt-dlp
          ffmpeg
          git
          poppler-utils
          curl
          fish
        ];
      in
      {
        packages.default = pkgs.python312Packages.buildPythonApplication {
          pname = "capture";
          version = "0.1.0";
          src = self;
          pyproject = true;
          build-system = [ pkgs.python312Packages.hatchling ];
          nativeBuildInputs = [ pkgs.makeWrapper ];
          makeWrapperArgs = [
            "--prefix PATH : ${pkgs.lib.makeBinPath runtime}"
          ];
          # The fish helper ships as package data (wheels drop execute
          # bits), so expose it as a command via its own wrapper.
          postInstall = ''
            makeWrapper ${pkgs.fish}/bin/fish $out/bin/single-file-archive \
              --add-flags "$out/${pkgs.python312.sitePackages}/capture/scripts/single-file-archive" \
              --prefix PATH : ${pkgs.lib.makeBinPath runtime}
          '';
        };

        apps.default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/capture";
        };

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
