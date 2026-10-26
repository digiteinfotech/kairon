package com.kairon.action.runtime;

import java.util.Map;

public interface KaironAction {

    String type();

    Map<String, Object> execute(ActionContext context);
}
