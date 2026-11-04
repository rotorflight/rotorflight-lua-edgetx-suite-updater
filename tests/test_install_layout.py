"""Which layout a source tree expects, and what an install removes from a card.

Run from the repository root: python -m unittest discover -s tests
"""

import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
UPDATER_PATH = os.path.join(HERE, "..", "src", "updater.py")

_spec = importlib.util.spec_from_file_location("updater", UPDATER_PATH)
updater = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(updater)


def write(root, rel, text="x"):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class SourceTreeLayoutTests(unittest.TestCase):
    def test_new_layout_is_read_from_paths_lua(self):
        with tempfile.TemporaryDirectory() as src_core:
            write(src_core, "lib/paths.lua", 'return {\n  core = "/SCRIPTS/RFSUITE/core",\n}\n')
            code, data = updater.source_tree_layout(src_core)
            self.assertEqual(code, ("SCRIPTS", "RFSUITE", "core"))
            self.assertEqual(data, ("SCRIPTS", "RFSUITE", "user"))

    def test_older_paths_lua_keeps_the_older_layout(self):
        with tempfile.TemporaryDirectory() as src_core:
            write(src_core, "lib/paths.lua", 'return {\n  core = "/SCRIPTS/TOOLS/rfsuite-core",\n}\n')
            code, data = updater.source_tree_layout(src_core)
            self.assertEqual(code, ("SCRIPTS", "TOOLS", "rfsuite-core"))
            self.assertEqual(data, ("SCRIPTS", "TOOLS", "rfsuite.user"))

    def test_tree_without_paths_lua_keeps_the_older_layout(self):
        with tempfile.TemporaryDirectory() as src_core:
            code, _ = updater.source_tree_layout(src_core)
            self.assertEqual(code, ("SCRIPTS", "TOOLS", "rfsuite-core"))


class PackageSourceTreeTests(unittest.TestCase):
    def stage(self, core_literal):
        """Runs the real staging on a minimal source tree; returns the staging folder."""

        roots = []

        class Host:
            def log(self, _message):
                pass

            def _generate_theme_index(self, _core, _user):
                pass

            def _precompile_i18n_dir(self, root):
                roots.append(root)

            def _resolve_i18n_dir(self, *_args):
                pass

        repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repo, True)
        write(repo, "src/main.lua", "-- entry")
        write(repo, "src/rfsuite/lib/paths.lua", 'return {\n  core = "%s",\n}\n' % core_literal)
        write(repo, "src/rfsuite/init.lua", "return {}")
        out = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, out, True)
        updater.RFSuiteUpdaterApp._package_source_tree(Host(), repo, out, "en")
        self.i18n_roots = roots
        return out

    def test_new_layout_source_tree_stages_the_new_folders(self):
        out = self.stage("/SCRIPTS/RFSUITE/core")
        self.assertTrue(os.path.isfile(os.path.join(out, "SCRIPTS", "TOOLS", "rfsuite.lua")))
        self.assertTrue(os.path.isfile(os.path.join(out, "SCRIPTS", "RFSUITE", "core", "lib", "paths.lua")))
        self.assertFalse(os.path.exists(os.path.join(out, "SCRIPTS", "TOOLS", "rfsuite-core")))
        core = os.path.join(out, "SCRIPTS", "RFSUITE", "core")
        self.assertTrue(any(core.startswith(root) for root in self.i18n_roots), self.i18n_roots)

    def test_older_source_tree_stages_the_older_folders(self):
        out = self.stage("/SCRIPTS/TOOLS/rfsuite-core")
        self.assertTrue(os.path.isfile(os.path.join(out, "SCRIPTS", "TOOLS", "rfsuite.lua")))
        self.assertTrue(os.path.isfile(os.path.join(out, "SCRIPTS", "TOOLS", "rfsuite-core", "lib", "paths.lua")))
        self.assertFalse(os.path.exists(os.path.join(out, "SCRIPTS", "RFSUITE")))


class DropPackagedDataTests(unittest.TestCase):
    def test_no_package_brings_a_data_file_along(self):
        with tempfile.TemporaryDirectory() as stage:
            write(stage, "SCRIPTS/TOOLS/rfsuite.user/preferences.ini", "default")
            write(stage, "SCRIPTS/RFSUITE/user/preferences.lua", "default")
            kept = write(stage, "SCRIPTS/RFSUITE/core/lib/version.lua")
            updater.drop_packaged_data(stage)
            self.assertFalse(os.path.exists(os.path.join(stage, "SCRIPTS", "TOOLS", "rfsuite.user")))
            self.assertFalse(os.path.exists(os.path.join(stage, "SCRIPTS", "RFSUITE", "user")))
            self.assertTrue(os.path.isfile(kept))


class RemovePreviousCodeTests(unittest.TestCase):
    def test_code_of_every_layout_and_entry_bytecode_go_and_data_stays(self):
        with tempfile.TemporaryDirectory() as card:
            for rel in (
                "SCRIPTS/RFSUITE/core/lib/version.lua",
                "SCRIPTS/TOOLS/rfsuite-core/lib/version.lua",
                "SCRIPTS/TOOLS/rfsuite/lib/version.lua",
                "SCRIPTS/TOOLS/rfsuite.luac",
                "SCRIPTS/FUNCTIONS/rfsbg.luac",
                "WIDGETS/rfsuite/main.luac",
                "WIDGETS/rfsuitesvc/main.luac",
            ):
                write(card, rel)
            kept = [
                write(card, "SCRIPTS/RFSUITE/user/preferences.lua"),
                write(card, "SCRIPTS/TOOLS/rfsuite.user/preferences.lua"),
                write(card, "SCRIPTS/TOOLS/rfsuite.lua"),
                write(card, "SCRIPTS/TOOLS/rf2.lua"),
                write(card, "SCRIPTS/TOOLS/rf2.luac"),
                write(card, "WIDGETS/rfsuite/main.lua"),
            ]

            updater.remove_previous_code(card)

            for gone in ("SCRIPTS/RFSUITE/core", "SCRIPTS/TOOLS/rfsuite-core", "SCRIPTS/TOOLS/rfsuite",
                         "SCRIPTS/TOOLS/rfsuite.luac", "SCRIPTS/FUNCTIONS/rfsbg.luac",
                         "WIDGETS/rfsuite/main.luac", "WIDGETS/rfsuitesvc/main.luac"):
                self.assertFalse(os.path.exists(os.path.join(card, *gone.split("/"))), gone)
            for path in kept:
                self.assertTrue(os.path.isfile(path), path)

    def test_a_card_without_the_suite_is_left_alone(self):
        with tempfile.TemporaryDirectory() as card:
            kept = write(card, "SCRIPTS/TOOLS/other.lua")
            updater.remove_previous_code(card)
            self.assertTrue(os.path.isfile(kept))


if __name__ == "__main__":
    unittest.main()
