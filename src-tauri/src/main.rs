// Sin consola en release; `--self-test` se engancha a la consola de quien lo lance.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod download;
mod logs;
mod paths;
mod platform;
mod selftest;
mod tools;

use tauri::Manager;

fn main() {
    platform::init_process();
    let _log_guard = logs::init();
    tracing::info!("=== MXP Suite {} ===", env!("CARGO_PKG_VERSION"));

    let args: Vec<String> = std::env::args().collect();
    if args.iter().any(|a| a == "--self-test") {
        platform::attach_parent_console();
        std::process::exit(selftest::run_cli(&args));
    }

    // Sin WebView2 Tauri no puede abrir la ventana: mejor un mensaje claro que un cierre mudo.
    if platform::webview2_version().is_none() {
        tracing::error!("WebView2 no está instalado");
        platform::fatal_message(
            "MXP Suite necesita Microsoft Edge WebView2",
            "Falta un componente de Windows (Microsoft Edge WebView2).\n\n\
             Vuelve a ejecutar el instalador de MXP Suite: lo instala solo.",
        );
        std::process::exit(2);
    }

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // Segunda instancia: se trae al frente la ventana que ya estaba abierta.
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.set_focus();
            }
        }))
        .manage(commands::Jobs::default())
        .invoke_handler(tauri::generate_handler![
            commands::tools_status,
            commands::app_info,
            commands::download_start,
            commands::download_cancel,
            commands::video_info,
            commands::playlist_expand,
        ])
        .run(tauri::generate_context!())
        .unwrap_or_else(|e| {
            tracing::error!("Tauri no arrancó: {e:?}");
            platform::fatal_message("MXP Suite no pudo arrancar", &format!("{e}"));
            std::process::exit(1);
        });
}
