# ADR 0022: every `tulsi COMMAND` the agent skills and AGENTS.md name is one the
# `tulsi` command has (its help text), so agents are not taught commands that
# don't exist.
{
  runCommand,
  tulsi-tools,
}:

runCommand "agent-skills-commands"
  {
    agents = ../../agents;
  }
  ''
    ${tulsi-tools}/bin/tulsi help > usage
    # The words after `tulsi ` (and their subcommand), as the skills write them.
    grep -rhoE '`tulsi( -[nq])? [a-z-]+( [a-z-]+)?' "$agents" \
      | sed -E 's/^`tulsi( -[nq])? //' | grep -v '^-' | sort -u > named
    missing=
    while read -r cmd sub; do
      grep -qE "^  $cmd( |$)" usage || grep -q "alias: $cmd)" usage || missing="$missing $cmd"
      case "$cmd" in
        config | recipe | service | ext | upgrade)
          if [ -n "$sub" ] && ! grep -qE "^  $cmd [a-z|-]*$sub|^  $cmd .*$sub" usage; then
            missing="$missing $cmd-$sub"
          fi ;;
      esac
    done < named
    if [ -n "$missing" ]; then
      echo "the skills name tulsi commands that do not exist:$missing" >&2
      cat named >&2
      exit 1
    fi
    echo "$(wc -l < named) tulsi commands named by the skills, all real" > $out
  ''
