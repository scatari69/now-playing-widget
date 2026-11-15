import os
import tempfile
import unittest
from unittest.mock import patch

folder = tempfile.TemporaryDirectory()
os.environ.update(SECRET_KEY='x' * 40, BASE_URL='https://example.com', SPOTIFY_CLIENT_ID='id', SPOTIFY_CLIENT_SECRET='secret', DATABASE_PATH=folder.name + '/test.db')
import app

class WidgetTests(unittest.TestCase):
    def setUp(self):
        with app.sqlite3.connect(app.DB) as db:
            db.execute('DELETE FROM users')
            db.execute('INSERT INTO users (id,name,refresh_token,widget_token) VALUES (?,?,?,?)', ('a','Alice','refresh','private'))
        self.client = app.app.test_client()

    def test_widget_is_private_and_hides_paused_playback(self):
        self.assertEqual(self.client.get('/widget/wrong').status_code, 404)
        with patch.object(app, 'api_token', return_value={'access_token': 'access'}), patch.object(app.requests, 'get') as get:
            get.return_value.status_code = 204
            self.assertEqual(self.client.get('/api/widget/private').json, {'playing': False})

    def test_settings_require_csrf_and_validate_values(self):
        with self.client.session_transaction() as session:
            session.update(user_id='a', csrf='valid')
        self.assertEqual(self.client.post('/settings', data={'action':'save'}).status_code, 403)
        self.assertEqual(self.client.post('/settings', data={'csrf':'valid','action':'save','style':'invalid','theme':'dark'}).status_code, 400)
        self.assertEqual(self.client.post('/settings', data={'csrf':'valid','action':'save','style':'bar','theme':'purple'}).status_code, 302)
        self.assertEqual(app.db_user('id', 'a')['style'], 'bar')

    def test_rotate_invalidates_link(self):
        with self.client.session_transaction() as session:
            session.update(user_id='a', csrf='valid')
        self.client.post('/settings', data={'csrf':'valid','action':'rotate'})
        self.assertEqual(self.client.get('/widget/private').status_code, 404)

if __name__ == '__main__':
    unittest.main()
