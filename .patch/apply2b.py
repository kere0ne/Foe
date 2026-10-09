p='app/main.py'
s=open(p).read()
orig=s

def rep(old,new,count=1):
    global s
    assert s.count(old)==count, 'anchor not found: %r (count=%d)' % (old[:80], s.count(old))
    s=s.replace(old,new)

def insert_before_line(anchor, chunk_text):
    global s
    i=s.index(anchor)
    ls=s.rfind('\n',0,i)+1
    s=s[:ls]+chunk_text+s[ls:]

def replace_line(anchor, new_text):
    global s
    i=s.index(anchor)
    ls=s.rfind('\n',0,i)+1
    le=s.index('\n',i)
    s=s[:ls]+new_text.rstrip('\n')+s[le:]

def insert_after_line(anchor, chunk_text):
    global s
    i=s.index(anchor)
    le=s.index('\n',i)
    s=s[:le+1]+chunk_text+s[le+1:]

# imports
rep('from urllib.parse import urlencode','from urllib.parse import urlencode, unquote, parse_qs, urlparse\nimport html as html_lib')

# constants
rep("ALLOW_HOST_COMMANDS = os.getenv('FOE_ALLOW_HOST_COMMANDS', 'false').lower() == 'true'",
    "ALLOW_HOST_COMMANDS = os.getenv('FOE_ALLOW_HOST_COMMANDS', 'false').lower() == 'true'\nAUTO_MEMORY = os.getenv('FOE_AUTO_MEMORY', 'true').strip().lower() != 'false'\nMAX_MEMORIES = int(os.getenv('FOE_MAX_MEMORIES', '500'))\nASSISTANT_PROJECT_NAME = 'Foe Assistant'\nWEB_FETCH_LIMIT = int(os.getenv('FOE_WEB_FETCH_CHARS', '9000'))\nUSER_AGENT = 'Mozilla/5.0 (compatible; FoeAgent/0.3)'")

# db schema: postgres branch
pg_anchor='con.execute("CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,content TEXT NOT NULL,created_at DOUBLE PRECISION NOT NULL)")'
rep(pg_anchor, pg_anchor + '\n' + open('.patch/schema_pg.txt').read().rstrip('\n'))

# db schema: sqlite branch
sq_anchor="CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,content TEXT NOT NULL,created_at REAL NOT NULL);''')"
sq_new=open('.patch/schema_sqlite.txt').read()
rep(sq_anchor, sq_anchor.replace(";''')",';') + '\n' + sq_new)

# memory cap
rep("if count>=100:", "if count>=MAX_MEMORIES:")
rep("'Memory limit reached (100). Delete an old memory first.'", "f'Memory limit reached ({MAX_MEMORIES}). Delete an old memory first.'")

# model classes
rep("class ChatIn(BaseModel): messages: list[dict[str, str]]; model: str | None = None; temperature: float = Field(default=0.2, ge=0, le=2)",
    "class ChatIn(BaseModel): messages: list[dict[str, str]]; model: str | None = None; temperature: float = Field(default=0.2, ge=0, le=2); conversation_id: str | None = None")
rep("class AgentIn(BaseModel): prompt: str = Field(min_length=1, max_length=12000); model: str | None = None; max_steps: int = Field(default=12, ge=1, le=24)",
    "class AgentIn(BaseModel): prompt: str = Field(min_length=1, max_length=12000); model: str | None = None; max_steps: int = Field(default=12, ge=1, le=24); history: list[dict[str, str]] = Field(default_factory=list)")

# helpers
helpers=open('.patch/helpers.txt').read()
rep('def password_hash(password: str) -> str:', helpers + 'def password_hash(password: str) -> str:')

# web tool dispatch in execute_agent_tool
tool_anchor='async def execute_agent_tool(pid: str, name: str, args: dict[str, Any], github_token: str | None = None) -> dict[str, Any]:\n    base=project_path(pid)'
tool_new=tool_anchor + "\n    if name == 'web_search':\n        return await web_search_tool(str(args.get('query','')))\n    if name == 'fetch_url':\n        return await web_fetch_tool(str(args.get('url','')))"
rep(tool_anchor, tool_new)

# AGENT_TOOLS additions
rep(']\nALLOWED_AGENT_CHECKS = ', open('.patch/webtools.txt').read() + 'ALLOWED_AGENT_CHECKS = ')

# replace old run_agent block with agent loop + assistant + conversations endpoints
start=s.index("@app.post('/api/projects/{pid}/agent')")
end=s.index("@app.post('/api/projects/{pid}/bots/start')")
s=s[:start]+open('.patch/agentblock.txt').read()+s[end:]

# chat persistence: insert conversation bookkeeping at top of stream()
rep('    async def stream():\n        failures=[]', open('.patch/chat_top.txt').read())

# openai stream accumulation
replace_line("if content: yield 'data: '+json.dumps({'message':{'content':content},'done':False})", open('.patch/chat_openai.txt').read())

# ollama stream accumulation
replace_line("if line: yield f'data: {line}", open('.patch/chat_ollama.txt').read())

# persist assistant reply + auto memory before [DONE]
insert_before_line("yield 'data: [DONE]", open('.patch/chat_save.txt').read())

# memory wording now includes auto-saved facts
rep('User-approved saved memories', 'Saved memories')

# version bump
rep("version='0.2.0'", "version='0.3.0'")

open(p,'w').write(s)
print('backend ok, delta chars:', len(s)-len(orig))
