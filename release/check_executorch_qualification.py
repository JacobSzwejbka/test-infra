import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.ci.backend_qualification import GitHub, require_qualification


def source_uri(value):
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme == "s3":
        if parsed.netloc not in ("pytorch", "pytorch-backup"):
            raise ValueError("Unexpected artifact bucket")
        return value
    if parsed.scheme and parsed.netloc not in (
        "download-s3.pytorch.org",
        "download.pytorch.org",
    ):
        raise ValueError("Unexpected artifact host")
    path = urllib.parse.unquote(parsed.path).lstrip("/")
    if not path.startswith("whl/test/"):
        raise ValueError("Expected a test-channel wheel")
    return "s3://pytorch/" + path


def verify_artifacts(uris, read_metadata, github):
    wheels = sorted({uri for uri in uris if uri.endswith(".whl")})
    if not wheels:
        raise ValueError("No ExecuTorch wheels selected for qualification")
    sources = {}
    for uri in wheels:
        if not Path(urllib.parse.urlparse(uri).path).name.startswith("executorch-"):
            raise ValueError("Unexpected package in ExecuTorch publication")
        sha = read_metadata(uri).get("source-sha", "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError(
                f"Missing qualified source provenance for {uri}; rebuild the candidate with the qualification gate"
            )
        sources[uri] = sha
    if len(set(sources.values())) != 1:
        raise ValueError("Publication contains wheels from different source commits")
    for sha in set(sources.values()):
        require_qualification(github, sha)
    return sources


def read_metadata(uri):
    parsed = urllib.parse.urlparse(uri)
    result = subprocess.run(
        [
            os.getenv("AWS", "aws"),
            "s3api",
            "head-object",
            "--bucket",
            parsed.netloc,
            "--key",
            parsed.path.lstrip("/"),
            "--output",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout).get("Metadata", {})


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--urls", action="store_true")
    mode.add_argument("--keys", action="store_true")
    mode.add_argument("--staging-uri")
    parser.add_argument("--bucket", default="pytorch")
    parser.add_argument("--dist-directory")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.staging_uri:
        if not args.dist_directory:
            parser.error("--dist-directory is required for staged publication")
        files = list(Path(args.dist_directory).rglob("*"))
        if any(p.is_file() and p.name.endswith((".tar.gz", ".zip")) for p in files):
            raise ValueError("Source distributions need qualified provenance support")
        uris = [
            source_uri(
                args.staging_uri.rstrip("/")
                + "/"
                + p.relative_to(args.dist_directory).as_posix()
            )
            for p in files
            if p.is_file() and p.suffix == ".whl"
        ]
    else:
        text = sys.stdin.read()
        if args.plan:
            values = re.findall(
                r"(?:\(dryrun\) copy:|\+ to promote:)\s+(s3://\S+)", text
            )
        else:
            values = text.split()
        uris = [
            source_uri("s3://" + args.bucket + "/" + value if args.keys else value)
            for value in values
        ]
    github = GitHub("pytorch/executorch", os.getenv("GH_TOKEN"))
    sources = verify_artifacts(uris, read_metadata, github)
    print(
        f"Qualified {len(sources)} ExecuTorch wheels from {next(iter(sources.values()))}"
    )
    if args.output:
        Path(args.output).write_text(json.dumps(sources))


if __name__ == "__main__":
    main()
