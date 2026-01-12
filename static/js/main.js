// --- AI Sidebar System Logic: Advanced Developer Interface ---
let chatHistory = [];
let lastEnterTime = 0;

// Setup event listeners for the specific requested interactions
document.addEventListener('DOMContentLoaded', () => {
    const userInput = document.getElementById('ai-user-input');

    // Auto-resize textarea
    userInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });

    // Handle "Double Enter" for sending
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            const currentTime = new Date().getTime();
            if (currentTime - lastEnterTime < 400) { // Quick double tap
                e.preventDefault();
                sendMessage();
                lastEnterTime = 0; // Reset
            } else {
                lastEnterTime = currentTime;
            }
        }
    });
});

function toggleChat() {
    const sidebar = document.getElementById('ai-sidebar');
    const trigger = document.getElementById('ai-edge-trigger');
    sidebar.classList.toggle('active');
    if (sidebar.classList.contains('active')) {
        trigger.classList.add('hidden');
    } else {
        trigger.classList.remove('hidden');
    }
}

async function sendMessage() {
    const input = document.getElementById('ai-user-input');
    const messagesDiv = document.getElementById('chat-messages');
    const statsMini = document.getElementById('ai-stats-realtime');
    const text = input.value.trim();

    if (!text) return;

    // Add User Message
    const userDiv = document.createElement('div');
    userDiv.className = 'user-msg';
    userDiv.textContent = text;
    messagesDiv.appendChild(userDiv);

    // Reset input
    input.value = '';
    input.style.height = 'auto';
    scrollToBottom();

    // Prepare AI Message Container with Thinking support
    const aiDiv = document.createElement('div');
    aiDiv.className = 'ai-msg';

    // Optional Thinking Block (hidden until needed)
    const thinkingBox = document.createElement('details');
    thinkingBox.className = 'thinking-box';
    thinkingBox.style.display = 'none';
    thinkingBox.innerHTML = '<summary>Thinking Process</summary><div class="thinking-content"></div>';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    contentDiv.innerHTML = '<em>Initialising synthesis...</em>';

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

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.substring(6));

                    if (data.error) {
                        contentDiv.innerHTML = `<div style="color: #ff3b30;">[Error]: ${data.error}</div>`;
                        return;
                    }

                    // Handle Thinking (if provided by model)
                    if (data.thinking) {
                        thinkingBox.style.display = 'block';
                        fullThinking += data.thinking;
                        thinkingBox.querySelector('.thinking-content').textContent = fullThinking;
                    }

                    // Handle Content
                    if (data.content) {
                        fullContent += data.content;
                        contentDiv.innerHTML = marked.parse(fullContent);
                        contentDiv.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
                    }

                    // Handle Final Metrics
                    if (data.done && data.metrics) {
                        const m = data.metrics;
                        const speed = (m.eval_count / m.eval_duration).toFixed(1);
                        metricsDiv.innerHTML = `<span>${m.eval_count} tokens</span> • <span>${speed} t/s</span> • <span>${m.total_duration.toFixed(2)}s</span>`;
                        statsMini.textContent = `${speed} t/s`;
                    }

                    scrollToBottom();
                }
            }
        }

        chatHistory.push({ role: 'user', content: text });
        chatHistory.push({ role: 'assistant', content: fullContent });

    } catch (error) {
        console.error('Chat Error:', error);
        contentDiv.innerHTML = `<div style="color: #ff3b30;">Connection offline. Ensure host 192.168.0.18 is reachable.</div>`;
    }
}

function scrollToBottom() {
    const viewport = document.getElementById('chat-messages');
    viewport.scrollTop = viewport.scrollHeight;
}