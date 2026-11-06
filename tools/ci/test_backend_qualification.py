import unittest
from unittest import mock

from backend_qualification import GitHub, require_qualification


SHA = "a" * 40


def run(
    number=1,
    status="completed",
    conclusion="success",
    sha=SHA,
    path=".github/workflows/backend-qualification.yml",
):
    return {
        "id": number,
        "status": status,
        "conclusion": conclusion,
        "head_sha": sha,
        "path": path,
        "html_url": f"https://github.com/pytorch/executorch/actions/runs/{number}",
    }


class QualificationTest(unittest.TestCase):
    def test_different_commit_and_reduced_workflow_do_not_qualify(self):
        github = GitHub("pytorch/executorch")
        with mock.patch.object(
            github,
            "get",
            return_value={
                "workflow_runs": [
                    run(sha="b" * 40),
                    run(path=".github/workflows/test-backend-qnn.yml"),
                ]
            },
        ):
            self.assertIsNone(github.latest_qualification(SHA))
            with self.assertRaises(RuntimeError):
                require_qualification(github, SHA)

    def test_newer_failure_or_pending_run_cannot_be_masked_by_older_success(self):
        github = GitHub("pytorch/executorch")
        for newer in [
            run(2, conclusion="failure"),
            run(2, status="in_progress", conclusion=None),
        ]:
            with self.subTest(newer=newer), mock.patch.object(
                github, "get", return_value={"workflow_runs": [run(), newer]}
            ):
                with self.assertRaises(RuntimeError):
                    require_qualification(github, SHA)

    def test_qualification_on_later_api_page_is_found(self):
        github = GitHub("pytorch/executorch")
        first = [run(i, path=".github/workflows/pull.yml") for i in range(100)]
        with mock.patch.object(
            github,
            "get",
            side_effect=[{"workflow_runs": first}, {"workflow_runs": [run(101)]}],
        ):
            self.assertEqual(github.latest_qualification(SHA)["id"], 101)

    def test_passed_full_qualification_is_accepted(self):
        github = mock.Mock()
        github.latest_qualification.return_value = run()
        self.assertEqual(require_qualification(github, SHA)["head_sha"], SHA)

    def test_mutable_source_ref_is_rejected_for_binary_publication(self):
        with self.assertRaises(ValueError):
            GitHub("pytorch/executorch").resolve("release/1.6", strict=True)

    def test_api_failure_does_not_authorize_publication(self):
        github = mock.Mock()
        github.latest_qualification.side_effect = OSError("unavailable")
        with self.assertRaises(OSError):
            require_qualification(github, SHA)


if __name__ == "__main__":
    unittest.main()
