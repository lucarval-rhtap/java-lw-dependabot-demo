# 🤖 Dependabot × Lightwell Demo

A **Red Hat Lightwell** Spring Boot demo on **Java 17** and **Maven** whose main purpose is to
demonstrate the **Dependabot + Lightwell integration**: getting dependency-update PRs that propose
Lightwell **remediated** (`.rhlw-0000X`) versions instead of — or alongside — plain upstream bumps.

It is aimed at engineers and reps evaluating whether Lightwell remediations are visible and
actionable in GitHub CI, and it doubles as a template for replicating the pipeline in other repos.

The repo pins `com.fasterxml.woodstox:woodstox-core` at plain upstream `6.0.3` (vulnerable to
CVE-2022-40152, remediated as `6.0.3.rhlw-00001`) — the canonical test case for the demo. The
result is visible in this repo's PR list, where **native Dependabot and the self-hosted workflow
answer the same CVE differently, side by side**:

| PR | Source | woodstox proposal for CVE-2022-40152 |
|----|--------|--------------------------------------|
| [#12](https://github.com/lucarval-rhtap/java-lw-dependabot-demo/pull/12) | Native Dependabot | `6.4.0` (upstream major) |
| [#14](https://github.com/lucarval-rhtap/java-lw-dependabot-demo/pull/14) | Self-hosted workflow (label `lightwell`) | `6.0.3.rhlw-00001` (Lightwell respin) |

| Property | Value |
|----------|-------|
| Spring Boot | 2.7.18 |
| Java | 17 |
| Build tool | Maven |
| GroupId | `com.redhat.lightwell` |
| Artifact | `spring-boot-lw-poc-0.0.1-SNAPSHOT.jar` |

## 🎯 The problem and the solution

**Native GitHub Dependabot cannot propose Lightwell remediations.** Two reasons:

1. Dependabot only consumes the **GitHub Advisory Database**, where Lightwell advisories don't
   exist — so it doesn't know a pinned version is vulnerable when a Lightwell remediation exists.
2. Its Maven version parser predates the `.rhlw-0000X` suffix, so it can't reason about respin
   ordering (`6.0.3.rhlw-00001 > 6.0.3`).

Facing the same CVE, native Dependabot therefore proposes the upstream fix (`6.4.0`) — see
[PR #12](https://github.com/lucarval-rhtap/java-lw-dependabot-demo/pull/12) — which discards the
staying-on-version benefit of a remediated artifact.

**The solution** is a self-hosted Dependabot pipeline
([`.github/workflows/lightwell-dependabot.yml`](./.github/workflows/lightwell-dependabot.yml),
weekly Mondays 06:00 UTC + manual
[`workflow_dispatch`](https://github.com/lucarval-rhtap/java-lw-dependabot-demo/actions/workflows/lightwell-dependabot.yml))
that feeds Lightwell advisory data to a patched Dependabot updater. It proposed the respin as
[PR #14](https://github.com/lucarval-rhtap/java-lw-dependabot-demo/pull/14), labeled `lightwell`,
running side by side with native Dependabot.

> **Note:** the workflow opens ordinary pull requests — it does **not** create Dependabot alerts
> or Security-tab entries, because github.com's alert machinery only consumes the GitHub Advisory
> Database (not fixable from a self-hosted setup). The PR list (filtered by the `lightwell`
> label) is the interface.

> **Possible alternative on GitHub Enterprise Cloud: [innersource advisories](https://docs.github.com/en/enterprise-cloud@latest/code-security/concepts/vulnerability-reporting-and-management/innersource-advisories).**
> Enterprises with a GitHub Code Security or GHAS license can upload OSV-format advisories (via
> `POST /enterprises/{enterprise}/innersource-vulnerabilities/sync`), which native Dependabot
> consumes to raise alerts and open fix PRs — potentially covering Lightwell remediations
> without the self-hosted pipeline, since `lightwell-osv` data is already in OSV format. Two
> caveats: Dependabot's `.rhlw-0000X` version-ordering limitation (see #2 above) would likely
> still apply, and this has **not been tested** here — no GitHub Enterprise environment was
> available to verify it. Not applicable to GitHub Enterprise Server, where Dependabot only
> consumes the public GitHub Advisory Database.

## 🤖 Self-hosted Lightwell Dependabot

### How it works

One job on `ubuntu-latest`, driven by [`scripts/lightwell_dependabot.py`](./scripts/lightwell_dependabot.py):

```
 project-lightwell/lightwell-osv          repo secrets
 (advisory data, cloned fresh)            (LIGHTWELL_USER/TOKEN)
          │                                     │
          ▼                                     │
 ┌─────────────────────────┐                   │
 │ dependabot_advisories   │  scripts/dependabot_advisories.py
 │ .py transform, --only   │  (in this repo)
 │ manifest GAVs           │
 └───────────┬─────────────┘                   │
             ▼ security-advisories             │
 ┌─────────────────────────┐    ┌──────────────────────────────┐
 │ dependabot-cli          │───▶│ quay.io/lucarval/            │
 │ (pinned release binary) │    │ dependabot-updater-maven:    │
 │ 1 version-update job +  │    │ lightwell                    │
 │ 1 security job per      │    │ (stock core + .rhlw patches) │
 │ vulnerable dep          │    └──────────────┬───────────────┘
 └───────────┬─────────────┘                   │
             ▼ create_pull_request payloads   ▼ auth against Lightwell registry
 ┌─────────────────────────┐
 │ branch + commit + PR    │  labeled `dependencies` + `lightwell`,
 │ with dedupe on re-runs  │  deduplicated against existing open PRs
 └─────────────────────────┘
```

In words:

1. **Install the stock [dependabot-cli](https://github.com/dependabot/cli)** (pinned release
   binary — no patching needed on GitHub-hosted runners).
2. **Transform advisories** — clone the upstream
   [`project-lightwell/lightwell-osv`](https://github.com/project-lightwell/lightwell-osv)
   advisory data and run the in-repo [`scripts/dependabot_advisories.py`](./scripts/dependabot_advisories.py)
   `--only <GAVs in the manifest>` to convert the Lightwell OSV
   records into dependabot job `security-advisories`, pre-filtered to this repo's dependencies.
3. **Run dependabot-cli** against the fork updater image
   `quay.io/lucarval/dependabot-updater-maven:lightwell` (stock dependabot-core plus the
   `.rhlw` version-ordering patches from
   [dependabot-core#16848](https://github.com/dependabot/dependabot-core/pull/16848) and the
   plain→respin fix):
   - one **version-update job** for the whole manifest (patch-level updates + advisory-driven
     respins; semver-major/minor noise suppressed, same policy as `.github/dependabot.yml`), and
   - one **security job per vulnerable dependency** (`security-updates-only` + a named
     dependency — the updater requires this, and it mirrors how github.com runs security
     updates).
4. **Open PRs** — each `create_pull_request` payload becomes a branch + commit + PR
   (`lightwell/dependabot/<group>/<artifact>-<version>`), deduplicated against existing open PRs
   so re-runs never duplicate.

Credentials never appear in the generated job inputs: the input files reference
`$LIGHTWELL_USER`/`$LIGHTWELL_TOKEN` environment variables, expanded by the CLI at run time.

### Prerequisites

| Requirement | Detail |
|-------------|--------|
| Updater image | `quay.io/lucarval/dependabot-updater-maven:lightwell` — public, pullable anonymously. This is the **only fork artifact** the pipeline depends on (unavoidable until [dependabot-core#16848](https://github.com/dependabot/dependabot-core/pull/16848) merges upstream). |
| Advisory data | Upstream [`project-lightwell/lightwell-osv`](https://github.com/project-lightwell/lightwell-osv) default branch (cloned fresh each run; the transform script lives in this repo) |
| Repo **Actions** secrets | `LIGHTWELL_USER`, `LIGHTWELL_TOKEN` — registry service account (same credentials as [local builds](#-lightwell-setup)) |
| Org/repo setting | **Settings → Actions → General → Workflow permissions → "Allow GitHub Actions to create and approve pull requests"** must be enabled, or PR creation fails after the branches are pushed. Alternatively, store a fine-grained PAT (Contents + Pull requests, read/write on this repo) as the secret `LIGHTWELL_GH_TOKEN` — the workflow falls back to it automatically. |

### Replicating in another repo (or with another registry)

1. **Copy** `.github/workflows/lightwell-dependabot.yml` and `scripts/`
   (`lightwell_dependabot.py` + `dependabot_advisories.py`) into the target repo. The driver
   reads the target repo from `$GITHUB_REPOSITORY` and the manifest from `pom.xml` at the
   repo root — nothing else to configure for a standard single-module Maven project.
2. **Add the Actions secrets** `LIGHTWELL_USER` / `LIGHTWELL_TOKEN` to the target repo.
3. **Ensure the PR-creation setting** (see prerequisites) is enabled for the org/repo.
4. Run the workflow manually once to verify, then let the weekly schedule take over.

The updater image is not quay-specific: rebuild it from any dependabot-core fork carrying the
`.rhlw` patches (the fork's `maven/Dockerfile` builds directly on the stock
`ghcr.io/dependabot/dependabot-updater-core` base — only `maven/` differs) and point
`UPDATER_IMAGE` at your registry.

### Caveats & known limitations

- **Scheduled workflows auto-disable after 60 days of repo inactivity** (GitHub policy for
  public repos) — re-enable the workflow manually if the schedule goes quiet.
- **Cross-branch advisory over-claim** (upstream `lightwell-osv` data bug): advisories using
  `introduced: "0"` claim all lower versions are affected, which occasionally produces an
  aggressive plain-upstream **major** proposal in security jobs (e.g. spring-security-core
  `5.7.11 → 6.5.8`). When it appears, close the PR — the correct respin proposal is not lost.
- **PRs created by `GITHUB_TOKEN` do not trigger CI workflows** (standard GitHub behavior for
  bot-created PRs).
- The transform script lives in this repo; if the workflow fails on a newly published
  advisory record, it will fail loudly at run time rather than in CI — fix the invariant
  in `scripts/dependabot_advisories.py` locally.

## 🚀 Using the demo app locally

### Prerequisites

- Java 17+
- Maven 3.6+
- A **Red Hat Lightwell Network** membership with a registry service account (see
  [Lightwell setup](#-lightwell-setup) below)

Dependencies are resolved from the **Lightwell Remediated** repository first
(`https://packages.redhat.com/lightwell/java/remediated/`, configured in `pom.xml`), falling back
to Maven Central for artifacts without a remediated version. Patched artifacts carry the
`.rhlw-0000X` version suffix (e.g. `5.3.17.rhlw-00001`) and sort higher than their upstream
versions, so Maven picks them up automatically.

### Quick start

```bash
mvn clean verify          # build and test
mvn spring-boot:run       # run locally on port 8080
```

Try the sample API (contract: `GET /api/greetings`, `operationId: getGreeting`):

```bash
curl -s "http://localhost:8080/api/greetings" | jq
curl -s "http://localhost:8080/api/greetings?name=Alice" | jq
```

After API contract changes, regenerate the server stubs:

```bash
mvn openapi-generator:generate
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

#### Native Dependabot — GitHub secrets

[`.github/dependabot.yml`](./.github/dependabot.yml) configures daily `maven` update checks that
authenticate to the Lightwell Remediated repository. To enable it, add two **Dependabot secrets**
in the GitHub repository under **Settings → Secrets and variables → Dependabot → Actions**:

| Secret | Value |
|--------|-------|
| `LIGHTWELL_USERNAME` | Registry service account username (`XXXXXXX\|service-account-name`) |
| `LIGHTWELL_TOKEN` | Registry service account token |

Once configured, native Dependabot opens PRs for upstream updates it can see (compare with the
[self-hosted pipeline](#-self-hosted-lightwell-dependabot), which additionally proposes
`.rhlw` remediations).

#### Why upstream bumps are suppressed

Dependabot always queries Maven Central alongside the Lightwell registry, and proposes the
single **highest** version it finds. A newer upstream release (e.g. `2.22.4`) always outcompetes
a remediated version on the same line (e.g. `2.21.1.rhlw-00002`). Because of this, the
configuration ignores all `semver-major` and `semver-minor` updates — only patch-level updates
pass through, which is where `.rhlw` remediations live (e.g. `2.21.1 → 2.21.1.rhlw-00001`).

To take an upstream major/minor upgrade deliberately, bump the version in `pom.xml` manually or
remove the `ignore` block temporarily.

## 🌐 REST API

| Method | Path | operationId | Description |
|--------|------|-------------|-------------|
| GET | `/api/greetings` | `getGreeting` | Return a greeting (optional `name` query parameter) |

Contract: [openapi/openapi.yaml](./openapi/openapi.yaml)
