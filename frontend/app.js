require.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs' } });
let editor, diffEditor, models = {}, openTabs = [], activeFile = null, dirHandle = null;
let inlineDecorations = [], inlineState = null, currentAiBubble = null, currentTimeline = null;

require(['vs/editor/editor.main'], function () {
    editor = monaco.editor.create(document.getElementById('monaco-editor'), { theme: 'vs-dark', automaticLayout: true });
    diffEditor = monaco.editor.createDiffEditor(document.getElementById('monaco-diff'), { theme: 'vs-dark', automaticLayout: true });

    editor.addAction({
        id: 'ai-inline-edit', label: 'AI: Inline Edit', keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyI],
        run: function(ed) {
            const selection = ed.getSelection();
            if (!selection || selection.isEmpty()) return alert("Highlight code first!");
            const inputBox = document.createElement('div');
            inputBox.style.cssText = 'position:absolute;z-index:100;background:#252526;border:1px solid #007acc;padding:5px;';
            inputBox.innerHTML = '<input type="text" placeholder="Edit..." style="background:#1e1e1e;color:#fff;border:none;outline:none;"><button>Go</button>';
            document.body.appendChild(inputBox);
            inputBox.querySelector('button').onclick = () => {
                ws.send(JSON.stringify({ type: "inline_chat", prompt: inputBox.querySelector('input').value, selected_code: ed.getModel().getValueInRange(selection) }));
                window.currentInlineSelection = selection;
                inputBox.remove();
            };
        }
    });
});

// File System
document.getElementById('open-folder-btn').onclick = async () => {
    dirHandle = await window.showDirectoryPicker();
    const tree = document.getElementById('file-tree');
    tree.innerHTML = '';
    for await (const entry of dirHandle.values()) {
        if (entry.kind === 'file') {
            const div = document.createElement('div');
            div.className = 'file-item';
            div.textContent = `📄 ${entry.name}`;
            div.onclick = () => openFile(entry, entry.name);
            tree.appendChild(div);
        }
    }
};

async function openFile(handle, path) {
    activeFile = path;
    if (!models[path]) models[path] = monaco.editor.createModel(await (await handle.getFile()).text(), 'javascript');
    if (!openTabs.includes(path)) openTabs.push(path);
    editor.setModel(models[path]);
    renderTabs();
}

function renderTabs() {
    const tabBar = document.getElementById('tabs');
    tabBar.innerHTML = '';
    openTabs.forEach(path => {
        const tab = document.createElement('div');
        tab.className = `tab ${path === activeFile ? 'active' : ''}`;
        tab.textContent = path;
        tab.onclick = () => { activeFile = path; editor.setModel(models[path]); renderTabs(); };
        tabBar.appendChild(tab);
    });
}

// WebSocket & Chat
const ws = new WebSocket('ws://localhost:8000/ws/agent');
const chatLog = document.getElementById('chat-log');
const promptInput = document.getElementById('prompt-input');
const sendBtn = document.getElementById('send-btn');
const stopBtn = document.getElementById('stop-btn');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'agent_status') {
        currentTimeline = document.createElement('div');
        currentTimeline.className = 'msg msg-timeline';
        currentTimeline.innerHTML = `🤖 Agent Step ${data.iteration}`;
        chatLog.appendChild(currentTimeline);
    } else if (data.type === 'tool_call') {
        addMessage('tool', `🔧 ${data.name}`);
    } else if (data.type === 'stream_chunk') {
        if (!currentAiBubble) { currentAiBubble = document.createElement('div'); currentAiBubble.className = 'msg msg-ai'; chatLog.appendChild(currentAiBubble); }
        currentAiBubble.innerHTML += data.content;
        chatLog.scrollTop = chatLog.scrollHeight;
    } else if (data.type === 'final_answer') {
        sendBtn.classList.remove('hidden'); stopBtn.classList.add('hidden');
        const match = data.content.match(/```[\w]*\n([\s\S]*?)\n```/);
        if (match && match[1] && activeFile) showDiff(models[activeFile].getValue(), match[1]);
        currentAiBubble = null; currentTimeline = null;
    }
};

function addMessage(type, content) {
    const div = document.createElement('div');
    div.className = `msg msg-${type}`;
    div.textContent = content;
    chatLog.appendChild(div);
}

function showDiff(original, modified) {
    diffEditor.setModel({ original: monaco.editor.createModel(original, 'javascript'), modified: monaco.editor.createModel(modified, 'javascript') });
    document.getElementById('diff-overlay').classList.remove('hidden');
}

document.getElementById('accept-ai').onclick = () => { if (activeFile) models[activeFile].setValue(diffEditor.getModel().modified.getValue()); document.getElementById('diff-overlay').classList.add('hidden'); };
document.getElementById('reject-ai').onclick = () => document.getElementById('diff-overlay').classList.add('hidden');

sendBtn.onclick = () => {
    if (!promptInput.value.trim()) return;
    addMessage('user', promptInput.value);
    ws.send(JSON.stringify({ prompt: promptInput.value, cursor_context: "" }));
    promptInput.value = '';
    sendBtn.classList.add('hidden'); stopBtn.classList.remove('hidden');
};
stopBtn.onclick = () => { ws.send(JSON.stringify({ type: "stop_generation" })); sendBtn.classList.remove('hidden'); stopBtn.classList.add('hidden'); };

// Slash Menu
promptInput.oninput = (e) => { document.getElementById('slash-menu').classList.toggle('hidden', !e.target.value.startsWith('/')); };
document.querySelectorAll('.slash-item').forEach(item => {
    item.onclick = () => { promptInput.value = item.dataset.cmd + ' '; document.getElementById('slash-menu').classList.add('hidden'); promptInput.focus(); };
});

// Terminal
const termInput = document.getElementById('terminal-input');
const termOutput = document.getElementById('terminal-output');
termInput.onkeydown = (e) => {
    if (e.key === 'Enter' && termInput.value) {
        termOutput.innerHTML += `<div>$ ${termInput.value}</div>`;
        ws.send(JSON.stringify({ type: "start_agent", task: `Run command: ${termInput.value}` }));
        termInput.value = '';
    }
};

// Resizers
function setupResizer(id, left, right) {
    const r = document.getElementById(id), l = document.getElementById(left);
    r.onmousedown = (e) => { let startX = e.clientX, startW = l.getBoundingClientRect().width; document.onmousemove = (ev) => { l.style.width = `${startW + ev.clientX - startX}px`; }; document.onmouseup = () => document.onmousemove = null; };
}
setupResizer('resizer-sidebar', 'sidebar-wrapper');
setupResizer('resizer-chat', 'ai-pane');
