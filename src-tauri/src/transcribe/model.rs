//! Una transcripción y su segmentación en frases, párrafos y subtítulos.
//! Todo parte de las PALABRAS con su tiempo: de ahí sale cualquier
//! granularidad sin volver a transcribir. Port de core/transcription/model.py.

use serde::{Deserialize, Serialize};

const SENTENCE_END: &[char] = &['.', '?', '!', '…', '。', '？', '！'];
const PAUSE_SENTENCE: f64 = 1.0; // s de silencio que cierran frase aunque no haya punto
const PAUSE_PARAGRAPH: f64 = 1.5; // s de silencio que abren párrafo
const MAX_SENTENCE_WORDS: usize = 40;
const PARAGRAPH_SENTENCES: usize = 5;
pub const SUB_MAX_CHARS: usize = 42; // por línea; 2 líneas por subtítulo
const SUB_MAX_SECONDS: f64 = 7.0;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Word {
    pub start: f64,
    pub end: f64,
    /// Incluye el espacio inicial si lo trae (" hola").
    pub text: String,
    #[serde(default = "one")]
    pub p: f32,
}

fn one() -> f32 {
    1.0
}

/// Un tramo con tiempos: frase, párrafo, palabra o subtítulo.
#[derive(Clone, Debug, Serialize)]
pub struct Span {
    pub start: f64,
    pub end: f64,
    pub words: Vec<Word>,
    /// Texto editado por el usuario, si lo hay.
    pub edited: Option<String>,
}

