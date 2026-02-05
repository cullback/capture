{
  description = "Capture websites as markdown";

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
          packages = with pkgs; [
            python312
            uv
            ruff
            pyright
            dprint
            fd
            ripgrep
            nixfmt-rfc-style
            # capture dependencies
            single-file-cli
            pandoc
            chromium
          ];
        };
      }
    );
}
