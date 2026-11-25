//! Candidate discovery and complete-link grouping, with ordered candidate selection.
#![forbid(unsafe_code)]
use serde::Deserialize;
use std::collections::{BTreeSet, HashMap};

const INVALID: &str = "ValueError: invalid photo-stack kernel input";
const NEAR: &str = "near_capture";
const UPLOAD: &str = "same_upload";
const WINDOW: i64 = 300_000_000;

type Record = (
    String,
    Option<String>,
    bool,
    Option<u32>,
    Option<String>,
    Option<String>,
    bool,
);
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    items: Vec<Record>,
    maximum_comparisons: i64,
}
struct Item {
    hash: u64,
    time: Option<i64>,
    aware: bool,
    day: Option<u32>,
    upload: Option<(String, String)>,
    unmatchable: bool,
}
#[derive(Clone, Hash, PartialEq, Eq)]
enum Key {
    Near(bool, i64, u8, u64),
    Upload(String, String, u8, u64, Option<u32>),
}
struct Cluster {
    members: Vec<usize>,
    reason: Option<&'static str>,
    keys: Vec<Key>,
}
#[derive(Default)]
struct Index {
    keys: HashMap<Key, BTreeSet<usize>>,
    any_day: HashMap<Key, BTreeSet<usize>>,
}

