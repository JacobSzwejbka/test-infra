import argparse
import json
import os
import re
import time
import urllib.parse
import urllib.request


class GitHub:
    def __init__(self, repository, token=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Invalid repository name")
        self.repository = repository
        self.token = token

    def get(self, path, params=None):
        url = f"https://api.github.com/repos/{self.repository}/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "backend-qualification",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=30
        ) as response:
            return json.load(response)

    def resolve(self, ref, strict=False):
        if re.fullmatch(r"[0-9a-f]{40}", ref):
            return ref
        if strict:
            raise ValueError("Publishing requires an immutable source SHA")
        sha = self.get("commits/" + urllib.parse.quote(ref, safe=""))["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("GitHub returned an invalid source SHA")
        return sha

    def latest_qualification(self, sha):
        matches = []
        for page in range(1, 21):
            runs = self.get(
                "actions/runs", {"head_sha": sha, "per_page": 100, "page": page}
            )["workflow_runs"]
            matches.extend(
                run
                for run in runs
                if run["head_sha"] == sha
                and run["path"] == ".github/workflows/backend-qualification.yml"
            )
            if len(runs) < 100:
                return max(matches, key=lambda run: run["id"]) if matches else None
        raise RuntimeError("Too many workflow runs to verify qualification safely")


def require_qualification(github, sha, timeout=0, interval=90):
    deadline = time.monotonic() + timeout
    while True:
        run = github.latest_qualification(sha)
        if run and run["status"] == "completed":
            if run["conclusion"] != "success":
                raise RuntimeError(
                    f'Full backend qualification failed for {sha}: {run["html_url"]}'
                )
            return run
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                f"No completed full backend qualification for {sha}; run Backend Qualification on that source commit"
            )
        time.sleep(min(interval, remaining))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repository",
        default=os.getenv("QUALIFICATION_REPOSITORY", "pytorch/executorch"),
    )
    parser.add_argument("--ref", default=os.environ.get("QUALIFICATION_REF"))
    parser.add_argument(
        "--strict",
        action="store_true",
        default=os.getenv("QUALIFICATION_STRICT") == "true",
    )
    parser.add_argument(
        "--timeout", type=int, default=int(os.getenv("QUALIFICATION_TIMEOUT", "18000"))
    )
    args = parser.parse_args()
    if not args.ref:
        parser.error("A source ref is required")
    github = GitHub(args.repository, os.getenv("GH_TOKEN"))
    sha = github.resolve(args.ref, args.strict)
    run = require_qualification(github, sha, args.timeout)
    print(f'Full backend qualification passed for {sha}: {run["html_url"]}')
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f'sha={sha}\nrun-url={run["html_url"]}\n')


if __name__ == "__main__":
    main()
