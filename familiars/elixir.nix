let pkgs = import <nixpkgs> { };
in pkgs.mkShell {
  buildInputs = with pkgs; [
    elixir
    elixir-ls
  ];

  shellHook = ''
    export GRIMOIRE_FAMILIAR=elixir
    export ELIXIR_EDITOR="zed --wait"
    echo "Elixir familiar summoned. Type 'exit' to dismiss."
  '';
}
