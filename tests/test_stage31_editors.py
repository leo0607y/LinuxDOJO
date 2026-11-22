"""Regression: inserting the exercise marker must not leave a stale ERROR count."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from curriculum import stage31_editors


class EditorFixtureTests(unittest.TestCase):
    def test_error_count_after_replacing_error_or_info_row(self):
        for position in (1001, 1002):
            with self.subTest(position=position):
                files = {}
                context = SimpleNamespace(data={}, write=lambda name, text, **kw: files.update({name: text}))
                with patch.object(stage31_editors.R, 'randint', return_value=position):
                    stage31_editors.s17(context)
                self.assertEqual(context.data['errs'], files['big.log'].count(' ERROR '))
                self.assertEqual(files['big.log'].count('FIX_' + context.data['tg']), 1)
