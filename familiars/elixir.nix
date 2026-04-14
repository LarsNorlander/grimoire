let pkgs = import <nixpkgs> { };
in pkgs.mkShell {
  buildInputs = with pkgs; [
    elixir
    elixir-ls
  ];

  shellHook = ''
    export GRIMOIRE_FAMILIAR=elixir
  '';
}
