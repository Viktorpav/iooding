// --- AI Sidebar System Logic: Advanced Developer Interface ---
let chatHistory = [], lastEnterTime = 0, abortController = null, isGenerating = false, currentAiDiv = null;
const MAX_HISTORY = 20;

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

document.addEventListener('DOMContentLoaded', () => {
    const userInput = document.getElementById('ai-user-input');

    // Recovery & UI Initialization
    const cachedInput = localStorage.getItem('ai_user_input_cache');
    if (cachedInput) { userInput.value = cachedInput; resizeInput(userInput); }

    const savedHistory = localStorage.getItem('ai_chat_history');
    if (savedHistory) {
        try { chatHistory = JSON.parse(savedHistory); renderHistory(chatHistory); }
        catch (e) { chatHistory = []; }
    }

    userInput.addEventListener('input', () => {
        resizeInput(userInput);
        localStorage.setItem('ai_user_input_cache', userInput.value);
    });

    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const now = Date.now();
            if (now - lastEnterTime < 600) { e.preventDefault(); handleSendClick(); }
            lastEnterTime = now;
        }
    });

    scrollToBottom(true);
    initMobileGestures();
    checkAiStatus();
    initScrollReveal();
    initSearchShortcut();
});

function initScrollReveal() {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('active');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1, rootMargin: "0px 0px -50px 0px" });

    document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
}

function initSearchShortcut() {
    document.addEventListener('keydown', (e) => {
        if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
            e.preventDefault();
            const searchInput = document.getElementById('nav-search-field');
            if (searchInput) searchInput.focus();
        }
    });
}

async function checkAiStatus() {
    const statusText = document.querySelector('.agent-status');
    const welcomeBox = document.getElementById('ai-welcome-box');

    try {
        const res = await fetch('/api/chat/status/');
        const data = await res.json();
        if (data.online) {
            statusText.innerHTML = '<span class="pulse"></span> Online';
            if (welcomeBox) welcomeBox.innerHTML = '<p>Interface active. Powering high-performance inference. How can I assist with your technical journey today?</p>';
            document.querySelectorAll('.ai-nav-btn').forEach(btn => btn.classList.add('online-pulse'));
        } else {
            statusText.innerHTML = '<span class="pulse offline"></span> AI Offline';
            if (welcomeBox) welcomeBox.innerHTML = '<p style="color:#ff3b30;">AI Error: All connection attempts failed. The high-performance inference engine is currently unreachable.</p>';
            document.querySelectorAll('.ai-nav-btn').forEach(btn => btn.classList.remove('online-pulse'));
        }
    } catch (e) {
        statusText.innerHTML = '<span class="pulse offline"></span> Connection Error';
    }
}

let touchStartY = 0;
function initMobileGestures() {
    const sidebar = document.getElementById('ai-sidebar');
    sidebar.addEventListener('touchstart', (e) => {
        if (window.innerWidth > 768) return;
        touchStartY = e.touches[0].clientY;
    });
    sidebar.addEventListener('touchmove', (e) => {
        if (window.innerWidth > 768 || touchStartY === 0) return;
        const deltaY = e.touches[0].clientY - touchStartY;
        if (deltaY > 100) { // Threshold for swipe down
            toggleChat();
            touchStartY = 0;
        }
    });
}

function resizeInput(el) { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; }

function toggleChat() {
    const sidebar = document.getElementById('ai-sidebar');
    const isActivating = !sidebar.classList.contains('active');
    sidebar.classList.toggle('active');
    document.body.classList.toggle('ai-active');
    if (isActivating) {
        scrollToBottom(true);
        document.getElementById('ai-user-input').focus();
    }
}

function sendQuickAction(query) {
    const sidebar = document.getElementById('ai-sidebar');
    if (!sidebar.classList.contains('active')) toggleChat();
    const input = document.getElementById('ai-user-input');
    input.value = query;
    handleSendClick();
}

function scrollToBottom(force = false) {
    const v = document.getElementById('chat-messages');
    if (v && (force || v.scrollTop + v.clientHeight >= v.scrollHeight - 100)) v.scrollTop = v.scrollHeight;
}

