from __future__ import annotations
import asyncio, json, os, re, shutil, sqlite3, subprocess, time, uuid, zipfile
from pathlib import Path, PurePosixPath
from typing import Any
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Header, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
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
GITHUB_API = 'https://api.github.com'
FOE_ACCESS_KEY = os.getenv('FOE_ACCESS_KEY', '').strip()
ALLOW_HOST_COMMANDS = os.getenv('FOE_ALLOW_HOST_COMMANDS', 'false').lower() == 'true'

app = FastAPI(title='Foe Agent API', version='0.2.0', description='AI software engineering workspace')

@app.middleware('http')
async def protect_api(request: Request, call_next):
    # Protect project/file mutation, agent execution, terminal and model endpoints on public hosting.
    if FOE_ACCESS_KEY and request.url.path.startswith('/api/') and request.url.path != '/api/health':
        import hmac
        supplied = request.headers.get('x-foe-access', '')
        if not hmac.compare_digest(supplied, FOE_ACCESS_KEY):
            return JSONResponse(status_code=401, content={'detail':'Foe access key required or invalid.'})
    return await call_next(request)


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
class AgentIn(BaseModel): prompt: str = Field(min_length=1, max_length=12000); model: str | None = None; max_steps: int = Field(default=8, ge=1, le=12)
class GithubFileIn(BaseModel): path: str = Field(min_length=1, max_length=500); content: str = Field(max_length=1000000); message: str = Field(default='Update from Foe Agent', min_length=1, max_length=200)

@app.get('/api/health')
def health():
    con=db(); count=con.execute('SELECT COUNT(*) n FROM projects').fetchone()['n']; con.close()
    return {'ok': True, 'service':'foe-agent', 'version':app.version, 'projects':count, 'access_required':bool(FOE_ACCESS_KEY), 'execution':'docker sandbox required' if not ALLOW_HOST_COMMANDS else 'host commands explicitly enabled'}

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



def github_headers(token: str | None):
    if not token or not token.strip():
        raise HTTPException(401, 'Connect GitHub with a fine-grained personal access token to use repository tools.')
    return {'Authorization': f'Bearer {token.strip()}', 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}

@app.get('/api/github/status')
async def github_status(x_github_token: str | None = Header(default=None)):
    if not x_github_token:
        return {'connected': False, 'message': 'GitHub is not connected in this browser.'}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(f'{GITHUB_API}/user', headers=github_headers(x_github_token))
        if r.status_code == 401:
            return {'connected': False, 'message': 'GitHub token is invalid or expired.'}
        r.raise_for_status(); u = r.json()
        return {'connected': True, 'login': u.get('login'), 'name': u.get('name')}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f'GitHub connection failed: {type(e).__name__}')

@app.get('/api/github/repos')
async def github_repos(x_github_token: str | None = Header(default=None)):
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f'{GITHUB_API}/user/repos', headers=github_headers(x_github_token), params={'sort':'updated','per_page':100,'affiliation':'owner,collaborator,organization_member'})
        if r.status_code >= 400:
            raise HTTPException(r.status_code, 'GitHub API rejected the request. Check token scopes and access.')
        return [{'full_name':x['full_name'],'name':x['name'],'private':x['private'],'default_branch':x['default_branch'],'html_url':x['html_url'],'description':x.get('description')} for x in r.json()]
    except HTTPException: raise
    except Exception as e: raise HTTPException(502, f'GitHub API unavailable: {type(e).__name__}')

@app.get('/api/github/repo/{owner}/{repo}/tree')
async def github_repo_tree(owner: str, repo: str, x_github_token: str | None = Header(default=None)):
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.get(f'{GITHUB_API}/repos/{owner}/{repo}/git/trees/HEAD', headers=github_headers(x_github_token), params={'recursive':'1'})
        if r.status_code >= 400: raise HTTPException(r.status_code, 'Could not read repository tree. Check repository access.')
        return {'tree':[{'path':x['path'],'type':x['type'],'size':x.get('size')} for x in r.json().get('tree',[]) if x.get('type')=='blob'][:2000]}
    except HTTPException: raise
    except Exception as e: raise HTTPException(502, f'GitHub API unavailable: {type(e).__name__}')

