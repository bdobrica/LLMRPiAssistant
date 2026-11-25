from html.parser import HTMLParser
import unittest

from rpi_assistant.app.control_server import render_page


class PageElements(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.links = []
        self.current = []
        self.forms = []
        self.inputs = set()
        self.feed(render_page(path).decode())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs['href'].startswith('/'):
            self.links.append(attrs['href'])
            if attrs.get('aria-current') == 'page':
                self.current.append(attrs['href'])
        if tag == 'form':
            self.forms.append(attrs['id'])
        if tag in ('input', 'button'):
            self.inputs.add(attrs.get('id'))


class PhonePagesTests(unittest.TestCase):
    def test_each_destination_has_shared_navigation_and_its_own_form(self):
        forms = {'/': 'volume-form', '/timers': 'timers-form',
                 '/reminders': 'reminders-form', '/shopping': 'shopping-form',
                 '/settings': 'settings', '/privacy': 'settings'}
        for path, form in forms.items():
            with self.subTest(path=path):
                page = PageElements(path)
                self.assertEqual(page.links, list(forms) + (['/admin/settings'] if path == '/settings' else []))
                self.assertEqual(page.current, [path])
                self.assertEqual(page.forms, [form])
                self.assertEqual('openai-key' in page.inputs, path == '/settings')
                self.assertEqual('check-microphone' in page.inputs, path == '/settings')
                self.assertEqual('conversation-logging' in page.inputs, path == '/privacy')
                self.assertEqual('privacy-delete' in page.inputs, path == '/privacy')
