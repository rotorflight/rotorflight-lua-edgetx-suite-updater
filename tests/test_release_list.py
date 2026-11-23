"""Which entry the version list selects when it is filled.

Run from the repository root: python -m unittest discover -s tests
"""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
UPDATER_PATH = os.path.join(HERE, "..", "src", "updater.py")

_spec = importlib.util.spec_from_file_location("updater", UPDATER_PATH)
updater = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(updater)


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Combo(dict):
    def __init__(self):
        super().__init__()
        self.index = None

    def current(self, index):
        self.index = index

    def selected(self):
        return self["values"][self.index]


def branch(name):
    return {"tag_name": f"Branch: {name}", "prerelease": True, "is_branch": True, "branch_name": name}


def release(tag, prerelease):
    return {"tag_name": f"Release: {tag}", "prerelease": prerelease, "is_branch": False}


class Host:
    """The parts of the app the list reads and writes, without a window."""

    def __init__(self, releases_data, include_prereleases):
        self.releases_data = releases_data
        self.include_prereleases = Value(include_prereleases)
        self.release_combo = Combo()
        self.selected_release_tag = Value("")
        self.selected = 0

    def _on_release_selected(self, _event):
        self.selected += 1


def fill(releases_data, include_prereleases=True):
    host = Host(releases_data, include_prereleases)
    updater.RFSuiteUpdaterApp._update_release_list(host)
    return host


# The order fetch_releases_async stores: the branches as the branches API lists them, then the
# releases newest first, as the releases API lists them.
FETCHED = [
    branch("docs/agent-skills"),
    branch("feat/dashboard-kse-kevd"),
    branch("master"),
    release("snapshot/0.3.0", True),
    release("snapshot/0.2.1", True),
]


class ReleaseListTests(unittest.TestCase):
    def test_the_newest_release_is_selected_before_any_branch(self):
        host = fill(FETCHED)
        self.assertEqual(host.release_combo.selected(), "Release: snapshot/0.3.0")
        self.assertEqual(host.selected, 1)

    def test_branches_stay_in_the_list_after_the_releases(self):
        host = fill(FETCHED)
        self.assertEqual(host.release_combo["values"], [
            "Release: snapshot/0.3.0",
            "Release: snapshot/0.2.1",
            "Branch: docs/agent-skills",
            "Branch: feat/dashboard-kse-kevd",
            "Branch: master",
        ])

    def test_a_full_release_comes_first_without_pre_releases(self):
        host = fill(FETCHED + [release("1.0.0", False)], include_prereleases=False)
        self.assertEqual(host.release_combo["values"], ["Release: 1.0.0"])

    def test_only_branches_still_selects_one(self):
        host = fill([branch("master")])
        self.assertEqual(host.release_combo.selected(), "Branch: master")

    def test_an_empty_list_selects_nothing(self):
        host = fill(FETCHED, include_prereleases=False)
        self.assertEqual(host.release_combo["values"], [])
        self.assertEqual(host.selected, 0)


if __name__ == "__main__":
    unittest.main()
