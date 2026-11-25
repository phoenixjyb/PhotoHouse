//! Exact quality fast path for already-normalized ASCII/common CJK text.
#![forbid(unsafe_code)]
use std::collections::HashSet;

const LIMIT: usize = 65536;
fn cjk(c: char) -> bool {
    ('\u{3400}'..='\u{4dbf}').contains(&c) || ('\u{4e00}'..='\u{9fff}').contains(&c)
}
fn word(c: char) -> bool {
    c.is_ascii_alphanumeric() || c == '_' || cjk(c)
}
fn supported(text: &str) -> bool {
    text.len() <= LIMIT
        && text
            .chars()
            .all(|c| c.is_ascii() || cjk(c) || "，。！？、：；（）【】《》…—‘’“”".contains(c))
}
fn tokens(text: &str) -> Vec<String> {
    let mut out = Vec::new();
    for group in text.split(|c| !word(c)).filter(|s| !s.is_empty()) {
        let mut rest = String::new();
        for c in group.chars() {
            if cjk(c) {
                out.push(c.to_string());
            } else {
                rest.push(c);
            }
        }
        if !rest.is_empty() {
            out.push(rest);
        }
    }
    out
}
fn whole(content: &str, phrase: &str) -> bool {
    let mut offset = 0;
    while let Some(relative) = content[offset..].find(phrase) {
        let start = offset + relative;
        let end = start + phrase.len();
        let left = content[..start].chars().next_back();
        let right = content[end..].chars().next();
        if left.is_none_or(|c| !word(c)) && right.is_none_or(|c| !word(c)) {
            return true;
        }
        // Move one code point, matching Python's overlapping find loop.
        match content[start..].chars().next() {
            Some(c) => offset = start + c.len_utf8(),
            None => return false,
        }
    }
    false
}
/// Unsupported Unicode/large inputs return None for the authoritative Python path.
pub fn quality(content: &str, phrase: &str) -> Option<(i64, i64, i64)> {
    if phrase.is_empty() || !supported(content) || !supported(phrase) {
        return None;
    }
    let query = tokens(phrase);
    let available: HashSet<_> = tokens(content).into_iter().collect();
    let coverage = if query.is_empty() {
        0
    } else {
        query.iter().filter(|t| available.contains(*t)).count() * 1000 / query.len()
    };
    Some((
        coverage as i64,
        i64::from(whole(content, phrase)),
        -(content.chars().count() as i64),
    ))
}
/// Characterization wire only; the production binding calls quality directly.
pub fn run_batch(payload: String) -> Result<String, String> {
    let invalid = || "ValueError: invalid_literal_batch".to_string();
    if payload.len() > 1024 * 1024 {
        return Err(invalid());
    }
    let value: serde_json::Value = serde_json::from_str(&payload).map_err(|_| invalid())?;
    let object = value.as_object().ok_or_else(invalid)?;
    if object.len() != 2 {
        return Err(invalid());
    }
    let content = object
        .get("content")
        .and_then(|v| v.as_str())
        .ok_or_else(invalid)?;
    let phrase = object
        .get("phrase")
        .and_then(|v| v.as_str())
        .ok_or_else(invalid)?;
    serde_json::to_string(&quality(content, phrase)).map_err(|_| invalid())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn mixed_word_remainder_and_codepoint_lengths() {
        assert_eq!(
            tokens("abc中def 海边合影"),
            ["中", "abcdef", "海", "边", "合", "影"]
        );
        assert_eq!(quality("周末海边合影。", "海边合影"), Some((1000, 0, -7)));
        assert_eq!(quality("a海边合影b", "海边合影"), Some((1000, 0, -6)));
        assert_eq!(quality("family picnic", "picnic"), Some((1000, 1, -13)));
    }
    #[test]
    fn unsupported_text_is_not_reinterpreted() {
        for text in ["café", "İ", "\u{f900}", "🙂", "ひらがな", "\u{301}"] {
            assert_eq!(quality(text, "a"), None);
        }
        assert_eq!(quality(&"a".repeat(LIMIT + 1), "a"), None);
        assert_eq!(quality("abc", ""), None);
    }
    #[test]
    fn invalid_wire_is_a_closed_error() {
        for input in [
            "null",
            "{}",
            "[]",
            "invalid",
            r#"{"content":1,"phrase":"a"}"#,
            r#"{"content":"\ud800","phrase":"a"}"#,
        ] {
            assert_eq!(
                run_batch(input.into()),
                Err("ValueError: invalid_literal_batch".into())
            );
        }
    }
}
