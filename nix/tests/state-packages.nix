# Verifies that tulsi.state turns a JSON state file into real system config.
{ self }:
{
  name = "tulsi-state-packages";

  nodes.machine =
    { ... }:
    {
      imports = [ self.nixosModules.default ];
      tulsi.state = {
        enable = true;
        file = ./state-test.json;
      };
    };

  testScript = ''
    machine.wait_for_unit("multi-user.target")

    with subtest("packages from state.json are installed"):
        machine.succeed("command -v hello")

    with subtest("Firefox extension policy is generated"):
        machine.succeed("grep -q 'uBlock0@raymondhill.net' /etc/firefox/policies/policies.json")

    with subtest("Chromium extension policy is generated"):
        machine.succeed("grep -q cjpalhdlnbpafiamejdnhcphjbkeiagm /etc/chromium/policies/managed/default.json")
  '';
}
