package com.kairon.action.parity;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FixtureSourcesTest {

    @Test
    void bundledDirectoryHoldsTheSyntheticFixtures() {
        List<Path> files = FixtureSources.files(List.of(FixtureSources.bundled()));
        assertEquals(3, files.size(), files.toString());
        assertTrue(files.stream().allMatch(p -> p.getFileName().toString().startsWith("synthetic_")));
    }

    @Test
    void externalDirectoryComesFromPropertyThenEnvironment() {
        assertEquals(Optional.empty(), FixtureSources.external(Map.of(), null));
        assertEquals(Optional.empty(), FixtureSources.external(Map.of(FixtureSources.ENV, " "), ""));
        assertEquals(Optional.of(Path.of("/env/dir")), FixtureSources.external(Map.of(FixtureSources.ENV, "/env/dir"), null));
        assertEquals(Optional.of(Path.of("/prop/dir")),
                FixtureSources.external(Map.of(FixtureSources.ENV, "/env/dir"), "/prop/dir"));
    }

    @Test
    void filesAreJsonAtAnyDepthSortedPerDirectoryWithoutDuplicates(@TempDir Path dir) throws IOException {
        Path first = Files.createDirectories(dir.resolve("a"));
        Path nested = Files.createDirectories(dir.resolve("b/nested"));
        Files.writeString(first.resolve("z.json"), "{}");
        Files.writeString(first.resolve("y.json"), "{}");
        Files.writeString(first.resolve("notes.txt"), "x");
        Files.writeString(nested.resolve("a.json"), "{}");
        List<Path> files = FixtureSources.files(List.of(first, dir.resolve("b"), first));
        Path root = dir.toAbsolutePath().normalize();
        assertEquals(List.of(Path.of("a/y.json"), Path.of("a/z.json"), Path.of("b/nested/a.json")),
                files.stream().map(root::relativize).toList());
    }

    @Test
    void missingConfiguredDirectoryIsAnError(@TempDir Path dir) {
        assertThrows(IllegalStateException.class, () -> FixtureSources.files(List.of(dir.resolve("missing"))));
    }
}
