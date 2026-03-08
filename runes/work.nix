{ pkgs, ... }: {
  environment.systemPackages = with pkgs; [
    # work-specific CLI tools
  ];

  homebrew.casks = [
    # work-specific apps
  ];
}
