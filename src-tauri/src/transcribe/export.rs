//! Exportación a TXT, MD, SRT, VTT, LRC, CSV, TSV, JSON, HTML, DOCX y PDF.
//! Port de core/transcription/exporters.py. La granularidad de los tiempos
//! (párrafo, frase, palabra, subtítulo) la elige el usuario y vale para todos.

use std::path::Path;

use super::model::{split_lines, Granularity, Span, Transcript};

pub const FORMATS: &[&str] = &["txt", "docx", "pdf", "srt", "vtt", "md", "html", "json", "csv", "tsv", "lrc"];

/// Granularidad por defecto: los subtítulos con frases de 30 s no sirven.
pub fn default_granularity(fmt: &str) -> Granularity {
    match fmt {
        "srt" | "vtt" | "lrc" => Granularity::Subtitle,
        _ => Granularity::Sentence,
    }
}

/// 62.345 s → "00:01:02,345" (SRT), "00:01:02.345" (VTT) o "01:02.3" (lectura).
pub fn ts(seconds: f64, sep: char, hours: bool) -> String {
    let ms = (seconds.max(0.0) * 1000.0).round() as u64;
    let (h, m, s, ms) = (ms / 3_600_000, ms / 60_000 % 60, ms / 1000 % 60, ms % 1000);
    if !hours {
        let base = if h > 0 { format!("{h}:{m:02}:{s:02}") } else { format!("{m:02}:{s:02}") };
        return format!("{base}.{}", ms / 100);
    }
    format!("{h:02}:{m:02}:{s:02}{sep}{ms:03}")
}

fn html_escape(s: &str) -> String {
    s.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;")
}

fn csv_field(s: &str, delim: char) -> String {
    if s.contains(delim) || s.contains('"') || s.contains('\n') {
        format!("\"{}\"", s.replace('"', "\"\""))
    } else {
        s.to_string()
    }
}

fn table(spans: &[Span], delim: char) -> String {
    let mut out = ["inicio", "fin", "inicio_s", "fin_s", "texto"].join(&delim.to_string()) + "\n";
    for s in spans {
        let row = [ts(s.start, ',', true), ts(s.end, ',', true), format!("{:.3}", s.start), format!("{:.3}", s.end), s.text()];
        out += &row.iter().map(|f| csv_field(f, delim)).collect::<Vec<_>>().join(&delim.to_string());
        out.push('\n');
    }
    out
}

/// Formatos de texto. `stamps` = poner tiempos donde el formato lo permite elegir.
pub fn render_text(t: &Transcript, fmt: &str, g: Granularity, stamps: bool) -> Option<String> {
    let spans = t.spans(g);
    let readable = |s: &Span| ts(s.start, '.', false);
    Some(match fmt {
        "txt" if !stamps => t.paragraphs().iter().map(|p| p.text()).collect::<Vec<_>>().join("\n\n") + "\n",
        "txt" => spans.iter().map(|s| format!("[{}] {}", readable(s), s.text())).collect::<Vec<_>>().join("\n") + "\n",
        "md" => {
            let mut out = format!("# {}\n\n", if t.source.is_empty() { "Transcripción" } else { &t.source });
            let list = if stamps { spans } else { t.paragraphs() };
            for s in list {
                if stamps {
                    out += &format!("**[{}]** ", readable(&s));
                }
                out += &s.text();
                out += "\n\n";
            }
            out
        }
        "srt" => spans
            .iter()
            .enumerate()
            .map(|(i, s)| format!("{}\n{} --> {}\n{}", i + 1, ts(s.start, ',', true), ts(s.end.max(s.start + 0.3), ',', true), split_lines(&s.text())))
            .collect::<Vec<_>>()
            .join("\n\n") + "\n",
        "vtt" => "WEBVTT\n\n".to_string()
            + &spans
                .iter()
                .map(|s| format!("{} --> {}\n{}", ts(s.start, '.', true), ts(s.end.max(s.start + 0.3), '.', true), split_lines(&s.text())))
                .collect::<Vec<_>>()
                .join("\n\n")
            + "\n",
        "lrc" => spans
            .iter()
            .map(|s| {
                let (m, sec) = ((s.start.max(0.0) / 60.0).floor(), s.start.max(0.0) % 60.0);
                format!("[{:02}:{:05.2}]{}", m as u64, sec, s.text())
            })
            .collect::<Vec<_>>()
            .join("\n") + "\n",
        // BOM: Excel abre bien los acentos.
        "csv" => format!("\u{feff}{}", table(&spans, ',')),
        "tsv" => table(&spans, '\t'),
        "json" => serde_json::to_string_pretty(&serde_json::json!({
            "source": t.source,
            "language": t.language,
            "duration": (t.duration * 1000.0).round() / 1000.0,
            "segments": spans.iter().map(|s| serde_json::json!({
                "start": (s.start * 1000.0).round() / 1000.0,
                "end": (s.end * 1000.0).round() / 1000.0,
                "text": s.text(),
                "words": s.words.iter().map(|w| serde_json::json!({
                    "start": (w.start * 1000.0).round() / 1000.0,
                    "end": (w.end * 1000.0).round() / 1000.0,
                    "word": w.text.trim(),
                    "probability": (w.p as f64 * 1000.0).round() / 1000.0,
                })).collect::<Vec<_>>(),
            })).collect::<Vec<_>>(),
        }))
        .ok()?,
        "html" => render_html(t, &spans, stamps),
        _ => return None,
    })
}

