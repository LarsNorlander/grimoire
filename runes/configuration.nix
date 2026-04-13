{ pkgs, ... }: {
  system.primaryUser = "larsnorlander";

  # Determinate manages the Nix installation; disable nix-darwin's management
  nix.enable = false;

  environment.variables.NPM_CONFIG_PREFIX = "$HOME/.npm-global";

  # CLI tools — replaces brew formulae
  environment.systemPackages = with pkgs; [
    uv           # Python package manager (used by cast)
    bat          # cat replacement
    btop         # system monitor
    fastfetch    # system info
    neovim
    nodejs       # global Node.js
    go
    starship     # prompt (binary here, config via rite)
  ];

  fonts.packages = with pkgs; [
    nerd-fonts.jetbrains-mono
  ];

  # Homebrew — owns GUI apps and casks
  homebrew = {
    enable = true;
    onActivation.cleanup = "zap";
    taps = [ "nikitabobko/tap" ];
    brews = [ "julia" ];
    casks = [
      "aerospace"
      "scroll-reverser"
      "1password-cli"
      "ghostty"
      "obsidian"
    ];
  };

  # macOS system defaults
  system.defaults = {
    NSGlobalDomain = {
      AppleInterfaceStyle = "Dark";
    };
    dock = {
      orientation = "left";
      show-recents = false;
      mineffect = "scale";
    };
  };

  system.stateVersion = 6;
}
