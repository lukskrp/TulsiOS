//! MCP request handling and the TulsiOS tools.

use serde_json::{json, Value};
use tokio::io::{AsyncRead, AsyncWrite};
use tulsi_state::Op;

use crate::approval::{Approver, Decision, Request};
use crate::backend::{Backend, JobResult};
use crate::transport::{Transport, INVALID_PARAMS, METHOD_NOT_FOUND};

/// Protocol versions this server speaks; the client's choice is echoed when
/// supported, otherwise the newest is offered.
const PROTOCOL_VERSIONS: [&str; 4] = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"];
const REQUESTER: &str = "an AI agent (through tulsi-mcp)";
const ACTION_APPLY: &str = "org.tulsi.apply";
const ACTION_EXTENSIONS: &str = "org.tulsi.extensions";

/// The polkit action tulsid checks for these operations (same rule as tulsid's
/// required_action): changes that only touch browser extensions have their own.
fn polkit_action(ops_json: &str) -> &'static str {
    match serde_json::from_str::<Vec<Op>>(ops_json) {
        Ok(ops)
            if !ops.is_empty()
                && ops.iter().all(|op| {
                    matches!(op, Op::AddExtension { .. } | Op::RemoveExtension { .. })
                }) =>
        {
            ACTION_EXTENSIONS
        }
        _ => ACTION_APPLY,
    }
}

const INSTRUCTIONS: &str = "\
TulsiOS is a NixOS-based system managed declaratively. Use these tools instead of \
editing files or running nixos-rebuild yourself.
- Find packages with search_packages; use the returned `attr` as the package name.
- Prefer apply_change (packages, browser extensions, service toggles) over editing \
configuration.nix. Call plan_change first and tell the user what will change.
- For other settings, read_configuration, then propose_configuration_edit with the \
COMPLETE new file contents, then apply_configuration_edit.
- Every apply/undo asks the human for approval and rebuilds the system, which can take \
minutes. If the human rejects, do not retry the same change unasked.
- Failed rebuilds are rolled back automatically; undo_last_change reverts the latest change.

Packaging software that is not in the Software Center (local packages):
- Only when search_packages finds nothing suitable. Ask for a download URL if you have none.
- fetch_source (url, or store_path for a file the user gave) → read Kind, Build hints, Contents.
- Write a callPackage expression: a function of its dependencies, e.g.
  { lib, stdenv, fetchurl, autoPatchelfHook, makeWrapper }: stdenv.mkDerivation (finalAttrs: { … }).
  Sources only through hashed fetchers (fetchurl, fetchzip, fetchFromGitHub) or requireFile
  for store_path sources (with meta.license set, or it counts as unfree); no path literals,
  no builtins.readFile/fetch*, no <nixpkgs>.
- Recipes: prebuilt tarball → unpack, install to $out/bin, autoPatchelfHook + buildInputs for
  missing libraries (the build log names them). .deb → nativeBuildInputs = [ dpkg
  autoPatchelfHook ]; unpackPhase = \"dpkg -x $src .\"; copy usr/ to $out. AppImage →
  appimageTools.wrapType2 { pname; version; src; }. autotools/CMake/Meson → stdenv.mkDerivation
  with cmake or meson+ninja+pkg-config. Rust → rustPlatform.buildRustPackage, Go →
  buildGoModule, Python → python3Packages.buildPythonApplication, npm → buildNpmPackage:
  start dependency hashes as lib.fakeHash, build_package reports the right one.
  Add meta = { description; homepage; license; mainProgram; } and, for GUI apps, a
  makeDesktopItem.
- build_package, fix errors (missing libraries, hashes), try_package, then
  propose_local_package with a one-line reason; the human reviews the expression.
- Unfree software: say so; the person must accept its licence. Kernel modules, drivers and
  system services are out of scope: explain instead. Stop after a few failed builds and
  report what blocks it.";

pub struct Server<B> {
    backend: B,
    approver: Approver,
    client_elicits: bool,
}

/// Result of a tool: text for the model, optional structured data, error flag.
struct ToolOutput {
    text: String,
    structured: Option<Value>,
    is_error: bool,
}

