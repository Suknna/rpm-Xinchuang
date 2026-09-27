"""Check OpenSSH Release lookup without real GitHub requests."""

import os
import sys
import unittest
import urllib.error
from io import BytesIO
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import check_update  # noqa: E402


class FakeResponse(BytesIO):
    status = 200


class ReleaseLookupTest(unittest.TestCase):
    def test_present_release(self):
        with mock.patch.object(check_update.urllib.request, "urlopen", return_value=FakeResponse(b"{}")):
            self.assertEqual(check_update.main(["has-release", "--repo", "owner/repo", "--tag", "v10.5p1"]), 0)

    def test_missing_release(self):
        error = urllib.error.HTTPError("x", 404, "Not Found", None, None)
        with mock.patch.object(check_update.urllib.request, "urlopen", side_effect=error):
            self.assertEqual(check_update.main(["has-release", "--repo", "owner/repo", "--tag", "v10.6p1"]), 3)

    def test_authentication_header(self):
        with mock.patch.object(check_update.urllib.request, "urlopen", return_value=FakeResponse(b"{}")) as call:
            check_update.release_exists("owner/repo", "v10.5p1", "secret")
            self.assertEqual(call.call_args.args[0].get_header("Authorization"), "Bearer secret")


if __name__ == "__main__":
    unittest.main()
