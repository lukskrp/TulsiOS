# ADR 0023: every package the Software Center's AI Agents page offers is in the
# package index (a renamed attr fails here, not as a dead card), and each unfree
# one is on tulsi.daemon.unfreeAgents, so it can be installed once its licence
# is accepted.
{
  runCommand,
  jq,
  tulsi-package-index,
  unfreeAgents,
}:

runCommand "ai-agents-index"
  {
    nativeBuildInputs = [ jq ];
    agents = ../../apps/ocimum-software-center/ocimum_software_center/ai-agents.json;
    allowed = builtins.toJSON unfreeAgents;
  }
  ''
    jq -r '.agents[] | .attr, (.variants // {} | .[])' "$agents" | sort -u > wanted
    jq -r '.[][0]' ${tulsi-package-index} | sort -u > indexed
    missing=$(comm -23 wanted indexed)
    if [ -n "$missing" ]; then
      echo "not in the package index: $missing" >&2
      exit 1
    fi
    jq -r '.[] | select(.[4]) | .[0]' ${tulsi-package-index} | sort -u > unfree
    echo "$allowed" | jq -r '.[]' | sort -u > allowed
    blocked=$(comm -12 wanted unfree | comm -23 - allowed)
    if [ -n "$blocked" ]; then
      echo "unfree, but not in tulsi.daemon.unfreeAgents: $blocked" >&2
      exit 1
    fi
    echo "$(wc -l < wanted) AI packages, all in the index" > $out
  ''
