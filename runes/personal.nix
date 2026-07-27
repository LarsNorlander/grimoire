{ pkgs, ... }: {

  environment.variables.NPM_CONFIG_PREFIX = "$HOME/.npm-global";

  environment.systemPackages = with pkgs; [
    nodejs
  ];

  homebrew.brews = [ ];
}
