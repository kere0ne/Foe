# Foe-native training run, 2026-10-09

From-scratch decode-only LM, random init, CPU, trainer `foe_native.train`.

- Params: 3,291,392
- Vocab: 259 (byte-level, artifacts/tokenizer.json)
- Corpus: 8 public-domain Project Gutenberg books, ~4.5 MB (data/, not committed)
- Steps: 1000 (batch 16, block 256, 4 layers / 4 heads / 256 width, AdamW lr 3e-4)
- Final loss: 1.79 at step 1000 (2.16 at resume point 750)
- Checkpoints: step-250/500/750/1000.pt + latest.pt (= step 1000); committed: latest.pt only

Trainer note applies: evaluate on held-out data before deploying.