function renderHistory(history) {
    const v = document.getElementById('chat-messages');
    v.innerHTML = '';
    // Show only last 10 messages for performance
    history.slice(-10).forEach(msg => msg.role === 'user' ? addUserMessageUI(msg.content) : addAssistantMessageUI(msg.content));
}

function createActionButtons(text, isUser) {
    const div = document.createElement('div');
    div.className = 'msg-actions';

    const btn = (html, title, cb) => {
        const b = document.createElement('button');
        b.className = 'action-btn'; b.innerHTML = html; b.title = title;
        b.onclick = (e) => { e.stopPropagation(); cb(); };
        return b;
    };

    div.appendChild(btn('<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>', 'Copy', () => {
        navigator.clipboard.writeText(text);
    }));

    if (isUser) {
        div.appendChild(btn('<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>', 'Edit', () => {
            if (isGenerating) stopGeneration();
            const input = document.getElementById('ai-user-input');
            input.value = text; resizeInput(input); input.focus();
        }));
    }
    return div;
}

function addUserMessageUI(text) {
    const v = document.getElementById('chat-messages');
    const wrap = document.createElement('div');
    wrap.className = 'user-wrapper';
    wrap.innerHTML = `<div class="user-msg">${text}</div>`;
    wrap.appendChild(createActionButtons(text, true));
    v.appendChild(wrap);
    
    // DOM Virtualization: Limit messages in DOM
    const messages = v.querySelectorAll('.user-wrapper, .ai-msg:not(.system-msg)');
    if (messages.length > 10) {
        messages[0].remove();
    }
}

function addAssistantMessageUI(content) {
    const v = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = 'ai-msg';
    div.innerHTML = `<div class="msg-content">${marked.parse(content)}</div>`;
    div.appendChild(createActionButtons(content, false));
    v.appendChild(div);
    div.querySelectorAll('pre code').forEach(hljs.highlightElement);

    // DOM Virtualization: Limit messages in DOM
    const messages = v.querySelectorAll('.user-wrapper, .ai-msg:not(.system-msg)');
    if (messages.length > 10) {
        messages[0].remove();
    }
}

function stopGeneration(cancel = false) {
    if (abortController) { abortController.abort(); abortController = null; }
    if (currentAiDiv) {
        const c = currentAiDiv.querySelector('.msg-content');
        if (c) {
            if (cancel && !c.textContent.trim()) currentAiDiv.remove();
            else c.insertAdjacentHTML('beforeend', ` <span style="opacity:0.5; font-size:0.75em;">(${cancel ? 'cancelled' : 'stopped'})</span>`);
        }
    }
    setGeneratingState(false);
    currentAiDiv = null;
}

function handleSendClick() { isGenerating ? stopGeneration() : sendMessage(); }

function setGeneratingState(active) {
    isGenerating = active;
    const btn = document.getElementById('ai-send-btn');
    btn.classList.toggle('stop-mode', active);
    btn.querySelector('.send-icon').style.display = active ? 'none' : 'block';
    btn.querySelector('.stop-icon').style.display = active ? 'block' : 'none';
}