@app.get('/api/github/repo/{owner}/{repo}/file')
async def github_read_file(owner: str, repo: str, path: str, x_github_token: str | None = Header(default=None)):
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f'{GITHUB_API}/repos/{owner}/{repo}/contents/{path}', headers=github_headers(x_github_token))
        if r.status_code == 404: raise HTTPException(404, 'GitHub file not found.')
        if r.status_code >= 400: raise HTTPException(r.status_code, 'Could not read file from GitHub.')
        obj=r.json()
        if obj.get('type') != 'file' or obj.get('size',0)>1000000: raise HTTPException(413, 'Only text files up to 1 MB can be opened from GitHub.')
        import base64
        try: content=base64.b64decode(obj.get('content','')).decode('utf-8')
        except Exception: raise HTTPException(415, 'File is not UTF-8 text.')
        return {'path':path,'content':content,'sha':obj.get('sha'),'size':obj.get('size')}
    except HTTPException: raise
    except Exception as e: raise HTTPException(502, f'GitHub API unavailable: {type(e).__name__}')

@app.put('/api/github/repo/{owner}/{repo}/file')
async def github_write_file(owner: str, repo: str, data: GithubFileIn, x_github_token: str | None = Header(default=None)):
    import base64
    headers=github_headers(x_github_token)
    async with httpx.AsyncClient(timeout=25) as client:
        check=await client.get(f'{GITHUB_API}/repos/{owner}/{repo}/contents/{data.path}',headers=headers)
        payload={'message':data.message,'content':base64.b64encode(data.content.encode()).decode()}
        if check.status_code == 200: payload['sha']=check.json().get('sha')
        elif check.status_code != 404: raise HTTPException(check.status_code,'Cannot check existing GitHub file; verify repository access.')
        r=await client.put(f'{GITHUB_API}/repos/{owner}/{repo}/contents/{data.path}',headers=headers,json=payload)
    if r.status_code >= 400: raise HTTPException(r.status_code, 'GitHub rejected the commit. Check token permissions (Contents: read/write).')
    result=r.json()
    return {'saved':True,'path':data.path,'commit':result.get('commit',{}).get('sha'),'url':result.get('content',{}).get('html_url')}


class GithubImportIn(BaseModel):
    project_id: str
    branch: str | None = None

@app.post('/api/github/import/{owner}/{repo}')
async def github_import_repo(owner: str, repo: str, data: GithubImportIn, x_github_token: str | None = Header(default=None)):
    base=project_path(data.project_id)
    headers=github_headers(x_github_token)
    try:
        async with httpx.AsyncClient(timeout=45,follow_redirects=True) as client:
            meta=await client.get(f'{GITHUB_API}/repos/{owner}/{repo}',headers=headers)
            if meta.status_code>=400: raise HTTPException(meta.status_code,'Cannot access repository. Check the token and repository name.')
            branch=data.branch or meta.json().get('default_branch','main')
            archive=await client.get(f'{GITHUB_API}/repos/{owner}/{repo}/zipball/{branch}',headers=headers)
            if archive.status_code>=400: raise HTTPException(archive.status_code,'GitHub could not provide a source archive.')
        import io
        with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
            entries=[x for x in z.infolist() if not x.is_dir()]
            if len(entries)>2000: raise HTTPException(413,'Repository archive has more than 2000 files.')
            total=0; copied=0
            for entry in entries:
                parts=PurePosixPath(entry.filename).parts
                rel='/'.join(parts[1:])
                if not rel or any(part in {'node_modules','.git','.venv','dist','build'} for part in PurePosixPath(rel).parts): continue
                if entry.file_size>2_000_000: continue
                total+=entry.file_size
                if total>MAX_UPLOAD*5: raise HTTPException(413,'Repository archive exceeds the import size limit.')
                dest=safe_file(base,rel); dest.parent.mkdir(parents=True,exist_ok=True)
                with z.open(entry) as src, dest.open('wb') as out: shutil.copyfileobj(src,out)
                copied+=1
        return {'imported':True,'repository':f'{owner}/{repo}','branch':branch,'files':copied,'bytes':total}
    except HTTPException: raise
    except zipfile.BadZipFile: raise HTTPException(400,'GitHub returned an invalid archive.')
    except Exception as e: raise HTTPException(502,f'GitHub import failed: {type(e).__name__}')

