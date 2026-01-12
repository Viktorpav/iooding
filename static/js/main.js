// --- AI Sidebar System Logic: Advanced Developer Interface ---
let chatHistory = [];
let lastEnterTime = 0;
let abortController = null;
let isGenerating = false;
const MAX_HISTORY = 50;

document.addEventListener('DOMContentLoaded', () => {
    const userInput = document.getElementById('ai-user-input');

    // 1. Recover cached input text
    const cachedInput = localStorage.getItem('ai_user_input_cache');
    if (cachedInput) {
        userInput.value = cachedInput;
        userInput.style.height = 'auto';
        userInput.style.height = (userInput.scrollHeight) + 'px';
    }

    // 2. Recover Chat History
    const savedHistory = localStorage.getItem('ai_chat_history');
    if (savedHistory) {
        try {
            chatHistory = JSON.parse(savedHistory);
            renderHistory(chatHistory);
        } catch (e) {
            console.error("Failed to load chat history", e);
            chatHistory = [];
        }
    }

    // 3. Auto-resize textarea & Cache on change
    userInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        localStorage.setItem('ai_user_input_cache', this.value);
    });

    // 4. Handle "Double Enter" for sending
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const currentTime = new Date().getTime();
            if (currentTime - lastEnterTime < 600) {
                e.preventDefault();
                handleSendClick();
                lastEnterTime = 0;
            } else {
                lastEnterTime = currentTime;
            }
        }
    });

    scrollToBottom(true);
});

// --- Layout Integration ---
function toggleChat() {
    const sidebar = document.getElementById('ai-sidebar');
    const trigger = document.getElementById('ai-edge-trigger');
    sidebar.classList.toggle('active');
    document.body.classList.toggle('ai-active');

    if (sidebar.classList.contains('active')) {
        trigger.classList.add('hidden');
        scrollToBottom(true);
        document.getElementById('ai-user-input').focus();
    } else {
        trigger.classList.remove('hidden');
    }
}

// --- Smart Scrolling (prevents jump during editing) ---
function scrollToBottom(force = false) {
    const viewport = document.getElementById('chat-messages');
    if (!viewport) return;

    const isAtBottom = viewport.scrollTop + viewport.clientHeight >= viewport.scrollHeight - 80;

    if (force || isAtBottom) {
        viewport.scrollTop = viewport.scrollHeight;
    }
}

// --- History Rendering ---
function renderHistory(history) {
    const messagesDiv = document.getElementById('chat-messages');
    history.forEach(msg => {
        if (msg.role === 'user') {
            addUserMessageUI(msg.content);
        } else if (msg.role === 'assistant') {
            addAssistantMessageUI(msg.content);
        }
    });
}

// --- Clipboard Actions ---
function copyText(text) {
    navigator.clipboard.writeText(text).then(() => {
        // Could show a toast notification here
    });
}

function editMessage(text) {
    const input = document.getElementById('ai-user-input');
    input.value = text;
    input.focus();
    input.style.height = 'auto';
    input.style.height = (input.scrollHeight) + 'px';
    localStorage.setItem('ai_user_input_cache', text);
}

// --- Action Buttons ---
function createActionButtons(text, isUser) {
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'msg-actions';

    const copyBtn = document.createElement('button');
    copyBtn.className = 'action-btn';
    copyBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`;
    copyBtn.title = 'Copy';
    copyBtn.onclick = (e) => { e.stopPropagation(); copyText(text); };
    actionsDiv.appendChild(copyBtn);

    if (isUser) {
        const editBtn = document.createElement('button');
        editBtn.className = 'action-btn';
        editBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>`;
        editBtn.title = 'Edit';
        editBtn.onclick = (e) => { e.stopPropagation(); editMessage(text); };
        actionsDiv.appendChild(editBtn);
    }

    return actionsDiv;
}

// --- Message UI ---
function addUserMessageUI(text) {
    const messagesDiv = document.getElementById('chat-messages');
    const wrapper = document.createElement('div');
    wrapper.className = 'user-wrapper';

    const userDiv = document.createElement('div');
    userDiv.className = 'user-msg';
    userDiv.textContent = text;

    wrapper.appendChild(userDiv);
    wrapper.appendChild(createActionButtons(text, true));
    messagesDiv.appendChild(wrapper);
}

function addAssistantMessageUI(content) {
    const messagesDiv = document.getElementById('chat-messages');
    const aiDiv = document.createElement('div');
    aiDiv.className = 'ai-msg';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    contentDiv.innerHTML = marked.parse(content);

    aiDiv.appendChild(contentDiv);
    aiDiv.appendChild(createActionButtons(content, false));
    messagesDiv.appendChild(aiDiv);

    contentDiv.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
}

// --- Unified Send/Stop Button ---
function handleSendClick() {
    if (isGenerating) {
        stopGeneration();
    } else {
        sendMessage();
    }
}

function stopGeneration() {
    if (abortController) {
        abortController.abort();
        abortController = null;
    }
    setGeneratingState(false);

    const messagesDiv = document.getElementById('chat-messages');
    const lastMsg = messagesDiv.lastElementChild;
    if (lastMsg && lastMsg.querySelector('.msg-content')) {
        lastMsg.querySelector('.msg-content').insertAdjacentHTML('beforeend', ' <span style="opacity:0.5; font-size:0.75em;">(stopped)</span>');
    }
}

