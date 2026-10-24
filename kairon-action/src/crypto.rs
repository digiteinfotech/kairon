//! Fernet (TTL ignored on decrypt) and AES-256-CTR tokens compatible with
//! `cryptography` as used by the Python callback server.

use aes::Aes128;
use aes::Aes256;
use base64::engine::general_purpose::{URL_SAFE, URL_SAFE_NO_PAD};
use base64::Engine;
use cbc::cipher::{block_padding::Pkcs7, BlockDecryptMut, BlockEncryptMut, KeyIvInit};
use cipher::StreamCipher;
use ctr::Ctr128BE;
use hmac::Mac;
use rand::RngCore;
use sha2::Sha256;

type Aes128CbcEnc = cbc::Encryptor<Aes128>;
type Aes128CbcDec = cbc::Decryptor<Aes128>;
type HmacSha256 = hmac::Hmac<Sha256>;
type Aes256Ctr = Ctr128BE<Aes256>;

const FERNET_VERSION: u8 = 0x80;

pub fn fernet_encrypt(plaintext: &str, key: &str) -> Result<String, String> {
    let (signing, encryption) = fernet_keys(key)?;
    let mut iv = [0u8; 16];
    rand::thread_rng().fill_bytes(&mut iv);
    let ciphertext = Aes128CbcEnc::new_from_slices(&encryption, &iv)
        .map_err(|err| err.to_string())?
        .encrypt_padded_vec_mut::<Pkcs7>(plaintext.as_bytes());
    let timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|err| err.to_string())?
        .as_secs();
    let mut token = Vec::with_capacity(1 + 8 + 16 + ciphertext.len() + 32);
    token.push(FERNET_VERSION);
    token.extend_from_slice(&timestamp.to_be_bytes());
    token.extend_from_slice(&iv);
    token.extend_from_slice(&ciphertext);
    let mac = hmac_sha256(&signing, &token)?;
    token.extend_from_slice(&mac);
    Ok(URL_SAFE.encode(token))
}

pub fn fernet_decrypt(token: &str, key: &str) -> Result<String, String> {
    let (signing, encryption) = fernet_keys(key)?;
    let raw = decode_urlsafe(token)?;
    if raw.len() < 1 + 8 + 16 + 16 + 32 {
        return Err("fernet token is too short".to_string());
    }
    if raw[0] != FERNET_VERSION {
        return Err("fernet version is not 0x80".to_string());
    }
    let (signed, mac) = raw.split_at(raw.len() - 32);
    let expected = hmac_sha256(&signing, signed)?;
    if mac != expected.as_slice() {
        return Err("fernet hmac mismatch".to_string());
    }
    let iv = &signed[9..25];
    let ciphertext = &signed[25..];
    let plain = Aes128CbcDec::new_from_slices(&encryption, iv)
        .map_err(|err| err.to_string())?
        .decrypt_padded_vec_mut::<Pkcs7>(ciphertext)
        .map_err(|err| err.to_string())?;
    String::from_utf8(plain).map_err(|err| err.to_string())
}

pub fn xor_encrypt(secret: &str, key_hex: &str, iv_hex: &str) -> Result<String, String> {
    let mut buf = secret.as_bytes().to_vec();
    apply_ctr(&mut buf, key_hex, iv_hex)?;
    Ok(URL_SAFE_NO_PAD.encode(buf))
}

pub fn xor_decrypt(token: &str, key_hex: &str, iv_hex: &str) -> Result<String, String> {
    let mut buf = URL_SAFE_NO_PAD
        .decode(token.trim_end_matches('='))
        .or_else(|_| URL_SAFE.decode(token))
        .map_err(|err| err.to_string())?;
    apply_ctr(&mut buf, key_hex, iv_hex)?;
    String::from_utf8(buf).map_err(|err| err.to_string())
}

fn apply_ctr(buf: &mut [u8], key_hex: &str, iv_hex: &str) -> Result<(), String> {
    let key = decode_hex(key_hex)?;
    let iv = decode_hex(iv_hex)?;
    let mut cipher = Aes256Ctr::new_from_slices(&key, &iv).map_err(|err| err.to_string())?;
    cipher.apply_keystream(buf);
    Ok(())
}

fn fernet_keys(key: &str) -> Result<([u8; 16], [u8; 16]), String> {
    let raw = decode_urlsafe(key)?;
    if raw.len() != 32 {
        return Err(format!("fernet key must be 32 bytes, got {}", raw.len()));
    }
    let mut signing = [0u8; 16];
    let mut encryption = [0u8; 16];
    signing.copy_from_slice(&raw[..16]);
    encryption.copy_from_slice(&raw[16..]);
    Ok((signing, encryption))
}

