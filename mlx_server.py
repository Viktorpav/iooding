import time
import json
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from mlx_lm import load, generate
import mlx.core as mx

app = FastAPI()

# Configuration for Speculative Decoding
MODEL_PATH = "mlx-community/gemma-4-e2b-it-4bit"
DRAFT_MODEL_PATH = "mlx-community/gemma-4-e2b-it-assistant-4bit" # Matching draft model

print(f"Loading models into MLX memory...")
model, tokenizer = load(MODEL_PATH)
draft_model, _ = load(DRAFT_MODEL_PATH)

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    
    # Convert chat template
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    
    def stream_gen():
        # Speculative decoding logic via mlx-lm
        # We yield chunks as they are generated
        for response in generate(
            model, 
            tokenizer, 
            prompt=prompt, 
            draft_model=draft_model,
            max_tokens=body.get("max_tokens", 1024),
            temp=body.get("temperature", 0.2),
            verbose=False
        ):
            chunk = {
                "choices": [{
                    "delta": {"content": response},
                    "index": 0,
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    if stream:
        return StreamingResponse(stream_gen(), media_type="text/event-stream")
    
    # Non-streaming fallback
    full_text = ""
    for response in generate(model, tokenizer, prompt=prompt, draft_model=draft_model):
        full_text += response
    
    return {
        "choices": [{"message": {"content": full_text}}]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
