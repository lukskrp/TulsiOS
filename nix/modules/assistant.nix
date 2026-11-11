# ocimum.assistant — agentic configuration assistant + MCP server (Phase 5).
{ config, lib, ... }:

{
  options.ocimum.assistant.enable = lib.mkEnableOption "the Ocimum Assistant and tulsi-mcp server (Phase 5, not functional yet)";

  config = lib.mkIf config.ocimum.assistant.enable {
    assertions = [
      {
        assertion = config.tulsi.daemon.enable;
        message = "ocimum.assistant requires tulsi.daemon.enable = true.";
      }
    ];
    # TODO(phase-5): panel applet, chat window, LLM provider settings.
  };
}
