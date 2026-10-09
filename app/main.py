from __future__ import annotations
import asyncio, json, os, re, shutil, sqlite3, subprocess, time, uuid, zipfile
from pathlib import Path, PurePosixPath
from typing import Any
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Header
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(os.getenv('FOE_DATA_DIR', './data')).resolve()
PROJECTS = ROOT / 'projects'
ROOT.mkdir(parents=True, exist_ok=True); PROJECTS.mkdir(parents=True, exist_ok=True)
DB = ROOT / 'foe.db'
MAX_UPLOAD = int(os.getenv('FOE_MAX_UPLOAD_BYTES', str(20 * 1024 * 1024)))
OLLAMA_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
DEFAULT_MODEL = os.getenv('OLLAMA_MODEL', 'qwen2.5-coder:7b')
SANDBOX_IMAGE = os.getenv('FOE_SANDBOX_IMAGE', 'foe-agent-sandbox:latest')
ALLOW_HOST_COMMANDS = os.getenv('FOE_ALLOW_HOST_COMMANDS', 'false').lower() == 'true'

app = FastAPI(title='Foe Agent API', version='0.1.0', description='Local-first AI software engineering workspace')


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript('''CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, prompt TEXT NOT NULL, status TEXT NOT NULL, plan TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL, FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE);''')
    return conn


def project_path(project_id: str) -> Path:
    con = db(); row = con.execute('SELECT id FROM projects WHERE id=?', (project_id,)).fetchone(); con.close()
    if not row: raise HTTPException(404, 'Project not found')
    path = (PROJECTS / project_id).resolve()
    if path.parent != PROJECTS.resolve(): raise HTTPException(400, 'Invalid project path')
    return path


def safe_file(base: Path, relative: str) -> Path:
    rel = PurePosixPath(relative.replace('\\', '/'))
    if not relative or rel.is_absolute() or any(p in ('..', '.') for p in rel.parts) or '\x00' in relative:
        raise HTTPException(400, 'Invalid file path')
    target = (base / Path(*rel.parts)).resolve()
    if target != base.resolve() and base.resolve() not in target.parents: raise HTTPException(400, 'Path escapes workspace')
    return target

class ProjectIn(BaseModel): name: str = Field(min_length=1, max_length=100)
class FileIn(BaseModel): path: str; content: str
class ChatIn(BaseModel): messages: list[dict[str, str]]; model: str | None = None; temperature: float = Field(default=0.2, ge=0, le=2)
class TaskIn(BaseModel): prompt: str = Field(min_length=1, max_length=12000)
class CommandIn(BaseModel): command: str = Field(min_length=1, max_length=2000); timeout: int = Field(default=15, ge=1, le=60)

@app.get('/api/health')
def health():
    con=db(); count=con.execute('SELECT COUNT(*) n FROM projects').fetchone()['n']; con.close()
    return {'ok': True, 'service':'foe-agent', 'version':app.version, 'projects':count, 'execution':'docker sandbox required' if not ALLOW_HOST_COMMANDS else 'host commands explicitly enabled'}

@app.get('/api/models')
async def models():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r=await client.get(f'{OLLAMA_URL}/api/tags'); r.raise_for_status(); payload=r.json()
        return {'provider':'ollama','connected':True,'default_model':DEFAULT_MODEL,'models':[m.get('name') for m in payload.get('models',[])]}
    except Exception as e:
        return {'provider':'ollama','connected':False,'default_model':DEFAULT_MODEL,'models':[],'error':f'Cannot reach Ollama at {OLLAMA_URL}: {type(e).__name__}'}

@app.post('/api/projects')
def create_project(data: ProjectIn):
    pid=uuid.uuid4().hex[:12]; now=time.time(); path=PROJECTS/pid; path.mkdir(parents=True)
    (path/'README.md').write_text(f'# {data.name}\n\nCreated with Foe Agent.\n', encoding='utf-8')
    con=db(); con.execute('INSERT INTO projects VALUES(?,?,?)',(pid,data.name,now)); con.commit(); con.close()
    return {'id':pid,'name':data.name,'created_at':now}

@app.get('/api/projects')
def list_projects():
    con=db(); rows=con.execute('SELECT * FROM projects ORDER BY created_at DESC').fetchall(); con.close(); return [dict(r) for r in rows]

@app.get('/api/projects/{pid}/files')
def list_files(pid: str):
    base=project_path(pid); result=[]
    for p in base.rglob('*'):
        if p.is_file() and not any(x in {'.git','node_modules','.venv'} for x in p.parts):
            result.append({'path':p.relative_to(base).as_posix(),'size':p.stat().st_size})
    return sorted(result,key=lambda x:x['path'])

@app.get('/api/projects/{pid}/file')
def read_file(pid: str, path: str):
    base=project_path(pid); target=safe_file(base,path)
    if not target.is_file(): raise HTTPException(404,'File not found')
    if target.stat().st_size > 2_000_000: raise HTTPException(413,'File too large to edit in browser')
    try: content=target.read_text(encoding='utf-8')
    except UnicodeDecodeError: raise HTTPException(415,'File is not UTF-8 text')
    return {'path':path,'content':content}

@app.put('/api/projects/{pid}/file')
def write_file(pid: str, data: FileIn):
    base=project_path(pid); target=safe_file(base,data.path)
    if len(data.content.encode()) > 2_000_000: raise HTTPException(413,'File exceeds 2 MB limit')
    target.parent.mkdir(parents=True,exist_ok=True); target.write_text(data.content,encoding='utf-8')
    return {'saved':True,'path':data.path,'bytes':target.stat().st_size}