impl ToolOutput {
    fn ok(text: impl Into<String>) -> Self {
        Self {
            text: text.into(),
            structured: None,
            is_error: false,
        }
    }
    fn data(text: impl Into<String>, structured: Value) -> Self {
        Self {
            text: text.into(),
            structured: Some(structured),
            is_error: false,
        }
    }
    fn error(text: impl Into<String>) -> Self {
        Self {
            text: text.into(),
            structured: None,
            is_error: true,
        }
    }
    fn into_value(self) -> Value {
        let mut v = json!({
            "content": [{ "type": "text", "text": self.text }],
            "isError": self.is_error,
        });
        if let Some(s) = self.structured {
            v["structuredContent"] = s;
        }
        v
    }
}

impl<B: Backend> Server<B> {
    pub fn new(backend: B, approver: Approver) -> Self {
        Self {
            backend,
            approver,
            client_elicits: false,
        }
    }

    /// Serves until the client closes the connection.
    pub async fn serve<R, W>(&mut self, transport: &mut Transport<R, W>)
    where
        R: AsyncRead + Unpin,
        W: AsyncWrite + Unpin,
    {
        while let Some(msg) = transport.next_message().await {
            let Some(method) = msg["method"].as_str().map(str::to_string) else {
                continue; // a stray response; nothing is waiting for it
            };
            let Some(id) = msg.get("id").cloned() else {
                continue; // notifications (initialized, cancelled, …) need no answer
            };
            let params = msg.get("params").cloned().unwrap_or(Value::Null);
            match method.as_str() {
                "initialize" => {
                    let result = self.initialize(&params);
                    transport.reply(id, result).await;
                }
                "ping" => transport.reply(id, json!({})).await,
                "tools/list" => transport.reply(id, json!({ "tools": tool_list() })).await,
                "tools/call" => {
                    let name = params["name"].as_str().unwrap_or_default().to_string();
                    let args = params.get("arguments").cloned().unwrap_or(json!({}));
                    match self.call(&name, &args, transport).await {
                        Some(out) => transport.reply(id, out.into_value()).await,
                        None => {
                            transport
                                .error(id, INVALID_PARAMS, &format!("unknown tool {name:?}"))
                                .await
                        }
                    }
                }
                other => {
                    transport
                        .error(
                            id,
                            METHOD_NOT_FOUND,
                            &format!("method {other:?} not supported"),
                        )
                        .await
                }
            }
        }
    }

    fn initialize(&mut self, params: &Value) -> Value {
        self.client_elicits = params["capabilities"].get("elicitation").is_some();
        let requested = params["protocolVersion"].as_str().unwrap_or_default();
        let version = PROTOCOL_VERSIONS
            .iter()
            .find(|v| **v == requested)
            .copied()
            .unwrap_or(PROTOCOL_VERSIONS[0]);
        json!({
            "protocolVersion": version,
            "capabilities": { "tools": { "listChanged": false } },
            "serverInfo": {
                "name": "tulsi-mcp",
                "title": "TulsiOS",
                "version": env!("CARGO_PKG_VERSION")
            },
            "instructions": INSTRUCTIONS
        })
    }

    async fn call<R, W>(
        &mut self,
        name: &str,
        args: &Value,
        transport: &mut Transport<R, W>,
    ) -> Option<ToolOutput>
    where
        R: AsyncRead + Unpin,
        W: AsyncWrite + Unpin,
    {
        let out = match name {
            "search_packages" => self.search(args).await,
            "package_info" => self.package_info(args).await,
            "get_state" => self.get_state().await,
            "read_configuration" => self.read_configuration().await,
            "history" => self.history(args).await,
            "plan_change" => self.plan_change(args).await,
            "apply_change" => self.apply_change(args, transport).await,
            "undo_last_change" => self.undo(args, transport).await,
            "propose_configuration_edit" => self.propose_config(args).await,
            "apply_configuration_edit" => self.apply_config(args, transport).await,
            "fetch_source" => crate::packaging::fetch_source(args)
                .await
                .map(|(t, v)| ToolOutput::data(t, v)),
            "build_package" => crate::packaging::build_package(args)
                .await
                .map(|(t, v)| ToolOutput::data(t, v)),
            "try_package" => crate::packaging::try_package(args)
                .await
                .map(|(t, v)| ToolOutput::data(t, v)),
            "propose_local_package" => self.propose_local(args, transport).await,
            _ => return None,
        };
        Some(out.unwrap_or_else(ToolOutput::error))
    }

