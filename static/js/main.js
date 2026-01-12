// --- AI Sidebar System Logic: Advanced Developer Interface ---
let chatHistory = [];
let lastEnterTime = 0;
let abortController = null; // Controller for stopping generation

// Setup event listeners for the specific requested interactions
document.addEventListener('DOMContentLoaded', () => {
    const userInput = document.getElementById('ai-user-input');
    const messagesDiv = document.getElementById('chat-messages');

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
            if (currentTime - lastEnterTime < 600) { // Double tap threshold
                e.preventDefault();
                sendMessage();
                lastEnterTime = 0;
            } else {
                lastEnterTime = currentTime;
            }
        }
    });

    scrollToBottom();
});

function toggleChat() {
    const sidebar = document.getElementById('ai-sidebar');
    const trigger = document.getElementById('ai-edge-trigger');
    sidebar.classList.toggle('active');
    if (sidebar.classList.contains('active')) {
        trigger.classList.add('hidden');
        scrollToBottom();
    } else {
        trigger.classList.remove('hidden');
    }
}

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

function copyText(text) {
    navigator.clipboard.writeText(text).then(() => {
        // Optional: Show copied feedback
    });
}

function editMessage(text) {
    const input = document.getElementById('ai-user-input');
    input.value = text;
    input.focus();
    // Trigger resize
    input.style.height = 'auto';
    input.style.height = (input.scrollHeight) + 'px';
}

function createActionButtons(text, isUser) {
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'msg-actions';

    // Copy Button
    const copyBtn = document.createElement('button');
    copyBtn.className = 'action-btn';
    copyBtn.innerHTML = `<span>Copy</span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`;
    copyBtn.onclick = () => copyText(text);
    actionsDiv.appendChild(copyBtn);

    // Edit Button (Only for user)
    if (isUser) {
        const editBtn = document.createElement('button');
        editBtn.className = 'action-btn';
        editBtn.innerHTML = `<span>Edit</span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>`;
        editBtn.onclick = () => editMessage(text);
        actionsDiv.appendChild(editBtn);
    }

    return actionsDiv;
}

function addUserMessageUI(text) {
    const messagesDiv = document.getElementById('chat-messages');

    // Wrapper for alignment and actions
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

// Initial state handler for the unified button
function handleSendClick() {
    const btn = document.getElementById('ai-send-btn');
    if (btn.classList.contains('stop-mode')) {
        stopGeneration();
    } else {
        sendMessage();
    }
}

function stopGeneration() {
    if (abortController) {
        abortController.abort();
        abortController = null;
        toggleStopButton(false);
        // Add a small indicator that it was stopped
        const messagesDiv = document.getElementById('chat-messages');
        const lastMsg = messagesDiv.lastElementChild;
        if (lastMsg && lastMsg.querySelector('.msg-content')) {
            lastMsg.querySelector('.msg-content').insertAdjacentHTML('beforeend', ' <span style="opacity:0.5; font-size:0.8em;">(Stopped)</span>');
        }
    }
}

function toggleStopButton(active) {
    const btn = document.getElementById('ai-send-btn');
    const sendIcon = btn.querySelector('.send-icon');
    const stopIcon = btn.querySelector('.stop-icon');

    if (active) {
        btn.classList.add('stop-mode');
        sendIcon.style.display = 'none';
        stopIcon.style.display = 'block';
    } else {
        btn.classList.remove('stop-mode');
        sendIcon.style.display = 'block';
        stopIcon.style.display = 'none';
    }
}

async function sendMessage() {
    const input = document.getElementById('ai-user-input');
    const messagesDiv = document.getElementById('chat-messages');
    const statsMini = document.getElementById('ai-stats-realtime');
    const text = input.value.trim();

    if (!text) return;

    // Add User Message
    addUserMessageUI(text);

    // Reset input and clear input cache (keeping history)
    input.value = '';
    input.style.height = 'auto';
    localStorage.removeItem('ai_user_input_cache');
    scrollToBottom();

    // Init AbortController
    abortController = new AbortController();
    toggleStopButton(true);

    // Prepare AI Message Container with Thinking support
    const aiDiv = document.createElement('div');
    aiDiv.className = 'ai-msg';

    const thinkingBox = document.createElement('details');
    thinkingBox.className = 'thinking-box';
    thinkingBox.style.display = 'none';
    thinkingBox.innerHTML = '<summary>Thinking Process</summary><div class="thinking-content"></div>';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    contentDiv.innerHTML = '<em>Generating response...</em>';

    const metricsDiv = document.createElement('div');
    metricsDiv.className = 'msg-metrics';

    aiDiv.appendChild(thinkingBox);
    aiDiv.appendChild(contentDiv);
    aiDiv.appendChild(metricsDiv);
    messagesDiv.appendChild(aiDiv);
    scrollToBottom();

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

        contentDiv.innerHTML = '';

        // Buffer to handle partial JSON chunks
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep the last partial line in buffer

            for (const line of lines) {
                const trimmedLine = line.trim();
                if (!trimmedLine || !trimmedLine.startsWith('data: ')) continue;

                try {
                    const jsonStr = trimmedLine.substring(6);
                    const data = JSON.parse(jsonStr);

                    if (data.error) {
                        contentDiv.innerHTML = `<div style="color: #ff3b30;">[System Error]: ${data.error}</div>`;
                        toggleStopButton(false);
                        return;
                    }

                    if (data.thinking) {
                        thinkingBox.style.display = 'block';
                        fullThinking += data.thinking;
                        thinkingBox.querySelector('.thinking-content').textContent = fullThinking;
                    }

                    if (data.content) {
                        fullContent += data.content;
                        // Use requestAnimationFrame for smoother UI updates if heavy
                        contentDiv.innerHTML = marked.parse(fullContent);
                        // Highlight only periodically or at the end to save resources, but fine for now
                        contentDiv.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
                    }

                    if (data.done && data.metrics) {
                        const m = data.metrics;
                        // Better metric validation to avoid 1000t/s on 1 token
                        let speed = 0;
                        if (m.eval_count > 1 && m.eval_duration > 0.1) {
                            speed = (m.eval_count / m.eval_duration).toFixed(1);
                        } else {
                            // Estimated falling back to token stream speed if server metrics are weird
                            speed = "—";
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

        // Add action buttons to the finalized message
        aiDiv.appendChild(createActionButtons(fullContent, false));

        // Finalize History
        chatHistory.push({ role: 'user', content: text });
        chatHistory.push({ role: 'assistant', content: fullContent });
        localStorage.setItem('ai_chat_history', JSON.stringify(chatHistory));

    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('Generation stopped by user');
            // Save partial state
            if (fullContent) {
                chatHistory.push({ role: 'user', content: text });
                chatHistory.push({ role: 'assistant', content: fullContent });
                localStorage.setItem('ai_chat_history', JSON.stringify(chatHistory));
                aiDiv.appendChild(createActionButtons(fullContent, false));
            }
        } else {
            console.error('Chat Error:', error);
            contentDiv.innerHTML = `<div style="color: #ff3b30;">Connection failed. Check host availability.</div>`;
        }
    } finally {
        toggleStopButton(false);
        abortController = null;
    }
}

function scrollToBottom() {
    const viewport = document.getElementById('chat-messages');
    viewport.scrollTop = viewport.scrollHeight;
}