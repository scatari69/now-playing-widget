import os
import secrets
import sqlite3
import time
from urllib.parse import urlencode, urlparse

import requests
from flask import Flask, abort, jsonify, redirect, render_template, request, session

app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY']
BASE_URL = os.environ['BASE_URL'].rstrip('/')
CLIENT_ID = os.environ['SPOTIFY_CLIENT_ID']
CLIENT_SECRET = os.environ['SPOTIFY_CLIENT_SECRET']
DB = os.environ.get('DATABASE_PATH', '/data/widget.db')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=urlparse(BASE_URL).scheme == 'https', MAX_CONTENT_LENGTH=16384)
if len(app.secret_key) < 32 or urlparse(BASE_URL).scheme not in ('https', 'http') or not urlparse(BASE_URL).netloc:
    raise RuntimeError('Set a strong SECRET_KEY and a valid BASE_URL')
os.makedirs(os.path.dirname(DB) or '.', exist_ok=True)
with sqlite3.connect(DB) as db:
    db.execute('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT NOT NULL, refresh_token TEXT NOT NULL, widget_token TEXT UNIQUE NOT NULL, style TEXT NOT NULL DEFAULT "card", theme TEXT NOT NULL DEFAULT "dark")')


def db_user(query, value):
    with sqlite3.connect(DB) as db:
        db.row_factory = sqlite3.Row
        return db.execute('SELECT * FROM users WHERE ' + query + ' = ?', (value,)).fetchone()


def api_token(data):
    response = requests.post('https://accounts.spotify.com/api/token', data=data, auth=(CLIENT_ID, CLIENT_SECRET), timeout=10)
    response.raise_for_status()
    return response.json()


def current_user():
    return db_user('id', session['user_id']) if session.get('user_id') else None


@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosiff'
    return response


@app.route('/')
def index():
    user = current_user()
    if user and 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return render_template('index.html', user=user, csrf=session.get('csrf'), base_url=BASE_URL)


@app.route('/login')
def login():
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    return redirect('https://accounts.spotify.com/authorize?' + urlencode({'client_id': CLIENT_ID, 'response_type': 'code', 'redirect_uri': BASE_URL + '/callback', 'scope': 'user-read-currently-playing', 'state': state}))


@app.route('/callback')
def callback():
    state = session.pop('oauth_state', '')
    if not state or not secrets.compare_digest(state, request.args.get('state', '')) or not request.args.get('code'):
        abort(400, 'Spotify authorization failed')
    try:
        tokens = api_token({'grant_type': 'authorization_code', 'code': request.args['code'], 'redirect_uri': BASE_URL + '/callback'})
        profile = requests.get('https://api.spotify.com/v1/me', headers={'Authorization': 'Bearer ' + tokens['access_token']}, timeout=10)
        profile.raise_for_status()
        profile = profile.json()
        with sqlite3.connect(DB) as db:
            db.execute('INSERT INTO users (id, name, refresh_token, widget_token) VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, refresh_token=excluded.refresh_token', (profile['id'], profile.get('display_name') or profile['id'], tokens['refresh_token'], secrets.token_urlsafe(32)))
    except (requests.RequestException, KeyError, ValueError):
        abort(502, 'Could not connect to Spotify')
    session.clear()
    session['user_id'] = profile['id']
    session['csrf'] = secrets.token_urlsafe(32)
    return redirect('/')


@app.post('/settings')
def settings():
    user = current_user()
    if not user:
        abort(401)
    if not secrets.compare_digest(session.get('csrf', ''), request.form.get('csrf', '')) or not session.get('csrf'):
        abort(403)
    action = request.form.get('action')
    with sqlite3.connect(DB) as db:
        if action == 'save':
            style, theme = request.form.get('style'), request.form.get('theme')
            if style not in ('card', 'minimal', 'bar') or theme not in ('dark', 'light', 'purple'):
                abort(400)
            db.execute('UPDATE users SET style=?, theme=? WHERE id=?', (style, theme, user['id']))
        elif action == 'rotate':
            db.execute('UPDATE users SET widget_token=? WHERE id=?', (secrets.token_urlsafe(32), user['id']))
        elif action == 'logout':
            session.clear()
        else:
            abort(400)
    return redirect('/')


@app.route('/widget/<token>')
def widget(token):
    user = db_user('widget_token', token)
    if not user:
        abort(404)
    return render_template('widget.html', user=user, token=token)


@app.route('/api/widget/<token>')
def widget_data(token):
    user = db_user('widget_token', token)
    if not user:
        abort(404)
    try:
        tokens = api_token({'grant_type': 'refresh_token', 'refresh_token': user['refresh_token']})
        if tokens.get('refresh_token'):
            with sqlite3.connect(DB) as db:
                db.execute('UPDATE users SET refresh_token=? WHERE id=?', (tokens['refresh_token'], user['id']))
        response = requests.get('https://api.spotify.com/v1/me/player/currently-playing', headers={'Authorization': 'Bearer ' + tokens['access_token']}, timeout=10)
        if response.status_code == 204:
            return jsonify(playing=False)
        response.raise_for_status()
        data = response.json()
        item = data.get('item') or {}
        images = (item.get('album') or {}).get('images') or []
        return jsonify(playing=bool(data.get('is_playing') and item), title=item.get('name', ''), artist=', '.join(a.get('name', '') for a in item.get('artists', [])), image=images[-1]['url'] if images else '', progress=data.get('progress_ms') or 0, duration=item.get('duration_ms') or 0)
    except (requests.RequestException, KeyError, ValueError):
        return jsonify(error='Spotify unavailable'), 502


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
