// --- AI Sidebar System Logic: Advanced Developer Interface ---
let chatHistory = [];
let lastEnterTime = 0;

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

    // 4. Handle "Double Enter" for sending (Requested Revert)
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

    // Handle scroll to bottom on resize or initial load
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

function addUserMessageUI(text) {
    const messagesDiv = document.getElementById('chat-messages');
    const userDiv = document.createElement('div');
    userDiv.className = 'user-msg';
    userDiv.textContent = text;
    messagesDiv.appendChild(userDiv);
}

function addAssistantMessageUI(content) {
    const messagesDiv = document.getElementById('chat-messages');
    const aiDiv = document.createElement('div');
    aiDiv.className = 'ai-msg';
    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    contentDiv.innerHTML = marked.parse(content);
    aiDiv.appendChild(contentDiv);
    messagesDiv.appendChild(aiDiv);
    contentDiv.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
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
            body: JSON.stringify({ message: text, messages: chatHistory })
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
                        const speed = (m.eval_count / (m.eval_duration || 0.001)).toFixed(1);
                        metricsDiv.innerHTML = `<span>${m.eval_count} tokens</span> • <span>${speed} t/s</span> • <span>${m.total_duration.toFixed(2)}s</span>`;
                        statsMini.textContent = `${speed} t/s`;
                    }

                    scrollToBottom();
                } catch (e) {
                    console.warn("JSON parse error:", e);
                }
            }
        }

        // Finalize History
        chatHistory.push({ role: 'user', content: text });
        chatHistory.push({ role: 'assistant', content: fullContent });
        localStorage.setItem('ai_chat_history', JSON.stringify(chatHistory));

    } catch (error) {
        console.error('Chat Error:', error);
        contentDiv.innerHTML = `<div style="color: #ff3b30;">Connection failed. Check host availability.</div>`;
    }
}

function scrollToBottom() {
    const viewport = document.getElementById('chat-messages');
    viewport.scrollTop = viewport.scrollHeight;
}