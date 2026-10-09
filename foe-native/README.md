Foe Native: from-scratch model lab

This experimental stack initializes a decoder-only Transformer with random weights, trains a fixed UTF-8 byte tokenizer, pretrains on a user-supplied corpus, saves checkpoints, and serves a small OpenAI-compatible chat API. It does not download Qwen, Gemini, OpenRouter models, or Ollama models.

Reality check: a randomly initialized model knows nothing. The default is a tiny research model to validate the pipeline, not a competitive assistant. A useful general model requires large licensed datasets, substantial GPU compute, instruction tuning, and evaluation. This repo does not claim the model is already trained.

Setup (Python 3.11+; install a CUDA-enabled PyTorch build separately for NVIDIA GPUs):

    cd foe-native
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

Put permitted plain text or Markdown files in data/. Never include credentials, private chats, or sensitive personal data.

    python -m foe_native.tokenizer --data data --output artifacts/tokenizer.json
    python -m foe_native.train --data data --out artifacts/checkpoints --steps 1000
    python -m foe_native.serve --checkpoint artifacts/checkpoints/latest.pt --host 127.0.0.1 --port 8090

API: POST http://127.0.0.1:8090/v1/chat/completions; GET /v1/models; GET /health. The prototype is non-streaming and does not support tool calls. Do not expose publicly without authentication, rate limits, and TLS.

Config env vars: FOE_N_LAYER (4), FOE_N_HEAD (4), FOE_N_EMBD (256), FOE_BLOCK_SIZE (256), FOE_BATCH_SIZE (16), FOE_LR (3e-4), FOE_DEVICE (auto/cuda/mps/cpu).

Stages: pretrain next-byte prediction; then implement and validate supervised instruction tuning; evaluate held-out loss and task quality; deploy only a trained and tested checkpoint. Low training loss alone does not prove reasoning. This is starter research code, not a frontier model. The existing Foe web app's tools remain separate until integrated with a private endpoint.