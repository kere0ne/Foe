"""Foe's own GitHub MCP server.

Run with: GITHUB_TOKEN=... python github_mcp.py
Uses stdio transport so an MCP client can launch it locally. Never commit tokens.
"""
import base64
import os
import re
import httpx
from mcp.server.fastmcp import FastMCP

TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
API = "https://api.github.com"
mcp = FastMCP("foe-github")

def headers():
    if not TOKEN:
        raise RuntimeError("Set GITHUB_TOKEN in the MCP server environment.")
    return {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}

def repo_path(owner: str, repo: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repo):
        raise ValueError("Invalid GitHub owner/repository.")
    return f"{owner}/{repo}"

@mcp.tool()
def list_repositories() -> dict:
    """List repositories available to the connected GitHub account."""
    with httpx.Client(timeout=20) as client:
        r = client.get(f"{API}/user/repos", headers=headers(),
                       params={"sort":"updated","per_page":100,"affiliation":"owner,collaborator,organization_member"})
        r.raise_for_status()
        return {"repositories":[{"full_name":x["full_name"],"private":x["private"],
                "default_branch":x["default_branch"],"html_url":x["html_url"],
                "description":x.get("description")} for x in r.json()]}

@mcp.tool()
def list_repository_files(owner: str, repo: str, branch: str = "HEAD") -> dict:
    """List files in a repository tree. Returns paths and sizes."""
    full=repo_path(owner,repo)
    with httpx.Client(timeout=25) as client:
        r=client.get(f"{API}/repos/{full}/git/trees/{branch}",headers=headers(),params={"recursive":"1"})
        r.raise_for_status()
        return {"repository":full,"files":[{"path":x["path"],"size":x.get("size")}
            for x in r.json().get("tree",[]) if x.get("type")=="blob"][:2000]}

@mcp.tool()
def read_repository_file(owner: str, repo: str, path: str, ref: str = "") -> dict:
    """Read a UTF-8 text file up to 500 KB from a repository."""
    full=repo_path(owner,repo)
    if not path or ".." in path.replace("\\","/").split("/"):
        raise ValueError("Invalid repository path.")
    params={"ref":ref} if ref else None
    with httpx.Client(timeout=20) as client:
        r=client.get(f"{API}/repos/{full}/contents/{path}",headers=headers(),params=params)
        r.raise_for_status(); obj=r.json()
        if obj.get("type")!="file" or obj.get("size",0)>500000:
            raise ValueError("Only text files up to 500 KB are supported.")
        try: content=base64.b64decode(obj.get("content","")).decode("utf-8")
        except Exception as exc: raise ValueError("File is not UTF-8 text.") from exc
        return {"path":path,"content":content,"sha":obj.get("sha"),"html_url":obj.get("html_url")}

@mcp.tool()
def write_repository_file(owner: str, repo: str, path: str, content: str,
                          message: str = "Update from Foe GitHub MCP", branch: str = "") -> dict:
    """Create or update a repository file as a Git commit. Use only when the user requested a change."""
    full=repo_path(owner,repo)
    if not path or ".." in path.replace("\\","/").split("/") or len(content.encode())>500000:
        raise ValueError("Invalid path or file exceeds 500 KB.")
    endpoint=f"{API}/repos/{full}/contents/{path}"
    h=headers(); params={"ref":branch} if branch else None
    with httpx.Client(timeout=25) as client:
        current=client.get(endpoint,headers=h,params=params)
        payload={"message":message,"content":base64.b64encode(content.encode()).decode()}
        if current.status_code==200: payload["sha"]=current.json().get("sha")
        elif current.status_code!=404: current.raise_for_status()
        if branch: payload["branch"]=branch
        r=client.put(endpoint,headers=h,json=payload); r.raise_for_status(); obj=r.json()
        return {"saved":True,"path":path,"commit":obj.get("commit",{}).get("sha"),
                "url":obj.get("content",{}).get("html_url")}

@mcp.tool()
def create_repository_branch(owner: str, repo: str, branch: str, from_branch: str = "") -> dict:
    """Create a new branch from the repository's default branch or the named source branch."""
    full=repo_path(owner,repo)
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,200}",branch) or branch.startswith("/") or ".." in branch.split("/"):
        raise ValueError("Invalid branch name.")
    with httpx.Client(timeout=20) as client:
        meta=client.get(f"{API}/repos/{full}",headers=headers()); meta.raise_for_status()
        source=from_branch or meta.json().get("default_branch","main")
        ref=client.get(f"{API}/repos/{full}/git/ref/heads/{source}",headers=headers()); ref.raise_for_status()
        r=client.post(f"{API}/repos/{full}/git/refs",headers=headers(),
                      json={"ref":f"refs/heads/{branch}","sha":ref.json()["object"]["sha"]})
        r.raise_for_status()
        return {"created":True,"branch":branch,"sha":r.json()["object"]["sha"]}

@mcp.tool()
def create_pull_request(owner: str, repo: str, title: str, head: str, base: str = "",
                        body: str = "") -> dict:
    """Open a pull request from an existing branch. Never merge automatically."""
    full=repo_path(owner,repo)
    with httpx.Client(timeout=20) as client:
        if not base:
            meta=client.get(f"{API}/repos/{full}",headers=headers()); meta.raise_for_status()
            base=meta.json().get("default_branch","main")
        r=client.post(f"{API}/repos/{full}/pulls",headers=headers(),
                      json={"title":title,"head":head,"base":base,"body":body,"draft":True})
        r.raise_for_status(); obj=r.json()
        return {"number":obj["number"],"url":obj["html_url"],"state":obj["state"],"draft":obj["draft"]}

if __name__ == "__main__":
    mcp.run()
