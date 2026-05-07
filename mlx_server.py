import json
import asyncio
import threading
import queue
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from mlx_lm import stream_generate
from mlx_lm.utils import load_model, load_tokenizer
from huggingface_hub import snapshot_download
from pathlib import Path
import mlx.core as mx

app = FastAPI()

# Configuration
MODEL_PATH = "mlx-community/gemma-4-e2b-it-OptiQ-4bit"
request_queue = queue.Queue()

# Optimization: Modern way to limit cache fragmentation
mx.set_cache_limit(0)

def ai_worker():
    """Single-threaded worker that owns the MLX GPU context"""
    try:
        # Use snapshot_download to get a Path object (fixes the string concat error)
        model_path = Path(snapshot_download(repo_id=MODEL_PATH))
        model, config = load_model(model_path, strict=False)
        tokenizer = load_tokenizer(model_path)
        print(f"Model {MODEL_PATH} loaded successfully into AI Worker (Strict=False).")
    except Exception as e:
        print(f"Critical error loading model: {e}")
        return

    while True:
        task = request_queue.get()
        if task is None: break
        
        prompt_raw, token_queue, loop, body = task
        try:
            # Use the model's official chat template for instruction-tuned performance
            messages = body.get("messages", [])
            prompt = tokenizer.apply_chat_template(
                messages, 
                tokenize=False, 
                add_generation_prompt=True
            )
            
            # Use strict stop tokens to prevent the model from looping markers
            stop_tokens = ["<end_of_turn>", "<eos>", "<turn|>"]
            
            # mlx_lm.stream_generate with greedy decoding (no temp) is the fastest
            is_thinking = False
            for response in stream_generate(
                model, 
                tokenizer, 
                prompt=prompt, 
                max_tokens=body.get("max_tokens", 1024),
            ):
                # Support both raw strings and GenerationResponse objects
                token = response.text if hasattr(response, 'text') else response
                
                # Filter out internal Thinking Process blocks (<|channel>thought ... <channel|>)
                if "<|channel>" in token:
                    is_thinking = True
                    continue
                if "<channel|>" in token:
                    is_thinking = False
                    continue
                
                # Manual stop-token check to prevent looping markers
                if any(stop in token for stop in ["<end_of_turn>", "<eos>", "<turn|>"]):
                    break
                
                # Only stream if we aren't in the middle of a "thought" block
                if not is_thinking:
                    loop.call_soon_threadsafe(token_queue.put_nowait, token)
            
            loop.call_soon_threadsafe(token_queue.put_nowait, None)
        except Exception as e:
            print(f"Inference Error: {e}")
            loop.call_soon_threadsafe(token_queue.put_nowait, None)
        finally:
            request_queue.task_done()

threading.Thread(target=ai_worker, daemon=True).start()

@app.get("/v1/models")
async def list_models():
    return {"object": "list", "data": [{"id": MODEL_PATH, "object": "model"}]}

@app.post("/v1/embeddings")
async def embeddings(request: Request):
    return {"object": "list", "data": [{"embedding": [0.0]*1536, "index": 0}]}

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    prompt = messages[-1]["content"] if messages else ""
    
    token_queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    request_queue.put((prompt, token_queue, loop, body))

    async def stream_gen():
        while True:
            try:
                # Wait for a token from the AI worker
                # If it takes > 5s (e.g. during prefill), send a heartbeat
                token = await asyncio.wait_for(token_queue.get(), timeout=5.0)
                
                if token is None:
                    break
                
                chunk = {
                    "choices": [{
                        "delta": {"content": token},
                        "index": 0,
                        "finish_reason": None
                    }]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
            except asyncio.TimeoutError:
                # SSE Heartbeat to keep the connection alive during long prefill
                yield ": heartbeat\n\n"
                
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_gen(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
