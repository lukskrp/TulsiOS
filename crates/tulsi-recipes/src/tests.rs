use super::*;

fn inspection(kind: Kind) -> Inspection {
    Inspection {
        kind: Some(kind),
        name: "frob".into(),
        version: "1.2".into(),
        description: "Frobnicates \"things\" for ${HOME}".into(),
        ..Default::default()
    }
}

fn answers(plan: &Plan) -> Answers {
    Answers {
        name: plan.name.clone(),
        version: plan.version.clone(),
        program: plan.program.clone(),
        menu: plan.menu,
        ..Default::default()
    }
}

fn source() -> Source {
    Source {
        store_name: "frob-1.2-frob.tar.gz".into(),
        hash: "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=".into(),
    }
}

fn expr(insp: Inspection, fixes: &Fixes) -> String {
    let plan = plan(&insp);
    expression(&plan, &answers(&plan), &source(), fixes).unwrap()
}

#[test]
fn names() {
    assert_eq!(local_name("My App 2"), "my-app-2");
    assert_eq!(local_name("2048"), "app-2048");
    assert_eq!(local_name("--x--"), "x");
    assert_eq!(
        store_name("frob", "1.2", Path::new("/d/Frob Setup (1).tar.gz")),
        "frob-1.2-Frob_Setup__1_.tar.gz"
    );
    assert_eq!(
        store_name("frob", "nightly", Path::new("x.AppImage")),
        "frob-0-x.AppImage"
    );
}

#[test]
fn which_recipe() {
    let mut deb = inspection(Kind::Deb);
    assert_eq!(plan(&deb).recipe, None, "a .deb without programs");
    deb.programs = vec!["frob".into()];
    assert_eq!(plan(&deb).recipe, Some(Recipe::Deb));
    let mut src = inspection(Kind::Archive);
    src.build_system = "meson".into();
    assert_eq!(plan(&src).recipe, Some(Recipe::Meson));
    src.build_system = "python".into();
    assert!(plan(&src).recipe.is_none() && plan(&src).why_not.contains("Python"));
    assert!(plan(&inspection(Kind::Installer)).recipe.is_none());
    let mut rpm = inspection(Kind::Rpm);
    rpm.programs = vec!["frob".into()];
    rpm.license = "GPL-3.0-or-later".into();
    assert_eq!(plan(&rpm).license, "free");
    rpm.license = "Proprietary".into();
    assert_eq!(plan(&rpm).license, "unfree");
}

#[test]
fn every_template_passes_the_safety_check() {
    let mut cases = vec![inspection(Kind::AppImage), inspection(Kind::Binary)];
    for kind in [Kind::Deb, Kind::Rpm] {
        let mut i = inspection(kind);
        i.programs = vec!["frob".into()];
        i.program_paths = vec!["usr/bin/frob".into()];
        i.desktop_files = vec!["usr/share/applications/frob.desktop".into()];
        i.electron = true;
        cases.push(i);
    }
    let mut archive = inspection(Kind::Archive);
    archive.programs = vec!["frob".into(), "frob-helper".into()];
    archive.program_paths = vec!["Frob-1.2/frob".into(), "Frob-1.2/bin/frob-helper".into()];
    archive.root = "Frob-1.2".into();
    archive.icons = vec!["Frob-1.2/icon.png".into()];
    cases.push(archive);
    for system in [
        "cmake",
        "meson",
        "autotools",
        "autoreconf",
        "make",
        "cargo",
        "go",
    ] {
        let mut i = inspection(Kind::Archive);
        i.build_system = system.into();
        cases.push(i);
    }
    let fixes = Fixes {
        inputs: ["xorg.libX11".to_string(), "gtk3".to_string()].into(),
        ignore_missing: ["libweird.so.3".to_string()].into(),
        dependency_hash: None,
    };
    for i in cases {
        let kind = i.kind;
        let e = expr(i, &fixes);
        assert!(
            tulsi_state::check_expression(&e).is_empty(),
            "{kind:?}:\n{e}"
        );
        assert!(e.contains("requireFile {"), "{e}");
        // Untrusted text is escaped, not interpolated.
        assert!(
            e.contains("Frobnicates \\\"things\\\" for \\${HOME}"),
            "{e}"
        );
    }
}

#[test]
fn prebuilt_packages() {
    let mut i = inspection(Kind::Deb);
    i.programs = vec!["frob".into()];
    i.electron = true;
    let fixes = Fixes {
        inputs: ["xorg.libX11".to_string()].into(),
        ..Default::default()
    };
    let e = expr(i, &fixes);
    assert!(e.starts_with("# Made by a TulsiOS recipe"), "{e}");
    assert!(e.contains("{ lib, stdenv, requireFile, autoPatchelfHook, dpkg, libGL, libnotify, libpulseaudio, systemd, xorg }:"), "{e}");
    assert!(e.contains("buildInputs = [ xorg.libX11 ];"), "{e}");
    assert!(
        e.contains("runtimeDependencies = [ libGL libnotify libpulseaudio systemd ];"),
        "{e}"
    );
    assert!(e.contains("dpkg-deb -x $src source"), "{e}");
    assert!(e.contains("chrome-sandbox -delete"), "{e}");

    let mut a = inspection(Kind::Archive);
    a.programs = vec!["frob".into()];
    a.program_paths = vec!["Frob-1.2/frob".into()];
    a.root = "Frob-1.2".into();
    a.icons = vec!["Frob-1.2/icon.png".into()];
    let e = expr(a, &Fixes::default());
    assert!(
        e.contains("makeWrapper $out/share/${pname}/'frob' $out/bin/'frob'"),
        "{e}"
    );
    assert!(
        e.contains("install -Dm444 'icon.png' $out/share/icons/hicolor/256x256/apps/${pname}.png"),
        "{e}"
    );
    assert!(e.contains("makeDesktopItem {"), "{e}");
}

#[test]
fn unusual_paths_are_refused() {
    let mut a = inspection(Kind::Archive);
    a.programs = vec!["frob".into()];
    a.program_paths = vec!["x/frob".into()];
    a.root = "it's ${here}".into();
    let plan = plan(&a);
    assert!(expression(&plan, &answers(&plan), &source(), &Fixes::default()).is_err());
}

#[test]
fn dependency_hashes_and_unfree() {
    let mut i = inspection(Kind::Archive);
    i.build_system = "cargo".into();
    let p = plan(&i);
    let mut ans = answers(&p);
    ans.unfree = true;
    let first = expression(&p, &ans, &source(), &Fixes::default()).unwrap();
    assert!(first.contains("cargoHash = lib.fakeHash;"), "{first}");
    assert!(first.contains("license = lib.licenses.unfree;"), "{first}");
    let fixes = Fixes {
        dependency_hash: Some(Some("sha256-BBBB=".into())),
        ..Default::default()
    };
    let second = expression(&p, &ans, &source(), &fixes).unwrap();
    assert!(second.contains("cargoHash = \"sha256-BBBB=\";"), "{second}");
}

#[test]
fn tables() {
    assert_eq!(
        package_for_soname("libX11.so.6").as_deref(),
        Some("xorg.libX11")
    );
    assert_eq!(package_for_soname("libnss3.so").as_deref(), Some("nss"));
    assert_eq!(package_for_soname("libnothing.so.1"), None);
    assert_eq!(package_for_dependency("GTK+-3.0").as_deref(), Some("gtk3"));
    assert_eq!(package_for_dependency("ZLIB").as_deref(), Some("zlib"));
}
