"""Small decoder-only Transformer initialized from random weights."""
from dataclasses import asdict, dataclass
import torch
from torch import nn
from torch.nn import functional as F

@dataclass
class ModelConfig:
    vocab_size: int = 259
    n_layer: int = 4
    n_head: int = 4
    n_embd: int = 256
    block_size: int = 256
    dropout: float = 0.1
    def validate(self):
        if self.n_embd % self.n_head: raise ValueError("n_embd must be divisible by n_head")
        if min(self.n_layer, self.n_head, self.n_embd, self.block_size) < 1: raise ValueError("dimensions must be positive")

class Block(nn.Module):
    def __init__(self, c):
        super().__init__()
        self.ln1=nn.LayerNorm(c.n_embd)
        self.attn=nn.MultiheadAttention(c.n_embd,c.n_head,dropout=c.dropout,batch_first=True)
        self.ln2=nn.LayerNorm(c.n_embd)
        self.mlp=nn.Sequential(nn.Linear(c.n_embd,4*c.n_embd),nn.GELU(),nn.Linear(4*c.n_embd,c.n_embd),nn.Dropout(c.dropout))
        self.register_buffer("mask",torch.triu(torch.ones(c.block_size,c.block_size,dtype=torch.bool),diagonal=1),persistent=False)
    def forward(self,x):
        y=self.ln1(x); a,_=self.attn(y,y,y,attn_mask=self.mask[:x.size(1),:x.size(1)],need_weights=False)
        x=x+a
        return x+self.mlp(self.ln2(x))

class FoeLM(nn.Module):
    def __init__(self,cfg):
        super().__init__(); cfg.validate(); self.config=cfg
        self.token=nn.Embedding(cfg.vocab_size,cfg.n_embd); self.position=nn.Embedding(cfg.block_size,cfg.n_embd)
        self.blocks=nn.Sequential(*(Block(cfg) for _ in range(cfg.n_layer))); self.norm=nn.LayerNorm(cfg.n_embd)
        self.lm_head=nn.Linear(cfg.n_embd,cfg.vocab_size,bias=False); self.lm_head.weight=self.token.weight
        self.apply(self._init_weights)
    @staticmethod
    def _init_weights(m):
        if isinstance(m,(nn.Linear,nn.Embedding)):
            nn.init.normal_(m.weight,mean=0.0,std=0.02)
            if isinstance(m,nn.Linear) and m.bias is not None: nn.init.zeros_(m.bias)
    def forward(self,idx,targets=None):
        _,n=idx.shape
        if n>self.config.block_size: raise ValueError("sequence exceeds block_size")
        pos=torch.arange(n,device=idx.device); x=self.token(idx)+self.position(pos)[None,:,:]
        logits=self.lm_head(self.norm(self.blocks(x)))
        loss=F.cross_entropy(logits.reshape(-1,logits.size(-1)),targets.reshape(-1)) if targets is not None else None
        return logits,loss
    @torch.no_grad()
    def generate(self,idx,max_new_tokens=128,temperature=0.8,top_k=40):
        self.eval()
        for _ in range(max_new_tokens):
            logits,_=self(idx[:,-self.config.block_size:]); logits=logits[:,-1,:]/max(temperature,1e-5)
            if top_k and top_k<logits.size(-1):
                vals,_=torch.topk(logits,top_k); logits[logits<vals[:,-1:]]=-float("inf")
            idx=torch.cat((idx,torch.multinomial(torch.softmax(logits,dim=-1),1)),dim=1)
        return idx
    def config_dict(self): return asdict(self.config)
