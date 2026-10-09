import os
import tempfile
from pathlib import Path

# Isolate persistent files for tests before importing the app.
_tmp = tempfile.TemporaryDirectory()
os.environ["FOE_DATA_DIR"] = _tmp.name

from fastapi.testclient import TestClient
from app.main import app, db, create_session
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
