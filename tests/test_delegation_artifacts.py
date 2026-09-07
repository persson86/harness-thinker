import unittest
from live_delegation import extract_static_html

HTML = '<!DOCTYPE html>\n<html><head><title>THINKER-SMOKE</title></head><body>Proposta</body></html>'


class ArtifactTests(unittest.TestCase):
    def test_actual_code_is_required_not_a_claim_of_delivery(self):
        self.assertIsNone(extract_static_html('Entrega: página HTML completa com título THINKER-SMOKE.'))
        self.assertEqual(extract_static_html(HTML), HTML)

    def test_notes_outside_a_single_fence_are_not_part_of_html_artifact(self):
        response = '```html\n' + HTML + '\n```\n\nNotas de entrega fora do artefato.'
        self.assertEqual(extract_static_html(response), HTML)
        self.assertIsNone(extract_static_html(HTML + '\nNotas soltas que apareceriam na página'))

    def test_ambiguous_or_active_artifact_is_not_automatically_reviewed(self):
        self.assertIsNone(extract_static_html('```html\n' + HTML + '\n```\n```html\n' + HTML + '\n```'))
        for addition in ('<script>alert(1)</script>', '<iframe></iframe>', '<p onclick="x()">texto</p>',
                         '<style>@import "https://example.invalid";</style>', '<img src="data:x">'):
            self.assertIsNone(extract_static_html(HTML.replace('Proposta', addition)))


if __name__ == '__main__':
    unittest.main()
