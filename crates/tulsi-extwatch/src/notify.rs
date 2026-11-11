//! Desktop notifications (org.freedesktop.Notifications). Optional: without a
//! notification server, adoption still happens, just silently.

use std::collections::HashMap;
use std::time::Duration;

use futures_util::StreamExt;
use zbus::zvariant::Value;

use crate::scan::Found;

const APP_NAME: &str = "TulsiOS";
const ICON: &str = "system-software-install";
const KEEP_ACTION: &str = "keep-imperative";

#[zbus::proxy(
    interface = "org.freedesktop.Notifications",
    default_service = "org.freedesktop.Notifications",
    default_path = "/org/freedesktop/Notifications"
)]
trait Notifications {
    #[allow(clippy::too_many_arguments)]
    fn notify(
        &self,
        app_name: &str,
        replaces_id: u32,
        app_icon: &str,
        summary: &str,
        body: &str,
        actions: &[&str],
        hints: HashMap<&str, Value<'_>>,
        expire_timeout: i32,
    ) -> zbus::Result<u32>;

    #[zbus(signal)]
    fn action_invoked(&self, id: u32, action_key: String) -> zbus::Result<()>;
}

#[derive(Debug, PartialEq, Eq)]
pub enum Choice {
    Adopt,
    KeepImperative,
}

pub struct Notifier {
    proxy: Option<NotificationsProxy<'static>>,
    /// Notification to replace with the result, per extension key.
    ids: std::sync::Mutex<HashMap<String, u32>>,
}

impl Notifier {
    pub fn disabled() -> Self {
        Self {
            proxy: None,
            ids: Default::default(),
        }
    }

    pub async fn connect() -> Self {
        let proxy = async {
            let conn = zbus::Connection::session().await?;
            NotificationsProxy::new(&conn).await
        }
        .await;
        match proxy {
            Ok(p) => Self {
                proxy: Some(p),
                ids: Default::default(),
            },
            Err(e) => {
                eprintln!("tulsi-extwatch: notifications unavailable ({e}); continuing without");
                Self::disabled()
            }
        }
    }

    /// "This extension will be installed declaratively", with a "Keep it
    /// imperative" button that can be used during `grace`.
    pub async fn announce(&self, ext: &Found, grace: Duration) -> Choice {
        let Some(proxy) = &self.proxy else {
            return Choice::Adopt;
        };
        let mut actions = match proxy.receive_action_invoked().await {
            Ok(stream) => Some(stream),
            Err(_) => None,
        };
        let body = format!(
            "TulsiOS will install \u{201c}{}\u{201d} for {} declaratively: it becomes part of \
             your system configuration, so it is restored automatically and can be undone \
             in the Software Center.",
            ext.name,
            browser_title(ext),
        );
        let buttons: &[&str] = if grace.is_zero() {
            &[]
        } else {
            &[KEEP_ACTION, "Keep it imperative"]
        };
        let id = match proxy
            .notify(
                APP_NAME,
                0,
                ICON,
                "Extension will be installed declaratively",
                &body,
                buttons,
                HashMap::new(),
                0,
            )
            .await
        {
            Ok(id) => id,
            Err(e) => {
                eprintln!("tulsi-extwatch: notification failed: {e}");
                return Choice::Adopt;
            }
        };
        self.ids.lock().unwrap().insert(ext.key(), id);

        if grace.is_zero() {
            return Choice::Adopt;
        }
        let Some(actions) = actions.as_mut() else {
            tokio::time::sleep(grace).await;
            return Choice::Adopt;
        };
        let wait = async {
            while let Some(signal) = actions.next().await {
                if let Ok(args) = signal.args() {
                    if args.id == id && args.action_key == KEEP_ACTION {
                        return Choice::KeepImperative;
                    }
                }
            }
            Choice::Adopt
        };
        tokio::time::timeout(grace, wait)
            .await
            .unwrap_or(Choice::Adopt)
    }

    /// Replaces the announcement with the outcome.
    pub async fn done(&self, ext: &Found, error: Option<&str>) {
        let Some(proxy) = &self.proxy else { return };
        let replaces = self.ids.lock().unwrap().remove(&ext.key()).unwrap_or(0);
        let (summary, body) = match error {
            None => (
                "Extension installed declaratively".to_string(),
                format!(
                    "\u{201c}{}\u{201d} is now managed by TulsiOS. {}",
                    ext.name,
                    match ext.browser {
                        tulsi_client::Browser::Firefox => "Restart Firefox to complete the switch.",
                        tulsi_client::Browser::Chromium => "Your browser applies it automatically.",
                    }
                ),
            ),
            Some(e) => (
                "Extension stays imperative".to_string(),
                format!(
                    "\u{201c}{}\u{201d} could not be made declarative: {}",
                    ext.name,
                    e.lines().next().unwrap_or(e)
                ),
            ),
        };
        let _ = proxy
            .notify(
                APP_NAME,
                replaces,
                ICON,
                &summary,
                &body,
                &[],
                HashMap::new(),
                -1,
            )
            .await;
    }
}

fn browser_title(ext: &Found) -> &'static str {
    match ext.browser {
        tulsi_client::Browser::Firefox => "Firefox",
        tulsi_client::Browser::Chromium => "Chromium-based browsers",
    }
}
