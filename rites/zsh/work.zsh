# Work profile additions — managed by grimoire

# mysql (installed by work.nix via Homebrew)
export PATH="/opt/homebrew/opt/mysql-client@8.4/bin:$PATH"

# openspec
fpath=("$HOME/.oh-my-zsh/custom/completions" $fpath)
autoload -Uz compinit
compinit

# sdkman
export SDKMAN_DIR="$HOME/.sdkman"
[[ -s "$HOME/.sdkman/bin/sdkman-init.sh" ]] && source "$HOME/.sdkman/bin/sdkman-init.sh"
