# 🌱 Spring Boot LW POC

A **Red Hat Lightwell** Spring Boot proof of concept on **Java 17** and **Maven**. Public REST APIs
follow an **API-first** contract defined in [openapi/openapi.yaml](./openapi/openapi.yaml).

| Property | Value |
|----------|-------|
| Spring Boot | 2.7.18 |
| Java | 17 |
| Build tool | Maven |
| GroupId | `com.redhat.lightwell` |
| Artifact | `spring-boot-lw-poc-0.0.1-SNAPSHOT.jar` |

## 🎯 Purpose

Minimal, well-documented baseline for local development, packaging, and testing on the Red Hat
Lightwell Network — suitable as a starting point for lightweight services or experiments.

## 📋 Prerequisites

- Java 17+
- Maven 3.6+
- A **Red Hat Lightwell Network** membership with a registry service account (see
  [Lightwell setup](#-lightwell-setup) below)

Dependencies are resolved from the **Lightwell Remediated** repository first
(`https://packages.redhat.com/lightwell/java/remediated/`, configured in `pom.xml`), falling back
to Maven Central for artifacts without a remediated version. Patched artifacts carry the
`.rhlw-0000X` version suffix (e.g. `5.3.17.rhlw-00001`) and sort higher than their upstream
versions, so Maven picks them up automatically.

## 🚀 Quick start

```bash
mvn clean verify          # build and test
mvn spring-boot:run       # run locally on port 8080
```

Try the sample API (contract: `GET /api/greetings`, `operationId: getGreeting`):

```bash
curl -s "http://localhost:8080/api/greetings" | jq
curl -s "http://localhost:8080/api/greetings?name=Alice" | jq
```

Browse and test the API in the browser (Swagger UI):

```bash
http://localhost:8080/swagger-ui.html
```

Raw OpenAPI contract at runtime: `http://localhost:8080/openapi/openapi.yaml`

After API contract changes:

```bash
mvn openapi-generator:generate
```

## 🧩 Application components

| Path | Description |
|------|-------------|
| `pom.xml` | Maven build, dependencies, Lightwell Remediated repository, OpenAPI Generator plugin |
| `openapi/openapi.yaml` | OpenAPI 3 contract — source of truth for public REST API |
| `src/main/java/com/redhat/lightwell/Application.java` | Spring Boot entry point |
| `src/main/java/com/redhat/lightwell/controller/GreetingController.java` | REST controller for greetings |
| `src/main/java/com/redhat/lightwell/service/GreetingService.java` | Greeting business logic |
| `src/main/java/com/redhat/lightwell/model/GreetingResponse.java` | API response DTO |
| `src/main/resources/application.properties` | Application configuration |
| `src/test/java/` | Unit and controller tests |
| `settings.xml.example` | Stub Maven settings for Lightwell authentication (copy to `~/.m2/settings.xml`) |
| `.github/dependabot.yml` | Dependabot config for daily dependency updates from the Lightwell Remediated repository |
| `.mavenrc.example` | Optional local Maven/JVM setup template |

Running the next Maven command you can get a fully detailed list of the dependencies of the project:

```bash
mvn dependency:tree > target/dependecy-tree.txt
```

To generate the SBOM, run:

```bash
syft ./target/spring-boot-lw-poc-0.0.1-SNAPSHOT.jar -o cyclonedx-json=target/spring-boot-lw-poc-0.0.1-sbom.json
```

### 🔐 Lightwell setup

The build and Dependabot both authenticate against the Lightwell Remediated repository using a
**registry service account**.

#### Where to get credentials

1. Log in to the [Lightwell Network console](https://packages.redhat.com) with an account covered
   by an active membership.
2. Navigate to **Registry Service Accounts** and create a new service account.
3. Note the **username** (format: `XXXXXXX|service-account-name`) and its **token**.

See the [official documentation](https://docs.redhat.com/en/documentation/red_hat_lightwell_network/current/get_started-create_a_red_hat_lightwell_network_service_account)
for details.

#### Local builds — `settings.xml.example`

Maven reads credentials from your `~/.m2/settings.xml`, keyed by the repository `<id>` declared in
`pom.xml` (`lightwell-remediated`). A committable stub is provided:

```bash
cp settings.xml.example ~/.m2/settings.xml   # or merge into your existing settings.xml
```

Edit the copy and replace `LIGHTWELL_USERNAME` and `LIGHTWELL_TOKEN` with your service account
username and token. Then verify resolution:

```bash
mvn dependency:resolve
```

Confirm the output shows artifacts resolving from
`https://packages.redhat.com/lightwell/java/remediated/` and that patched artifacts carry the
`.rhlw-0000X` suffix.

> ⚠️ Never commit a filled-in `settings.xml` — the repo's `.gitignore` already excludes it.

#### Dependabot — GitHub secrets

[`.github/dependabot.yml`](./.github/dependabot.yml) configures daily `maven` update checks that
authenticate to the Lightwell Remediated repository. To enable it, add two **Dependabot secrets**
in the GitHub repository under **Settings → Secrets and variables → Dependabot → Actions**:

| Secret | Value |
|--------|-------|
| `LIGHTWELL_USERNAME` | Registry service account username (`XXXXXXX\|service-account-name`) |
| `LIGHTWELL_TOKEN` | Registry service account token |

Once configured, Dependabot opens PRs that bump dependencies to their remediated
(`.rhlw-0000X`) versions when Red Hat publishes them.

### Lightwell Dependency Resolution

This application includes the following dependencies available from the validated and remediated repos:

* validated: `:2.21.1`
* remediated: `spring-boot-starter-web:2.7.18.rhlw-00003`

NOTE: To use the remediated version, just uncomment the version lines in the `pom.xml` file.

#### Direct access

```bash
cat ~/.m2/repository/com/fasterxml/jackson/jakarta/rs/jackson-jakarta-rs-json-provider/2.21.1/jackson-jakarta-rs-json-provider-2.21.1.jar.lastUpdated
```

The output will be similar to:

```text
#NOTE: This is a Maven Resolver internal implementation file, its format can be changed without prior notice.
#Wed Jul 08 12:23:53 CEST 2026
https\://packages.redhat.com/lightwell/java/remediated/.error=
https\://packages.redhat.com/lightwell/java/remediated/.lastUpdated=1783506186784
https\://packages.redhat.com/lightwell/java/validated/.lastUpdated=1783506233044
```

```bash
cat ~/.m2/repository/org/springframework/boot/spring-boot-starter-web/2.7.18.rhlw-00003/spring-boot-starter-web-2.7.18.rhlw-00003.jar.lastUpdated
```

The output will be similar to:

```text
#NOTE: This is a Maven Resolver internal implementation file, its format can be changed without prior notice.
#Wed Jul 08 12:28:24 CEST 2026
https\://packages.redhat.com/lightwell/java/remediated/.lastUpdated=1783506504815
https\://repo.maven.apache.org/maven2/.error=
https\://repo.maven.apache.org/maven2/.lastUpdated=1783506403778

## 🌐 REST API

| Method | Path | operationId | Description |
|--------|------|-------------|-------------|
| GET | `/api/greetings` | `getGreeting` | Return a greeting (optional `name` query parameter) |

Human guide: [docs/API.md](./docs/API.md) · Contract: [openapi/openapi.yaml](./openapi/openapi.yaml)

## 📚 Repository documentation

| Path | Description |
|------|-------------|
| [AGENTS.md](./AGENTS.md) | Instructions for AI coding agents |
| [llms.txt](./llms.txt) | Machine-readable index of project documentation |
| [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | Architecture, API-first design, Lightwell integration |
| [docs/API.md](./docs/API.md) | API-first workflow, samples, contract checklist |
| [docs/BUILD-AND-RUN.md](./docs/BUILD-AND-RUN.md) | Build, credentials, TLS, and run locally |
| [docs/TESTING.md](./docs/TESTING.md) | Testing strategy and practices |
| [docs/DOCUMENTATION.md](./docs/DOCUMENTATION.md) | Documentation standards |
| [docs/CONVENTIONS.md](./docs/CONVENTIONS.md) | Code and documentation conventions |
| `.cursor/rules/` | Cursor-specific rules |

## 🔗 External references

- [Red Hat Lightwell Network — service account](https://docs.redhat.com/en/documentation/red_hat_lightwell_network/current/get_started-create_a_red_hat_lightwell_network_service_account)
- [Spring Boot 2.7 Reference Documentation](https://docs.spring.io/spring-boot/docs/2.7.18/reference/html/)
- [Spring Boot Maven Plugin](https://docs.spring.io/spring-boot/docs/2.7.18/maven-plugin/reference/htmlsingle/)
- [Apache Maven](https://maven.apache.org/guides/)
