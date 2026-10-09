"""Standalone bot runner for a private, trusted Foe deployment.

Do not expose this service publicly without a long random FOE_BOT_RUNTIME_TOKEN.
It runs user-supplied Python source and should be deployed separately from the AI web app.
"""
from __future__ import annotations
import asyncio, hmac, os, re, shutil, signal, sys, time, uuid
from pathlib import Path, PurePosixPath
from typing import Any
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

TOKEN=os.getenv("FOE_BOT_RUNTIME_TOKEN","").strip()
ROOT=Path(os.getenv("FOE_BOT_WORKDIR","./bot_data")).resolve()
ROOT.mkdir(parents=True,exist_ok=True)
MAX_RUNTIME=min(max(int(os.getenv("BOT_MAX_RUNTIME_SECONDS","72000")),60),72000)
MAX_BOTS=max(1,min(int(os.getenv("BOT_MAX_CONCURRENT","3")),10))
MAX_TOTAL_BYTES=5*1024*1024
PROCESSES: dict[str,dict[str,Any]]={}
app=FastAPI(title="Foe Bot Runtime",version="0.1.0")

class StartBot(BaseModel):
    name: str=Field(default="discord-bot",min_length=1,max_length=80)
    entrypoint: str=Field(default="main.py",min_length=1,max_length=300)
    files: dict[str,str]=Field(min_length=1)
    requirements: list[str]=Field(default_factory=list,max_length=50)
    env: dict[str,str]=Field(default_factory=dict)
    runtime_seconds: int=Field(default=72000,ge=60,le=72000)

def auth(x_foe_bot_token: str | None):
    if not TOKEN or not x_foe_bot_token or not hmac.compare_digest(TOKEN,x_foe_bot_token):
        raise HTTPException(401,"Invalid bot-runtime token.")

def safe_path(base: Path, name: str) -> Path:
    rel=PurePosixPath(name.replace("\\","/"))
    if not name or rel.is_absolute() or any(x in {"..","."} for x in rel.parts) or "\x00" in name:
        raise HTTPException(400,"Invalid relative file path.")
    target=(base/Path(*rel.parts)).resolve()
    if target!=base.resolve() and base.resolve() not in target.parents:
        raise HTTPException(400,"Path escapes bot workspace.")
    return target

def public_status(bot_id: str, record: dict[str,Any]) -> dict:
    proc=record["process"]
    alive=proc.returncode is None
    return {"id":bot_id,"name":record["name"],"entrypoint":record["entrypoint"],
            "status":"running" if alive else "stopped","started_at":record["started_at"],
            "expires_at":record["expires_at"],"exit_code":proc.returncode}

async def expire_bot(bot_id: str, seconds: int):
    await asyncio.sleep(seconds)
    record=PROCESSES.get(bot_id)
    if record and record["process"].returncode is None:
        proc=record["process"]
        proc.terminate()
        try: await asyncio.wait_for(proc.wait(),timeout=8)
        except asyncio.TimeoutError: proc.kill(); await proc.wait()

@app.get("/health")
def health():
    return {"ok":True,"service":"foe-bot-runtime","max_runtime_seconds":MAX_RUNTIME,"running":sum(x["process"].returncode is None for x in PROCESSES.values())}

@app.get("/bots")
def list_bots(x_foe_bot_token: str | None=Header(default=None)):
    auth(x_foe_bot_token)
    return {"bots":[public_status(k,v) for k,v in PROCESSES.items()]}

@app.get("/bots/{bot_id}")
def bot_status(bot_id: str,x_foe_bot_token: str | None=Header(default=None)):
    auth(x_foe_bot_token)
    if bot_id not in PROCESSES: raise HTTPException(404,"Bot not found.")
    return public_status(bot_id,PROCESSES[bot_id])

