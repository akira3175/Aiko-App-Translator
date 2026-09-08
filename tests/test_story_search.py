import tempfile
import unittest
from pathlib import Path

from services.library.search import search_chapters


class StorySearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.raw = Path(self.temp.name) / 'raw'
        self.target = Path(self.temp.name) / 'translated'
        self.raw.mkdir()
        self.target.mkdir()

    def search(self, **options):
        return search_chapters(self.raw, self.target, lambda folder, name: folder / name,
                               lambda path: path.read_text(encoding='utf-8'),
                               {key: [value] for key, value in options.items()})

    def test_unicode_offsets_case_and_word_boundaries(self):
        (self.target / 'v1_c1.md').write_text('😀 Mèo mèo mèocon _mèo mèo\u0301', encoding='utf-8')
        hits = self.search(q='mèo', word='1')['items']
        self.assertEqual([3, 7], [hit['start'] for hit in hits])
        self.assertEqual(1, len(self.search(q='mèo', word='1', case='1')['items']))

    def test_literal_scope_and_translated_only_chapters(self):
        (self.raw / 'v1_c1.md').write_text('a.b axb', encoding='utf-8')
        (self.target / 'v1_c2.md').write_text('a.b', encoding='utf-8')
        hits = self.search(q='a.b', scope='both')['items']
        self.assertEqual(['source', 'target'], [hit['kind'] for hit in hits])
        self.assertEqual(1, len(self.search(q='a.b')['items']))

    def test_pagination_does_not_drop_or_duplicate_hits(self):
        for index in range(23):
            (self.target / f'v1_c{index}.md').write_text('x ' * (105 if index == 0 else 1), encoding='utf-8')
        cursor = '0:0'
        hits = []
        while cursor:
            page = self.search(q='x', cursor=cursor)
            self.assertLessEqual(len(page['items']), 100)
            hits.extend(page['items'])
            cursor = page['next']
        self.assertEqual(127, len(hits))
        self.assertEqual(127, len({(hit['name'], hit['start']) for hit in hits}))

    def test_invalid_inputs(self):
        for options in ({'q': ''}, {'q': 'a', 'scope': 'other'}, {'q': 'a', 'cursor': '-1:0'}):
            with self.assertRaises(ValueError):
                self.search(**options)
