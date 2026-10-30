package com.redhat.lightwell;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Verifies that the OpenAPI contract and Swagger UI are exposed when the application runs.
 */
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    /**
     * Serves the API-first contract file at a stable URL for consumers and Swagger UI.
     */
    @Test
    void shouldServeOpenApiContract() throws Exception {
        mockMvc.perform(get("/openapi/openapi.yaml"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("openapi: 3.0.3")))
                .andExpect(content().string(containsString("/api/greetings")));
    }

    /**
     * Exposes Swagger UI for browsing and testing the contract interactively.
     */
    @Test
    void shouldRedirectToSwaggerUi() throws Exception {
        mockMvc.perform(get("/swagger-ui.html"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/swagger-ui/index.html"));
    }
}