impl Span {
    fn of(words: Vec<Word>) -> Span {
        Span { start: words[0].start, end: words[words.len() - 1].end, words, edited: None }
    }
    pub fn text(&self) -> String {
        match &self.edited {
            Some(t) => t.clone(),
            None => self.words.iter().map(|w| w.text.as_str()).collect::<String>().trim().to_string(),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Granularity {
    Paragraph,
    Sentence,
    Word,
    Subtitle,
}

#[derive(Clone, Debug, Serialize)]
pub struct Transcript {
    pub words: Vec<Word>,
    pub language: String,
    /// Título visible (nombre del archivo o del vídeo).
    pub source: String,
    /// Audio local original, si lo hay (para el HTML interactivo).
    pub audio_path: Option<String>,
    pub duration: f64,
    /// Ediciones frase a frase (índice de frase → texto).
    #[serde(skip)]
    pub edits: Vec<Option<String>>,
}

impl Transcript {
    pub fn sentences(&self) -> Vec<Span> {
        let mut out = Vec::new();
        let mut cur: Vec<Word> = Vec::new();
        for (i, w) in self.words.iter().enumerate() {
            cur.push(w.clone());
            let next = self.words.get(i + 1);
            let ends = w.text.trim_end().ends_with(SENTENCE_END);
            let pause = next.is_some_and(|n| n.start - w.end >= PAUSE_SENTENCE);
            if next.is_none() || ends || pause || cur.len() >= MAX_SENTENCE_WORDS {
                let mut s = Span::of(std::mem::take(&mut cur));
                s.edited = self.edits.get(out.len()).cloned().flatten();
                out.push(s);
            }
        }
        out
    }

    pub fn paragraphs(&self) -> Vec<Span> {
        let sentences = self.sentences();
        let mut out = Vec::new();
        let mut group: Vec<&Span> = Vec::new();
        for (i, s) in sentences.iter().enumerate() {
            group.push(s);
            let next = sentences.get(i + 1);
            if next.is_none() || next.unwrap().start - s.end >= PAUSE_PARAGRAPH || group.len() >= PARAGRAPH_SENTENCES {
                let mut p = Span::of(group.iter().flat_map(|s| s.words.clone()).collect());
                if group.iter().any(|s| s.edited.is_some()) {
                    p.edited = Some(group.iter().map(|s| s.text()).collect::<Vec<_>>().join(" "));
                }
                out.push(p);
                group.clear();
            }
        }
        out
    }

    pub fn subtitles(&self) -> Vec<Span> {
        let mut out = Vec::new();
        for s in self.sentences() {
            if s.edited.is_some() {
                out.push(s); // frase editada: se respeta entera
                continue;
            }
            let mut cur: Vec<Word> = Vec::new();
            for w in s.words {
                let candidate: String = cur.iter().chain(std::iter::once(&w)).map(|w| w.text.as_str()).collect();
                let too_long = candidate.trim().chars().count() > SUB_MAX_CHARS * 2;
                let too_slow = !cur.is_empty() && w.end - cur[0].start > SUB_MAX_SECONDS;
                if !cur.is_empty() && (too_long || too_slow) {
                    out.push(Span::of(std::mem::take(&mut cur)));
                }
                cur.push(w);
            }
            if !cur.is_empty() {
                out.push(Span::of(cur));
            }
        }
        out
    }

    pub fn spans(&self, g: Granularity) -> Vec<Span> {
        match g {
            Granularity::Paragraph => self.paragraphs(),
            Granularity::Sentence => self.sentences(),
            Granularity::Subtitle => self.subtitles(),
            Granularity::Word => self.words.iter().map(|w| Span::of(vec![w.clone()])).collect(),
        }
    }

    /// Aplica textos editados frase a frase. Falso si no cuadra el número.
    pub fn apply_edits(&mut self, texts: &[String]) -> bool {
        self.edits.clear();
        let sentences = self.sentences();
        if texts.len() != sentences.len() {
            return false;
        }
        self.edits = sentences
            .iter()
            .zip(texts)
            .map(|(s, t)| {
                let t = t.trim();
                (t != s.text()).then(|| t.to_string())
            })
            .collect();
        true
    }
}

/// Parte un subtítulo en 2 líneas equilibradas por el espacio más centrado.
pub fn split_lines(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    if chars.len() <= SUB_MAX_CHARS {
        return text.to_string();
    }
    let middle = chars.len() / 2;
    let Some(cut) = chars.iter().enumerate().filter(|(_, c)| **c == ' ').map(|(i, _)| i).min_by_key(|i| i.abs_diff(middle)) else {
        return text.to_string();
    };
    let (a, b): (String, String) = (chars[..cut].iter().collect(), chars[cut + 1..].iter().collect());
    format!("{a}\n{b}")
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    pub fn sample() -> Transcript {
        let w = |s: f64, e: f64, t: &str| Word { start: s, end: e, text: t.into(), p: 1.0 };
        Transcript {
            words: vec![
                w(0.0, 0.5, " Hola"), w(0.5, 1.0, " mundo."), w(1.1, 1.5, " Esto"), w(1.5, 2.0, " sigue"),
                w(4.0, 4.5, " Tras"), w(4.5, 5.0, " pausa."),
            ],
            language: "es".into(),
            source: "Prueba ñandú".into(),
            audio_path: None,
            duration: 5.0,
            edits: vec![],
        }
    }

    #[test]
    fn sentences_split_on_period_and_pause() {
        let t = sample();
        let s: Vec<String> = t.sentences().iter().map(|s| s.text()).collect();
        assert_eq!(s, ["Hola mundo.", "Esto sigue", "Tras pausa."]);
    }

    #[test]
    fn paragraphs_split_on_long_pause() {
        assert_eq!(sample().paragraphs().len(), 2);
    }

    #[test]
    fn edits_apply_and_flow_to_paragraphs() {
        let mut t = sample();
        assert!(t.apply_edits(&["Hola, mundo.".into(), "Esto sigue".into(), "Tras pausa.".into()]));
        assert_eq!(t.sentences()[0].text(), "Hola, mundo.");
        assert!(t.paragraphs()[0].text().starts_with("Hola, mundo."));
        assert!(!t.apply_edits(&["solo una".into()]));
    }

    #[test]
    fn subtitle_lines() {
        let s = "Esta es una frase bastante larga para un subtítulo de prueba";
        let out = split_lines(s);
        assert_eq!(out.lines().count(), 2);
        assert_eq!(out.replace('\n', " "), s);
    }
}
