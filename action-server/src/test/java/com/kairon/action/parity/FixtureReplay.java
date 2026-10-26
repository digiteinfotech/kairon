package com.kairon.action.parity;

import com.kairon.action.ActionSettings;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.RequestIds;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Replays one fixture against the embedded server with the in-memory catalog: seeds the catalog, starts the
 * upstream stubs, sends every recorded inbound request, then compares the responses, the upstream calls and the
 * written documents. All comparisons share one {@link Placeholders.Bindings}, so an indexed placeholder must stand
 * for the same value across response, outbound calls and Mongo writes. The runner that turns each fixture into a
 * reported test (T-053) builds on {@link #run}.
 */
final class FixtureReplay {

    /** Inbound request headers the JDK client refuses to set, or that describe the recorder's transport. */
    private static final Set<String> SKIPPED_REQUEST_HEADERS = Set.of("host", "content-length", "connection", "expect",
            "upgrade", "transfer-encoding", "accept-encoding");

    private static final HttpClient CLIENT = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30)).build();

    private FixtureReplay() {
    }

    /** Outcome of a replay; {@link #passed()} when there are no mismatches. */
    record Result(String nodeId, List<String> mismatches, List<UpstreamStubs.Hit> hits) {
        boolean passed() {
            return mismatches.isEmpty();
        }

        String report() {
            return nodeId + (passed() ? ": OK" : ":\n  - " + String.join("\n  - ", mismatches));
        }
    }

    static Result run(Fixture fixture, int serverPort, MemoryActionCatalog catalog, ActionSettings settings) {
        List<String> mismatches = new ArrayList<>();
        String previousHttpsBase = settings.getHttpsStubBase();
        catalog.clear();
        RequestIds.clear();
        try (UpstreamStubs stubs = UpstreamStubs.start(fixture)) {
            settings.setHttpsStubBase(stubs.httpsBase());
            CatalogSeeder.seed(fixture, catalog::put, stubs.seedRewrite());
            var names = WrittenDocs.collections(fixture);
            WrittenDocs.Snapshot before = WrittenDocs.snapshot(catalog::all, names);
            JsonMatcher matcher = new JsonMatcher(new Placeholders.Bindings());
            int i = 0;
            for (Fixture.Exchange exchange : fixture.exchanges()) {
                String label = "exchanges[" + i++ + "]";
                HttpResponse<byte[]> response = send(serverPort, exchange.request());
                for (String problem : compareResponse(exchange.response(), response, matcher, stubs)) {
                    mismatches.add(label + ": " + problem);
                }
            }
            mismatches.addAll(stubs.verify(matcher));
            WrittenDocs.Snapshot after = WrittenDocs.snapshot(catalog::all, names);
            for (String problem : WrittenDocs.diff(fixture.mongo().writtenByCollection(),
                    WrittenDocs.actualWrites(before, after), matcher, stubs.outputRewrite())) {
                mismatches.add("written " + problem);
            }
            return new Result(fixture.nodeId(), List.copyOf(mismatches), stubs.hits());
        } finally {
            settings.setHttpsStubBase(previousHttpsBase);
            RequestIds.clear();
        }
    }

    static HttpResponse<byte[]> send(int port, Fixture.Request request) {
        String uri = "http://127.0.0.1:" + port + request.path() + (request.query().isEmpty() ? "" : "?" + request.query());
        HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(uri)).timeout(Duration.ofSeconds(120));
        for (Fixture.Header header : request.headers()) {
            if (!SKIPPED_REQUEST_HEADERS.contains(header.name().toLowerCase(Locale.ROOT))) {
                builder.header(header.name(), header.value());
            }
        }
        byte[] body = UpstreamStubs.encode(request.body());
        builder.method(request.method().toUpperCase(Locale.ROOT),
                body.length == 0 ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofByteArray(body));
        try {
            return CLIENT.send(builder.build(), HttpResponse.BodyHandlers.ofByteArray());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        } catch (Exception e) {
            throw new IllegalStateException("replay request " + uri + " failed", e);
        }
    }

    /**
     * Status, media type and body (placeholder-aware) of an inbound response. Other response headers
     * (date, server, content-length, request ids) are transport detail and not compared.
     */
    static List<String> compareResponse(Fixture.HttpReply expected, HttpResponse<byte[]> actual, JsonMatcher matcher,
                                        UpstreamStubs stubs) {
        List<String> out = new ArrayList<>();
        if (expected.status() != actual.statusCode()) {
            out.add("status expected " + expected.status() + " but was " + actual.statusCode());
        }
        List<String> contentType = Fixture.values(expected.headers(), "content-type");
        if (!contentType.isEmpty()) {
            String want = UpstreamStubs.mediaType(contentType.get(0));
            String got = actual.headers().firstValue("content-type").map(UpstreamStubs::mediaType).orElse(null);
            if (!want.equals(got)) {
                out.add("content-type expected " + contentType.get(0) + " but was " + got);
            }
        }
        byte[] body = "base64".equals(expected.body().encoding()) ? actual.body()
                : stubs.toRecorded(new String(actual.body(), StandardCharsets.UTF_8)).getBytes(StandardCharsets.UTF_8);
        for (String problem : UpstreamStubs.compareBody(expected.body(), body, matcher)) {
            out.add("body " + problem);
        }
        return out;
    }
}
