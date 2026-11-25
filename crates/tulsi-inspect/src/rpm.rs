//! The few fields of an .rpm header TulsiOS needs, without the rpm tools.
//!
//! Layout: a 96-byte lead, then the signature header (padded to 8 bytes), then
//! the main header. A header is: magic `8e ad e8 01`, 4 reserved bytes, the
//! number of index entries and the data size (big-endian u32 each), the index
//! entries (tag, type, offset, count; 16 bytes), then the data.

use std::path::Path;

use crate::read_at;

const LEAD: u64 = 96;
const MAGIC: [u8; 4] = [0x8e, 0xad, 0xe8, 0x01];
/// Headers bigger than this are not read (real ones are well below).
const MAX_HEADER: usize = 64 << 20;

const TAG_NAME: u32 = 1000;
const TAG_VERSION: u32 = 1001;
const TAG_SUMMARY: u32 = 1004;
const TAG_LICENSE: u32 = 1014;
const TAG_URL: u32 = 1020;
const TAG_PROVIDENAME: u32 = 1047;

const TYPE_STRING: u32 = 6;
const TYPE_STRING_ARRAY: u32 = 8;
const TYPE_I18NSTRING: u32 = 9;

#[derive(Debug, Default, PartialEq, Eq)]
pub struct Header {
    pub name: String,
    pub version: String,
    pub summary: String,
    pub url: String,
    pub license: String,
    pub provides: Vec<String>,
}

fn be32(b: &[u8]) -> u32 {
    u32::from_be_bytes([b[0], b[1], b[2], b[3]])
}

/// Reads a header at `offset`: (index entries, data, total length in bytes).
fn read_raw(file: &mut std::fs::File, offset: u64) -> Result<(Vec<u8>, Vec<u8>, u64), String> {
    let intro = read_at(file, offset, 16).map_err(|e| e.to_string())?;
    if intro[..4] != MAGIC {
        return Err("not an rpm header".into());
    }
    let entries = be32(&intro[8..12]) as usize;
    let size = be32(&intro[12..16]) as usize;
    if entries * 16 + size > MAX_HEADER {
        return Err("rpm header too large".into());
    }
    let index = read_at(file, offset + 16, entries * 16).map_err(|e| e.to_string())?;
    let data =
        read_at(file, offset + 16 + (entries * 16) as u64, size).map_err(|e| e.to_string())?;
    Ok((index, data, 16 + (entries * 16 + size) as u64))
}

/// Strings of an entry: one for STRING/I18NSTRING (the first translation),
/// `count` for STRING_ARRAY.
fn strings(data: &[u8], typ: u32, offset: usize, count: usize) -> Vec<String> {
    let n = match typ {
        TYPE_STRING => 1,
        TYPE_I18NSTRING => 1,
        TYPE_STRING_ARRAY => count,
        _ => return Vec::new(),
    };
    let mut out = Vec::new();
    let mut pos = offset;
    for _ in 0..n {
        let Some(rest) = data.get(pos..) else { break };
        let end = rest.iter().position(|&b| b == 0).unwrap_or(rest.len());
        out.push(String::from_utf8_lossy(&rest[..end]).into_owned());
        pos += end + 1;
    }
    out
}

pub fn parse(index: &[u8], data: &[u8]) -> Header {
    let mut h = Header::default();
    for entry in index.as_chunks::<16>().0 {
        let (tag, typ) = (be32(&entry[0..4]), be32(&entry[4..8]));
        let (offset, count) = (be32(&entry[8..12]) as usize, be32(&entry[12..16]) as usize);
        let first = || {
            strings(data, typ, offset, count)
                .into_iter()
                .next()
                .unwrap_or_default()
        };
        match tag {
            TAG_NAME => h.name = first(),
            TAG_VERSION => h.version = first(),
            TAG_SUMMARY => h.summary = first(),
            TAG_URL => h.url = first(),
            TAG_LICENSE => h.license = first(),
            TAG_PROVIDENAME => {
                h.provides = strings(data, typ, offset, count)
                    .into_iter()
                    // Not file or capability provides (`/usr/bin/x`, `libfoo.so()(64bit)`).
                    .filter(|p| !p.starts_with('/') && !p.contains('('))
                    .collect()
            }
            _ => {}
        }
    }
    h
}

pub fn read_header(path: &Path) -> Result<Header, String> {
    let mut file = std::fs::File::open(path).map_err(|e| e.to_string())?;
    let (_, _, sig_len) = read_raw(&mut file, LEAD)?;
    // The signature header is padded to a multiple of 8 bytes.
    let main = LEAD + sig_len.div_ceil(8) * 8;
    let (index, data, _) = read_raw(&mut file, main)?;
    Ok(parse(&index, &data))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(tag: u32, typ: u32, offset: u32, count: u32) -> Vec<u8> {
        [tag, typ, offset, count]
            .iter()
            .flat_map(|v| v.to_be_bytes())
            .collect()
    }

    #[test]
    fn parses_fields() {
        let data = b"frob\x001.2\x00A frobnicator\x00https://frob.example\x00frob\x00/usr/bin/frob\x00frob-cli\x00libfrob.so.1()(64bit)\x00";
        let mut index = Vec::new();
        index.extend(entry(TAG_NAME, TYPE_STRING, 0, 1));
        index.extend(entry(TAG_VERSION, TYPE_STRING, 5, 1));
        index.extend(entry(TAG_SUMMARY, TYPE_I18NSTRING, 9, 1));
        index.extend(entry(TAG_URL, TYPE_STRING, 23, 1));
        index.extend(entry(TAG_PROVIDENAME, TYPE_STRING_ARRAY, 44, 4));
        let h = parse(&index, data);
        assert_eq!(h.name, "frob");
        assert_eq!(h.version, "1.2");
        assert_eq!(h.summary, "A frobnicator");
        assert_eq!(h.url, "https://frob.example");
        assert_eq!(h.provides, ["frob", "frob-cli"]);
    }

    #[test]
    fn rejects_other_files() {
        let dir = std::env::temp_dir().join(format!("tulsi-rpm-test-{}", std::process::id()));
        std::fs::write(&dir, vec![0u8; 200]).unwrap();
        assert!(read_header(&dir).is_err());
        let _ = std::fs::remove_file(&dir);
    }
}