fn bands(value: u64, count: u8) -> Vec<(u8, u64, u8)> {
    let mut offset = 0;
    (0..count)
        .map(|band| {
            let width = 64 / count + u8::from(band < 64 % count);
            let part = (value >> offset) & ((1_u64 << width) - 1);
            offset += width;
            (band, part, width)
        })
        .collect()
}
fn keys(item: &Item) -> Vec<Key> {
    if let Some(time) = item.time {
        bands(item.hash, 5)
            .into_iter()
            .map(|(b, part, _)| Key::Near(item.aware, time.div_euclid(WINDOW), b, part))
            .collect()
    } else if let Some((account, batch)) = &item.upload {
        bands(item.hash, 3)
            .into_iter()
            .map(|(b, part, _)| Key::Upload(account.clone(), batch.clone(), b, part, item.day))
            .collect()
    } else {
        Vec::new()
    }
}
impl Index {
    fn add(&mut self, item: &Item, cluster: usize) -> Vec<Key> {
        let keys = keys(item);
        for key in &keys {
            self.keys.entry(key.clone()).or_default().insert(cluster);
            if let Key::Upload(a, b, band, part, _) = key {
                self.any_day
                    .entry(Key::Upload(a.clone(), b.clone(), *band, *part, None))
                    .or_default()
                    .insert(cluster);
            }
        }
        keys
    }
    fn candidates(&self, item: &Item) -> BTreeSet<usize> {
        let mut ids = BTreeSet::new();
        if let Some(time) = item.time {
            for (band, part, width) in bands(item.hash, 5) {
                for variant in std::iter::once(part).chain((0..width).map(|bit| part ^ (1 << bit)))
                {
                    let bucket = time.div_euclid(WINDOW);
                    for neighbor in bucket - 1..=bucket + 1 {
                        if let Some(found) = self
                            .keys
                            .get(&Key::Near(item.aware, neighbor, band, variant))
                        {
                            ids.extend(found);
                        }
                    }
                }
            }
        } else if let Some((account, batch)) = &item.upload {
            for (band, part, width) in bands(item.hash, 3) {
                for variant in std::iter::once(part).chain((0..width).map(|bit| part ^ (1 << bit)))
                {
                    if let Some(day) = item.day {
                        for selected in [Some(day), None] {
                            if let Some(found) = self.keys.get(&Key::Upload(
                                account.clone(),
                                batch.clone(),
                                band,
                                variant,
                                selected,
                            )) {
                                ids.extend(found);
                            }
                        }
                    } else if let Some(found) = self.any_day.get(&Key::Upload(
                        account.clone(),
                        batch.clone(),
                        band,
                        variant,
                        None,
                    )) {
                        ids.extend(found);
                    }
                }
            }
        }
        ids
    }
    fn remove(&mut self, id: usize, keys: &[Key]) {
        for key in keys {
            Self::discard(&mut self.keys, key, id);
            if let Key::Upload(a, b, band, part, _) = key {
                Self::discard(
                    &mut self.any_day,
                    &Key::Upload(a.clone(), b.clone(), *band, *part, None),
                    id,
                );
            }
        }
    }
    fn discard(map: &mut HashMap<Key, BTreeSet<usize>>, key: &Key, id: usize) {
        if let Some(ids) = map.get_mut(key) {
            ids.remove(&id);
            if ids.is_empty() {
                map.remove(key);
            }
        }
    }
}
fn relation(left: &Item, right: &Item) -> Option<&'static str> {
    let distance = (left.hash ^ right.hash).count_ones();
    match (left.time, right.time) {
        (Some(a), Some(b))
            if left.aware == right.aware && distance <= 8 && a.abs_diff(b) <= WINDOW as u64 =>
        {
            Some(NEAR)
        }
        (None, None)
            if distance <= 4
                && left.upload.is_some()
                && left.upload == right.upload
                && (left.day.is_none() || right.day.is_none() || left.day == right.day) =>
        {
            Some(UPLOAD)
        }
        _ => None,
    }
}
fn parse(payload: &str) -> Result<(Vec<Item>, i64), String> {
    let value: serde_json::Value = serde_json::from_str(payload).map_err(|_| INVALID.to_owned())?;
    let input: Input = serde_json::from_value(value).map_err(|_| INVALID.to_owned())?;
    if input.items.len() > 100000 || input.maximum_comparisons < 0 {
        return Err(INVALID.to_owned());
    }
    let items = input
        .items
        .into_iter()
        .map(|(hash, time, aware, day, account, batch, unmatchable)| {
            if hash.len() != 16
                || !hash
                    .bytes()
                    .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
                || day.is_some_and(|d| !(1..=3652059).contains(&d))
            {
                return Err(INVALID.to_owned());
            }
            let hash = u64::from_str_radix(&hash, 16).map_err(|_| INVALID.to_owned())?;
            let time = time
                .map(|text| {
                    let number = text.parse::<i64>().map_err(|_| INVALID.to_owned())?;
                    if number.to_string() != text
                        || !(-62135596800000000..=253402300799999999).contains(&number)
                    {
                        return Err(INVALID.to_owned());
                    }
                    Ok(number)
                })
                .transpose()?;
            let upload = match (account, batch) {
                (Some(a), Some(b)) if !a.is_empty() && !b.is_empty() => Some((a, b)),
                _ => None,
            };
            Ok(Item {
                hash,
                time,
                aware,
                day,
                upload,
                unmatchable,
            })
        })
        .collect::<Result<Vec<_>, String>>()?;
    Ok((items, input.maximum_comparisons))
}
/// Shared core entry point. The adapter supplies Python cancellation checks; the
/// characterization wrapper supplies a no-op. No partial grouping is returned.
pub struct Kernel;
impl Kernel {
    pub fn run(
        payload: &str,
        check: &mut impl FnMut() -> Result<(), String>,
    ) -> Result<String, String> {
        let (items, budget) = parse(payload)?;
        let mut index = Index::default();
        let mut clusters: Vec<Cluster> = Vec::new();
        let mut comparisons = 0_i64;
        for (item_id, item) in items.iter().enumerate() {
            check()?;
            let mut selected = None;
            if !item.unmatchable {
                for cluster_id in index.candidates(item) {
                    check()?;
                    let cluster = &mut clusters[cluster_id];
                    if cluster.members.len() >= 24 {
                        continue;
                    }
                    let mut reason = None;
                    let mut eligible = true;
                    for member in &cluster.members {
                        // Refuse before increment so even i64::MAX budgets cannot overflow.
                        if comparisons >= budget {
                            return Err("ValueError: pair comparison budget exceeded".to_owned());
                        }
                        comparisons += 1;
                        let pair = relation(item, &items[*member]);
                        if pair.is_none() || (reason.is_some() && pair != reason) {
                            eligible = false;
                            break;
                        }
                        reason = pair;
                    }
                    if eligible
                        && reason.is_some()
                        && (cluster.reason.is_none() || cluster.reason == reason)
                    {
                        selected = Some(cluster_id);
                        cluster.reason = reason;
                        cluster.members.push(item_id);
                        cluster.keys.extend(index.add(item, cluster_id));
                        if cluster.members.len() == 24 {
                            index.remove(cluster_id, &cluster.keys);
                        }
                        break;
                    }
                }
            }
            if selected.is_none() {
                let keys = if item.unmatchable {
                    Vec::new()
                } else {
                    index.add(item, clusters.len())
                };
                clusters.push(Cluster {
                    members: vec![item_id],
                    reason: None,
                    keys,
                });
            }
        }
        let mut groups = Vec::new();
        for cluster in clusters {
            check()?;
            if cluster.members.len() >= 2 {
                groups.push((cluster.members, cluster.reason));
            }
        }
        serde_json::to_string(&groups).map_err(|_| INVALID.to_owned())
    }
}
/// Data-only function characterized by rust-anything; the Python API remains outside this seam.
pub fn group_items(payload: String) -> Result<String, String> {
    Kernel::run(&payload, &mut || Ok(()))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn budget_and_cancellation_refuse_partial_output() {
        let payload = r#"{"items":[["0000000000000000","0",false,null,null,null,false],["0000000000000000","0",false,null,null,null,false]],"maximum_comparisons":0}"#;
        assert_eq!(
            group_items(payload.to_owned()),
            Err("ValueError: pair comparison budget exceeded".to_owned())
        );
        assert_eq!(
            Kernel::run(payload, &mut || Err("stopped".to_owned())),
            Err("stopped".to_owned())
        );
    }
    #[test]
    fn invalid_input_refuses_instead_of_panicking() {
        for payload in ["", "{}", "null", r#"{"items":[],"maximum_comparisons":-1}"#] {
            assert_eq!(group_items(payload.to_owned()), Err(INVALID.to_owned()));
        }
    }
    #[test]
    fn floor_buckets_and_unsigned_hashes() {
        assert_eq!(bands(u64::MAX, 5).len(), 5);
        assert_eq!((-1_i64).div_euclid(WINDOW), -1);
    }
}
