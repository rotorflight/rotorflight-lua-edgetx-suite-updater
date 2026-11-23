"""What a source-branch install stages beside the code: widgets, function scripts, templates,
announcement folders and the build identity, as the suite's own packager stages them.

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
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def read(root, rel):
    with open(os.path.join(root, *rel.split("/")), "r", encoding="utf-8") as f:
        return f.read()


class Host(updater.RFSuiteUpdaterApp):
    """The app's own staging and i18n methods, without a window."""

    def __init__(self):
        pass

    def log(self, _message):
        pass


def source_tree(repo, version_patch="1"):
    write(repo, "src/main.lua", "-- entry")
    write(repo, "src/rfsuite/lib/paths.lua", 'return {\n  core = "/SCRIPTS/RFSUITE/core",\n}\n')
    write(repo, "src/rfsuite/lib/version.lua", "M.MAJOR = 0\nM.MINOR = 3\nM.PATCH = %s\n" % version_patch)
    write(repo, "src/rfsuite/i18n/init.lua", "return {}")
    write(repo, "src/rfsuite/i18n/en.lua", 'return {\n  templates = {\n    rotorflight = {\n'
                                           '      about = "A model for Rotorflight",\n    },\n  },\n}\n')
    write(repo, "src/widgets/rfsuite/main.lua", "-- dashboard")
    write(repo, "src/widgets/rfsuitesvc/main.lua", "-- service")
    write(repo, "src/functions/rfsbg.lua", "-- background")
    write(repo, "src/functions/notes.txt", "not a script")
    write(repo, "src/templates/5.Rotorflight/Rotorflight.yml", "header: {}")
    write(repo, "src/templates/5.Rotorflight/Rotorflight.lua", 'local s = "@i18n(templates.rotorflight.about)@"')
    write(repo, "src/templates/5.Rotorflight/about.txt", "@i18n(templates.rotorflight.about)@\n")
    for pack in ("en", "de"):
        for sub in ("evt", "inflight"):
            write(repo, f"src/rfsuite/audio/{pack}/default/{sub}/a.wav")


class BranchPackageTests(unittest.TestCase):
    def stage(self, version_patch="1"):
        repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repo, True)
        source_tree(repo, version_patch)
        out = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, out, True)
        Host()._package_source_tree(repo, out, "en")
        return out

    def assertStaged(self, out, rel):
        self.assertTrue(os.path.isfile(os.path.join(out, *rel.split("/"))), rel)

    def test_every_widget_directory_is_staged(self):
        out = self.stage()
        self.assertStaged(out, "WIDGETS/rfsuite/main.lua")
        self.assertStaged(out, "WIDGETS/rfsuitesvc/main.lua")

    def test_function_scripts_are_staged_flat(self):
        out = self.stage()
        self.assertStaged(out, "SCRIPTS/FUNCTIONS/rfsbg.lua")
        self.assertFalse(os.path.exists(os.path.join(out, "SCRIPTS", "FUNCTIONS", "notes.txt")))

    def test_templates_are_staged_and_resolved(self):
        out = self.stage()
        self.assertStaged(out, "TEMPLATES/5.Rotorflight/Rotorflight.yml")
        self.assertEqual(read(out, "TEMPLATES/5.Rotorflight/about.txt"), "A model for Rotorflight\n")
        self.assertEqual(read(out, "TEMPLATES/5.Rotorflight/Rotorflight.lua"), 'local s = "A model for Rotorflight"')

    def test_inflight_announcements_are_staged(self):
        out = self.stage()
        for pack in ("en", "de"):
            self.assertStaged(out, f"SOUNDS/rf/{pack}/evt/a.wav")
            self.assertStaged(out, f"SOUNDS/rf/{pack}/inflight/a.wav")

    def test_the_build_identity_names_the_version_and_follows_the_sources(self):
        first = read(self.stage("1"), "SCRIPTS/RFSUITE/core/build.txt")
        again = read(self.stage("1"), "SCRIPTS/RFSUITE/core/build.txt")
        other = read(self.stage("2"), "SCRIPTS/RFSUITE/core/build.txt")
        self.assertRegex(first, r"^[0-9a-f]{16}-0\.3\.1\n$")
        self.assertEqual(first, again)
        self.assertNotEqual(first.split("-")[0], other.split("-")[0])


PACKAGE_LANGUAGE = """local M = {}
function M.packageLanguage()
  return "en"
end
return M
"""


class SoundPackTests(unittest.TestCase):
    """One pack per archive where the tree falls back to the package's pack, both packs otherwise."""

    def stage(self, lang, fallback):
        repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repo, True)
        source_tree(repo)
        if fallback:
            write(repo, "src/rfsuite/lib/system_locale.lua", PACKAGE_LANGUAGE)
        out = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, out, True)
        Host()._package_source_tree(repo, out, lang)
        sounds = os.path.join(out, "SOUNDS", "rf")
        return sorted(d for d in os.listdir(sounds) if os.path.isdir(os.path.join(sounds, d)))

    def test_a_tree_with_the_fallback_stages_the_chosen_language_only(self):
        self.assertEqual(self.stage("de", fallback=True), ["de"])
        self.assertEqual(self.stage("en", fallback=True), ["en"])

    def test_a_language_without_its_own_pack_gets_the_english_one(self):
        self.assertEqual(self.stage("fr", fallback=True), ["en"])

    def test_an_older_tree_keeps_both_packs(self):
        self.assertEqual(self.stage("de", fallback=False), ["de", "en"])

    def test_only_a_real_definition_counts(self):
        with tempfile.TemporaryDirectory() as core:
            write(core, "lib/system_locale.lua", "-- function M.packageLanguage() is planned\n")
            self.assertEqual(updater.sound_packs_to_stage(core, core, "de"), ["en", "de"])
            write(core, "lib/system_locale.lua", "M.packageLanguage = function()\n  return nil\nend\n")
            os.makedirs(os.path.join(core, "de"))
            self.assertEqual(updater.sound_packs_to_stage(core, core, "de"), ["de"])


if __name__ == "__main__":
    unittest.main()
