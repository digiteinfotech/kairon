package com.kairon.action.support;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

/**
 * Runs a snippet under the reference Python interpreter (the kairon venv) for live interop checks.
 * Interpreter: system property {@code kairon.python}, env {@code KAIRON_PYTHON}, else the repo venv.
 * Tests that use it skip (JUnit assumption) when the interpreter or its packages are missing.
 */
final class PythonBridge {

    private static final String DEFAULT = "/Data/projects/kairon/.venv/bin/python3";

    private PythonBridge() {}

    static String interpreter() {
        String configured = System.getProperty("kairon.python");
        if (configured == null || configured.isBlank()) {
            configured = System.getenv("KAIRON_PYTHON");
        }
        return configured == null || configured.isBlank() ? DEFAULT : configured;
    }

    /** True when the interpreter exists and can import every module listed. */
    static boolean available(String... modules) {
        File python = new File(interpreter());
        if (!python.canExecute()) {
            return false;
        }
        try {
            run("import " + String.join(", ", modules) + "\nprint('ok')", "");
            return true;
        } catch (RuntimeException e) {
            return false;
        }
    }

    /** Runs {@code script} with {@code stdin} as standard input; returns stdout, throws on a non-zero exit. */
    static String run(String script, String stdin) {
        try {
            Process process = new ProcessBuilder(interpreter(), "-I", "-c", script)
                    .directory(new File(System.getProperty("java.io.tmpdir")))
                    .start();
            process.getOutputStream().write(stdin.getBytes(StandardCharsets.UTF_8));
            process.getOutputStream().close();
            byte[] out = process.getInputStream().readAllBytes();
            byte[] err = process.getErrorStream().readAllBytes();
            if (!process.waitFor(60, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                throw new IllegalStateException("python timed out");
            }
            if (process.exitValue() != 0) {
                throw new IllegalStateException("python failed: " + new String(err, StandardCharsets.UTF_8));
            }
            return new String(out, StandardCharsets.UTF_8).strip();
        } catch (IllegalStateException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
