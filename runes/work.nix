{ pkgs, ... }: {
  environment.systemPackages = with pkgs; [
    jq
  ];

  homebrew = {
    brews = [
      "awscli"
      "gitleaks"
      "mysql-client@8.4"
      "yarn"
      # Moved off pinned nixpkgs for a faster cadence.
      "gh"               # GitHub CLI; chases GitHub API changes
      "golangci-lint"    # adds linters often; must match the Go version
      "kubernetes-cli"   # kubectl; keep near the cluster's k8s minor
      "bun"              # fast-moving JS runtime
      # Containers: Lima runs a rootful Docker VM (rites/lima); the host-side
      # CLI talks to it over the forwarded socket (rites/docker).
      "lima"
      "docker"
      "docker-compose"
      "docker-buildx"
      "docker-credential-helper"  # keychain-backed `docker login`
    ];
    casks = [
      "session-manager-plugin"
      "typora"
    ];
  };
}
