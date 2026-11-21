fn main() {
    // Manifiesto propio: añade longPathAware (rutas de más de 260 caracteres)
    // conservando lo que Tauri pone por defecto (Common Controls v6, DPI).
    let windows = tauri_build::WindowsAttributes::new()
        .app_manifest(include_str!("windows-app-manifest.xml"));
    tauri_build::try_build(tauri_build::Attributes::new().windows_attributes(windows))
        .expect("tauri-build falló");
}