    async fn search(&self, args: &Value) -> Result<ToolOutput, String> {
        let query = required_str(args, "query")?;
        let limit = args["limit"].as_u64().unwrap_or(10).clamp(1, 50) as u32;
        let results = self.backend.search(query, limit).await?;
        if results.is_empty() {
            return Ok(ToolOutput::data(
                format!("No packages match {query:?}."),
                json!({ "packages": [] }),
            ));
        }
        let text = results
            .iter()
            .map(|p| {
                let mut flags = Vec::new();
                if p.installed {
                    flags.push("installed")
                }
                if p.unfree {
                    flags.push("unfree")
                }
                if p.license.is_some() && !p.license_accepted {
                    flags.push("a person must accept its licence in the Software Center first")
                }
                let flags = if flags.is_empty() {
                    String::new()
                } else {
                    format!(" [{}]", flags.join(", "))
                };
                format!("{} {} — {}{flags}", p.attr, p.version, p.description)
            })
            .collect::<Vec<_>>()
            .join("\n");
        Ok(ToolOutput::data(text, json!({ "packages": results })))
    }

    async fn package_info(&self, args: &Value) -> Result<ToolOutput, String> {
        let info = self
            .backend
            .package_info(required_str(args, "attr")?)
            .await?;
        let text = serde_json::to_string_pretty(&info).expect("serializes");
        Ok(ToolOutput::data(
            text,
            serde_json::to_value(&info).expect("serializes"),
        ))
    }

    async fn get_state(&self) -> Result<ToolOutput, String> {
        let text = self.backend.get_state().await?;
        let value: Value = serde_json::from_str(&text).map_err(|e| e.to_string())?;
        Ok(ToolOutput::data(text, value))
    }

    async fn read_configuration(&self) -> Result<ToolOutput, String> {
        let text = self.backend.get_config().await?;
        if text.is_empty() {
            return Ok(ToolOutput::ok("configuration.nix does not exist yet."));
        }
        Ok(ToolOutput::ok(text))
    }

    async fn history(&self, args: &Value) -> Result<ToolOutput, String> {
        let limit = args["limit"].as_u64().unwrap_or(10).clamp(1, 100) as u32;
        let entries = self.backend.history(limit).await?;
        let text = entries
            .iter()
            .map(|e| format!("{} {}", e.commit, e.summary))
            .collect::<Vec<_>>()
            .join("\n");
        Ok(ToolOutput::data(text, json!({ "history": entries })))
    }

    async fn plan_change(&self, args: &Value) -> Result<ToolOutput, String> {
        let ops = operations(args)?;
        let plan = self.backend.plan(&ops).await?;
        if plan.changes.is_empty() {
            return Ok(ToolOutput::data(
                "Nothing would change.",
                json!({ "changes": [] }),
            ));
        }
        Ok(ToolOutput::data(
            format!(
                "Would change:\n{}\n(Nothing was applied.)",
                plan.changes.join("\n")
            ),
            json!({ "changes": plan.changes }),
        ))
    }

    async fn apply_change<R, W>(
        &mut self,
        args: &Value,
        transport: &mut Transport<R, W>,
    ) -> Result<ToolOutput, String>
    where
        R: AsyncRead + Unpin,
        W: AsyncWrite + Unpin,
    {
        let ops = operations(args)?;
        let reason = required_str(args, "reason")?;
        let plan = self.backend.plan(&ops).await?;
        if plan.changes.is_empty() {
            return Ok(ToolOutput::ok(
                "Nothing to change; the system already matches.",
            ));
        }
        let request = Request {
            title: "An AI agent wants to change this system".into(),
            reason: reason.into(),
            changes: plan.changes.clone(),
            diff: None,
            requester: REQUESTER.into(),
            action: polkit_action(&ops),
        };
        self.approved(&request, transport).await?;
        job_output(self.backend.apply(&ops).await?)
    }

