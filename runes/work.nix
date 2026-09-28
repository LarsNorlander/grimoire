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

  # Start the Lima docker VM at login; Lima has no autostart of its own.
  # RunAtLoad also fires on activation, and `limactl start NAME` *creates*
  # NAME from the default template when it doesn't exist, so only start an
  # instance rites/lima has already created from the managed template.
  launchd.user.agents.lima-docker = {
    serviceConfig = {
      ProgramArguments = [
        "/bin/sh"
        "-c"
        "test -f \"$HOME/.lima/docker/lima.yaml\" && exec /opt/homebrew/bin/limactl start docker"
      ];
      RunAtLoad = true;
      StandardOutPath = "/tmp/lima-docker.launchd.log";
      StandardErrorPath = "/tmp/lima-docker.launchd.log";
    };
  };
}
