"""Regression tests for the Lua language-file reader in src/updater.py.

Run from the repository root:

    python -m unittest discover -s tests -v

A '--' inside a quoted Lua string is text, not a comment. Stripping it cut the
string and made the whole language table unreadable (every @i18n(...)@ tag then
shipped unresolved).
"""

import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
UPDATER_PATH = os.path.join(HERE, "..", "src", "updater.py")

_spec = importlib.util.spec_from_file_location("updater", UPDATER_PATH)
updater = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(updater)


class StripLuaCommentTests(unittest.TestCase):
    def test_comment_after_code_is_removed(self):
        self.assertEqual(updater._strip_lua_comment('x = 1 -- note\n'), 'x = 1 \n')

    def test_comment_only_line_becomes_empty(self):
        self.assertEqual(updater._strip_lua_comment('  -- note\n'), '  \n')

    def test_dashes_inside_double_quotes_are_kept(self):
        line = '        help_p2 = "steht dort --.",\n'
        self.assertEqual(updater._strip_lua_comment(line), line)

    def test_dashes_inside_single_quotes_are_kept(self):
        line = "name = 'a -- b'\n"
        self.assertEqual(updater._strip_lua_comment(line), line)

    def test_escaped_quote_does_not_end_the_string(self):
        line = 'v = "say \\" -- here" -- real comment\n'
        self.assertEqual(updater._strip_lua_comment(line), 'v = "say \\" -- here" \n')

    def test_line_without_newline_stays_without_newline(self):
        self.assertEqual(updater._strip_lua_comment('x = 1 -- note'), 'x = 1 ')


class LoadLuaI18nTableTests(unittest.TestCase):
    def setUp(self):
        self.app = updater.RFSuiteUpdaterApp.__new__(updater.RFSuiteUpdaterApp)
        self.app.log = lambda message: None
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, text):
        path = os.path.join(self._tmp.name, "de.lua")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_table_with_dashes_in_a_string_is_read_completely(self):
        path = self._write(
            "return {\n"
            "  app = {\n"
            "    loading = \"Lade...\", -- trailing comment\n"
            "    modules = {\n"
            "      flight_tuning = { name = \"Flugabstimmung\" },\n"
            "      fblstatus = {\n"
            "        help_p2 = \"fehlt eine Spalte, steht dort --.\",\n"
            "        help_p3 = \"Diagramm\"\n"
            "      },\n"
            "    },\n"
            "  },\n"
            "}\n"
        )
        table = self.app._load_lua_i18n_table(path)
        self.assertEqual(table["app"]["loading"], "Lade...")
        self.assertEqual(table["app"]["modules"]["flight_tuning"]["name"], "Flugabstimmung")
        self.assertEqual(
            table["app"]["modules"]["fblstatus"]["help_p2"],
            "fehlt eine Spalte, steht dort --.",
        )
        self.assertEqual(table["app"]["modules"]["fblstatus"]["help_p3"], "Diagramm")

    def test_missing_file_returns_empty_table(self):
        self.assertEqual(self.app._load_lua_i18n_table(os.path.join(self._tmp.name, "none.lua")), {})

    def test_broken_file_raises_instead_of_returning_empty(self):
        path = self._write('return {\n  app = {\n    loading = "unterminated\n')
        with self.assertRaises(RuntimeError):
            self.app._load_lua_i18n_table(path)

    def test_file_without_table_raises(self):
        path = self._write("-- only a comment\n")
        with self.assertRaises(RuntimeError):
            self.app._load_lua_i18n_table(path)


if __name__ == "__main__":
    unittest.main()
