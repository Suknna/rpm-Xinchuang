"""Run the real CI build step with a container-output fixture as a non-root runner."""

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


@unittest.skipIf(os.geteuid() == 0, "root bypasses the runner directory permission check")
class WorkflowArtifactsTest(unittest.TestCase):
    def test_centos_openssh_artifacts_are_collected_in_a_fresh_checkout(self):
        workflow = (ROOT / ".github/workflows/rpm-xinchuang.yml").read_text()
        job = workflow.split("  component-build:\n", 1)[1].split("  component-install:\n", 1)[0]
        script = textwrap.dedent(job.split("        run: |\n", 1)[1].split("      - uses:", 1)[0])
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            (root / "scripts").mkdir()
            shutil.copyfile(ROOT / "scripts/platforms.sh", root / "scripts/platforms.sh")
            (root / "spec").mkdir()
            (root / "spec/openssh.spec").write_text("%global ver 10.6p1\n")
            (root / "bin").mkdir()
            docker = root / "bin/docker"
            docker.write_text(textwrap.dedent("""\
                #!/usr/bin/env python3
                import pathlib
                import sys

                if '/src/scripts/build-in-container.sh' in sys.argv:
                    parent = pathlib.Path('dist')
                    created = not parent.exists()
                    output = parent / sys.argv[-1]
                    output.mkdir(parents=True)
                    for name in ('openssh-10.6p2-2.centos7.x86_64.rpm', 'SHA256SUMS',
                                 'SOURCE-SHA256SUM', 'openssh-centos7.spec'):
                        (output / name).write_text('container-produced ' + name)
                    # A container-created root-owned 0755 directory is readable
                    # but not writable by the runner. Emulate that boundary
                    # without requiring sudo or Docker in the unit suite.
                    if created:
                        parent.chmod(0o555)
                elif '/src/scripts/verify-rpms.sh' not in sys.argv:
                    raise SystemExit('unexpected container command')
                """))
            docker.chmod(0o755)
            env = dict(os.environ, PATH=str(root / "bin") + os.pathsep + os.environ["PATH"],
                       ENTRY=json.dumps({"package": "openssh", "el": "centos7", "version": "10.6p2",
                                         "url": "https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-10.6p2.tar.gz"}))
            try:
                result = subprocess.run(["bash", "-e", "-c", script], cwd=root, env=env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                source = root / "dist/centos7"
                target = root / "dist/openssh/centos7"
                self.assertEqual({path.name for path in source.iterdir()},
                                 {path.name for path in target.iterdir()})
                for path in source.iterdir():
                    self.assertEqual((target / path.name).read_bytes(), path.read_bytes())
            finally:
                if (root / "dist").exists():
                    (root / "dist").chmod(0o755)


if __name__ == "__main__":
    unittest.main()
