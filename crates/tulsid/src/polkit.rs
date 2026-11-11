//! Minimal polkit client: asks whether the D-Bus caller may perform an action.

use std::collections::HashMap;

use zbus::zvariant::Value;

#[zbus::proxy(
    interface = "org.freedesktop.PolicyKit1.Authority",
    default_service = "org.freedesktop.PolicyKit1",
    default_path = "/org/freedesktop/PolicyKit1/Authority"
)]
trait Authority {
    fn check_authorization(
        &self,
        subject: &(&str, HashMap<&str, Value<'_>>),
        action_id: &str,
        details: HashMap<&str, &str>,
        flags: u32,
        cancellation_id: &str,
    ) -> zbus::Result<(bool, bool, HashMap<String, String>)>;
}

const ALLOW_USER_INTERACTION: u32 = 1;

/// Returns `Ok(true)` if `sender` (a unique bus name) is authorized for
/// `action`. Polkit may prompt the user through their authentication agent.
pub async fn check(conn: &zbus::Connection, sender: &str, action: &str) -> zbus::Result<bool> {
    let authority = AuthorityProxy::new(conn).await?;
    let mut subject_details = HashMap::new();
    subject_details.insert("name", Value::from(sender));
    let (authorized, _challenge, _details) = authority
        .check_authorization(
            &("system-bus-name", subject_details),
            action,
            HashMap::new(),
            ALLOW_USER_INTERACTION,
            "",
        )
        .await?;
    Ok(authorized)
}
