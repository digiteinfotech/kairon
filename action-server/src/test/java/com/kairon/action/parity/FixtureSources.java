package com.kairon.action.parity;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.URISyntaxException;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Stream;

/**
 * Where replay finds fixtures: every {@code *.json} under the bundled {@code src/test/resources/parity/fixtures/}
 * (at any depth), plus every {@code *.json} under an optional external directory, normally the Python recorder's
 * output {@code tests/parity/fixtures/}. The external directory comes from the system property
 * {@value #PROPERTY} or, when that is unset, the environment variable {@value #ENV}. Gradle forwards the
 * environment to the test JVM, so {@code KAIRON_PARITY_FIXTURES=../tests/parity/fixtures ./gradlew test} replays
 * real recordings.
 */
final class FixtureSources {

    static final String BUNDLED = "/parity/fixtures";
    static final String PROPERTY = "kairon.parity.fixtures";
    static final String ENV = "KAIRON_PARITY_FIXTURES";

    private FixtureSources() {
    }

    /** The bundled fixture directory on the test classpath. */
    static Path bundled() {
        URL url = FixtureSources.class.getResource(BUNDLED);
        if (url == null) {
            throw new IllegalStateException("no test resource directory " + BUNDLED);
        }
        try {
            return Path.of(url.toURI());
        } catch (URISyntaxException e) {
            throw new IllegalStateException(e);
        }
    }

    /** The configured external directory, if any (property first, then environment). */
    static Optional<Path> external(Map<String, String> env, String property) {
        String value = property != null && !property.isBlank() ? property : env.get(ENV);
        return value == null || value.isBlank() ? Optional.empty() : Optional.of(Path.of(value.trim()));
    }

    static Optional<Path> external() {
        return external(System.getenv(), System.getProperty(PROPERTY));
    }

    /**
     * Fixture files of each directory, sorted by path within a directory, directories in the given order, without
     * duplicates. A configured directory that does not exist is an error, not an empty set.
     */
    static List<Path> files(List<Path> directories) {
        Set<Path> out = new LinkedHashSet<>();
        for (Path directory : directories) {
            if (!Files.isDirectory(directory)) {
                throw new IllegalStateException("parity fixture directory " + directory.toAbsolutePath() + " does not exist");
            }
            try (Stream<Path> walk = Files.walk(directory)) {
                walk.filter(Files::isRegularFile)
                        .filter(p -> p.getFileName().toString().endsWith(".json"))
                        .map(p -> p.toAbsolutePath().normalize())
                        .sorted()
                        .forEach(out::add);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        }
        return List.copyOf(out);
    }

    /** Bundled directory first, then the external one when configured. */
    static List<Path> directories() {
        List<Path> out = new ArrayList<>();
        out.add(bundled());
        external().ifPresent(out::add);
        return out;
    }
}
