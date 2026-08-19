{ pkgs, ... }: {
  system.primaryUser = "larsnorlander";

  # Determinate manages the Nix installation; disable nix-darwin's management
  nix.enable = false;

  # CLI tools — replaces brew formulae
  environment.systemPackages = with pkgs; [
    uv           # Python package manager (used by cast)
    bat          # cat replacement
    btop         # system monitor
    fastfetch    # system info
    neovim
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
    # Homebrew 6 refuses to load casks/formulae from untrusted third-party taps;
    # `trusted` adds `trusted: true` to the Brewfile entry so activation doesn't abort.
    taps = [
      {
        name = "nikitabobko/tap";
        trusted = true;
      }
    ];
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
