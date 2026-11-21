//! Todo lo específico del sistema operativo vive aquí. El resto de la app no
//! llama a APIs de Windows directamente: añadir Mac o Linux será escribir otro
//! módulo con estas mismas funciones.

#[cfg(windows)]
mod windows;
#[cfg(windows)]
pub use self::windows::*;
