package com.redhat.lightwell.model;

/**
 * JSON response body for the greetings API {@code GET /api/greetings} endpoint.
 */
public class GreetingResponse {

    private final String message;

    /**
     * Creates a greeting response with the given message text.
     *
     * @param message greeting text exposed as {@code message} in JSON
     */
    public GreetingResponse(String message) {
        this.message = message;
    }

    /**
     * Returns the greeting message serialized in the JSON response.
     *
     * @return greeting text
     */
    public String getMessage() {
        return message;
    }
}