fn hmac_sha256(key: &[u8], data: &[u8]) -> Result<[u8; 32], String> {
    let mut mac = HmacSha256::new_from_slice(key).map_err(|err| err.to_string())?;
    mac.update(data);
    let bytes = mac.finalize().into_bytes();
    let mut out = [0u8; 32];
    out.copy_from_slice(&bytes);
    Ok(out)
}

fn decode_urlsafe(token: &str) -> Result<Vec<u8>, String> {
    let trimmed = token.trim();
    if let Ok(raw) = URL_SAFE.decode(trimmed) {
        return Ok(raw);
    }
    let pad = (4 - trimmed.len() % 4) % 4;
    let mut padded = trimmed.to_string();
    padded.extend(std::iter::repeat('=').take(pad));
    URL_SAFE
        .decode(padded.as_bytes())
        .or_else(|_| URL_SAFE_NO_PAD.decode(trimmed))
        .map_err(|err| err.to_string())
}

fn decode_hex(text: &str) -> Result<Vec<u8>, String> {
    if text.len() % 2 != 0 {
        return Err("hex length must be even".to_string());
    }
    (0..text.len())
        .step_by(2)
        .map(|index| {
            u8::from_str_radix(&text[index..index + 2], 16).map_err(|err| err.to_string())
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    const KEY: &str = "gH8F9M-3GTxT1z-XyvJXZlCfxfbMuFr2HgXDHl7Xkuw=";
    const AES_KEY: &str = "3b1fbd562a0b5a29cc9a1b29b2c2d17a8a62b0d94f7637f1088e07fa1dbdcd14";
    const AES_IV: &str = "2f7b56a2c3e4d5f681d8ab92bc9d8f47";

    #[test]
    fn aes_ctr_matches_known_vector() {
        let token = xor_encrypt("abc123tokenhashvalue0123456789ab", AES_KEY, AES_IV).unwrap();
        assert_eq!(token, "ppWrWFIe5HwrjOvpVuUuUOe9N_rQRKb4M6-gCyRZwg4");
        let plain = xor_decrypt(&token, AES_KEY, AES_IV).unwrap();
        assert_eq!(plain, "abc123tokenhashvalue0123456789ab");
    }

    #[test]
    fn fernet_roundtrip_ignores_clock() {
        let token = fernet_encrypt("hello-kairon", KEY).unwrap();
        assert_eq!(fernet_decrypt(&token, KEY).unwrap(), "hello-kairon");
    }

    #[test]
    fn fernet_and_aes_match_python_cryptography() {
        let python = "/Data/projects/kairon/.venv/bin/python";
        if !std::path::Path::new(python).exists() {
            eprintln!("python venv missing, skip cryptography compatibility");
            return;
        }
        let token = fernet_encrypt("hello-kairon", KEY).unwrap();
        let script = r#"
import sys
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import base64, binascii
mode, key, payload = sys.argv[1], sys.argv[2], sys.argv[3]
if mode == "fdec":
    print(Fernet(key.encode()).decrypt(payload.encode()).decode())
elif mode == "fenc":
    print(Fernet(key.encode()).encrypt(payload.encode()).decode())
elif mode == "aes":
    secret, keyhex, ivhex = payload.split("|")
    cipher = Cipher(algorithms.AES(binascii.unhexlify(keyhex)), modes.CTR(binascii.unhexlify(ivhex)))
    enc = cipher.encryptor()
    raw = enc.update(secret.encode()) + enc.finalize()
    print(base64.urlsafe_b64encode(raw).decode().rstrip("="))
"#;
        let decrypted = python_out(python, script, &["fdec", KEY, &token]);
        assert_eq!(decrypted, "hello-kairon");
        let py_token = python_out(python, script, &["fenc", KEY, "from-python"]);
        assert_eq!(fernet_decrypt(&py_token, KEY).unwrap(), "from-python");
        let payload = format!("abc123tokenhashvalue0123456789ab|{AES_KEY}|{AES_IV}");
        let py_aes = python_out(python, script, &["aes", "x", &payload]);
        assert_eq!(py_aes, "ppWrWFIe5HwrjOvpVuUuUOe9N_rQRKb4M6-gCyRZwg4");
    }

    fn python_out(python: &str, script: &str, args: &[&str]) -> String {
        let output = std::process::Command::new(python)
            .arg("-c")
            .arg(script)
            .args(args)
            .output()
            .expect("python");
        assert!(
            output.status.success(),
            "python failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        String::from_utf8_lossy(&output.stdout).trim().to_string()
    }
}