@app.post("/bots/start")
async def start_bot(data: StartBot,x_foe_bot_token: str | None=Header(default=None)):
    auth(x_foe_bot_token)
    active=sum(x["process"].returncode is None for x in PROCESSES.values())
    if active>=MAX_BOTS: raise HTTPException(429,f"Maximum concurrent bot count is {MAX_BOTS}.")
    if data.entrypoint not in data.files: raise HTTPException(400,"Entrypoint must be included in files.")
    total=sum(len(v.encode()) for v in data.files.values())
    if total>MAX_TOTAL_BYTES: raise HTTPException(413,"Bot source exceeds 5 MB.")
    for package in data.requirements:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:[<>=!~]=?[A-Za-z0-9_.+-]+)?",package):
            raise HTTPException(400,"Invalid requirement specifier.")
    for key,value in data.env.items():
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,100}",key) or key in {"PATH","PYTHONPATH","HOME","FOE_BOT_RUNTIME_TOKEN"}:
            raise HTTPException(400,f"Invalid or reserved environment variable: {key}")
        if len(value)>10000: raise HTTPException(400,"Environment variable value is too long.")
    bot_id=uuid.uuid4().hex[:12]
    base=(ROOT/bot_id).resolve(); base.mkdir(parents=True)
    try:
        for name,content in data.files.items():
            target=safe_path(base,name); target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(content,encoding="utf-8")
        if data.requirements:
            pip=await asyncio.create_subprocess_exec(sys.executable,"-m","pip","install","--disable-pip-version-check","--no-input","--target",str(base/"packages"),*data.requirements,
                stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
            try: out,_=await asyncio.wait_for(pip.communicate(),timeout=240)
            except asyncio.TimeoutError: pip.kill(); await pip.wait(); raise HTTPException(408,"Dependency installation timed out.")
            if pip.returncode!=0: raise HTTPException(400,"Dependency installation failed: "+out.decode(errors="replace")[-2500:])
        env={"PATH":os.environ.get("PATH",""),"PYTHONUNBUFFERED":"1","HOME":str(base),**data.env}
        env["PYTHONPATH"]=str(base/"packages")+os.pathsep+str(base)
        target=safe_path(base,data.entrypoint)
        if not target.is_file(): raise HTTPException(400,"Entrypoint file was not written.")
        proc=await asyncio.create_subprocess_exec(sys.executable,str(target),cwd=str(base),env=env,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT,start_new_session=True)
        now=time.time(); duration=min(data.runtime_seconds,MAX_RUNTIME)
        PROCESSES[bot_id]={"name":data.name,"entrypoint":data.entrypoint,"base":base,"process":proc,
                           "started_at":now,"expires_at":now+duration,"log_task":asyncio.create_task(collect_logs(bot_id,proc)),
                           "logs":[]}
        asyncio.create_task(expire_bot(bot_id,duration))
        return {"started":True,"bot":public_status(bot_id,PROCESSES[bot_id]),"runtime_limit_seconds":duration}
    except Exception:
        shutil.rmtree(base,ignore_errors=True)
        raise

async def collect_logs(bot_id: str,proc: asyncio.subprocess.Process):
    if proc.stdout is None: return
    record=PROCESSES.get(bot_id)
    if not record: return
    while True:
        line=await proc.stdout.readline()
        if not line: break
        record["logs"].append(line.decode(errors="replace").rstrip()[:2000])
        record["logs"]=record["logs"][-300:]

@app.get("/bots/{bot_id}/logs")
def bot_logs(bot_id: str,x_foe_bot_token: str | None=Header(default=None)):
    auth(x_foe_bot_token)
    if bot_id not in PROCESSES: raise HTTPException(404,"Bot not found.")
    return {"id":bot_id,"logs":PROCESSES[bot_id]["logs"][-200:]}

@app.post("/bots/{bot_id}/stop")
async def stop_bot(bot_id: str,x_foe_bot_token: str | None=Header(default=None)):
    auth(x_foe_bot_token)
    record=PROCESSES.get(bot_id)
    if not record: raise HTTPException(404,"Bot not found.")
    proc=record["process"]
    if proc.returncode is None:
        proc.terminate()
        try: await asyncio.wait_for(proc.wait(),timeout=8)
        except asyncio.TimeoutError: proc.kill(); await proc.wait()
    return {"stopped":True,"bot":public_status(bot_id,record)}

if __name__=="__main__":
    if not TOKEN:
        raise SystemExit("FOE_BOT_RUNTIME_TOKEN is required. Refusing to start without authentication.")
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=int(os.getenv("PORT","8765")))
