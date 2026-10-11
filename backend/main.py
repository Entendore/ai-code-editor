import json
import subprocess
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from llama_cpp import Llama
from vcs import vcs
from vector_store import index_codebase, search_codebase

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

print("Loading local LLM...")
# Ensure you have downloaded a model (e.g., qwen2.5-coder-7b-instruct-q4_k_m.gguf) into backend/models/
model_path = "./models/coder.gguf"
if not os.path.exists(model_path):
    print("WARNING: Model not found. Please download a .gguf model and place it in backend/models/coder.gguf")
    llm = None
else:
    llm = Llama(model_path=model_path, n_ctx=4096, n_gpu_layers=-1, verbose=False)

def read_file(file_path: str) -> str:
    try:
        with open(file_path, 'r') as f: return f.read()
    except Exception as e: return f"Error: {str(e)}"

def run_terminal_command(command: str) -> str:
    result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=".")
    return result.stdout + "\n" + result.stderr

available_tools = {
    "read_file": read_file,
    "run_terminal_command": run_terminal_command,
    "create_checkpoint": lambda description: vcs.checkpoint(description),
    "revert_to_checkpoint": lambda snap_id: vcs.revert(snap_id)
}

tools_schema = [
    {"type": "function", "function": {"name": "read_file", "description": "Read a file", "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}}},
    {"type": "function", "function": {"name": "run_terminal_command", "description": "Run shell command (use bun)", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "create_checkpoint", "description": "Save state", "parameters": {"type": "object", "properties": {"description": {"type": "string"}}, "required": ["description"]}}},
    {"type": "function", "function": {"name": "revert_to_checkpoint", "description": "Revert state", "parameters": {"type": "object", "properties": {"snap_id": {"type": "string"}}, "required": ["snap_id"]}}}
]

AGENT_SYSTEM_PROMPT = """You are an autonomous AI coding agent using Bun. 
1. Checkpoint before changes. 2. Execute. 3. Verify. 4. Self-correct or revert. 
Tools: read_file, run_terminal_command, create_checkpoint, revert_to_checkpoint."""

@app.post("/api/index")
async def index_files(files: list[dict]):
    return JSONResponse(content={"message": index_codebase(files)})

@app.get("/api/vcs/snapshots")
async def get_snapshots():
    return JSONResponse(content={"snapshots": vcs.list_snapshots()})

@app.post("/api/autocomplete")
async def autocomplete(payload: dict):
    prefix, suffix = payload.get("prefix", ""), payload.get("suffix", "")
    if not llm: return {"suggestion": ""}
    fim_prompt = f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"
    response = llm(prompt=fim_prompt, max_tokens=40, temperature=0.1, stop=["\n\n", "<|fim_suffix|>"])
    return {"suggestion": response["choices"][0]["text"].strip()}

@app.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "stop_generation": continue
            
            user_prompt = message.get("prompt", "")
            cursor_context = message.get("cursor_context", "")
            
            if "@codebase" in user_prompt:
                rag_context = search_codebase(user_prompt.replace("@codebase", ""))
                system_prompt = f"Codebase context:\n{rag_context}\n{cursor_context}"
            else:
                system_prompt = f"You are an AI coding assistant.\n{cursor_context}"

            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            
            if message.get("type") == "inline_chat":
                selected_code = message.get("selected_code", "")
                messages.append({"role": "system", "content": f"Modify this code:\n{selected_code}\nOutput ONLY code."})

            for i in range(10):
                await websocket.send_text(json.dumps({"type": "agent_status", "iteration": i+1}))
                response = llm.create_chat_completion(messages=messages, tools=tools_schema, tool_choice="auto", temperature=0.1)
                msg = response["choices"][0]["message"]
                messages.append(msg)
                
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        func_name, func_args = tc["function"]["name"], json.loads(tc["function"]["arguments"])
                        await websocket.send_text(json.dumps({"type": "tool_call", "name": func_name, "args": func_args}))
                        result = available_tools[func_name](**func_args) if func_name in available_tools else "Error"
                        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": str(result)})
                else:
                    stream = llm.create_chat_completion(messages=messages, temperature=0.1, stream=True)
                    full_resp = ""
                    for chunk in stream:
                        if "content" in chunk["choices"][0]["delta"] and chunk["choices"][0]["delta"]["content"]:
                            text = chunk["choices"][0]["delta"]["content"]
                            full_resp += text
                            await websocket.send_text(json.dumps({"type": "stream_chunk", "content": text}))
                    await websocket.send_text(json.dumps({"type": "final_answer", "content": full_resp}))
                    break
    except WebSocketDisconnect: print("Client disconnected")
