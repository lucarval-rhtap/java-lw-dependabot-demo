package com.redhat.lightwell.service;

import com.redhat.lightwell.model.GreetingResponse;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/**
 * Builds greeting messages for the greetings API.
 */
@Service
public class GreetingService {

    private static final String DEFAULT_NAME = "World";

    /**
     * Resolves the user name and returns a greeting response.
     *
     * @param name requested display name; blank values use the default name
     * @return greeting response containing the formatted message
     */
    public GreetingResponse greet(String name) {
        String resolvedName = StringUtils.hasText(name) ? name.trim() : DEFAULT_NAME;
        return new GreetingResponse("Hello, " + resolvedName + "!");
    }
}
