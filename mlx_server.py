import json
import asyncio
import threading
import queue
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from mlx_lm import load, stream_generate  # Use mlx_lm for text-only stability
import mlx.core as mx

app = FastAPI()

# Configuration
MODEL_PATH = "mlx-community/gemma-4-e2b-it-OptiQ-4bit"
request_queue = queue.Queue()

# Optimization: Limit cache fragmentation on Mac
mx.metal.set_cache_limit(0)

def ai_worker():
    """Single-threaded worker that owns the MLX GPU context"""
    try:
        # Use mlx_lm (text-only) with strict=False to ignore multimodal overhead
        model, tokenizer = load(MODEL_PATH, strict=False)
        print(f"Model {MODEL_PATH} loaded successfully into AI Worker (Text-only mode).")
    except Exception as e:
        print(f"Critical error loading model: {e}")
        return

    while True:
        task = request_queue.get()
        if task is None: break
        
        prompt, token_queue, loop, body = task
        try:
            # mlx_lm.stream_generate is the fastest way for text-only chat
            for response in stream_generate(
                model, 
                tokenizer, 
                prompt=prompt, 
                max_tokens=body.get("max_tokens", 1024),
                temp=body.get("temperature", 0.1),
            ):
                # In mlx_lm, response is just a string token
                loop.call_soon_threadsafe(token_queue.put_nowait, response)
            
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
