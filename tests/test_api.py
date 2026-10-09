import os
import tempfile
from pathlib import Path

# Isolate persistent files for tests before importing the app.
_tmp = tempfile.TemporaryDirectory()
os.environ["FOE_DATA_DIR"] = _tmp.name

from fastapi.testclient import TestClient
from app.main import app, db, create_session, provider_config, AGENT_TOOLS
import time, uuid

client = TestClient(app)
con = db()
_test_uid = uuid.uuid4().hex
con.execute('INSERT INTO users(id,email,password_hash,google_sub,created_at) VALUES(?,?,?,?,?)',
            (_test_uid, 'foe-tests@example.com', '', 'google-test-subject', time.time()))
_test_token = create_session(con, _test_uid)
con.commit()
con.close()
client.headers.update({'Authorization': 'Bearer ' + _test_token})

def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True

def test_create_and_list_project():
    created = client.post("/api/projects", json={"name": "demo"})
    assert created.status_code == 200
    project = created.json()
    assert project["name"] == "demo"
    listed = client.get("/api/projects")
    assert any(item["id"] == project["id"] for item in listed.json())

def test_file_round_trip_and_path_traversal():
    project = client.post("/api/projects", json={"name": "files"}).json()
    pid = project["id"]
    saved = client.put(f"/api/projects/{pid}/file", json={"path": "src/main.py", "content": "print('hello')"})
    assert saved.status_code == 200
    read = client.get(f"/api/projects/{pid}/file", params={"path": "src/main.py"})
    assert read.json()["content"] == "print('hello')"
    blocked = client.put(f"/api/projects/{pid}/file", json={"path": "../escape.txt", "content": "no"})
    assert blocked.status_code == 400

def test_task_is_recorded_as_plan():
    project = client.post("/api/projects", json={"name": "tasks"}).json()
    response = client.post(f"/api/projects/{project['id']}/tasks", json={"prompt": "Add a test"})
    assert response.status_code == 200
    assert response.json()["status"] == "planned"

def test_saved_memories_round_trip():
    created = client.post('/api/memories', json={'content': 'Prefers concise Python examples'})
    assert created.status_code == 200
    memory = created.json()
    listed = client.get('/api/memories')
    assert any(item['id'] == memory['id'] for item in listed.json())
    deleted = client.delete('/api/memories/' + memory['id'])
    assert deleted.status_code == 200
    assert all(item['id'] != memory['id'] for item in client.get('/api/memories').json())


def test_deepseek_provider_removed():
    assert provider_config('deepseek') is None


def test_agent_exposes_sandboxed_command_runner():
    names = {item['function']['name'] for item in AGENT_TOOLS}
    assert 'run_command' in names

def test_agent_tools_include_web():
    names = {item['function']['name'] for item in AGENT_TOOLS}
    assert {'web_search', 'fetch_url'} <= names


def test_strip_html():
    from app.main import strip_html
    assert strip_html('<script>bad()</script><p>Hello <b>world</b></p>') == 'Hello world'


def test_conversations_endpoints_and_isolation():
    assert client.get('/api/conversations').json() == []
    assert client.get('/api/conversations/doesnotexist/messages').status_code == 404
    assert client.delete('/api/conversations/doesnotexist').status_code == 404


def test_assistant_agent_without_provider_uses_brain():
    response = client.post('/api/assistant/agent', json={'prompt': 'hello'})
    assert response.status_code == 200
    body = response.json()
    assert body['ok'] is True
    assert body['provider'] == 'foe-brain'
    assert 'Foe' in body['response'] or 'foe' in body['response'].lower()


def test_brain_calculator_and_utilities():
    assert client.post('/api/assistant/agent', json={'prompt': 'calculate 15% of 240'}).json()['response'].startswith('(15/100*240)') or '36' in client.post('/api/assistant/agent', json={'prompt': 'calculate 15% of 240'}).json()['response']
    assert '8' in client.post('/api/assistant/agent', json={'prompt': 'calculate 2^3'}).json()['response']
    assert 'km' in client.post('/api/assistant/agent', json={'prompt': 'convert 5 miles to km'}).json()['response']
    assert 'UUID' in client.post('/api/assistant/agent', json={'prompt': 'give me a uuid'}).json()['response']


def test_brain_notes_and_files_round_trip():
    noted = client.post('/api/assistant/agent', json={'prompt': 'note brain test entry'})
    assert noted.status_code == 200 and 'saved' in noted.json()['response'].lower()
    shown = client.post('/api/assistant/agent', json={'prompt': 'show my notes'})
    assert 'brain test entry' in shown.json()['response']
    created = client.post('/api/assistant/agent', json={'prompt': 'create a file hello.txt with: hi from foe'})
    assert created.status_code == 200 and 'hello.txt' in created.json()['response']
    read = client.post('/api/assistant/agent', json={'prompt': 'read the file hello.txt'})
    assert 'hi from foe' in read.json()['response']


def test_capabilities_and_auth_mode_are_public():
    from fastapi.testclient import TestClient as TC
    from app.main import app as app2
    anon = TC(app2)
    caps = anon.get('/api/assistant/capabilities')
    assert caps.status_code == 200 and len(caps.json()['capabilities']) >= 8
    mode = anon.get('/api/auth/mode')
    assert mode.status_code == 200 and mode.json()['mode'] in ('local', 'google')


def test_chat_falls_back_to_brain():
    stream = client.post('/api/chat', json={'messages': [{'role': 'user', 'content': 'what can you do'}]})
    assert stream.status_code == 200
    assert 'foe' in stream.text.lower()