AGENT_TOOLS = [
 {'type':'function','function':{'name':'list_files','description':'List all project files.','parameters':{'type':'object','properties':{},'required':[]}}},
 {'type':'function','function':{'name':'read_file','description':'Read a UTF-8 text file from the project.','parameters':{'type':'object','properties':{'path':{'type':'string'}},'required':['path']}}},
 {'type':'function','function':{'name':'write_file','description':'Create or replace a UTF-8 project file. Only write files necessary for the user request.','parameters':{'type':'object','properties':{'path':{'type':'string'},'content':{'type':'string'}},'required':['path','content']}}},
 {'type':'function','function':{'name':'search_files','description':'Search text in project text files.','parameters':{'type':'object','properties':{'query':{'type':'string'}},'required':['query']}}},
 {'type':'function','function':{'name':'run_check','description':'Run a safe, pre-approved test or syntax-check command in the isolated Docker sandbox. Allowed commands: pytest -q, python -m pytest -q, python -m compileall ., node --test, npm test, npm run build, npm run lint, ruff check ., go test ./..., cargo test, git diff --check, git status --short.','parameters':{'type':'object','properties':{'command':{'type':'string'}},'required':['command']}}}
]
ALLOWED_AGENT_CHECKS = {'pytest -q','python -m pytest -q','python -m compileall .','node --test','npm test','npm run build','npm run lint','ruff check .','go test ./...','cargo test','git diff --check','git status --short'}