function setGeneratingState(active) {
    isGenerating = active;
    const btn = document.getElementById('ai-send-btn');
    const sendIcon = btn.querySelector('.send-icon');
    const stopIcon = btn.querySelector('.stop-icon');

    if (active) {
        btn.classList.add('stop-mode');
        if (sendIcon) sendIcon.style.display = 'none';
        if (stopIcon) stopIcon.style.display = 'block';
    } else {
        btn.classList.remove('stop-mode');
        if (sendIcon) sendIcon.style.display = 'block';
        if (stopIcon) stopIcon.style.display = 'none';
    }
}

// --- Main Send Logic ---
async function sendMessage() {
    const input = document.getElementById('ai-user-input');
    const messagesDiv = document.getElementById('chat-messages');
    const statsMini = document.getElementById('ai-stats-realtime');
    const text = input.value.trim();

    if (!text || isGenerating) return;

    addUserMessageUI(text);

    input.value = '';
    input.style.height = 'auto';
    localStorage.removeItem('ai_user_input_cache');
    scrollToBottom(true);

    abortController = new AbortController();
    setGeneratingState(true);

    const aiDiv = document.createElement('div');
    aiDiv.className = 'ai-msg';

    const thinkingBox = document.createElement('details');
    thinkingBox.className = 'thinking-box';
    thinkingBox.style.display = 'none';
    thinkingBox.innerHTML = '<summary>Thinking Process</summary><div class="thinking-content"></div>';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    contentDiv.innerHTML = '<em class="generating-placeholder">Generating...</em>';

    const metricsDiv = document.createElement('div');
    metricsDiv.className = 'msg-metrics';

    aiDiv.appendChild(thinkingBox);
    aiDiv.appendChild(contentDiv);
    aiDiv.appendChild(metricsDiv);
    messagesDiv.appendChild(aiDiv);
    scrollToBottom(true);

    let fullContent = "";
    let fullThinking = "";

    try {
        const response = await fetch('/api/chat/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, messages: chatHistory }),
            signal: abortController.signal
        });

        if (!response.ok) throw new Error(`Status: ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        contentDiv.innerHTML = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                const trimmedLine = line.trim();
                if (!trimmedLine || !trimmedLine.startsWith('data: ')) continue;

                try {
                    const data = JSON.parse(trimmedLine.substring(6));

                    if (data.error) {
                        contentDiv.innerHTML = `<div style="color: #ff3b30;">[Error]: ${data.error}</div>`;
                        setGeneratingState(false);
                        return;
                    }

                    if (data.thinking) {
                        thinkingBox.style.display = 'block';
                        fullThinking += data.thinking;
                        thinkingBox.querySelector('.thinking-content').textContent = fullThinking;
                    }

                    if (data.content) {
                        fullContent += data.content;
                        contentDiv.innerHTML = marked.parse(fullContent);
                        contentDiv.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
                    }

                    if (data.done && data.metrics) {
                        const m = data.metrics;
                        let speed = "—";
                        if (m.eval_count > 1 && m.eval_duration > 0.1) {
                            speed = (m.eval_count / m.eval_duration).toFixed(1);
                        }
                        if (speed !== "—") {
                            metricsDiv.innerHTML = `<span>${m.eval_count} tokens</span> • <span>${speed} t/s</span> • <span>${m.total_duration.toFixed(2)}s</span>`;
                            statsMini.textContent = `${speed} t/s`;
                        }
                    }

                    scrollToBottom();
                } catch (e) {
                    console.warn("JSON parse error:", e);
                }
            }
        }

        aiDiv.appendChild(createActionButtons(fullContent, false));
        saveHistory(text, fullContent);

    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('Generation stopped by user');
            if (fullContent) {
                aiDiv.appendChild(createActionButtons(fullContent, false));
                saveHistory(text, fullContent);
            }
        } else {
            console.error('Chat Error:', error);
            contentDiv.innerHTML = `<div style="color: #ff3b30;">Connection failed.</div>`;
        }
    } finally {
        setGeneratingState(false);
        abortController = null;
    }
}

// --- History Management ---
function saveHistory(userText, assistantText) {
    chatHistory.push({ role: 'user', content: userText });
    chatHistory.push({ role: 'assistant', content: assistantText });

    // Keep history within limit
    if (chatHistory.length > MAX_HISTORY) {
        chatHistory = chatHistory.slice(chatHistory.length - MAX_HISTORY);
    }

    try {
        localStorage.setItem('ai_chat_history', JSON.stringify(chatHistory));
    } catch (e) {
        console.warn('localStorage limit reached, trimming history');
        chatHistory = chatHistory.slice(-20);
        localStorage.setItem('ai_chat_history', JSON.stringify(chatHistory));
    }
}

function clearHistory() {
    chatHistory = [];
    localStorage.removeItem('ai_chat_history');
    const messagesDiv = document.getElementById('chat-messages');
    // Keep the welcome message
    const welcome = messagesDiv.querySelector('.system-msg');
    messagesDiv.innerHTML = '';
    if (welcome) messagesDiv.appendChild(welcome);
}