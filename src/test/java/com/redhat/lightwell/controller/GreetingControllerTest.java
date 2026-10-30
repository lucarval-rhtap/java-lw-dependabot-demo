package com.redhat.lightwell.controller;

import com.redhat.lightwell.model.GreetingResponse;
import com.redhat.lightwell.service.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * HTTP slice tests for {@link GreetingController}.
 */
@WebMvcTest(GreetingController.class)
class GreetingControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private GreetingService greetingService;

    /**
     * Verifies the default greeting when the {@code name} query parameter is omitted.
     */
    @Test
    void shouldReturnGreetingWithoutNameParameter() throws Exception {
        when(greetingService.greet(null)).thenReturn(new GreetingResponse("Hello, World!"));

        mockMvc.perform(get("/api/greetings"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, World!"));
    }

    /**
     * Verifies a personalized greeting when {@code name} is supplied.
     */
    @Test
    void shouldReturnGreetingWithNameParameter() throws Exception {
        when(greetingService.greet("Alice")).thenReturn(new GreetingResponse("Hello, Alice!"));

        mockMvc.perform(get("/api/greetings").param("name", "Alice"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, Alice!"));
    }
}
