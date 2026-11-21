//! Bounded canonical float32 validation and exact f64 batch products.
//! Accurate sum adapted from CPython math_fsum; see third_party/python/NOTICE.md.
#![forbid(unsafe_code)]
use serde_json::Value;
use sha2::{Digest, Sha256};
const MAX: usize = 4 * 1024 * 1024;
fn invalid() -> String {
    "ValueError: invalid_vector_batch".into()
}

#[derive(Default)]
struct Sum {
    parts: Vec<f64>,
    special: f64,
    infinities: f64,
}
impl Sum {
    fn add(&mut self, mut x: f64) -> Result<(), String> {
        if !x.is_finite() {
            if x.is_infinite() {
                self.infinities += x;
            }
            self.special += x;
            self.parts.clear();
            return Ok(());
        }
        let mut used = 0;
        for j in 0..self.parts.len() {
            let mut y = self.parts[j];
            if x.abs() < y.abs() {
                std::mem::swap(&mut x, &mut y);
            }
            let hi = x + y;
            let lo = y - (hi - x);
            if lo != 0.0 {
                self.parts[used] = lo;
                used += 1;
            }
            x = hi;
        }
        self.parts.truncate(used);
        if !x.is_finite() {
            return Err("OverflowError: intermediate overflow in fsum".into());
        }
        if x != 0.0 {
            self.parts.push(x);
        }
        Ok(())
    }
    fn total(mut self) -> Result<f64, String> {
        if self.special != 0.0 {
            return if self.infinities.is_nan() {
                Err("ValueError: -inf + inf in fsum".into())
            } else {
                Ok(self.special)
            };
        }
        let mut hi = self.parts.pop().unwrap_or(0.0);
        let mut lo = 0.0;
        while let Some(y) = self.parts.pop() {
            let x = hi;
            hi = x + y;
            lo = y - (hi - x);
            if lo != 0.0 {
                break;
            }
        }
        let last = self.parts.last();
        if last.is_some_and(|p| lo != 0.0 && lo.signum() == p.signum()) {
            let y = lo * 2.0;
            let x = hi + y;
            if y == x - hi {
                hi = x;
            }
        }
        Ok(hi)
    }
}
fn hex(raw: &[u8]) -> String {
    raw.iter().map(|byte| format!("{byte:02x}")).collect()
}
fn decode(text: &str) -> Result<Vec<u8>, String> {
    if text.len() > MAX * 2
        || !text.len().is_multiple_of(2)
        || !text
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err(invalid());
    }
    let digit = |b: u8| (b & 15) + (b >> 6) * 9;
    Ok(text
        .as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|p| digit(p[0]) * 16 + digit(p[1]))
        .collect())
}
fn read64(row: &[u8; 8], little: bool) -> f64 {
    if little {
        f64::from_le_bytes(*row)
    } else {
        f64::from_be_bytes(*row)
    }
}
fn read_values(raw: &[u8], little: bool) -> Vec<f64> {
    raw.as_chunks::<8>()
        .0
        .iter()
        .map(|v| read64(v, little))
        .collect()
}
fn push64(out: &mut Vec<u8>, value: f64, little: bool) {
    out.extend_from_slice(&if little {
        value.to_le_bytes()
    } else {
        value.to_be_bytes()
    });
}
/// Shared buffer API; callers retain authorization, metadata and callback scope.
pub struct Kernel;
impl Kernel {
    pub fn canonicalize(
        raw: &[u8],
        dimension: usize,
        little: bool,
        checksum: &mut dyn FnMut(usize) -> Result<String, String>,
    ) -> Result<Vec<u8>, String> {
        if !(1..=4096).contains(&dimension)
            || raw.len() > MAX / 2
            || !raw.len().is_multiple_of(dimension * 4)
        {
            return Err(invalid());
        }
        let mut out = Vec::with_capacity(raw.len() * 2);
        for (index, row) in raw.chunks_exact(dimension * 4).enumerate() {
            let expected = checksum(index)?;
            let mut hash = Sha256::new();
            hash.update(b"photohouse-visual-vector-v1\0");
            hash.update((dimension as u32).to_be_bytes());
            hash.update(row);
            if format!("{:x}", hash.finalize()) != expected {
                return Err(invalid());
            }
            let mut values = Vec::with_capacity(dimension);
            let mut sum = Sum::default();
            for word in row.as_chunks::<4>().0.iter() {
                let value = f32::from_be_bytes(*word) as f64;
                if !value.is_finite() {
                    return Err(invalid());
                }
                values.push(value);
                sum.add(value * value)?;
            }
            let norm = sum.total()?.sqrt();
            if !norm.is_finite() || norm == 0.0 || (norm - 1.0).abs() > 1e-3 {
                return Err(invalid());
            }
            for value in values {
                push64(&mut out, value / norm, little);
            }
        }
        Ok(out)
    }
    pub fn score(
        raw: &[u8],
        query: &[u8],
        dimension: usize,
        little: bool,
        selected: &mut dyn FnMut(usize) -> Result<bool, String>,
    ) -> Result<Vec<(usize, f64)>, String> {
        if !(1..=4096).contains(&dimension)
            || raw.len() > MAX
            || !raw.len().is_multiple_of(dimension * 8)
            || query.len() != dimension * 8
        {
            return Err(invalid());
        }
        let query = read_values(query, little);
        if query.iter().any(|x| !x.is_finite()) {
            return Err(invalid());
        }
        let mut result = Vec::new();
        for (index, row) in raw.chunks_exact(dimension * 8).enumerate() {
            if !selected(index)? {
                continue;
            }
            let mut sum = Sum::default();
            for (value, q) in row.as_chunks::<8>().0.iter().zip(&query) {
                sum.add(read64(value, little) * q)?;
            }
            result.push((index, sum.total()?));
        }
        Ok(result)
    }
    /// Queries arrive in numeric seed-ID order; equal scores retain the first.
    pub fn best_seed(
        raw: &[u8],
        queries: &[u8],
        dimension: usize,
        little: bool,
        observe: &mut dyn FnMut(usize) -> Result<(), String>,
    ) -> Result<Vec<(usize, usize, f64)>, String> {
        if !(1..=4096).contains(&dimension)
            || raw.len() > MAX
            || !raw.len().is_multiple_of(dimension * 8)
            || raw.len() / (dimension * 8) > 512
            || !queries.len().is_multiple_of(dimension * 8)
            || !(1..=24).contains(&(queries.len() / (dimension * 8)))
        {
            return Err(invalid());
        }
        let queries = read_values(queries, little);
        if queries.iter().any(|v| !v.is_finite()) {
            return Err(invalid());
        }
        let mut output = Vec::with_capacity(raw.len() / (dimension * 8));
        for (row_index, row) in raw.chunks_exact(dimension * 8).enumerate() {
            observe(row_index)?;
            let values = read_values(row, little);
            if values.iter().any(|v| !v.is_finite()) {
                return Err(invalid());
            }
            let mut best: Option<(usize, f64)> = None;
            for (query_index, query) in queries.chunks_exact(dimension).enumerate() {
                let mut sum = Sum::default();
                for (left, right) in values.iter().zip(query) {
                    sum.add(left * right)?;
                }
                let score = sum.total()?;
                if best.is_none_or(|(_, previous)| score > previous) {
                    best = Some((query_index, score));
                }
            }
            // Query-count admission above guarantees a nonempty best value.
            let (seed, score) = best.ok_or_else(invalid)?;
            output.push((row_index, seed, score));
        }
        Ok(output)
    }
}
/// The portable characterization envelope; production calls the byte-buffer API.
pub fn run_batch(payload: String) -> Result<String, String> {
    if payload.len() > 10 * 1024 * 1024 {
        return Err(invalid());
    }
    let value: Value = serde_json::from_str(&payload).map_err(|_| invalid())?;
    let data = value.as_object().ok_or_else(invalid)?;
    let text = |key| data.get(key).and_then(Value::as_str).ok_or_else(invalid);
    let dimension = data
        .get("dimension")
        .and_then(Value::as_u64)
        .filter(|x| (1..=4096).contains(x))
        .ok_or_else(invalid)? as usize;
    let little = match text("byteorder")? {
        "little" => true,
        "big" => false,
        _ => return Err(invalid()),
    };
    let raw = decode(text("data")?)?;
    if data.len() != 5 {
        return Err(invalid());
    }
    match data.get("op").and_then(Value::as_str) {
        Some("canonicalize") => {
            let checksums = data
                .get("checksums")
                .and_then(Value::as_array)
                .ok_or_else(invalid)?;
            if raw.len() / (dimension * 4) != checksums.len() {
                return Err(invalid());
            }
            Kernel::canonicalize(&raw, dimension, little, &mut |i| {
                checksums
                    .get(i)
                    .and_then(Value::as_str)
                    .map(str::to_owned)
                    .ok_or_else(invalid)
            })
            .map(|x| hex(&x))
        }
        Some("best_seed") => {
            let queries = decode(text("query")?)?;
            let result = Kernel::best_seed(&raw, &queries, dimension, little, &mut |_| Ok(()))?;
            let mut out = Vec::with_capacity(result.len() * 12);
            for (_, seed, score) in result {
                out.extend_from_slice(&if little {
                    (seed as u32).to_le_bytes()
                } else {
                    (seed as u32).to_be_bytes()
                });
                push64(&mut out, score, little);
            }
            Ok(hex(&out))
        }
        Some("score") => {
            let query = decode(text("query")?)?;
            let result = Kernel::score(&raw, &query, dimension, little, &mut |_| Ok(true))?;
            let mut raw = Vec::with_capacity(result.len() * 8);
            for (_, score) in result {
                push64(&mut raw, score, little);
            }
            Ok(hex(&raw))
        }
        _ => Err(invalid()),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cancellation_and_bad_inputs() {
        assert!(Kernel::canonicalize(&[0; 8], 2, true, &mut |_| Err("cancel".into())).is_err());
        assert!(Kernel::score(&[0; 8], &[0; 8], 0, true, &mut |_| Ok(true)).is_err());
        assert!(decode("FF").is_err());
    }
    #[test]
    fn best_seed_refuses_and_cancels() {
        let bytes = [0; 8];
        assert!(Kernel::best_seed(&bytes, &bytes, 0, true, &mut |_| Ok(())).is_err());
        assert!(Kernel::best_seed(&bytes, &bytes, 1, true, &mut |_| Err("cancel".into())).is_err());
    }
    #[test]
    fn accurate_cancellation_and_half_even() -> Result<(), String> {
        let mut sum = Sum::default();
        for v in [1e16, 1.0, -1e16] {
            sum.add(v)?;
        }
        assert_eq!(sum.total()?, 1.0);
        let mut sum = Sum::default();
        for v in [1e-16, 1.0, 1e16] {
            sum.add(v)?;
        }
        assert_eq!(sum.total()?.to_bits(), 10000000000000002_f64.to_bits());
        Ok(())
    }
}
