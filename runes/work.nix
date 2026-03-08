{ pkgs, ... }: {
  environment.systemPackages = with pkgs; [
    awscli2
    gh
    golangci-lint
    jq
    kubectl
  ];

  homebrew.brews = [
    "mysql-client@8.4"
  ];

  homebrew.casks = [
    "typora"
  ];
}