    async fn undo<R, W>(
        &mut self,
        args: &Value,
        transport: &mut Transport<R, W>,
    ) -> Result<ToolOutput, String>
    where
        R: AsyncRead + Unpin,
        W: AsyncWrite + Unpin,
    {
        let reason = required_str(args, "reason")?;
        let latest = self.backend.history(1).await?;
        let Some(latest) = latest.first() else {
            return Ok(ToolOutput::error("There is no change to undo."));
        };
        let request = Request {
            title: "An AI agent wants to undo the latest system change".into(),
            reason: reason.into(),
            changes: vec![format!(
                "Undo: {}",
                latest.summary.trim_start_matches("tulsi: ")
            )],
            diff: None,
            requester: REQUESTER.into(),
            action: ACTION_APPLY,
        };
        self.approved(&request, transport).await?;
        job_output(self.backend.undo().await?)
    }

    async fn propose_config(&self, args: &Value) -> Result<ToolOutput, String> {
        let contents = required_str(args, "contents")?;
        let plan = self.backend.plan_config(contents).await?;
        if !plan.changed {
            return Ok(ToolOutput::ok(
                "The proposed contents are identical to the current file.",
            ));
        }
        Ok(ToolOutput::data(
            format!(
                "Syntax OK. Proposed change (nothing was applied):\n{}",
                plan.diff
            ),
            json!({ "diff": plan.diff }),
        ))
    }

    async fn apply_config<R, W>(
        &mut self,
        args: &Value,
        transport: &mut Transport<R, W>,
    ) -> Result<ToolOutput, String>
    where
        R: AsyncRead + Unpin,
        W: AsyncWrite + Unpin,
    {
        let contents = required_str(args, "contents")?;
        let summary = required_str(args, "summary")?;
        let reason = required_str(args, "reason")?;
        let plan = self.backend.plan_config(contents).await?;
        if !plan.changed {
            return Ok(ToolOutput::ok(
                "Nothing to change; configuration.nix already has these contents.",
            ));
        }
        let request = Request {
            title: "An AI agent wants to edit configuration.nix".into(),
            reason: reason.into(),
            changes: vec![format!("Edit configuration.nix: {summary}")],
            diff: Some(plan.diff),
            requester: REQUESTER.into(),
            action: ACTION_APPLY,
        };
        self.approved(&request, transport).await?;
        job_output(self.backend.apply_config(contents, summary).await?)
    }

    /// Adds a local package the agent built: tulsid checks it, the human approves
    /// (seeing the whole expression), then tulsid writes it and rebuilds.
    async fn propose_local<R, W>(
        &mut self,
        args: &Value,
        transport: &mut Transport<R, W>,
    ) -> Result<ToolOutput, String>
    where
        R: AsyncRead + Unpin,
        W: AsyncWrite + Unpin,
    {
        let name = required_str(args, "name")?;
        let expression = required_str(args, "expression")?;
        let reason = required_str(args, "reason")?;
        let origin = args["origin"].as_str().unwrap_or_default();
        let op = json!([{
            "op": "addLocalPackage",
            "name": name,
            "expression": expression,
            "version": args["version"].as_str().unwrap_or_default(),
            "description": args["description"].as_str().unwrap_or_default(),
            "origin": origin,
        }]);
        let ops = op.to_string();
        let plan = self.backend.plan(&ops).await?;
        let mut changes = plan.changes.clone();
        if !origin.is_empty() {
            changes.push(format!("Source: {origin}"));
        }
        let request = Request {
            title: format!("An AI agent packaged \"{name}\" and wants to install it"),
            reason: reason.into(),
            changes,
            diff: Some(expression.to_string()),
            requester: REQUESTER.into(),
            action: ACTION_APPLY,
        };
        self.approved(&request, transport).await?;
        job_output(self.backend.apply(&ops).await?)
    }

    /// Ok if the human approved; Err with the reason otherwise.
    async fn approved<R, W>(
        &self,
        request: &Request,
        transport: &mut Transport<R, W>,
    ) -> Result<(), String>
    where
        R: AsyncRead + Unpin,
        W: AsyncWrite + Unpin,
    {
        match self
            .approver
            .ask(request, transport, self.client_elicits)
            .await
        {
            Decision::Approved(via) => {
                eprintln!(
                    "tulsi-mcp: approved via {via}: {}",
                    request.changes.join("; ")
                );
                Ok(())
            }
            Decision::Rejected(why) => Err(format!("Not applied: {why}.")),
        }
    }
}

