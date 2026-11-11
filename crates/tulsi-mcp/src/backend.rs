//! What the MCP tools need from the system: tulsid over D-Bus in production,
//! a fake in tests.

use futures_util::StreamExt;
use tulsi_client::{ConfigPlan, HistoryEntry, ManagerProxy, PackageInfo, Plan};

/// Outcome of a change job.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct JobResult {
    /// False if there was nothing to change (no job ran).
    pub ran: bool,
    pub success: bool,
    pub message: String,
}

#[allow(async_fn_in_trait)]
pub trait Backend {
    async fn get_state(&self) -> Result<String, String>;
    async fn search(&self, query: &str, limit: u32) -> Result<Vec<PackageInfo>, String>;
    async fn package_info(&self, attr: &str) -> Result<PackageInfo, String>;
    async fn history(&self, limit: u32) -> Result<Vec<HistoryEntry>, String>;
    async fn plan(&self, ops_json: &str) -> Result<Plan, String>;
    async fn apply(&self, ops_json: &str) -> Result<JobResult, String>;
    async fn undo(&self) -> Result<JobResult, String>;
    async fn get_config(&self) -> Result<String, String>;
    async fn plan_config(&self, contents: &str) -> Result<ConfigPlan, String>;
    async fn apply_config(&self, contents: &str, summary: &str) -> Result<JobResult, String>;
}

pub struct Dbus {
    proxy: ManagerProxy<'static>,
}

impl Dbus {
    pub async fn connect() -> Result<Self, String> {
        let conn = tulsi_client::connect()
            .await
            .map_err(|e| format!("cannot connect to D-Bus: {e}"))?;
        let proxy = ManagerProxy::new(&conn).await.map_err(err)?;
        Ok(Self { proxy })
    }

    /// Subscribes to Finished first, starts the job, waits for its result.
    async fn run_job<F>(&self, start: F) -> Result<JobResult, String>
    where
        F: std::future::Future<Output = zbus::Result<u64>>,
    {
        let mut finished = self.proxy.receive_finished().await.map_err(err)?;
        let job = start.await.map_err(err)?;
        if job == 0 {
            return Ok(JobResult {
                ran: false,
                success: true,
                message: "nothing to change".into(),
            });
        }
        while let Some(signal) = finished.next().await {
            let Ok(args) = signal.args() else { continue };
            if args.job == job {
                return Ok(JobResult {
                    ran: true,
                    success: args.success,
                    message: args.message.clone(),
                });
            }
        }
        Err("lost connection to tulsid".into())
    }
}

/// tulsid's errors carry the useful text in the method error message.
fn err(e: zbus::Error) -> String {
    match e {
        zbus::Error::MethodError(name, Some(msg), _) => {
            if name.as_str() == "org.freedesktop.DBus.Error.ServiceUnknown" {
                "tulsid (the TulsiOS system service) is not running".into()
            } else {
                let kind = name.as_str().trim_start_matches("org.tulsi.Error.");
                format!("{kind}: {msg}")
            }
        }
        other => other.to_string(),
    }
}

fn decode<T: serde::de::DeserializeOwned>(text: String) -> Result<T, String> {
    serde_json::from_str(&text).map_err(|e| format!("unexpected reply from tulsid: {e}"))
}

impl Backend for Dbus {
    async fn get_state(&self) -> Result<String, String> {
        self.proxy.get_state().await.map_err(err)
    }
    async fn search(&self, query: &str, limit: u32) -> Result<Vec<PackageInfo>, String> {
        decode(self.proxy.search(query, limit).await.map_err(err)?)
    }
    async fn package_info(&self, attr: &str) -> Result<PackageInfo, String> {
        decode(self.proxy.package_info(attr).await.map_err(err)?)
    }
    async fn history(&self, limit: u32) -> Result<Vec<HistoryEntry>, String> {
        decode(self.proxy.history(limit).await.map_err(err)?)
    }
    async fn plan(&self, ops_json: &str) -> Result<Plan, String> {
        decode(self.proxy.plan(ops_json).await.map_err(err)?)
    }
    async fn apply(&self, ops_json: &str) -> Result<JobResult, String> {
        self.run_job(self.proxy.apply(ops_json)).await
    }
    async fn undo(&self) -> Result<JobResult, String> {
        self.run_job(self.proxy.undo()).await
    }
    async fn get_config(&self) -> Result<String, String> {
        self.proxy.get_config().await.map_err(err)
    }
    async fn plan_config(&self, contents: &str) -> Result<ConfigPlan, String> {
        decode(self.proxy.plan_config(contents).await.map_err(err)?)
    }
    async fn apply_config(&self, contents: &str, summary: &str) -> Result<JobResult, String> {
        self.run_job(self.proxy.apply_config(contents, summary))
            .await
    }
}
