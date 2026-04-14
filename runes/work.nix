{ pkgs, ... }: {
  environment.systemPackages = with pkgs; [
    awscli2
    gh
    golangci-lint
    jq
    kubectl
    bun
  ];

  homebrew.brews = [
    "mysql-client@8.4"
  ];

  homebrew.casks = [
    "typora"
  ];
}