fn required_str<'a>(args: &'a Value, key: &str) -> Result<&'a str, String> {
    match args[key].as_str() {
        Some(s) if !s.trim().is_empty() => Ok(s),
        _ => Err(format!("missing required argument {key:?}")),
    }
}

/// Validates `operations` against the tulsi-state Op format; returns JSON.
fn operations(args: &Value) -> Result<String, String> {
    let ops: Vec<Op> = serde_json::from_value(args["operations"].clone())
        .map_err(|e| format!("invalid operations: {e}"))?;
    if ops.is_empty() {
        return Err("operations must not be empty".into());
    }
    Ok(serde_json::to_string(&ops).expect("ops serialize"))
}

fn job_output(result: JobResult) -> Result<ToolOutput, String> {
    if !result.ran {
        Ok(ToolOutput::ok("Nothing to change."))
    } else if result.success {
        Ok(ToolOutput::data(
            format!("Applied and rebuilt: {}", result.message),
            json!({ "success": true, "message": result.message }),
        ))
    } else {
        Ok(ToolOutput {
            text: format!(
                "The change failed and was rolled back; nothing changed.\n{}",
                result.message
            ),
            structured: Some(json!({ "success": false, "message": result.message })),
            is_error: true,
        })
    }
}

fn operations_schema() -> Value {
    json!({
        "type": "array",
        "minItems": 1,
        "description": "Changes to make. Examples: {\"op\":\"addPackage\",\"name\":\"vlc\"}, \
            {\"op\":\"removePackage\",\"name\":\"gimp\"}, \
            {\"op\":\"addExtension\",\"browser\":\"firefox\",\"id\":\"uBlock0@raymondhill.net\"}, \
            {\"op\":\"setService\",\"name\":\"printing\",\"enable\":true}",
        "items": {
            "type": "object",
            "required": ["op"],
            "properties": {
                "op": { "enum": ["addPackage", "removePackage", "addExtension", "removeExtension", "setService"] },
                "name": { "type": "string", "description": "nixpkgs attribute (packages) or NixOS service name" },
                "browser": { "enum": ["firefox", "chromium"] },
                "id": { "type": "string", "description": "browser extension id" },
                "enable": { "type": "boolean" }
            }
        }
    })
}

fn tool(name: &str, title: &str, description: &str, schema: Value, read_only: bool) -> Value {
    json!({
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": schema,
        "annotations": {
            "title": title,
            "readOnlyHint": read_only,
            "destructiveHint": !read_only,
            "idempotentHint": read_only,
            "openWorldHint": false
        }
    })
}

