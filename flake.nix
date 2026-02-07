{
  description = "Capture websites as markdown";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.11";
  };

  outputs =
    { self, nixpkgs }:
    let
      supportedSystems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          python = pkgs.python312;
        in
        {
          capture = python.pkgs.buildPythonApplication {
            pname = "capture";
            version = "0.1.0";
            src = ./.;
            format = "pyproject";

            build-system = [ python.pkgs.setuptools ];

            dependencies = [ python.pkgs.pyyaml ];

            doCheck = false;

            makeWrapperArgs = [
              "--prefix"
              "PATH"
              ":"
              (pkgs.lib.makeBinPath [
                pkgs.single-file-cli
                pkgs.pandoc
                pkgs.chromium
              ])
            ];

            meta = {
              description = "Capture websites as markdown";
              mainProgram = "capture";
            };
          };
          default = self.packages.${system}.capture;
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
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
    };
}
