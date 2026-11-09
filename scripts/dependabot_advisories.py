#!/usr/bin/env python3
"""Transform Lightwell OSV advisories into dependabot job security-advisories.

Provenance: copied verbatim from
github.com/lcarva/lightwell-osv@feat/dependabot-advisories-transform
(commit 227e87a, 2026-11-09). This in-repo copy is the system of record for
the transform; advisory *data* comes from a checkout of upstream
project-lightwell/lightwell-osv passed via --advisories.

Dependabot (dependabot-cli / dependabot-core) does not read OSV records
directly. Security updates are fed to the updater through the job
definition's `security-advisories` array (on github.com the backend fills
this from the GitHub Advisory Database; self-hosted we populate it from
Lightwell OSV records instead).

This tool reads `advisories/*.json` and emits:

  1. Transformed OSV records (default `build/osv-<ecosystem>/`): identical to
     the source record except `affected[].package.ecosystem` is rewritten
     from `Red Hat Lightwell:<eco>` to `<eco>`, so generic OSV consumers
     match them. Everything else — coordinates, ranges, and
     `database_specific.lightwell` (incl. `backport_base_version`, needed
     for cross-branch disambiguation) — is preserved verbatim.
  2. A YAML snippet (default `build/security-advisories-<ecosystem>.yaml`)
     with one job entry per advisory, in the schema dependabot-core expects
     (job/security_advisory_entry.rb):

         - dependency-name: "<groupId:artifactId>"
           affected-versions: ["[<introduced>,<fixed>)"]
           patched-versions:  ["[<fixed>,)"]

     `introduced: "0"` becomes an open-ended lower bound `[0,<fixed>)`.

     Entries are keyed per advisory (records for the same package merge in
     the updater: affected -> vulnerable, patched/unaffected -> safe, safe
     wins — see job.rb#security_advisories_for).

Maven requirement strings are emitted for Maven; PyPI gets PEP 440-style
`>=introduced,<fixed` / `>=fixed` strings, which dependabot also accepts.

Usage:
  dependabot_advisories.py [--ecosystem Maven] [--only NAME ...]
                            [--advisories DIR] [--out-dir DIR]
  NAME is `groupId:artifactId` (Maven) or a PyPI project name; --only
  restricts output to those packages (cheap per-repo pre-filter).
Exit status: 0 ok, 1 errors found, 2 usage/IO failure.
"""

import argparse
import json
import sys
from pathlib import Path

RHLW_PREFIX = "Red Hat Lightwell:"


class TransformError(Exception):
    pass


def maven_req(introduced, fixed):
    # Maven range syntax needs a comma between bounds; "[0,<fixed>)" is the
    # standard way to express an open-ended lower bound (verified against
    # dependabot's Maven requirement parser — "(<fixed>)" is illformed).
    return f"[{introduced},{fixed})"


def pypi_req(introduced, fixed):
    if introduced == "0":
        return f"<{fixed}"
    return f">={introduced},<{fixed}"