fn tool_list() -> Vec<Value> {
    let empty = json!({ "type": "object", "properties": {} });
    let reason =
        json!({ "type": "string", "description": "Why, in one sentence; shown to the human." });
    vec![
        tool("search_packages", "Search packages",
            "Search the ~137k nixpkgs packages by name or description. Returns attribute names to use in operations.",
            json!({ "type": "object", "required": ["query"], "properties": {
                "query": { "type": "string" },
                "limit": { "type": "integer", "minimum": 1, "maximum": 50, "default": 10 } } }), true),
        tool("package_info", "Package details", "Details of one package by attribute name.",
            json!({ "type": "object", "required": ["attr"], "properties": { "attr": { "type": "string" } } }), true),
        tool("get_state", "Managed state",
            "Packages, browser extensions and service toggles managed by TulsiOS (state.json).", empty.clone(), true),
        tool("read_configuration", "Read configuration.nix",
            "The user's own NixOS configuration file.", empty.clone(), true),
        tool("history", "Change history", "Recent system changes, newest first.",
            json!({ "type": "object", "properties": {
                "limit": { "type": "integer", "minimum": 1, "maximum": 100, "default": 10 } } }), true),
        tool("plan_change", "Plan a change", "Show what operations would change. Applies nothing.",
            json!({ "type": "object", "required": ["operations"], "properties": { "operations": operations_schema() } }), true),
        tool("apply_change", "Apply a change",
            "Apply operations after the human approves, then rebuild the system. Rolled back automatically if the rebuild fails.",
            json!({ "type": "object", "required": ["operations", "reason"], "properties": {
                "operations": operations_schema(), "reason": reason.clone() } }), false),
        tool("undo_last_change", "Undo the latest change",
            "Revert the most recent system change after the human approves.",
            json!({ "type": "object", "required": ["reason"], "properties": { "reason": reason.clone() } }), false),
        tool("propose_configuration_edit", "Propose a configuration.nix edit",
            "Check new COMPLETE contents for configuration.nix (syntax) and show the diff. Applies nothing.",
            json!({ "type": "object", "required": ["contents"], "properties": {
                "contents": { "type": "string", "description": "The complete new file." } } }), true),
        tool("apply_configuration_edit", "Apply a configuration.nix edit",
            "Replace configuration.nix with new COMPLETE contents after the human approves, then rebuild. Rolled back if the rebuild fails.",
            json!({ "type": "object", "required": ["contents", "summary", "reason"], "properties": {
                "contents": { "type": "string", "description": "The complete new file." },
                "summary": { "type": "string", "description": "Short description for the history, e.g. 'enable Bluetooth'." },
                "reason": reason.clone() } }), false),
        tool("fetch_source", "Fetch software to package",
            "Download a URL (or take a file already in the Nix store) and describe it: kind, hash, contents, build hints, and how to reference it as src.",
            json!({ "type": "object", "properties": {
                "url": { "type": "string", "description": "http(s) URL of the download" },
                "store_path": { "type": "string", "description": "/nix/store/… path of a file the user provided" } } }), true),
        tool("build_package", "Build a local package",
            "Save a callPackage Nix expression as the draft of local package `name` and build it in Nix's sandbox. Returns the programs built, or the build log tail.",
            json!({ "type": "object", "required": ["name", "expression"], "properties": {
                "name": { "type": "string", "description": "lowercase name, e.g. 'frob'" },
                "expression": { "type": "string", "description": "the complete package.nix" } } }), false),
        tool("try_package", "Try a built package",
            "Run a program of the last build of `name` briefly (default --version) with an empty HOME and no display.",
            json!({ "type": "object", "required": ["name"], "properties": {
                "name": { "type": "string" },
                "program": { "type": "string", "description": "file name in bin/ (default: the first)" },
                "args": { "type": "array", "items": { "type": "string" } } } }), false),
        tool("propose_local_package", "Install a local package",
            "Ask the human to add the built package to this computer (they see the whole expression), then rebuild. It appears in the Software Center under 'Made on this computer'.",
            json!({ "type": "object", "required": ["name", "expression", "reason"], "properties": {
                "name": { "type": "string" },
                "expression": { "type": "string", "description": "the exact package.nix that was built" },
                "version": { "type": "string" },
                "description": { "type": "string" },
                "origin": { "type": "string", "description": "where the software came from (URL or file name)" },
                "reason": reason } }), false),
    ]
}

#[cfg(test)]
mod tests {
    use std::sync::Mutex;

    use super::*;
    use crate::approval::Mode;
    use tulsi_client::{ConfigPlan, HistoryEntry, PackageInfo, Plan, State};

    #[derive(Default)]
    struct Fake {
        applied: Mutex<Vec<String>>,
        configs: Mutex<Vec<String>>,
        undone: Mutex<u32>,
    }

    impl Backend for &Fake {
        async fn get_state(&self) -> Result<String, String> {
            Ok(State::default().to_json_pretty())
        }
        async fn search(&self, query: &str, _: u32) -> Result<Vec<PackageInfo>, String> {
            Ok(vec![PackageInfo {
                attr: query.into(),
                pname: query.into(),
                version: "1.0".into(),
                description: "a package".into(),
                unfree: false,
                installed: false,
                license: None,
                license_accepted: false,
                local: false,
                origin: String::new(),
            }])
        }
        async fn package_info(&self, attr: &str) -> Result<PackageInfo, String> {
            Err(format!("NotFound: no package \"{attr}\""))
        }
        async fn history(&self, _: u32) -> Result<Vec<HistoryEntry>, String> {
            Ok(vec![HistoryEntry {
                commit: "abc1234".into(),
                time: 0,
                summary: "tulsi: install vlc".into(),
            }])
        }
        async fn plan(&self, ops: &str) -> Result<Plan, String> {
            let ops: Vec<Op> = serde_json::from_str(ops).unwrap();
            let new = State::default().with_ops(&ops).map_err(|e| e.to_string())?;
            Ok(Plan {
                changes: State::default().diff(&new),
                state: new,
            })
        }
        async fn apply(&self, ops: &str) -> Result<JobResult, String> {
            self.applied.lock().unwrap().push(ops.into());
            Ok(JobResult {
                ran: true,
                success: true,
                message: "tulsi: install vlc (commit 1)".into(),
            })
        }
        async fn undo(&self) -> Result<JobResult, String> {
            *self.undone.lock().unwrap() += 1;
            Ok(JobResult {
                ran: true,
                success: true,
                message: "undone".into(),
            })
        }
        async fn get_config(&self) -> Result<String, String> {
            Ok("{ }\n".into())
        }
        async fn plan_config(&self, contents: &str) -> Result<ConfigPlan, String> {
            Ok(ConfigPlan {
                changed: contents != "{ }\n",
                diff: "-{ }\n+{ x = 1; }\n".into(),
            })
        }
        async fn apply_config(&self, contents: &str, _: &str) -> Result<JobResult, String> {
            self.configs.lock().unwrap().push(contents.into());
            Ok(JobResult {
                ran: true,
                success: true,
                message: "edited".into(),
            })
        }
    }

