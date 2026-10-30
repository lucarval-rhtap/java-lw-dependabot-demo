package com.redhat.lightwell.service;

import com.redhat.lightwell.model.GreetingResponse;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Unit tests for {@link GreetingService}.
 */
class GreetingServiceTest {

    private final GreetingService greetingService = new GreetingService();

    /**
     * Uses the default name when {@code name} is {@code null}.
     */
    @Test
    void shouldReturnDefaultGreetingWhenNameIsNull() {
        GreetingResponse response = greetingService.greet(null);

        assertThat(response.getMessage()).isEqualTo("Hello, World!");
    }

    /**
     * Uses the default name when {@code name} is blank or whitespace only.
     */
    @Test
    void shouldReturnDefaultGreetingWhenNameIsBlank() {
        GreetingResponse response = greetingService.greet("   ");

        assertThat(response.getMessage()).isEqualTo("Hello, World!");
    }

    /**
     * Formats a greeting with the supplied non-blank name.
     */
    @Test
    void shouldReturnPersonalizedGreetingWhenNameIsProvided() {
        GreetingResponse response = greetingService.greet("Alice");

        assertThat(response.getMessage()).isEqualTo("Hello, Alice!");
    }

    /**
     * Trims leading and trailing whitespace from the name before greeting.
     */
    @Test
    void shouldTrimNameBeforeGreeting() {
        GreetingResponse response = greetingService.greet("  Bob  ");

        assertThat(response.getMessage()).isEqualTo("Hello, Bob!");
    }
}
