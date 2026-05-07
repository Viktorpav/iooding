import requests
import time
import json

# Testing our new MLX Native Server
URL = "http://localhost:8080/v1/chat/completions"
PROMPT = "What is Django? Explain it in 3 sentences."
PAYLOAD = {
    "messages": [{"role": "user", "content": PROMPT}],
    "max_tokens": 512,
    "stream": True  # We use streaming to measure "Thinking Time" (TTFT)
}

print(f"\n{'='*50}")
print(f"Benchmarking: MLX Native Server (Port 8080)")
print(f"{'='*50}")

start_total = time.time()
first_token_time = None
tokens_received = 0

with requests.post(URL, json=PAYLOAD, stream=True) as response:
    for line in response.iter_lines():
        if line:
            if first_token_time is None:
                first_token_time = time.time() - start_total
            
            line_str = line.decode('utf-8')
            if line_str.startswith("data: "):
                data_str = line_str[6:]
                if data_str == "[DONE]":
                    break
                
                try:
                    chunk = json.loads(data_str)
                    content = chunk["choices"][0]["delta"].get("content", "")
                    if content:
                        tokens_received += 1
                        # print(content, end="", flush=True) # Uncomment to see the stream
                except:
                    pass

elapsed_total = time.time() - start_total
gen_speed = tokens_received / (elapsed_total - first_token_time) if first_token_time else 0

print(f"\n\nRESULTS:")
print(f"Thinking Time (TTFT): {first_token_time:.2f}s  <-- This is the reasoning phase")
print(f"Total Generation:      {tokens_received} tokens")
print(f"Total Time:           {elapsed_total:.2f}s")
print(f"Pure Generation Speed: {gen_speed:.1f} tok/s")
print(f"{'='*50}")