    const INIT: &str = r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}"#;
    const INIT_ELICIT: &str = r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{"elicitation":{}},"clientInfo":{"name":"test","version":"0"}}}"#;
    const INSTALL: &str = r#"{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"apply_change","arguments":{"operations":[{"op":"addPackage","name":"vlc"}],"reason":"user asked for a media player"}}}"#;

    /// Runs a session; returns the server's output messages.
    async fn session(fake: &Fake, mode: Mode, command: &[&str], input: &[&str]) -> Vec<Value> {
        let input = input.join("\n") + "\n";
        let mut transport = Transport::new(input.as_bytes(), Vec::new());
        let approver = Approver {
            mode,
            command: command.iter().map(|s| s.to_string()).collect(),
        };
        Server::new(fake, approver).serve(&mut transport).await;
        String::from_utf8(transport.into_writer())
            .unwrap()
            .lines()
            .map(|l| serde_json::from_str(l).unwrap())
            .collect()
    }

    fn text(msg: &Value) -> &str {
        msg["result"]["content"][0]["text"]
            .as_str()
            .unwrap_or_default()
    }

    #[tokio::test]
    async fn handshake_and_tool_list() {
        let fake = Fake::default();
        let out = session(
            &fake,
            Mode::Auto,
            &[],
            &[
                INIT,
                r#"{"jsonrpc":"2.0","method":"notifications/initialized"}"#,
                r#"{"jsonrpc":"2.0","id":2,"method":"tools/list"}"#,
                r#"{"jsonrpc":"2.0","id":3,"method":"nope"}"#,
                "not json",
            ],
        )
        .await;
        assert_eq!(out[0]["result"]["protocolVersion"], "2025-06-18");
        assert_eq!(out[0]["result"]["serverInfo"]["name"], "tulsi-mcp");
        let tools: Vec<&str> = out[1]["result"]["tools"]
            .as_array()
            .unwrap()
            .iter()
            .map(|t| t["name"].as_str().unwrap())
            .collect();
        assert_eq!(tools.len(), 14);
        assert!(tools.contains(&"propose_local_package"));
        assert!(tools.contains(&"apply_configuration_edit"));
        assert_eq!(out[2]["error"]["code"], METHOD_NOT_FOUND);
        assert_eq!(out[3]["error"]["code"], crate::transport::PARSE_ERROR);
    }

    #[tokio::test]
    async fn unknown_protocol_version_gets_newest() {
        let fake = Fake::default();
        let init = INIT.replace("2025-06-18", "1999-01-01");
        let out = session(&fake, Mode::Auto, &[], &[&init]).await;
        assert_eq!(out[0]["result"]["protocolVersion"], PROTOCOL_VERSIONS[0]);
    }

    #[tokio::test]
    async fn read_only_tools_need_no_approval() {
        let fake = Fake::default();
        let out = session(&fake, Mode::Dialog, &["false"], &[
            INIT,
            r#"{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"plan_change","arguments":{"operations":[{"op":"addPackage","name":"vlc"}]}}}"#,
            r#"{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search_packages","arguments":{"query":"vlc"}}}"#,
            r#"{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"package_info","arguments":{"attr":"nope"}}}"#,
        ]).await;
        assert!(text(&out[1]).contains("+ package vlc"), "{}", out[1]);
        assert_eq!(
            out[2]["result"]["structuredContent"]["packages"][0]["attr"],
            "vlc"
        );
        assert_eq!(out[3]["result"]["isError"], true);
        assert!(fake.applied.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn approved_dialog_applies() {
        let fake = Fake::default();
        let out = session(&fake, Mode::Dialog, &["true"], &[INIT, INSTALL]).await;
        assert_eq!(out[1]["result"]["isError"], false, "{}", out[1]);
        assert!(text(&out[1]).starts_with("Applied and rebuilt"));
        assert_eq!(fake.applied.lock().unwrap().len(), 1);
    }

    #[tokio::test]
    async fn rejected_dialog_applies_nothing() {
        let fake = Fake::default();
        let out = session(&fake, Mode::Dialog, &["false"], &[INIT, INSTALL]).await;
        assert_eq!(out[1]["result"]["isError"], true);
        assert!(text(&out[1]).contains("rejected"), "{}", out[1]);
        assert!(fake.applied.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn no_approval_channel_means_no_change() {
        // Auto mode, client without elicitation, no dialog program.
        let fake = Fake::default();
        let out = session(
            &fake,
            Mode::Auto,
            &["/nonexistent/approver"],
            &[INIT, INSTALL],
        )
        .await;
        assert_eq!(out[1]["result"]["isError"], true);
        assert!(
            text(&out[1]).contains("no way to ask the user"),
            "{}",
            out[1]
        );
        assert!(fake.applied.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn elicitation_accept_and_decline() {
        let fake = Fake::default();
        let accept = r#"{"jsonrpc":"2.0","id":"tulsi-1","result":{"action":"accept","content":{"approve":true}}}"#;
        let out = session(
            &fake,
            Mode::Elicitation,
            &[],
            &[INIT_ELICIT, INSTALL, accept],
        )
        .await;
        assert_eq!(out[1]["method"], "elicitation/create");
        assert!(out[1]["params"]["message"]
            .as_str()
            .unwrap()
            .contains("+ package vlc"));
        assert_eq!(out[2]["result"]["isError"], false, "{}", out[2]);
        assert_eq!(fake.applied.lock().unwrap().len(), 1);

        let fake = Fake::default();
        let decline = r#"{"jsonrpc":"2.0","id":"tulsi-1","result":{"action":"accept","content":{"approve":false}}}"#;
        let out = session(
            &fake,
            Mode::Elicitation,
            &[],
            &[INIT_ELICIT, INSTALL, decline],
        )
        .await;
        assert_eq!(out[2]["result"]["isError"], true);
        assert!(fake.applied.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn requests_arriving_during_elicitation_are_answered_after() {
        let fake = Fake::default();
        let ping = r#"{"jsonrpc":"2.0","id":7,"method":"ping"}"#;
        let accept = r#"{"jsonrpc":"2.0","id":"tulsi-1","result":{"action":"accept","content":{"approve":true}}}"#;
        let out = session(
            &fake,
            Mode::Elicitation,
            &[],
            &[INIT_ELICIT, INSTALL, ping, accept],
        )
        .await;
        assert_eq!(out[2]["id"], 2);
        assert_eq!(out[3]["id"], 7);
    }

    #[tokio::test]
    async fn configuration_edit_and_undo_need_approval() {
        let fake = Fake::default();
        let edit = r#"{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"apply_configuration_edit","arguments":{"contents":"{ x = 1; }\n","summary":"set x","reason":"testing"}}}"#;
        let undo = r#"{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"undo_last_change","arguments":{"reason":"testing"}}}"#;
        let missing = r#"{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"apply_change","arguments":{"operations":[{"op":"addPackage","name":"vlc"}]}}}"#;
        let out = session(&fake, Mode::Dialog, &["true"], &[INIT, edit, undo, missing]).await;
        assert_eq!(fake.configs.lock().unwrap().as_slice(), ["{ x = 1; }\n"]);
        assert_eq!(*fake.undone.lock().unwrap(), 1);
        assert!(
            text(&out[3]).contains("missing required argument \"reason\""),
            "{}",
            out[3]
        );
        assert!(fake.applied.lock().unwrap().is_empty());
    }
}
