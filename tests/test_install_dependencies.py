import sys
import unittest
from unittest.mock import call, patch

from scripts import install_dependencies


class InstallDependenciesTests(unittest.TestCase):
    def run_installer(self, available_packages):
        def has_package(package):
            return package in available_packages

        with patch.object(
            install_dependencies, "pkg_config_has", side_effect=has_package
        ):
            with patch.object(install_dependencies, "run") as run:
                with patch.object(sys, "argv", ["install_dependencies.py"]):
                    install_dependencies.main()

        return run.call_args_list

    def test_prefers_girepository_2(self):
        calls = self.run_installer({"girepository-2.0"})

        self.assertEqual(
            calls[0],
            call(sys.executable, "-m", "pip", "install", "PyGObject>=3.52.0"),
        )
        self.assertEqual(
            calls[1],
            call(sys.executable, "-m", "pip", "install", "-r", "requirements.txt"),
        )

    def test_uses_legacy_pygobject_for_girepository_1(self):
        calls = self.run_installer({"gobject-introspection-1.0"})

        self.assertEqual(
            calls[0],
            call(sys.executable, "-m", "pip", "install", "PyGObject>=3.40.0,<3.52"),
        )

    def test_fails_without_girepository_development_files(self):
        with patch.object(install_dependencies, "pkg_config_has", return_value=False):
            with patch.object(install_dependencies, "run") as run:
                with patch.object(sys, "argv", ["install_dependencies.py"]):
                    with self.assertRaises(SystemExit):
                        install_dependencies.main()

        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
