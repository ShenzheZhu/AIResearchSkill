"""A failed repeat must not leave a previous passing replay report."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import public_case


class ReplayEvidenceTest(unittest.TestCase):
    def test_failed_repeat_invalidates_prior_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "case.json").write_text(json.dumps({"revisions": {"historical": "source"}}))
            (output / "replay.json").write_text('{"matched": true}')
            process = subprocess.CompletedProcess([], 1, "", "interpreter failed")
            with patch.object(public_case.subprocess, "run", return_value=process):
                with self.assertRaisesRegex(RuntimeError, "probe infrastructure failed"):
                    public_case.replay(output)
            self.assertFalse((output / "replay.json").exists())
            self.assertIn("interpreter failed", (output / "replay-historical.log").read_text())


if __name__ == "__main__":
    unittest.main()
