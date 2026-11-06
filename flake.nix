{
  description = "Reusable LLM setup, skills, and configuration sync tools";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    amp.url = "github:darwin67/ampcode-nix";
    amp.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { nixpkgs, amp, ... }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" ];
    in {
      devShells = nixpkgs.lib.genAttrs systems (system:
        let pkgs = import nixpkgs { inherit system; };
        in {
          default = pkgs.mkShell {
            packages = [
              (pkgs.python3.withPackages (ps: [ ps.pyyaml ]))
              pkgs.git
              pkgs.actionlint
              pkgs.bun
              amp.packages.${system}.default
            ];
          };
        });
    };
}
