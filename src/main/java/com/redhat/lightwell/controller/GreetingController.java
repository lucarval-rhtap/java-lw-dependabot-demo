package com.redhat.lightwell.controller;

import com.redhat.lightwell.model.GreetingResponse;
import com.redhat.lightwell.service.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST controller for the greetings API ({@code operationId: getGreeting}) defined in
 * {@code openapi/openapi.yaml}. See {@code docs/API.md}.
 */
@RestController
@RequestMapping("/api/greetings")
public class GreetingController {

    private final GreetingService greetingService;

    /**
     * Creates the controller with its greeting service dependency.
     *
     * @param greetingService service that builds greeting responses
     */
    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    /**
     * Returns a personalized greeting for the optional {@code name} query parameter.
     *
     * @param name display name; omitted, blank, or whitespace-only values default to {@code World}
     * @return JSON greeting payload with HTTP 200
     */
    @GetMapping
    public GreetingResponse greet(@RequestParam(required = false) String name) {
        return greetingService.greet(name);
    }
}
