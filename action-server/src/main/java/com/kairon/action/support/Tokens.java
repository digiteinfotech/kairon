package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.runtime.ActionFailure;
import jakarta.inject.Singleton;

import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Fernet and HS* JWT compatible with Python cryptography.Fernet and PyJWT.
 * Inner claims use json.dumps spacing. The JWT payload is compact.
 */
@Singleton
public class Tokens {

    private final ActionSettings settings;
    private final SecureRandom random = new SecureRandom();

    public Tokens(ActionSettings settings) {
        this.settings = settings;
    }

    public String encrypt(String message) {
        byte[] key = fernetKey();
        byte[] signing = Arrays.copyOfRange(key, 0, 16);
        byte[] encryption = Arrays.copyOfRange(key, 16, 32);
        byte[] iv = new byte[16];
        random.nextBytes(iv);
        byte[] timestamp = long8(Instant.now().getEpochSecond());
        try {
            Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(encryption, "AES"), new IvParameterSpec(iv));
            byte[] cipherText = cipher.doFinal(message.getBytes(StandardCharsets.UTF_8));
            byte[] prefix = concat(new byte[]{(byte) 0x80}, timestamp, iv, cipherText);
            byte[] hmac = mac(signingKeyAlg(), signing, prefix);
            return Base64.getUrlEncoder().encodeToString(concat(prefix, hmac));
        } catch (ActionFailure e) {
            throw e;
        } catch (Exception e) {
            throw new ActionFailure("Fernet encrypt failed: " + e.getMessage(), e);
        }
    }

    public String decrypt(String token) {
        byte[] key = fernetKey();
        byte[] signing = Arrays.copyOfRange(key, 0, 16);
        byte[] encryption = Arrays.copyOfRange(key, 16, 32);
        byte[] raw = Base64.getUrlDecoder().decode(token);
        if (raw.length < 1 + 8 + 16 + 32 || raw[0] != (byte) 0x80) {
            throw new ActionFailure("Fernet token is invalid");
        }
        int hmacStart = raw.length - 32;
        byte[] prefix = Arrays.copyOfRange(raw, 0, hmacStart);
        byte[] given = Arrays.copyOfRange(raw, hmacStart, raw.length);
        byte[] expected;
        try {
            expected = mac("HmacSHA256", signing, prefix);
        } catch (Exception e) {
            throw new ActionFailure("Fernet decrypt failed: " + e.getMessage(), e);
        }
        if (!MessageDigest.isEqual(expected, given)) {
            throw new ActionFailure("Fernet token signature mismatch");
        }
        byte[] iv = Arrays.copyOfRange(raw, 9, 25);
        byte[] cipherText = Arrays.copyOfRange(raw, 25, hmacStart);
        try {
            Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
            cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(encryption, "AES"), new IvParameterSpec(iv));
            return new String(cipher.doFinal(cipherText), StandardCharsets.UTF_8);
        } catch (Exception e) {
            throw new ActionFailure("Fernet decrypt failed: " + e.getMessage(), e);
        }
    }

    public String storePageToken(Map<String, Object> data, int expiryMinutes, java.util.List<String> accessLimit) {
        long now = Instant.now().getEpochSecond();
        int minutes = expiryMinutes > 0 ? expiryMinutes : settings.getTokenExpire();
        Map<String, Object> claims = new LinkedHashMap<>();
        if (data != null) {
            claims.putAll(data);
        }
        claims.put("exp", now + minutes * 60L);
        claims.put("iat", now);
        claims.put("jti", uuid7());
        if (accessLimit != null) {
            claims.put("access-limit", accessLimit);
        }
        claims.put("type", "store_page");
        return signEncrypted(claims);
    }

    /** Integration tokens skip exp/iat, matching Authentication.create_access_token. */
    public String integrationToken(Map<String, Object> data) {
        Map<String, Object> claims = new LinkedHashMap<>();
        if (data != null) {
            claims.putAll(data);
        }
        claims.put("type", "integration");
        return signEncrypted(claims);
    }

    public Map<String, Object> decryptClaims(String jwt) {
        String[] parts = jwt.split("\\.");
        if (parts.length != 3) {
            throw new ActionFailure("JWT is invalid");
        }
        String payloadJson = new String(Base64.getUrlDecoder().decode(pad(parts[1])), StandardCharsets.UTF_8);
        Map<String, Object> outer = Jsons.readMap(payloadJson);
        String sub = Maps.str(outer.get("sub"));
        String plain = decrypt(sub);
        return Jsons.readMap(plain);
    }

    public String uuid7() {
        return uuid7Raw().toString();
    }

    public String uuid7Hex() {
        return uuid7Raw().toString().replace("-", "");
    }

    private String signEncrypted(Map<String, Object> claims) {
        String cipher = encrypt(Jsons.pythonDumps(claims));
        Map<String, Object> outer = new LinkedHashMap<>();
        outer.put("sub", cipher);
        outer.put("version", "2.0");
        if (claims.get("exp") instanceof Number exp) {
            outer.put("exp", exp.longValue());
        }
        if (claims.get("iat") instanceof Number iat) {
            outer.put("iat", iat.longValue());
        }
        return jwt(outer);
    }

    private String jwt(Map<String, Object> payload) {
        String algorithm = settings.getJwtAlgorithm() == null ? "HS256" : settings.getJwtAlgorithm();
        String macName = switch (algorithm) {
            case "HS384" -> "HmacSHA384";
            case "HS512" -> "HmacSHA512";
            default -> "HmacSHA256";
        };
        if (!algorithm.equals("HS256") && !algorithm.equals("HS384") && !algorithm.equals("HS512")) {
            algorithm = "HS256";
        }
        String secret = settings.getJwtSecret();
        if (secret == null || secret.isBlank()) {
            throw new ActionFailure("JWT secret is not configured");
        }
        try {
            String header = base64Url(("{\"typ\":\"JWT\",\"alg\":\"" + algorithm + "\"}").getBytes(StandardCharsets.UTF_8));
            String body = base64Url(compact(payload).getBytes(StandardCharsets.UTF_8));
            String signingInput = header + "." + body;
            byte[] signature = mac(macName, secret.getBytes(StandardCharsets.UTF_8), signingInput.getBytes(StandardCharsets.UTF_8));
            return signingInput + "." + base64Url(signature);
        } catch (ActionFailure e) {
            throw e;
        } catch (Exception e) {
            throw new ActionFailure("JWT sign failed: " + e.getMessage(), e);
        }
    }

    private static String compact(Map<String, Object> payload) {
        StringBuilder out = new StringBuilder();
        out.append('{');
        boolean first = true;
        for (Map.Entry<String, Object> entry : payload.entrySet()) {
            if (!first) {
                out.append(',');
            }
            first = false;
            out.append(Jsons.quote(entry.getKey())).append(':');
            Object value = entry.getValue();
            if (value instanceof Number number) {
                out.append(number.longValue());
            } else {
                out.append(Jsons.quote(String.valueOf(value)));
            }
        }
        out.append('}');
        return out.toString();
    }

    private byte[] fernetKey() {
        String key = settings.getFernetKey();
        if (key == null || key.isBlank()) {
            throw new ActionFailure("Fernet key is not configured");
        }
        byte[] decoded = Base64.getUrlDecoder().decode(key);
        if (decoded.length != 32) {
            throw new ActionFailure("Fernet key must decode to 32 bytes");
        }
        return decoded;
    }

    private static String signingKeyAlg() {
        return "HmacSHA256";
    }

    private UUID uuid7Raw() {
        long ms = System.currentTimeMillis() & 0xffffffffffffL;
        long randA = random.nextInt(1 << 12);
        long randB = random.nextLong() & 0x3fffffffffffffffL;
        long msb = (ms << 16) | (0x7L << 12) | randA;
        long lsb = (0x2L << 62) | randB;
        return new UUID(msb, lsb);
    }

    private static byte[] mac(String algorithm, byte[] key, byte[] data) throws Exception {
        Mac mac = Mac.getInstance(algorithm);
        mac.init(new SecretKeySpec(key, algorithm));
        return mac.doFinal(data);
    }

    private static byte[] long8(long value) {
        byte[] out = new byte[8];
        for (int i = 7; i >= 0; i--) {
            out[i] = (byte) (value & 0xff);
            value >>= 8;
        }
        return out;
    }

    private static byte[] concat(byte[]... parts) {
        int size = 0;
        for (byte[] part : parts) {
            size += part.length;
        }
        byte[] out = new byte[size];
        int offset = 0;
        for (byte[] part : parts) {
            System.arraycopy(part, 0, out, offset, part.length);
            offset += part.length;
        }
        return out;
    }

    private static String base64Url(byte[] data) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(data);
    }

    private static String pad(String segment) {
        int mod = segment.length() % 4;
        if (mod == 0) {
            return segment;
        }
        return segment + "=".repeat(4 - mod);
    }
}
