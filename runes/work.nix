{ pkgs, ... }: {
  environment.systemPackages = with pkgs; [
    jq
  ];

  homebrew = {
    brews = [
      "awscli"
      "gitleaks"
      "mysql-client@8.4"
      "tmux"
      "yarn"
      # Moved off pinned nixpkgs for a faster cadence.
      "gh"               # GitHub CLI; chases GitHub API changes
      "golangci-lint"    # adds linters often; must match the Go version
      "kubernetes-cli"   # kubectl; keep near the cluster's k8s minor
      "bun"              # fast-moving JS runtime
    ];
    casks = [
      "session-manager-plugin"
      "typora"
    ];
  };
}
