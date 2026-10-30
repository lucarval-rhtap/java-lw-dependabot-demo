package com.redhat.lightwell;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Spring Boot entry point for the LW POC application.
 */
@SpringBootApplication
public class Application {

    /**
     * Starts the Spring Boot application.
     *
     * @param args command-line arguments passed to Spring Boot
     */
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
