"""Fixed UTF-8 byte tokenizer; no pretrained tokenizer."""
import argparse,json
from pathlib import Path
PAD,BOS,EOS=256,257,258
VOCAB_SIZE=259
def encode(text): return list(text.encode("utf-8",errors="replace"))
def decode(ids): return bytes(int(i) for i in ids if 0<=int(i)<256).decode("utf-8",errors="replace")
def main():
 p=argparse.ArgumentParser(); p.add_argument("--data",default="data"); p.add_argument("--output",default="artifacts/tokenizer.json"); a=p.parse_args()
 files=sorted(x for x in Path(a.data).rglob("*") if x.is_file() and x.suffix.lower() in {".txt",".md"})
 if not files: raise SystemExit("No .txt or .md training files found. Add a licensed corpus first.")
 size=sum(len(x.read_bytes()) for x in files); out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps({"type":"utf8-byte","vocab_size":VOCAB_SIZE,"files":len(files),"bytes":size},indent=2)+"\n")
 print(f"Indexed {len(files)} files, {size:,} bytes -> {out}. Byte vocabulary is fixed; trainer reads the corpus.")
if __name__=="__main__": main()