@app.delete('/api/projects/{pid}/file')
def delete_file(pid: str, path: str):
    base=project_path(pid); target=safe_file(base,path)
    if not target.is_file(): raise HTTPException(404,'File not found')
    target.unlink(); return {'deleted':True,'path':path}

@app.post('/api/projects/{pid}/upload')
async def upload(pid: str, file: UploadFile = File(...)):
    base=project_path(pid); name=Path(file.filename or 'upload.bin').name
    if not name or name in {'.','..'}: raise HTTPException(400,'Invalid filename')
    raw=await file.read(MAX_UPLOAD+1)
    if len(raw)>MAX_UPLOAD: raise HTTPException(413,f'Upload limit is {MAX_UPLOAD} bytes')
    if name.lower().endswith('.zip'):
        try:
            import io
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                entries=z.infolist()
                if len(entries)>2000: raise HTTPException(413,'Archive contains too many entries')
                for entry in entries:
                    dest=safe_file(base,entry.filename)
                    if entry.is_dir(): dest.mkdir(parents=True,exist_ok=True); continue
                    if entry.file_size > MAX_UPLOAD: raise HTTPException(413,'Archive entry too large')
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(entry) as src, dest.open('wb') as out: shutil.copyfileobj(src,out)
        except zipfile.BadZipFile: raise HTTPException(400,'Invalid ZIP archive')
        return {'uploaded':True,'kind':'zip','files':len(entries)}
    target=safe_file(base,name); target.write_bytes(raw)
    return {'uploaded':True,'kind':'file','path':name,'bytes':len(raw)}

@app.post('/api/chat')
async def chat(data: ChatIn):
    if not data.messages or any(m.get('role') not in {'system','user','assistant'} or not isinstance(m.get('content'),str) for m in data.messages):
        raise HTTPException(400,'Messages must contain valid roles and text content')
    async def stream():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120,connect=5)) as client:
                async with client.stream('POST', f'{OLLAMA_URL}/api/chat', json={'model':data.model or DEFAULT_MODEL,'messages':data.messages,'stream':True,'options':{'temperature':data.temperature}}) as response:
                    if response.status_code >= 400:
                        body=(await response.aread()).decode('utf-8', errors='replace')
                        yield 'data: ' + json.dumps({'error':f'AI provider returned HTTP {response.status_code}: {body[:500]}'}) + '\n\n'
                        return
                    async for line in response.aiter_lines():
                        if line: yield f'data: {line}\n\n'
                    yield 'data: [DONE]\n\n'
        except Exception as e:
            yield 'data: ' + json.dumps({'error':f'AI provider unavailable at {OLLAMA_URL}: {type(e).__name__}. Start Ollama and pull a model.'}) + '\n\n'
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.post('/api/projects/{pid}/tasks')
def create_task(pid: str, data: TaskIn):
    project_path(pid); tid=uuid.uuid4().hex[:12]; now=time.time()
    plan='1. Inspect project files\n2. Propose a minimal implementation plan\n3. Make edits with user review\n4. Run tests in the sandbox\n5. Report verified results'
    con=db(); con.execute('INSERT INTO tasks(id,project_id,prompt,status,plan,result,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(tid,pid,data.prompt,'planned',plan,'',now,now)); con.commit(); con.close()
    return {'id':tid,'project_id':pid,'prompt':data.prompt,'status':'planned','plan':plan,'note':'Task recorded. Autonomous tool execution is not yet wired; use chat and file APIs for supervised changes.'}

@app.get('/api/projects/{pid}/tasks')
def list_tasks(pid: str):
    project_path(pid); con=db(); rows=con.execute('SELECT * FROM tasks WHERE project_id=? ORDER BY created_at DESC',(pid,)).fetchall(); con.close(); return [dict(r) for r in rows]

@app.post('/api/projects/{pid}/terminal')
def terminal(pid: str, data: CommandIn):
    base=project_path(pid)
    if not ALLOW_HOST_COMMANDS:
        if not shutil.which('docker'): raise HTTPException(503,'Docker is required for terminal execution. Start Docker and build the sandbox image.')
        cmd=['docker','run','--rm','--network','none','--memory','512m','--cpus','1','--pids-limit','128','--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--cap-drop','ALL','--security-opt','no-new-privileges','--user','10001:10001','-v',f'{base}:/workspace:rw','-w','/workspace',SANDBOX_IMAGE,'/bin/sh','-lc',data.command]
    else:
        # Explicit local-development escape hatch. Never enable on a public deployment.
        cmd=['/bin/sh','-lc',data.command]
    try:
        completed=subprocess.run(cmd,cwd=base,capture_output=True,text=True,timeout=data.timeout,check=False)
        return {'exit_code':completed.returncode,'stdout':completed.stdout[-20000:],'stderr':completed.stderr[-20000:],'sandboxed':not ALLOW_HOST_COMMANDS}
    except subprocess.TimeoutExpired as e:
        return {'exit_code':124,'stdout':(e.stdout or '')[-20000:] if isinstance(e.stdout,str) else '', 'stderr':'Command timed out','sandboxed':not ALLOW_HOST_COMMANDS}

@app.get('/')
def index(): return FileResponse(Path(__file__).parent/'static'/'index.html')
app.mount('/static',StaticFiles(directory=Path(__file__).parent/'static'),name='static')
