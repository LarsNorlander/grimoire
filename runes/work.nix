{ pkgs, ... }: {
  environment.systemPackages = with pkgs; [
    gh
    golangci-lint
    jq
    kubectl
    bun
  ];

  homebrew = {
    brews = [
      "awscli"
      "nvm"
      "gitleaks"
      "mysql-client@8.4"
      "tmux"
      "yarn"
    ];
    casks = [
      "session-manager-plugin"
      "typora"
    ];
  };
}
