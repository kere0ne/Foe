p='app/main.py'
s=open(p).read()
orig=s

def rep(old,new,count=1):
    global s
    assert s.count(old)==count, 'anchor not found: %r (count=%d)' % (old[:80], s.count(old))
    s=s.replace(old,new)

rep("from urllib.parse import urlencode","from urllib.parse import urlencode, unquote, parse_qs, urlparse\nimport html as html_lib")

rep("ALLOW_HOST_COMMANDS = os.getenv('FOE_ALLOW_HOST_COMMANDS', 'false').lower() == 'true'",
"""ALLOW_HOST_COMMANDS = os.getenv('FOE_ALLOW_HOST_COMMANDS', 'false').lower() == 'true'
AUTO_MEMORY = os.getenv('FOE_AUTO_MEMORY', 'true').strip().lower() != 'false'
MAX_MEMORIES = int(os.getenv('FOE_MAX_MEMORIES', '500'))
ASSISTANT_PROJECT_NAME = 'Foe Assistant'
WEB_FETCH_LIMIT = int(os.getenv('FOE_WEB_FETCH_CHARS', '9000'))
USER_AGENT = 'Mozilla/5.0 (compatible; FoeAgent/0.3)'""")

rep('con.execute("CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,content TEXT NOT NULL,created_at DOUBLE PRECISION NOT NULL)")',
'''con.execute("CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,content TEXT NOT NULL,created_at DOUBLE PRECISION NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL, FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE)")''')

rep("CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,content TEXT NOT NULL,created_at REAL NOT NULL);''')",
"""CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,content TEXT NOT NULL,created_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL, FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE);''')")

rep("if count>=100:\n        con.close(); raise HTTPException(429,'Memory limit reached (100). Delete an old memory first.')",
"if count>=MAX_MEMORIES:\n        con.close(); raise HTTPException(429,f'Memory limit reached ({MAX_MEMORIES}). Delete an old memory first.')")

rep("class ChatIn(BaseModel): messages: list[dict[str, str]]; model: str | None = None; temperature: float = Field(default=0.2, ge=0, le=2)",
"class ChatIn(BaseModel): messages: list[dict[str, str]]; model: str | None = None; temperature: float = Field(default=0.2, ge=0, le=2); conversation_id: str | None = None")
rep("class AgentIn(BaseModel): prompt: str = Field(min_length=1, max_length=12000); model: str | None = None; max_steps: int = Field(default=12, ge=1, le=24)",
"class AgentIn(BaseModel): prompt: str = Field(min_length=1, max_length=12000); model: str | None = None; max_steps: int = Field(default=12, ge=1, le=24); history: list[dict[str, str]] = Field(default_factory=list)")

helpers=open('.patch/helpers.txt').read()
rep("def password_hash(password: str) -> str:", helpers + "def password_hash(password: str) -> str:")

agent_anchor = 'async def execute_agent_tool(pid: str, name: str, args: dict[str, Any], github_token: str | None = None) -> dict[str, Any]:\n    base=project_path(pid)'
agent_new = agent_anchor + "\n    if name == 'web_search':\n        return await web_search_tool(str(args.get('query','')))\n    if name == 'fetch_url':\n        return await web_fetch_tool(str(args.get('url','')))"
rep(agent_anchor, agent_new)

web_tools=open('.patch/webtools.txt').read()
rep("]\nALLOWED_AGENT_CHECKS = ", web_tools + "ALLOWED_AGENT_CHECKS = ")

start=s.index("@app.post('/api/projects/{pid}/agent')")
end=s.index("@app.post('/api/projects/{pid}/bots/start')")
agentblock=open('.patch/agentblock.txt').read()
s=s[:start]+agentblock+s[end:]

open(p,'w').write(s)
print('backend core ok, delta chars:', len(s)-len(orig))