def transform_record(record, ecosystem):
    """Return (job_entry, transformed_record) for one OSV advisory."""
    ident = record.get("id", "<no-id>")
    affected = record.get("affected") or []
    if len(affected) != 1:
        raise TransformError(f"{ident}: expected exactly 1 affected block, got {len(affected)}")
    block = affected[0]
    package = block.get("package") or {}
    name = package.get("name")
    eco = package.get("ecosystem", "")
    if not name:
        raise TransformError(f"{ident}: missing package.name")
    if not eco.startswith(RHLW_PREFIX):
        raise TransformError(f"{ident}: unexpected ecosystem {eco!r}")
    short_eco = eco[len(RHLW_PREFIX):]
    if short_eco != ecosystem:
        return None  # other ecosystem, caller filters

    ranges = block.get("ranges") or []
    if len(ranges) != 1:
        raise TransformError(f"{ident}: expected exactly 1 range, got {len(ranges)}")
    if ranges[0].get("type") != "ECOSYSTEM":
        raise TransformError(f"{ident}: expected ECOSYSTEM range, got {ranges[0].get('type')!r}")
    events = ranges[0].get("events") or []
    introduced = [e["introduced"] for e in events if "introduced" in e]
    fixed = [e["fixed"] for e in events if "fixed" in e]
    if len(introduced) != 1 or len(fixed) != 1:
        raise TransformError(
            f"{ident}: expected exactly one introduced and one fixed event, got "
            f"{len(introduced)}/{len(fixed)}"
        )
    introduced, fixed = introduced[0], fixed[0]

    # Preserve database_specific.lightwell (backport_base_version et al.).
    transformed = json.loads(json.dumps(record))  # deep copy
    transformed["affected"][0]["package"]["ecosystem"] = short_eco

    if ecosystem == "Maven":
        affected_versions = [maven_req(introduced, fixed)]
        patched_versions = [f"[{fixed},)"]
    else:
        affected_versions = [pypi_req(introduced, fixed)]
        patched_versions = [f">={fixed}"]

    entry = {
        "dependency-name": name,
        "affected-versions": affected_versions,
        "patched-versions": patched_versions,
        # Provenance for humans reading a generated input.yml; dependabot
        # ignores unknown keys? No — job schema is strict, so this goes in a
        # comment instead (see yaml rendering).
        "_advisory-id": ident,
        "_backport-base-version": (
            block.get("database_specific", {}).get("lightwell", {}).get("backport_base_version")
        ),
    }
    return entry, transformed


def yaml_str(value):
    return json.dumps(value)  # JSON string quoting is valid YAML flow scalar


def render_entries_yaml(entries):
    lines = ["# Generated by tools/dependabot_advisories.py — do not edit by hand.",
             f"# {len(entries)} entries."]
    for e in entries:
        lines.append(f"# {e['_advisory-id']} (backport base: {e['_backport-base-version']})")
        lines.append(f"- dependency-name: {yaml_str(e['dependency-name'])}")
        lines.append("  affected-versions:")
        for v in e["affected-versions"]:
            lines.append(f"    - {yaml_str(v)}")
        lines.append("  patched-versions:")
        for v in e["patched-versions"]:
            lines.append(f"    - {yaml_str(v)}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ecosystem", default="Maven",
                    help="short ecosystem to emit (default: Maven)")
    ap.add_argument("--only", nargs="*", default=None, metavar="NAME",
                    help="restrict to these package names (e.g. groupId:artifactId)")
    ap.add_argument("--advisories", default="advisories", metavar="DIR",
                    help="advisories directory (default: ./advisories)")
    ap.add_argument("--out-dir", default="build", metavar="DIR",
                    help="output directory (default: ./build)")
    ap.add_argument("--skip-osv", action="store_true",
                    help="only emit the job YAML, not transformed OSV records")
    args = ap.parse_args()

    adv_dir = Path(args.advisories)
    files = sorted(adv_dir.glob("*.json"))
    if not files:
        print(f"error: no advisories found in {adv_dir}", file=sys.stderr)
        return 2

    eco_slug = args.ecosystem.lower()
    out_dir = Path(args.out_dir)
    osv_dir = out_dir / f"osv-{eco_slug}"
    if not args.skip_osv:
        osv_dir.mkdir(parents=True, exist_ok=True)

    entries, errors, skipped_other_eco = [], [], 0
    for path in files:
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: unreadable: {exc}")
            continue
        try:
            result = transform_record(record, args.ecosystem)
        except TransformError as exc:
            errors.append(str(exc))
            continue
        if result is None:
            skipped_other_eco += 1
            continue
        entry, transformed = result
        if args.only is not None and entry["dependency-name"] not in args.only:
            continue
        entries.append(entry)
        if not args.skip_osv:
            (osv_dir / path.name).write_text(json.dumps(transformed, indent=2) + "\n")

    yaml_path = out_dir / f"security-advisories-{eco_slug}.yaml"
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(render_entries_yaml(entries))

    print(f"{len(files)} advisories read, {len(entries)} {args.ecosystem} entries emitted "
          f"({skipped_other_eco} other-ecosystem, {len(files) - len(entries) - skipped_other_eco - len(errors)} filtered)")
    print(f"job YAML:   {yaml_path}")
    if not args.skip_osv:
        print(f"OSV records: {osv_dir}/")
    for err in errors:
        print(f"error: {err}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
