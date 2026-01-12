// --- AI Chat Widget Logic ---

function toggleChat() {
    const window = document.getElementById('ai-chat-window');
    const isVisible = window.style.display !== 'none';

    if (!isVisible) {
        window.style.display = 'flex';
        // Pop in animation
        window.style.opacity = '0';
        window.style.transform = 'scale(0.8) translateY(20px)';
        window.style.pointerEvents = 'none';

        requestAnimationFrame(() => {
            window.style.transition = 'all 0.4s cubic-bezier(0.165, 0.84, 0.44, 1)';
            window.style.opacity = '1';
            window.style.transform = 'scale(1) translateY(0)';
            window.style.pointerEvents = 'all';
        });
    } else {
        window.style.opacity = '0';
        window.style.transform = 'scale(0.8) translateY(20px)';
        window.style.pointerEvents = 'none';
        setTimeout(() => {
            window.style.display = 'none';
        }, 400);
    }
}

// Auto-resize textarea
const aiInput = document.getElementById('ai-user-input');
if (aiInput) {
    aiInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });
}

// Send Message
async function sendMessage() {
    const input = document.getElementById('ai-user-input');
    const messagesDiv = document.getElementById('chat-messages');
    const text = input.value.trim();

    if (!text) return;

    // 1. Add User Message
    const userDiv = document.createElement('div');
    userDiv.className = 'user-msg';
    userDiv.textContent = text;
    messagesDiv.appendChild(userDiv);

    // Reset input
    input.value = '';
    input.style.height = 'auto';
    scrollToBottom();

    // 2. Prepare AI Message Container
    const aiDiv = document.createElement('div');
    aiDiv.className = 'ai-msg';
    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    contentDiv.innerHTML = '<span class="loading-dots">...</span>';
    aiDiv.appendChild(contentDiv);
    messagesDiv.appendChild(aiDiv);
    scrollToBottom();

    let fullContent = "";

    try {
        const response = await fetch('/api/chat/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken') // Django CSRF
            },
            body: JSON.stringify({ message: text })
        });

        if (!response.ok) throw new Error('Failed to connect');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        contentDiv.innerHTML = ''; // Clear loading

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.substring(6));
                        if (data.content) {
                            fullContent += data.content;
                            // Update HTML using Marked
                            contentDiv.innerHTML = marked.parse(fullContent);

                            // Highlight code blocks
                            contentDiv.querySelectorAll('pre code').forEach((block) => {
                                hljs.highlightElement(block);
                            });

                            scrollToBottom();
                        }
                    } catch (e) { console.error("Parse error", e); }
                }
            }
        }

    } catch (error) {
        console.error(error);
        contentDiv.innerHTML = `<span style="color: #ff3b30;">Error: ${error.message}</span>`;
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