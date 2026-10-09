"""Next-token pretraining for FoeLM from random initialization."""
import argparse,os
from pathlib import Path
import torch
from .model import FoeLM,ModelConfig
from .tokenizer import encode

def device_name():
 d=os.getenv("FOE_DEVICE","auto")
 if d!="auto": return d
 if torch.cuda.is_available(): return "cuda"
 if hasattr(torch.backends,"mps") and torch.backends.mps.is_available(): return "mps"
 return "cpu"
def load_corpus(root):
 files=sorted(p for p in Path(root).rglob("*") if p.is_file() and p.suffix.lower() in {".txt",".md"})
 chunks=[]
 for p in files:
  t=p.read_text(encoding="utf-8",errors="replace").strip()
  if t: chunks.extend(encode(t+"\n\n"))
 if len(chunks)<100: raise SystemExit(f"Corpus in {root} is empty or too small; add licensed .txt/.md files.")
 return torch.tensor(chunks,dtype=torch.long)
def main():
 p=argparse.ArgumentParser(); p.add_argument("--data",default="data"); p.add_argument("--out",default="artifacts/checkpoints"); p.add_argument("--steps",type=int,default=1000); p.add_argument("--save-every",type=int,default=250); p.add_argument("--batch-size",type=int,default=int(os.getenv("FOE_BATCH_SIZE","16"))); p.add_argument("--block-size",type=int,default=int(os.getenv("FOE_BLOCK_SIZE","256"))); p.add_argument("--layers",type=int,default=int(os.getenv("FOE_N_LAYER","4"))); p.add_argument("--heads",type=int,default=int(os.getenv("FOE_N_HEAD","4"))); p.add_argument("--width",type=int,default=int(os.getenv("FOE_N_EMBD","256"))); p.add_argument("--lr",type=float,default=float(os.getenv("FOE_LR","3e-4"))); p.add_argument("--resume",default=""); a=p.parse_args()
 if min(a.steps,a.save_every,a.batch_size,a.block_size,a.layers,a.heads,a.width)<=0: raise SystemExit("Training dimensions and step counts must be positive.")
 dev=torch.device(device_name()); data=load_corpus(a.data); cfg=ModelConfig(n_layer=a.layers,n_head=a.heads,n_embd=a.width,block_size=a.block_size); model=FoeLM(cfg).to(dev); opt=torch.optim.AdamW(model.parameters(),lr=a.lr); step=0
 if a.resume:
  ck=torch.load(a.resume,map_location=dev,weights_only=False); cfg=ModelConfig(**ck["config"]); model=FoeLM(cfg).to(dev); model.load_state_dict(ck["model"]); opt=torch.optim.AdamW(model.parameters(),lr=a.lr); opt.load_state_dict(ck["optimizer"]); step=int(ck["step"])
 out=Path(a.out); out.mkdir(parents=True,exist_ok=True); model.train(); print(f"Foe random-init pretraining device={dev} bytes={len(data):,} params={sum(p.numel() for p in model.parameters()):,}")
 if len(data)<=model.config.block_size+1: raise SystemExit("Corpus must be longer than block_size + 1 bytes.")
 while step<a.steps:
  starts=torch.randint(0,len(data)-model.config.block_size-1,(a.batch_size,)); x=torch.stack([data[i:i+model.config.block_size] for i in starts]).to(dev); y=torch.stack([data[i+1:i+model.config.block_size+1] for i in starts]).to(dev)
  _,loss=model(x,y); opt.zero_grad(set_to_none=True); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1.0); opt.step(); step+=1
  if step==1 or step%25==0: print(f"step={step} loss={loss.item():.4f}")
  if step%a.save_every==0 or step==a.steps:
   ck={"step":step,"model":model.state_dict(),"optimizer":opt.state_dict(),"config":model.config_dict(),"loss":float(loss.item())}; torch.save(ck,out/f"step-{step}.pt"); torch.save(ck,out/"latest.pt"); print(f"saved {out / chr(108)+chr(97)+chr(116)+chr(101)+chr(115)+chr(116)+chr(46)+chr(112)+chr(116)}")
 print("Run complete. Evaluate on held-out data before deploying.")
if __name__=="__main__": main()
