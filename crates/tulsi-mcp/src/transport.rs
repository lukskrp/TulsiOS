//! Newline-delimited JSON-RPC 2.0 over a byte stream (MCP's stdio transport).
//!
//! Besides answering client requests, the server sometimes needs to ask the
//! client something (MCP elicitation) while handling a request. `request`
//! sends a server→client request and reads until its response arrives,
//! keeping any other messages for later.

use std::collections::VecDeque;

use serde_json::{json, Value};
use tokio::io::{AsyncBufReadExt, AsyncRead, AsyncWrite, AsyncWriteExt, BufReader, Lines};

pub const PARSE_ERROR: i64 = -32700;
pub const INVALID_REQUEST: i64 = -32600;
pub const METHOD_NOT_FOUND: i64 = -32601;
pub const INVALID_PARAMS: i64 = -32602;

pub struct Transport<R, W> {
    lines: Lines<BufReader<R>>,
    writer: W,
    backlog: VecDeque<Value>,
    next_id: u64,
}

impl<R: AsyncRead + Unpin, W: AsyncWrite + Unpin> Transport<R, W> {
    pub fn new(reader: R, writer: W) -> Self {
        Self {
            lines: BufReader::new(reader).lines(),
            writer,
            backlog: VecDeque::new(),
            next_id: 1,
        }
    }

    /// Next message from the client, or None at end of input.
    pub async fn next_message(&mut self) -> Option<Value> {
        if let Some(msg) = self.backlog.pop_front() {
            return Some(msg);
        }
        self.read_line_message().await
    }

    async fn read_line_message(&mut self) -> Option<Value> {
        loop {
            let line = self.lines.next_line().await.ok().flatten()?;
            if line.trim().is_empty() {
                continue;
            }
            match serde_json::from_str::<Value>(&line) {
                Ok(msg) if msg.is_object() => return Some(msg),
                Ok(_) => {
                    self.error(Value::Null, INVALID_REQUEST, "expected a JSON object")
                        .await
                }
                Err(e) => {
                    self.error(Value::Null, PARSE_ERROR, &format!("parse error: {e}"))
                        .await
                }
            }
        }
    }

    pub async fn send(&mut self, msg: &Value) {
        let mut line = msg.to_string();
        line.push('\n');
        // If the client went away there is nobody to report to.
        let _ = self.writer.write_all(line.as_bytes()).await;
        let _ = self.writer.flush().await;
    }

    pub async fn reply(&mut self, id: Value, result: Value) {
        self.send(&json!({ "jsonrpc": "2.0", "id": id, "result": result }))
            .await;
    }

    pub async fn error(&mut self, id: Value, code: i64, message: &str) {
        self.send(&json!({
            "jsonrpc": "2.0", "id": id, "error": { "code": code, "message": message }
        }))
        .await;
    }

    /// Sends a request to the client and waits for its response.
    pub async fn request(&mut self, method: &str, params: Value) -> Result<Value, String> {
        let id = format!("tulsi-{}", self.next_id);
        self.next_id += 1;
        self.send(&json!({ "jsonrpc": "2.0", "id": id, "method": method, "params": params }))
            .await;
        loop {
            let Some(msg) = self.read_line_message().await else {
                return Err("the client closed the connection".into());
            };
            let is_response = msg.get("method").is_none();
            if is_response && msg["id"] == json!(id) {
                if let Some(err) = msg.get("error") {
                    return Err(err["message"]
                        .as_str()
                        .unwrap_or("client error")
                        .to_string());
                }
                return Ok(msg["result"].clone());
            }
            self.backlog.push_back(msg);
        }
    }

    #[cfg(test)]
    pub fn into_writer(self) -> W {
        self.writer
    }
}
