package com.kairon.action;

import io.micronaut.runtime.Micronaut;

/** Micronaut port of the Python kairon.actions webhook. */
public class Application {

    public static void main(String[] args) {
        Micronaut.run(Application.class, args);
    }
}
