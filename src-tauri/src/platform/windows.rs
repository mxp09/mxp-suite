use std::ffi::OsString;
use std::os::windows::ffi::{OsStrExt, OsStringExt};
use std::path::PathBuf;

use windows_sys::Win32::System::Console::{AttachConsole, ATTACH_PARENT_PROCESS};
use windows_sys::Win32::System::Diagnostics::Debug::{
    SetErrorMode, SEM_FAILCRITICALERRORS, SEM_NOOPENFILEERRORBOX,
};
use windows_sys::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONERROR, MB_OK};
use winreg::enums::{HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE};
use winreg::RegKey;

/// Ajustes de proceso que se aplican antes que nada.
pub fn init_process() {
    // Si a un binario hijo (ffmpeg, yt-dlp, whisper) le falta una DLL, Windows
    // abre un diálogo modal que congela todo hasta que alguien pulsa Aceptar.
    // Con este modo (lo heredan los hijos) simplemente falla con un código que
    // la app sabe traducir.
    unsafe {
        SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX);
    }
}

/// `mxp-suite.exe --self-test` desde una terminal: que se vea la salida.
pub fn attach_parent_console() {
    unsafe {
        AttachConsole(ATTACH_PARENT_PROCESS);
    }
}

fn wide(s: &str) -> Vec<u16> {
    std::ffi::OsStr::new(s).encode_wide().chain(Some(0)).collect()
}

/// Mensaje de error nativo, para cuando no hay ventana de la app que lo muestre.
pub fn fatal_message(title: &str, body: &str) {
    let (t, b) = (wide(title), wide(body));
    unsafe {
        MessageBoxW(std::ptr::null_mut(), b.as_ptr(), t.as_ptr(), MB_OK | MB_ICONERROR);
    }
}

const WEBVIEW2_GUID: &str = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}";

/// Versión instalada de WebView2, o None. Rutas oficiales de Microsoft:
/// por máquina (32/64 bits) y por usuario.
pub fn webview2_version() -> Option<String> {
    let keys = [
        (HKEY_LOCAL_MACHINE, format!(r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}")),
        (HKEY_LOCAL_MACHINE, format!(r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}")),
        (HKEY_CURRENT_USER, format!(r"Software\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}")),
    ];
    keys.iter().find_map(|(root, path)| {
        let v: String = RegKey::predef(*root).open_subkey(path).ok()?.get_value("pv").ok()?;
        (!v.is_empty() && v != "0.0.0.0").then_some(v)
    })
}

/// (versión legible, número de build). Windows 10 1809 = build 17763.
pub fn os_version() -> (String, u32) {
    let key = RegKey::predef(HKEY_LOCAL_MACHINE)
        .open_subkey(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion");
    let Ok(key) = key else { return ("desconocida".into(), 0) };
    let build: u32 = key
        .get_value::<String, _>("CurrentBuildNumber")
        .ok()
        .and_then(|b| b.parse().ok())
        .unwrap_or(0);
    let name: String = key.get_value("ProductName").unwrap_or_default();
    let display: String = key.get_value("DisplayVersion").unwrap_or_default();
    // ProductName dice "Windows 10" también en Windows 11; el build lo desempata.
    let name = if build >= 22000 { name.replace("Windows 10", "Windows 11") } else { name };
    (format!("{name} {display} (build {build})").trim().to_string(), build)
}

/// Carpeta "Descargas" real del usuario (puede estar movida a OneDrive o a otro disco).
pub fn known_downloads_dir() -> Option<PathBuf> {
    use windows_sys::Win32::System::Com::CoTaskMemFree;
    use windows_sys::Win32::UI::Shell::{FOLDERID_Downloads, SHGetKnownFolderPath};
    unsafe {
        let mut ptr: *mut u16 = std::ptr::null_mut();
        if SHGetKnownFolderPath(&FOLDERID_Downloads, 0, std::ptr::null_mut(), &mut ptr) != 0 {
            return None;
        }
        let len = (0..).take_while(|&i| *ptr.add(i) != 0).count();
        let path = OsString::from_wide(std::slice::from_raw_parts(ptr, len));
        CoTaskMemFree(ptr as _);
        Some(PathBuf::from(path))
    }
}

/// Lanza un proceso sin abrir ventana de consola.
pub fn hide_console(cmd: &mut std::process::Command) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    cmd.creation_flags(CREATE_NO_WINDOW);
}

/// Traduce los códigos de salida de Windows que significan "no pudo ni arrancar".
pub fn explain_exit_code(code: i32) -> Option<&'static str> {
    match code as u32 {
        0xC000_0135 => Some("falta una DLL del sistema"),
        0xC000_007B => Some("binario de otra arquitectura (32/64 bits) o DLL dañada"),
        0xC000_001D => Some("tu procesador no soporta las instrucciones de este binario"),
        0xC000_0142 => Some("Windows no pudo inicializarlo (DLL bloqueada)"),
        0xC000_0005 => Some("se cerró por un acceso inválido a memoria"),
        _ => None,
    }
}