/// HTML autónomo: cada palabra lleva su tiempo; con el audio al lado, clic = saltar ahí.
fn render_html(t: &Transcript, spans: &[Span], stamps: bool) -> String {
    let title = html_escape(if t.source.is_empty() { "Transcripción" } else { &t.source });
    let audio = t
        .audio_path
        .as_deref()
        .filter(|p| Path::new(p).is_file())
        .map(|p| format!(r#"<audio id="a" controls src="file:///{}"></audio>"#, html_escape(&p.replace('\\', "/"))))
        .unwrap_or_default();
    let rows: String = spans
        .iter()
        .map(|s| {
            let words = if s.edited.is_some() {
                html_escape(&s.text())
            } else {
                s.words.iter().map(|w| format!(r#"<span data-t="{:.2}">{}</span>"#, w.start, html_escape(&w.text))).collect()
            };
            let stamp = if stamps { format!(r#"<time data-t="{:.2}">{}</time> "#, s.start, ts(s.start, '.', false)) } else { String::new() };
            format!("<p>{stamp}{words}</p>\n")
        })
        .collect();
    format!(
        r#"<!doctype html><html lang="{lang}"><meta charset="utf-8"><title>{title}</title>
<style>body{{background:#000;color:#F2F2F2;font:16px/1.7 Segoe UI,sans-serif;max-width:780px;margin:40px auto;padding:0 16px}}
h1{{color:#FFE600;font-size:22px}}time{{color:#FFE600;font-size:13px;cursor:pointer;margin-right:6px}}
span[data-t]:hover{{background:#1F1C00;cursor:pointer}}audio{{width:100%;margin-bottom:16px}}</style>
<h1>{title}</h1>{audio}
{rows}<script>document.addEventListener('click',e=>{{const t=e.target.dataset.t,a=document.getElementById('a');if(t&&a){{a.currentTime=+t;a.play()}}}})</script>
</html>"#,
        lang = html_escape(if t.language.is_empty() { "es" } else { &t.language }),
    )
}

fn meta_line(t: &Transcript) -> String {
    format!("Idioma: {}  ·  Duración: {}  ·  MXP Suite", t.language, ts(t.duration, '.', false))
}

fn save_docx(t: &Transcript, spans: &[Span], stamps: bool, path: &Path) -> Result<(), String> {
    use docx_rs::{Docx, Paragraph, Run};
    let title = if t.source.is_empty() { "Transcripción".to_string() } else { t.source.clone() };
    let mut doc = Docx::new()
        .add_paragraph(Paragraph::new().add_run(Run::new().add_text(title).bold().size(32)))
        .add_paragraph(Paragraph::new().add_run(Run::new().add_text(meta_line(t)).size(18).color("808080")));
    let list = if stamps { spans.to_vec() } else { t.paragraphs() };
    for s in list {
        let mut p = Paragraph::new();
        if stamps {
            p = p.add_run(Run::new().add_text(format!("[{}] ", ts(s.start, '.', false))).size(18).color("808080"));
        }
        doc = doc.add_paragraph(p.add_run(Run::new().add_text(s.text())));
    }
    let file = std::fs::File::create(path).map_err(|e| e.to_string())?;
    doc.build().pack(file).map_err(|e| e.to_string())
}

fn save_pdf(t: &Transcript, spans: &[Span], stamps: bool, path: &Path) -> Result<(), String> {
    use genpdf::{elements, fonts, style, Element};
    // Segoe UI viene con todo Windows y cubre acentos, ñ y demás.
    let dir = std::env::var("WINDIR").unwrap_or_else(|_| r"C:\Windows".into()) + r"\Fonts\";
    let load = |f: &str| {
        std::fs::read(format!("{dir}{f}")).map_err(|e| format!("falta la fuente {f}: {e}")).and_then(|b| fonts::FontData::new(b, None).map_err(|e| e.to_string()))
    };
    let family = fonts::FontFamily {
        regular: load("segoeui.ttf")?,
        bold: load("segoeuib.ttf")?,
        italic: load("segoeuii.ttf")?,
        bold_italic: load("segoeuiz.ttf")?,
    };
    let mut doc = genpdf::Document::new(family);
    doc.set_title(if t.source.is_empty() { "Transcripción" } else { &t.source });
    let mut deco = genpdf::SimplePageDecorator::new();
    deco.set_margins(15);
    doc.set_page_decorator(deco);
    doc.set_font_size(11);
    doc.push(elements::Paragraph::new(if t.source.is_empty() { "Transcripción".to_string() } else { t.source.clone() }).styled(style::Style::new().bold().with_font_size(16)));
    doc.push(elements::Paragraph::new(meta_line(t)).styled(style::Style::new().with_font_size(9).with_color(style::Color::Rgb(120, 120, 120))));
    doc.push(elements::Break::new(1));
    let list = if stamps { spans.to_vec() } else { t.paragraphs() };
    for s in list {
        let line = if stamps { format!("[{}]  {}", ts(s.start, '.', false), s.text()) } else { s.text() };
        doc.push(elements::Paragraph::new(line));
        doc.push(elements::Break::new(0.5));
    }
    doc.render_to_file(path).map_err(|e| e.to_string())
}

pub fn export(t: &Transcript, fmt: &str, path: &Path, g: Granularity, stamps: bool) -> Result<(), String> {
    let spans = t.spans(g);
    match fmt {
        "docx" => save_docx(t, &spans, stamps, path),
        "pdf" => save_pdf(t, &spans, stamps, path),
        _ => {
            let text = render_text(t, fmt, g, stamps).ok_or_else(|| format!("formato desconocido: {fmt}"))?;
            std::fs::write(path, text).map_err(|e| e.to_string())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::super::model::tests::sample;
    use super::*;

    #[test]
    fn timestamps() {
        assert_eq!(ts(62.345, ',', true), "00:01:02,345");
        assert_eq!(ts(62.345, '.', false), "01:02.3");
    }

    #[test]
    fn srt_and_vtt() {
        let t = sample();
        let srt = render_text(&t, "srt", Granularity::Subtitle, true).unwrap();
        assert!(srt.starts_with("1\n00:00:00,000 --> "));
        assert!(render_text(&t, "vtt", Granularity::Subtitle, true).unwrap().starts_with("WEBVTT"));
    }

    #[test]
    fn csv_has_bom_and_quotes() {
        let mut t = sample();
        t.apply_edits(&["Hola, \"mundo\".".into(), "Esto sigue".into(), "Tras pausa.".into()]);
        let csv = render_text(&t, "csv", Granularity::Sentence, true).unwrap();
        assert!(csv.starts_with('\u{feff}'));
        assert!(csv.contains("\"Hola, \"\"mundo\"\".\""));
    }

    #[test]
    fn html_escapes() {
        let mut t = sample();
        t.source = "<script>alert(1)</script>".into();
        let html = render_text(&t, "html", Granularity::Sentence, true).unwrap();
        assert!(!html.contains("<script>alert"));
    }

    #[test]
    fn every_format_writes_a_file() {
        let dir = std::env::temp_dir().join("mxp export ñ");
        std::fs::create_dir_all(&dir).unwrap();
        let t = sample();
        for fmt in FORMATS {
            let p = dir.join(format!("prueba.{fmt}"));
            export(&t, fmt, &p, default_granularity(fmt), true).unwrap_or_else(|e| panic!("{fmt}: {e}"));
            assert!(p.metadata().unwrap().len() > 20, "{fmt} vacío");
        }
        let _ = std::fs::remove_dir_all(&dir);
    }
}
