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

// Toggle Chat Window
function toggleChat() {
    const window = document.getElementById('ai-chat-window');
    const btn = document.getElementById('ai-toggle-btn');

    if (window.style.display === 'none') {
        window.style.display = 'flex';
        // Simple pop animation
        window.style.opacity = '0';
        window.style.transform = 'translateY(10px)';
        setTimeout(() => {
            window.style.transition = 'all 0.3s ease';
            window.style.opacity = '1';
            window.style.transform = 'translateY(0)';
        }, 10);
    } else {
        window.style.display = 'none';
    }
}

// Send Message
async function sendMessage() {
    const input = document.getElementById('ai-user-input');
    const messagesDiv = document.getElementById('chat-messages');
    const text = input.value.trim();

    if (!text) return;

    // 1. Add User Message
    messagesDiv.innerHTML += `<div class="user-msg">${escapeHtml(text)}</div>`;
    input.value = '';
    scrollToBottom();

    // 2. Create AI Message Bubble (Empty initially)
    const aiBubbleId = 'ai-msg-' + Date.now();
    messagesDiv.innerHTML += `<div id="${aiBubbleId}" class="ai-msg">...</div>`;
    const aiBubble = document.getElementById(aiBubbleId);
    scrollToBottom();

    try {
        // 3. Call Django API
        const response = await fetch('/api/chat/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let aiText = '';

        // Clear the "..." loading placeholder
        aiBubble.innerHTML = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n\n');

            lines.forEach(line => {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.substring(6));
                        if (data.content) {
                            aiText += data.content;
                            // Update HTML (simple markdown support could be added here)
                            aiBubble.innerText = aiText;
                            scrollToBottom();
                        }
                    } catch (e) { console.error(e); }
                }
            });
        }

    } catch (err) {
        aiBubble.innerHTML = '<span class="text-danger">Error connecting to agent.</span>';
    }
}

// Helper: Auto-scroll
function scrollToBottom() {
    const messagesDiv = document.getElementById('chat-messages');
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// Helper: Escape HTML to prevent injection
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Allow "Enter" to send
document.getElementById('ai-user-input').addEventListener('keypress', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});