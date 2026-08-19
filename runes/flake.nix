{
  description = "grimoire system configuration";

  inputs = {
    # Pinned to a stable release so `nix flake update` only pulls backports
    # within the release. Moving to a newer release (e.g. 26.11) is a
    # deliberate one-line edit here, not a surprise from tracking unstable.
    # Tools that need a faster cadence live in Homebrew instead (see runes).
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-26.05-darwin";
    # nix-darwin pinned to the matching release: master is what introduced
    # the `brew bundle --force-cleanup` break, so keep it on the same train.
    nix-darwin.url = "github:nix-darwin/nix-darwin/nix-darwin-26.05";
    nix-darwin.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nix-darwin, nixpkgs, ... }: {
    darwinConfigurations = {
      personal = nix-darwin.lib.darwinSystem {
        system = "aarch64-darwin";
        modules = [ ./configuration.nix ./personal.nix ];
      };
      work = nix-darwin.lib.darwinSystem {
        system = "aarch64-darwin";
        modules = [ ./configuration.nix ./work.nix ];
      };
    };
  };
}
