# Work profile additions — managed by grimoire

# tmux — bare terminals attach to a shared session; IDE panels and nested shells stay plain zsh
if [[ -z "$TMUX" && "$TERM_PROGRAM" == "ghostty" ]] && command -v tmux >/dev/null 2>&1; then
  exec tmux new-session -A -s main
fi

# Added by LM Studio CLI (lms)
export PATH="$PATH:/Users/larsnorlander/.lmstudio/bin"
# End of LM Studio CLI section

# mysql (installed by work.nix via Homebrew)
export PATH="/opt/homebrew/opt/mysql-client@8.4/bin:$PATH"

# openspec
fpath=("$HOME/.oh-my-zsh/custom/completions" $fpath)
autoload -Uz compinit
compinit

# sdkman
export SDKMAN_DIR="$HOME/.sdkman"
[[ -s "$HOME/.sdkman/bin/sdkman-init.sh" ]] && source "$HOME/.sdkman/bin/sdkman-init.sh"

# nvm
export NVM_DIR="$HOME/.nvm"
[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"
[ -s "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm" ] && \. "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm"
