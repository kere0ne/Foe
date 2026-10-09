"""Minimal local non-streaming OpenAI-compatible inference API."""
import argparse,os
from pathlib import Path
import torch
from fastapi import FastAPI,HTTPException
from pydantic import BaseModel,Field
import uvicorn
from .model import FoeLM,ModelConfig
from .tokenizer import encode,decode
app=FastAPI(title="Foe Native Inference",version="0.1.0"); model=None; device=None; model_id="foe-native-untrained"
class Message(BaseModel): role:str; content:str
class ChatRequest(BaseModel):
 model:str="foe-native"
 messages:list[Message]
 max_tokens:int=Field(default=128,ge=1,le=1024)
 temperature:float=Field(default=0.8,ge=0.0,le=2.0)
@app.on_event("startup")
def load_model():
 global model,device,model_id
 checkpoint=os.getenv("FOE_CHECKPOINT","artifacts/checkpoints/latest.pt"); device=torch.device(os.getenv("FOE_DEVICE","cuda" if torch.cuda.is_available() else "cpu"))
 if not Path(checkpoint).is_file(): print(f"No checkpoint at {checkpoint}; inference unavailable."); return
 ck=torch.load(checkpoint,map_location=device,weights_only=False); model=FoeLM(ModelConfig(**ck["config"])).to(device); model.load_state_dict(ck["model"]); model.eval(); model_id=f"foe-native-step-{ck.get(chr(115)+chr(116)+chr(101)+chr(112),0)}"
@app.get("/health")
def health(): return {"ok":True,"model_loaded":model is not None,"model":model_id,"device":str(device) if device else None}
@app.get("/v1/models")
def models(): return {"object":"list","data":[{"id":"foe-native","object":"model","owned_by":"kere0ne"}] if model is not None else []}
@app.post("/v1/chat/completions")
def chat(req:ChatRequest):
 if model is None: raise HTTPException(503,"No trained Foe checkpoint loaded. Train a model first.")
 if not req.messages: raise HTTPException(400,"messages must not be empty")
 prompt="".join(f"{m.role.upper()}: {m.content}\n" for m in req.messages)+"ASSISTANT:"; ids=encode(prompt)[-max(1,model.config.block_size-1):]; x=torch.tensor([ids],dtype=torch.long,device=device)
 with torch.inference_mode(): result=model.generate(x,max_new_tokens=min(req.max_tokens,model.config.block_size),temperature=max(req.temperature,0.05))
 answer=decode(result[0,len(ids):].tolist()).strip()
 return {"id":"foe-native-chat","object":"chat.completion","created":0,"model":"foe-native","choices":[{"index":0,"message":{"role":"assistant","content":answer},"finish_reason":"length"}],"usage":{"prompt_tokens":len(ids),"completion_tokens":len(encode(answer)),"total_tokens":len(ids)+len(encode(answer))}}
def main():
 p=argparse.ArgumentParser(); p.add_argument("--host",default="127.0.0.1"); p.add_argument("--port",type=int,default=8090); a=p.parse_args(); uvicorn.run(app,host=a.host,port=a.port)
if __name__=="__main__": main()
