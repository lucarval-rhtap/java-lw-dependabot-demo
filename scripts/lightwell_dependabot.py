#!/usr/bin/env python3
"""Self-hosted Dependabot driver for Red Hat Lightwell remediations.

Implements the Phase 3A pipeline (see the repo README and
~/.opencode/plan/dependabot-lightwell-phase3a-plan.md for background):

  1. Parse the Maven manifest (pom.xml) for direct dependency coordinates
     (parent, dependencies, dependencyManagement).
  2. Run the Lightwell OSV -> dependabot-advisories transform
     (scripts/dependabot_advisories.py, an in-repo copy), pre-filtered to the
     manifest's coordinates, against advisory data from a checkout of upstream
     project-lightwell/lightwell-osv.
  3. Assemble dependabot-cli job inputs:
       - one version-update job: all (filtered) advisories + ignore-conditions
         that suppress semver-major/minor noise (update-types never apply to
         security jobs, so this stays off the security path by construction),
       - one security job per manifest dependency that has advisories:
         security-updates-only + dependencies: [GAV] (mirrors how github.com
         runs security updates). A security job that finds nothing vulnerable
         ends with the expected security_update_not_needed job error (exit 1)
         -- that is tolerated.
  4. Run the stock dependabot-cli per input against the fork updater image
     (quay.io/lucarval/dependabot-updater-maven:lightwell), capturing
     create_pull_request payloads from stdout.
  5. Turn each payload into a branch + commit + pull request, deduplicating
     against existing open PRs (and within the run) so re-runs don't
     duplicate.

Credentials never appear in the input files: they reference environment
variables ($LIGHTWELL_USER / $LIGHTWELL_TOKEN), which dependabot-cli expands
at run time (os.ExpandEnv); the GitHub token is auto-injected by the CLI from
LOCAL_GITHUB_ACCESS_TOKEN.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required (python3 -c 'import yaml' || pip install pyyaml)")

LIGHTWELL_MAVEN_REPO = "https://packages.redhat.com/lightwell/java/remediated"
UPDATE_TIMEOUT = "30m"
GIT_AUTHOR_NAME = "lightwell-dependabot"
GIT_AUTHOR_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
PR_BRANCH_PREFIX = "lightwell/dependabot"
PR_LABELS = ["dependencies", "lightwell"]

INPUT_CREDENTIALS = [
    {
        "type": "maven_repository",
        "url": LIGHTWELL_MAVEN_REPO,
        "username": "$LIGHTWELL_USER",
        "password": "$LIGHTWELL_TOKEN",
    },
]


def log(msg):
    print(f"[lightwell] {msg}", flush=True)


def run(cmd, cwd=None, check=True, **kw):
    p = subprocess.run(cmd, cwd=cwd, **kw)
    if check and p.returncode != 0:
        raise SystemExit(f"command failed ({p.returncode}): {' '.join(map(str, cmd))}")
    return p


# --------------------------------------------------------------------------
# 1) Manifest parsing
# --------------------------------------------------------------------------

def _local(tag):
    return tag.split("}")[-1]


def _findall_local(elem, name):
    return [c for c in elem if _local(c.tag) == name]


def _child_text(elem, name):
    for c in elem:
        if _local(c.tag) == name and c.text:
            return c.text.strip()
    return None


def manifest_dependency_names(pom_path):
    """Direct dependency coordinates (groupId:artifactId) from a pom.xml.

    Covers <parent>, <dependencies> and <dependencyManagement>/<dependencies>.
    Build plugins are deliberately excluded -- the verified Phase 1-2 runs
    covered dependencies and the parent only.
    """
    root = ET.parse(pom_path).getroot()

    names = []

    parent = _findall_local(root, "parent")
    if parent:
        g, a = _child_text(parent[0], "groupId"), _child_text(parent[0], "artifactId")
        if g and a:
            names.append(f"{g}:{a}")

    deps_containers = _findall_local(root, "dependencies")
    dm = _findall_local(root, "dependencyManagement")
    if dm:
        deps_containers += _findall_local(dm[0], "dependencies")
    for container in deps_containers:
        for dep in _findall_local(container, "dependency"):
            g, a = _child_text(dep, "groupId"), _child_text(dep, "artifactId")
            if g and a:
                names.append(f"{g}:{a}")

    # de-duplicate, preserve order
    return list(dict.fromkeys(names))


# --------------------------------------------------------------------------
# 2) Transform
# --------------------------------------------------------------------------

def run_transform(advisories_repo, names, out_dir):
    """Run the in-repo copy of dependabot_advisories.py, pre-filtered to the
    manifest GAVs, against advisory data in a lightwell-osv checkout.

    Returns the path of the generated job-advisories YAML. Fails loudly on
    invariant violations (that is the mitigation for having no upstream CI).
    """
    script = Path(__file__).resolve().parent / "dependabot_advisories.py"
    if not script.is_file():
        raise SystemExit(f"transform script not found: {script}")
    sha = run(["git", "-C", str(advisories_repo), "rev-parse", "--short", "HEAD"],
              check=False, capture_output=True, text=True).stdout.strip()
    if sha:
        log(f"advisory data: {advisories_repo} @ {sha}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(script),
        "--only", *names,
        "--advisories", str(Path(advisories_repo) / "advisories"),
        "--skip-osv",
        "--out-dir", str(out_dir),
    ]
    log(f"running transform: {' '.join(cmd[1:])}")
    run(cmd, cwd=Path(__file__).resolve().parent)
    yaml_path = out_dir / "security-advisories-maven.yaml"
    if not yaml_path.is_file():
        raise SystemExit(f"transform produced no output at {yaml_path}")
    return yaml_path


def load_advisories(yaml_path):
    with open(yaml_path) as f:
        advisories = yaml.safe_load(f)
    if advisories is None:
        advisories = []
    if not isinstance(advisories, list):
        raise SystemExit(f"unexpected advisories shape in {yaml_path}")
    return advisories


# --------------------------------------------------------------------------
# 3) Input assembly
# --------------------------------------------------------------------------

def base_job(repo):
    return {
        "package-manager": "maven",
        "source": {
            "provider": "github",
            "repo": repo,
            "directory": "/",
        },
        "allowed-updates": [{"update-type": "all"}],
        "dependency-groups": [],
    }


def write_input(path, job):
    doc = {"job": job, "credentials": INPUT_CREDENTIALS}
    with open(path, "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)
    return path


def version_update_input(repo, advisories):
    job = base_job(repo)
    job["security-advisories"] = advisories
    job["security-updates-only"] = False
    # Mirrors .github/dependabot.yml: suppress semver major/minor upstream
    # bumps so only patch-level updates (where .rhlw remediations live) pass
    # through. Update-types are skipped when security-updates-only is true,
    # so the security jobs below are unfiltered by construction.
    job["ignore-conditions"] = [{
        "dependency-name": "*",
        "update-types": ["version-update:semver-major", "version-update:semver-minor"],
    }]
    return job


def security_update_input(repo, dep_name, dep_advisories):
    job = base_job(repo)
    job["security-advisories"] = dep_advisories
    job["security-updates-only"] = True
    job["dependencies"] = [dep_name]
    return job


# --------------------------------------------------------------------------
# 4) CLI runs
# --------------------------------------------------------------------------

def run_cli(input_path, log_path, updater_image):
    cmd = [
        "dependabot", "update", "-f", str(input_path),
        "--updater-image", updater_image,
        "--skip-image-verification",
        "--timeout", UPDATE_TIMEOUT,
    ]
    log(f"running: {' '.join(cmd)}")
    with open(log_path, "w") as f:
        p = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        log(f"WARNING: dependabot exited {p.returncode} (see {log_path}); "
            f"security jobs report 'no update needed' this way, continuing")
    return p.returncode


def extract_payloads(log_path):
    """Pull create_pull_request payloads out of a CLI run log (JSON lines)."""
    payloads = []
    with open(log_path, errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "create_pull_request":
                payloads.append(obj["data"])
    return payloads


# --------------------------------------------------------------------------
# 5) PR opening
# --------------------------------------------------------------------------

def git(repo_dir, *args, **kw):
    return run(["git", "-C", str(repo_dir), *args], **kw)


def default_branch(repo_dir):
    p = git(repo_dir, "rev-parse", "--abbrev-ref", "origin/HEAD", check=False,
            capture_output=True, text=True)
    ref = p.stdout.strip() if p.returncode == 0 else ""
    return ref.split("/")[-1] if ref else "main"


def existing_open_prs():
    """{title, headRefName} of currently open PRs, for dedupe."""
    p = run(["gh", "pr", "list", "--state", "open", "--json", "title,headRefName",
             "--limit", "300"], capture_output=True, text=True)
    return json.loads(p.stdout or "[]")


def existing_labels():
    p = run(["gh", "label", "list", "--json", "name", "--limit", "100"],
            capture_output=True, text=True)
    return {e["name"] for e in json.loads(p.stdout or "[]")}


def apply_payload_files(repo_dir, payload):
    for f in payload.get("updated-dependency-files", []):
        if f.get("directory", "/") != "/":
            raise SystemExit(f"unexpected non-root directory in payload: {f}")
        path = repo_dir / f["name"]
        if f.get("deleted"):
            git(repo_dir, "rm", "-f", "--", f["name"], check=False)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f["content"])


def open_pr(repo_dir, base, payload, labels):
    name = payload["dependencies"][0]["name"]
    version = payload["dependencies"][0]["version"]
    title = payload["pr-title"]
    branch = f"{PR_BRANCH_PREFIX}/{name.replace(':', '/')}-{version}"

    git(repo_dir, "checkout", "--detach")
    git(repo_dir, "fetch", "origin")
    git(repo_dir, "reset", "--hard", payload["base-commit-sha"])
    git(repo_dir, "clean", "-fd")
    git(repo_dir, "checkout", "-B", branch)
    apply_payload_files(repo_dir, payload)

    git(repo_dir, "add", "-A")
    with tempfile.NamedTemporaryFile("w", suffix=".msg", delete=False) as mf:
        mf.write(payload["commit-message"])
        msg_file = mf.name
    git(repo_dir, "-c", f"user.name={GIT_AUTHOR_NAME}",
        "-c", f"user.email={GIT_AUTHOR_EMAIL}",
        "commit", "-F", msg_file)
    os.unlink(msg_file)

    git(repo_dir, "push", "--force", "origin", branch)

    with tempfile.NamedTemporaryFile("w", suffix=".body", delete=False) as bf:
        bf.write(payload.get("pr-body") or "")
        body_file = bf.name
    cmd = ["gh", "pr", "create", "--base", base, "--head", branch,
           "--title", title, "--body-file", body_file]
    if labels:
        cmd += ["--label", *labels]
    p = run(cmd, capture_output=True, text=True, check=False)
    os.unlink(body_file)
    if p.returncode != 0:
        log(f"WARNING: gh pr create failed for {branch}: {p.stderr.strip()}")
    else:
        log(f"opened PR: {p.stdout.strip()}")


def open_prs(repo_dir, payloads):
    if not payloads:
        log("no create_pull_request payloads -- nothing to open")
        return 0

    base = default_branch(repo_dir)
    labels = sorted(existing_labels() & set(PR_LABELS))
    open_prs_now = existing_open_prs()
    seen_titles = {pr["title"] for pr in open_prs_now}
    seen_heads = {pr["headRefName"] for pr in open_prs_now}

    opened = 0
    for payload in payloads:
        title = payload["pr-title"]
        name = payload["dependencies"][0]["name"]
        version = payload["dependencies"][0]["version"]
        head = f"{PR_BRANCH_PREFIX}/{name.replace(':', '/')}-{version}"
        if title in seen_titles or head in seen_heads:
            log(f"skipping (open PR already exists): {title}")
            continue
        seen_titles.add(title)
        seen_heads.add(head)
        open_pr(repo_dir, base, payload, labels)
        opened += 1
    return opened


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"),
                    help="target repo (owner/name); default $GITHUB_REPOSITORY")
    ap.add_argument("--repo-dir", default=".",
                    help="local clone of the target repo (default: cwd)")
    ap.add_argument("--pom", default=None,
                    help="path to pom.xml (default: <repo-dir>/pom.xml)")
    ap.add_argument("--advisories-repo", required=True,
                    help="path to an upstream lightwell-osv checkout "
                         "(project-lightwell/lightwell-osv, default branch)")
    ap.add_argument("--updater-image", required=True,
                    help="fork updater image, e.g. "
                         "quay.io/lucarval/dependabot-updater-maven:lightwell")
    ap.add_argument("--work-dir", default="lightwell-work",
                    help="scratch dir for inputs and run logs")
    args = ap.parse_args()

    if not args.repo:
        ap.error("--repo or $GITHUB_REPOSITORY is required")
    repo_dir = Path(args.repo_dir).resolve()
    pom_path = Path(args.pom) if args.pom else repo_dir / "pom.xml"
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1) manifest
    names = manifest_dependency_names(pom_path)
    log(f"manifest dependencies ({len(names)}): {', '.join(names)}")

    # 2) transform, pre-filtered to the manifest
    adv_yaml = run_transform(args.advisories_repo, names, work_dir / "transform")
    advisories = load_advisories(adv_yaml)
    adv_names = list(dict.fromkeys(a["dependency-name"] for a in advisories))
    log(f"advisories matching the manifest: {len(advisories)} entries, "
        f"{len(adv_names)} dependencies: {', '.join(adv_names) or '(none)'}")

    # 3) inputs
    inputs = []
    inputs.append(("version-update",
                   write_input(work_dir / "input-version-update.yml",
                               version_update_input(args.repo, advisories))))
    for dep in adv_names:
        dep_advisories = [a for a in advisories if a["dependency-name"] == dep]
        slug = dep.replace(":", ".")
        inputs.append((f"security-{slug}",
                       write_input(work_dir / f"input-security-{slug}.yml",
                                   security_update_input(args.repo, dep, dep_advisories))))

    # 4) runs
    all_payloads = []
    version_rc = 0
    for label, input_path in inputs:
        log_path = Path(str(input_path).replace("input-", "log-")).with_suffix(".log")
        rc = run_cli(input_path, log_path, args.updater_image)
        payloads = extract_payloads(log_path)
        for d in payloads:
            log(f"{label}: proposed -> {d['pr-title']}")
        all_payloads.extend(payloads)
        if label == "version-update":
            version_rc = rc

    # 5) PRs
    opened = open_prs(repo_dir, all_payloads)

    log(f"done: {len(all_payloads)} proposals, {opened} PRs opened")
    if version_rc != 0:
        raise SystemExit(f"version-update job exited {version_rc} -- "
                         f"check {work_dir}/log-version-update.log")


if __name__ == "__main__":
    main()
