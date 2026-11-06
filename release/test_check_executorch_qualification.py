import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from check_executorch_qualification import source_uri, verify_artifacts


SHA = "a" * 40
URI = "s3://pytorch/whl/test/cpu/executorch-1.6.0+cpu-cp311-cp311-linux_x86_64.whl"


class ArtifactQualificationTest(unittest.TestCase):
    def test_missing_provenance_and_mixed_sources_block_publication(self):
        github = mock.Mock()
        for metadata in [{}, {"source-sha": "release/1.6"}]:
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                verify_artifacts([URI], lambda uri: metadata, github)
        with self.assertRaises(ValueError):
            verify_artifacts(
                [URI, URI.replace("cpu-", "cu134-")],
                lambda uri: {"source-sha": SHA if uri == URI else "b" * 40},
                github,
            )
        github.latest_qualification.assert_not_called()

    def test_only_passed_full_qualification_accepts_wheels(self):
        github = mock.Mock()
        github.latest_qualification.return_value = {
            "status": "completed",
            "conclusion": "success",
            "html_url": "https://github.com/pytorch/executorch/actions/runs/1",
        }
        result = verify_artifacts([URI], lambda uri: {"source-sha": SHA}, github)
        self.assertEqual(result, {URI: SHA})
        github.latest_qualification.assert_called_once_with(SHA)
        github.latest_qualification.return_value["conclusion"] = "failure"
        with self.assertRaises(RuntimeError):
            verify_artifacts([URI], lambda uri: {"source-sha": SHA}, github)

    def test_url_decoding_preserves_actual_s3_key(self):
        self.assertEqual(
            source_uri("/whl/test/cpu/executorch-1.6.0%2Bcpu.whl"),
            "s3://pytorch/whl/test/cpu/executorch-1.6.0+cpu.whl",
        )
        with self.assertRaises(ValueError):
            source_uri("https://unknown.example/wheel.whl")

    def test_failed_gate_stops_s3_copy_even_without_shell_errexit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            aws = root / "aws"
            aws.write_text(
                f"""#!{sys.executable}
import json, os, sys
args = sys.argv[1:]
with open(os.environ['TEST_AWS_CALLS'], 'a') as output:
    output.write(json.dumps(args) + '\\n')
if 'head-object' in args:
    print(json.dumps({{'Metadata': {{}}}}))
elif '--dryrun' in args:
    print('(dryrun) copy: {URI} to s3://pytorch/whl/executorch.whl')
"""
            )
            aws.chmod(0o755)
            calls = root / "calls.jsonl"
            script = Path(__file__).parent / "promote/common_utils.sh"
            env = {
                **os.environ,
                "AWS": str(aws),
                "TEST_AWS_CALLS": str(calls),
                "TEST_WITHOUT_GIT_TAG": "1",
                "TEST_PYTORCH_PROMOTE_VERSION": "1.6.0",
                "PYTORCH_S3_FROM": "s3://pytorch/whl/test",
                "PYTORCH_S3_TO": "s3://pytorch/whl",
                "DRY_RUN": "disabled",
                "PACKAGE_EXCLUDE_TARGETS": "",
            }
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    'set +e; source "$1"; aws_promote executorch',
                    "test",
                    str(script),
                ],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            recorded = [json.loads(line) for line in calls.read_text().splitlines()]
            self.assertTrue(any("head-object" in call for call in recorded))
            self.assertFalse(
                any(
                    call[:2] == ["s3", "cp"] and "--dryrun" not in call
                    for call in recorded
                )
            )


if __name__ == "__main__":
    unittest.main()
