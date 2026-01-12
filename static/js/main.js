// --- AI Sidebar Logic ---
let chatHistory = [];

function toggleChat() {
    const sidebar = document.getElementById('ai-sidebar');
    const trigger = document.getElementById('ai-sidebar-trigger');

    sidebar.classList.toggle('active');

    if (sidebar.classList.contains('active')) {
        sidebar.style.display = 'flex';
        trigger.style.opacity = '0';
        trigger.style.pointerEvents = 'none';
    } else {
        setTimeout(() => {
            if (!sidebar.classList.contains('active')) {
                sidebar.style.display = 'none';
            }
        }, 600);
        trigger.style.opacity = '1';
        trigger.style.pointerEvents = 'all';
    }
}

async function sendMessage() {
    const input = document.getElementById('ai-user-input');
    const messagesDiv = document.getElementById('chat-messages');
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

    // Prepare AI Message Container
    const aiDiv = document.createElement('div');
    aiDiv.className = 'ai-msg';
    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    contentDiv.innerHTML = '<span class="loading-dots">Thinking...</span>';
    aiDiv.appendChild(contentDiv);
    messagesDiv.appendChild(aiDiv);
    scrollToBottom();

    let fullContent = "";

    try {
        const response = await fetch('/api/chat/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                message: text,
                messages: chatHistory
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Server connection failed: ${response.status}`);
        }

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
                        contentDiv.innerHTML = `<div style="color: #ff3b30;">Ollama Error: ${data.error}</div>`;
                        return;
                    }

                    if (data.content) {
                        fullContent += data.content;
                        contentDiv.innerHTML = marked.parse(fullContent);
                        // Re-highlight
                        contentDiv.querySelectorAll('pre code').forEach((block) => {
                            hljs.highlightElement(block);
                        });
                        scrollToBottom();
                    }
                }
            }
        }

        // Store in history
        chatHistory.push({ role: 'user', 'content': text });
        chatHistory.push({ role: 'assistant', 'content': fullContent });

    } catch (error) {
        console.error('Chat Error:', error);
        contentDiv.innerHTML = `<div style="color: #ff3b30;">Unable to connect to Qwen Agent. Please ensure the qwen2.5-coder:32b model is available in Ollama.</div>`;
    }
}


function scrollToBottom() {

    const messagesDiv = document.getElementById('chat-messages');
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// Helper: Get CSRF Cookie
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Event Listeners
if (aiInput) {
    aiInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}

// --- Original Blog Logic (kept for compatibility) ---
function handleReply(response_id) {
    const reply_form_container = document.querySelector(`#reply-form-container-${response_id}`)
    if (reply_form_container) {
        reply_form_container.style.display = 'block';
    }
}

function handleCancel(response_id) {
    const reply_form_container = document.querySelector(`#reply-form-container-${response_id}`)
    if (reply_form_container) {
        reply_form_container.style.display = 'none';
    }
}