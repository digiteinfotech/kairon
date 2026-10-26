package com.kairon.action.support;

/** Test access to package-private {@link ActionSupport#pythonJsonError(String)}. */
public final class ActionSupportJsonAccess {

    private ActionSupportJsonAccess() {}

    public static String error(String text) {
        return ActionSupport.pythonJsonError(text);
    }
}