async def execute_agent_tool(pid: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    base=project_path(pid)
    if name == 'list_files':
        items=[]
        for p in base.rglob('*'):
            if p.is_file() and not any(x in {'.git','node_modules','.venv','__pycache__'} for x in p.parts):
                items.append({'path':p.relative_to(base).as_posix(),'size':p.stat().st_size})
        return {'files':sorted(items,key=lambda x:x['path'])[:1500]}
    if name == 'read_file':
        path=str(args.get('path','')); target=safe_file(base,path)
        if not target.is_file(): return {'error':'File not found'}
        if target.stat().st_size > 200000: return {'error':'File exceeds 200 KB agent read limit'}
        try: return {'path':path,'content':target.read_text(encoding='utf-8')}
        except UnicodeDecodeError: return {'error':'Not a UTF-8 text file'}
    if name == 'write_file':
        path=str(args.get('path','')); content=args.get('content')
        if not isinstance(content,str): return {'error':'content must be text'}
        target=safe_file(base,path)
        if len(content.encode())>1000000: return {'error':'File exceeds 1 MB write limit'}
        target.parent.mkdir(parents=True,exist_ok=True); target.write_text(content,encoding='utf-8')
        return {'written':path,'bytes':target.stat().st_size}
    if name == 'search_files':
        query=str(args.get('query','')).strip()
        if not query: return {'error':'Search query is empty'}
        hits=[]
        for p in base.rglob('*'):
            if not p.is_file() or any(x in {'.git','node_modules','.venv','__pycache__'} for x in p.parts) or p.stat().st_size>200000: continue
            try:
                for i,line in enumerate(p.read_text(encoding='utf-8').splitlines(),1):
                    if query.lower() in line.lower(): hits.append({'path':p.relative_to(base).as_posix(),'line':i,'text':line[:300]})
                    if len(hits)>=100: return {'matches':hits}
            except (UnicodeDecodeError,OSError): continue
        return {'matches':hits}
    if name == 'run_check':
        command=str(args.get('command','')).strip()
        if command not in ALLOWED_AGENT_CHECKS: return {'error':'Command is not in the safe check allowlist','allowed':sorted(ALLOWED_AGENT_CHECKS)}
        if not shutil.which('docker'): return {'error':'Sandbox execution unavailable on this host: Docker is not installed. Run Foe locally with Docker or configure a dedicated sandbox runner.'}
        data=CommandIn(command=command,timeout=45)
        # Keep checks isolated: no network, bounded resources, read-only root, only workspace mounted writable.
        cmd=['docker','run','--rm','--network','none','--memory','768m','--cpus','1','--pids-limit','128','--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=96m','--cap-drop','ALL','--security-opt','no-new-privileges','--user','10001:10001','-v',f'{base}:/workspace:rw','-w','/workspace',SANDBOX_IMAGE,'/bin/sh','-lc',command]
        try:
            done=subprocess.run(cmd,cwd=base,capture_output=True,text=True,timeout=data.timeout,check=False)
            return {'command':command,'exit_code':done.returncode,'stdout':done.stdout[-12000:],'stderr':done.stderr[-12000:],'sandboxed':True}
        except subprocess.TimeoutExpired:
            return {'command':command,'exit_code':124,'stderr':'Timed out after 45 seconds','sandboxed':True}
    return {'error':f'Unknown tool: {name}'}

@app.post('/api/projects/{pid}/agent')
async def run_agent(pid: str, data: AgentIn):
    base=project_path(pid)
    async with httpx.AsyncClient(timeout=httpx.Timeout(120,connect=5)) as client:
        try:
            tags=await client.get(f'{OLLAMA_URL}/api/tags'); tags.raise_for_status()
            available=[m.get('name') for m in tags.json().get('models',[])]
            model=data.model or DEFAULT_MODEL
            if available and model not in available: raise HTTPException(400,f'Model {model} is not installed on the configured provider.')
            rows=[]
            for p in base.rglob('*'):
                if p.is_file() and not any(x in {'.git','node_modules','.venv','__pycache__'} for x in p.parts):
                    rows.append(p.relative_to(base).as_posix())
            context='\n'.join(rows[:250])
            messages=[
                {'role':'system','content':'You are Foe, a software engineering agent working inside one user-selected project. Use tools to inspect files before changing code, make focused edits, and run tests when possible. Do not claim a test passed unless the tool output confirms it. Never attempt secrets extraction, destructive disk operations, or network exfiltration. Tool execution is limited to this project and approved checks. If you are done, respond with a concise summary and list files changed and test results. Current project file list:\n'+context},
                {'role':'user','content':data.prompt}
            ]
            steps=[]; final=''
            for _ in range(data.max_steps):
                r=await client.post(f'{OLLAMA_URL}/api/chat',json={'model':model,'messages':messages,'tools':AGENT_TOOLS,'stream':False,'options':{'temperature':0.1}})
                if r.status_code>=400: raise HTTPException(502,'Model provider error: '+r.text[:400])
                msg=r.json().get('message',{})
                calls=msg.get('tool_calls') or []
                messages.append({'role':'assistant','content':msg.get('content',''),'tool_calls':calls})
                if not calls:
                    final=msg.get('content','')
                    break
                for call in calls:
                    fn=call.get('function',{}); name=fn.get('name',''); args=fn.get('arguments') or {}
                    if not isinstance(args,dict): args={}
                    result=await execute_agent_tool(pid,name,args)
                    steps.append({'tool':name,'arguments':{k:v for k,v in args.items() if k!='content'},'result':result})
                    messages.append({'role':'tool','tool_name':name,'content':json.dumps(result,ensure_ascii=False)[:16000]})
            if not final:
                r=await client.post(f'{OLLAMA_URL}/api/chat',json={'model':model,'messages':messages,'stream':False,'options':{'temperature':0.1}})
                r.raise_for_status(); final=r.json().get('message',{}).get('content','Agent stopped after reaching the tool-step limit.')
            return {'ok':True,'model':model,'response':final,'steps':steps,'step_limit':data.max_steps}
        except HTTPException: raise
        except httpx.ConnectError: raise HTTPException(503,f'Cannot reach Ollama at {OLLAMA_URL}. Configure OLLAMA_BASE_URL to a reachable model endpoint.')
        except Exception as e: raise HTTPException(502,f'Agent run failed: {type(e).__name__}: {str(e)[:250]}')

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
