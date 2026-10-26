package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-018 (outbound-clients R4 c1-c5) and T-019 (outbound-clients R8 c1). */
class HttpCallerWireFormatTest {

    private StubServer stub;
    private HttpCaller caller;

    @BeforeEach
    void setUp() throws Exception {
        stub = StubServer.start();
        stub.on("/echo", request -> StubServer.Reply.json(200, "{\"ok\": true}"));
        stub.on("/path%20with%20space", request -> StubServer.Reply.json(200, "{\"ok\": true}"));
        ActionSettings settings = new ActionSettings();
        settings.setRequestTimeout(5);
        caller = new HttpCaller(settings);
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    private static Map<String, Object> sample() {
        Map<String, Object> nested = new LinkedHashMap<>();
        nested.put("x", 1);
        nested.put("y", 2);
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("name", "John Doe");
        body.put("nested", nested);
        body.put("tags", Arrays.asList("a", null, "b c"));
        body.put("missing", null);
        body.put("flag", true);
        body.put("ratio", 1.0);
        body.put("count", 3);
        return body;
    }

    private static final String ENCODED = "name=John+Doe&nested=x&nested=y&tags=a&tags=b+c&flag=True&ratio=1.0&count=3";

    @Test
    void jsonContentTypeHasNoCharset() {
        caller.exchange("POST", stub.url("/echo"), Map.of(), Map.of("a", 1), "json");
        caller.executeStrict("PUT", stub.url("/echo"), Map.of(), Map.of("a", 1), "json");
        assertEquals(2, stub.requests.size());
        stub.requests.forEach(request -> assertEquals("application/json", request.header("Content-Type")));
    }

    @Test
    void formEncodingMatchesPythonRequests() {
        assertEquals(ENCODED, HttpCaller.formEncode(sample()));
        caller.executeStrict("POST", stub.url("/echo"), Map.of(), sample(), "data");
        caller.exchange("POST", stub.url("/echo"), Map.of(), sample(), "data");
        for (StubServer.Captured request : stub.requests) {
            assertEquals(ENCODED, request.text());
            assertEquals("application/x-www-form-urlencoded", request.header("Content-Type"));
        }
    }

    @Test
    void queryEncodingMatchesPythonRequests() {
        caller.executeStrict("GET", stub.url("/echo"), Map.of(), sample(), "json");
        caller.exchange("GET", stub.url("/echo?fixed=1"), Map.of(), sample(), "json");
        assertEquals(ENCODED, stub.requests.get(0).query());
        assertEquals("fixed=1&" + ENCODED, stub.requests.get(1).query());
        assertEquals(0, stub.requests.get(0).body().length);
    }

    @Test
    void urlWithRawSpacesIsRequotedInsteadOfFailing() {
        HttpCaller.Exchange exchange = caller.exchange("GET", stub.url("/path with space") + "?q=a b&done=50%", Map.of(), Map.of("p", "x y"), "json");
        assertEquals(200, exchange.status());
        StubServer.Captured request = stub.requests.get(0);
        assertEquals("/path%20with%20space", request.path());
        assertEquals("q=a%20b&done=50%25&p=x+y", request.query());
        assertEquals("http://h/a%20b?c=%E2%82%AC&d=%41", HttpCaller.requote("http://h/a b?c=€&d=%41"));
    }

    @Test
    void quotePlusMatchesPython() {
        assertEquals("a+b%2Ac~d_e.f-g%2F%26%3D%C3%A9", HttpCaller.quotePlus("a b*c~d_e.f-g/&=é"));
    }

    @Test
    void pythonFloatRepr() {
        assertEquals("1.0", HttpCaller.pyFloat(1.0));
        assertEquals("0.1", HttpCaller.pyFloat(0.1));
        assertEquals("10000000.0", HttpCaller.pyFloat(1e7));
        assertEquals("1e+16", HttpCaller.pyFloat(1e16));
        assertEquals("1.5e-05", HttpCaller.pyFloat(1.5e-5));
        assertEquals("0.0001", HttpCaller.pyFloat(1e-4));
    }

    @Test
    void mediaIdsProduceOneMultipartRequestPerFileLikePython() {
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("caption", "two files");
        fields.put("media_ids", List.of("m1", "m2"));
        List<HttpCaller.MediaFile> files = new ArrayList<>();
        files.add(new HttpCaller.MediaFile("one.png", "image/png", new byte[]{1, 2, 3}));
        files.add(new HttpCaller.MediaFile("two.pdf", "application/pdf", "%PDF".getBytes(StandardCharsets.UTF_8)));

        List<Object> responses = caller.multipart("post", stub.url("/echo"), Map.of("Authorization", "Bearer t"), fields, files);

        assertEquals(List.of(Map.of("ok", true), Map.of("ok", true)), responses, "one response per media file");
        assertEquals(2, stub.requests.size(), "one multipart request per media file");
        String[] parts = {
                "name=\"file\"; filename=\"one.png\"\r\nContent-Type: image/png\r\n\r\n\u0001\u0002\u0003\r\n",
                "name=\"file\"; filename=\"two.pdf\"\r\nContent-Type: application/pdf\r\n\r\n%PDF\r\n"
        };
        for (int i = 0; i < 2; i++) {
            StubServer.Captured request = stub.requests.get(i);
            assertEquals("POST", request.method());
            assertEquals("Bearer t", request.header("Authorization"));
            assertTrue(request.header("X-TimeStamp") != null);
            String type = request.header("Content-Type");
            assertTrue(type.startsWith("multipart/form-data; boundary="), type);
            String boundary = type.substring(type.indexOf('=') + 1);
            String body = new String(request.body(), StandardCharsets.ISO_8859_1);
            assertEquals(1, count(body, "Content-Disposition: form-data; name=\"file\";"));
            assertTrue(body.contains(parts[i]), body);
            assertTrue(body.contains("name=\"caption\"\r\n\r\ntwo files\r\n"));
            assertFalse(body.contains("media_ids"));
            assertTrue(body.endsWith("--" + boundary + "--\r\n"));
            assertEquals(2, count(body, "--" + boundary + "\r\n"));
        }
    }

    @Test
    void jsonContentTypeMultipartDropsFieldsLikeRequests() {
        List<HttpCaller.MediaFile> files = List.of(new HttpCaller.MediaFile("one.txt", "text/plain", "hi".getBytes(StandardCharsets.UTF_8)));
        caller.multipart("PUT", stub.url("/echo"), Map.of("Content-Type", "application/json"), Map.of("caption", "x"), files, "json");
        StubServer.Captured request = stub.requests.get(0);
        assertEquals("PUT", request.method());
        assertTrue(request.header("Content-Type").startsWith("multipart/form-data; boundary="));
        assertFalse(request.text().contains("caption"));
        assertEquals(1, count(request.text(), "name=\"file\""));
    }

    private static int count(String text, String needle) {
        int count = 0;
        for (int at = text.indexOf(needle); at >= 0; at = text.indexOf(needle, at + 1)) {
            count++;
        }
        return count;
    }
}
