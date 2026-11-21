//! Log a %APPDATA%\MXP_Downloader\logs\mxp-suite.log (rota a diario).
//! Es lo que se pide cuando alguien dice "no me funciona".

use tracing_appender::non_blocking::WorkerGuard;

pub fn init() -> Option<WorkerGuard> {
    let appender = tracing_appender::rolling::daily(crate::paths::logs_dir(), "mxp-suite.log");
    let (writer, guard) = tracing_appender::non_blocking(appender);
    tracing_subscriber::fmt()
        .with_writer(writer)
        .with_ansi(false)
        .with_target(false)
        .try_init()
        .ok()?;
    Some(guard)
}