async function sendMessage() {
    const input = document.getElementById('ai-user-input');
    const text = input.value.trim();
    if (!text) return;

    if (isGenerating) stopGeneration(true);

    addUserMessageUI(text);
    input.value = ''; resizeInput(input);
    localStorage.removeItem('ai_user_input_cache');
    scrollToBottom(true);

    abortController = new AbortController();
    setGeneratingState(true);

    const v = document.getElementById('chat-messages');
    const aiDiv = document.createElement('div');
    aiDiv.className = 'ai-msg';
    aiDiv.innerHTML = `<details class="thinking-box" style="display:none"><summary>Thinking Process</summary><div class="thinking-content"></div></details>
                       <div class="msg-content"><em>Generating...</em></div><div class="msg-metrics"></div>`;
    v.appendChild(aiDiv);
    currentAiDiv = aiDiv;
    scrollToBottom(true);

    let fullContent = "", fullThinking = "";
    try {
        const res = await fetch('/api/chat/', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('iooding_csrftoken')
            },
            body: JSON.stringify({ message: text, messages: chatHistory }),
            signal: abortController.signal
        });

        if (!res.ok) throw new Error(`Status: ${res.status}`);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let lastRenderTime = 0;

        aiDiv.querySelector('.msg-content').innerHTML = '';

        let renderPending = false;

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const data = JSON.parse(line.substring(6));
                if (data.error) throw new Error(data.error);
                if (data.thinking) {
                    const box = aiDiv.querySelector('.thinking-box');
                    box.style.display = 'block';
                    fullThinking += data.thinking;
                    box.querySelector('.thinking-content').textContent = fullThinking;
                }
                if (data.content) {
                    fullContent += data.content;
                }
                if (data.done && data.metrics) {
                    aiDiv.querySelector('.msg-content').innerHTML = marked.parse(fullContent);
                    aiDiv.querySelectorAll('pre code').forEach(hljs.highlightElement);
                    const m = data.metrics;
                    const speed = (m.tokens_per_sec != null && !isNaN(m.tokens_per_sec)) ? m.tokens_per_sec.toFixed(1) : (m.eval_count / (m.total_duration || 0.001)).toFixed(1);
                    aiDiv.querySelector('.msg-metrics').innerHTML = `<span>${m.eval_count} tokens</span> • <span>${speed} t/s</span> • <span>${(m.total_duration || 0).toFixed(2)}s</span>`;
                    document.getElementById('ai-stats-realtime').textContent = `${speed} t/s`;
                }
                scrollToBottom();
            }

            if (fullContent && !renderPending) {
                renderPending = true;
                requestAnimationFrame(() => {
                    if (currentAiDiv) {
                        currentAiDiv.querySelector('.msg-content').innerHTML = marked.parse(fullContent);
                        scrollToBottom();
                    }
                    renderPending = false;
                });
            }
        }
        if (fullContent) { aiDiv.appendChild(createActionButtons(fullContent, false)); saveHistory(text, fullContent); }
    } catch (err) {
        if (err.name !== 'AbortError') aiDiv.querySelector('.msg-content').innerHTML = `<div style="color:#ff3b30;">${err.message || 'Connection failed'}</div>`;
    } finally { setGeneratingState(false); abortController = null; currentAiDiv = null; }
}

function saveHistory(u, a) {
    chatHistory.push({ role: 'user', content: u }, { role: 'assistant', content: a });
    chatHistory = chatHistory.slice(-MAX_HISTORY);
    localStorage.setItem('ai_chat_history', JSON.stringify(chatHistory));
}

function clearHistory() {
    if (!document.getElementById('ai-clear-modal')) {
        const modal = document.createElement('div');
        modal.id = 'ai-clear-modal';
        modal.className = 'premium-modal';
        modal.innerHTML = `
            <div class="premium-modal-content">
                <h4>Clean Conversation?</h4>
                <p>This will erase the entire AI context. Are you sure?</p>
                <div class="premium-modal-actions">
                    <button class="action-btn-pill btn-cancel" onclick="document.getElementById('ai-clear-modal').style.display='none'">Cancel</button>
                    <button class="action-btn-pill btn-confirm" onclick="confirmClearHistory()">Clean</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }
    document.getElementById('ai-clear-modal').style.display = 'flex';
}

function confirmClearHistory() {
    chatHistory = [];
    localStorage.removeItem('ai_chat_history');
    const v = document.getElementById('chat-messages'), w = v.querySelector('.system-msg');
    v.innerHTML = ''; if (w) v.appendChild(w);
    document.getElementById('ai-clear-modal').style.display = 'none';
}

// --- Comment System Logic ---
function handleReply(id) {
    const container = document.getElementById(`reply-form-container-${id}`);
    if (container) {
        // Hide other open reply forms if any
        document.querySelectorAll('[id^="reply-form-container-"]').forEach(el => el.style.display = 'none');
        container.style.display = 'block';
        const input = container.querySelector('textarea, input[type="text"]');
        if (input) input.focus();
    }
}

function handleCancel(id) {
    const container = document.getElementById(`reply-form-container-${id}`);
    if (container) container.style.display = 'none';
}