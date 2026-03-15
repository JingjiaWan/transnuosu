/**
 * Yi-LM Online - 前端交互脚本
 * 功能：翻译、Chatbot、词典、用户反馈、主题切换
 */

// ============================================================================
// 常量与配置
// ============================================================================

const CONFIG = {
    STORAGE_KEYS: {
        FEEDBACK_USER_ID: 'yi_feedback_user_id',
        CHAT_SESSIONS: 'yi_chat_sessions',
        THEME: 'yi_theme'
    },
    TOAST_DURATION: {
        ERROR: 3200,
        SUCCESS: 2400
    }
};

// ============================================================================
// DOM 元素引用
// ============================================================================

const elements = {
    // 翻译相关
    inputText: document.getElementById('inputText'),
    translateBtn: document.getElementById('translateBtn'),
    conversationList: document.getElementById('conversationList'),
    dictionaryEntries: document.getElementById('dictionaryEntries'),
    sidebar: document.getElementById('sidebar'),
    sidebarToggle: document.getElementById('sidebarToggle'),
    sidebarSubtitle: document.getElementById('sidebarSubtitle'),
    
    // Chatbot 相关
    chatMessages: document.getElementById('chatMessages'),
    chatInput: document.getElementById('chatInput'),
    chatSendBtn: document.getElementById('chatSendBtn'),
    sessionList: document.getElementById('sessionList'),
    clearHistoryBtn: document.getElementById('clearHistoryBtn'),
    newChatBtn: document.getElementById('newChatBtn'),
    
    // 全局
    themeToggle: document.getElementById('themeToggle'),
    userArea: document.getElementById('userArea'),
    toast: document.getElementById('toast')
};

// ============================================================================
// 状态管理
// ============================================================================

const state = {
    conversations: [],
    selectedConversationId: null,
    currentUser: null,
    chatSessions: {
        sessions: {},
        current_session_id: null
    },
    toastTimer: null
};

// ============================================================================
// 工具函数
// ============================================================================

/**
 * HTML 转义，防止 XSS
 */
function escapeHTML(str) {
    const escapeMap = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return String(str).replace(/[&<>"']/g, char => escapeMap[char]);
}

/**
 * 生成唯一 ID
 */
function generateId() {
    if (window.crypto?.randomUUID) {
        return window.crypto.randomUUID();
    }
    return `id_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
}

/**
 * 格式化时间戳
 */
function formatTime(date = new Date()) {
    return date.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * 格式化日期
 */
function formatDate(date = new Date()) {
    return date.toLocaleDateString('zh-CN', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// ============================================================================
// Markdown 渲染
// ============================================================================

/**
 * 渲染行内 Markdown（加粗、斜体、代码）
 */
function renderInlineMarkdown(text = '') {
    let html = escapeHTML(text);
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    return html;
}

/**
 * 渲染完整 Markdown
 */
function renderMarkdown(text = '') {
    const normalized = (text || '').replace(/\r\n/g, '\n').trim();
    if (!normalized) {
        return '<p>暂无结果</p>';
    }

    const lines = normalized.split('\n');
    const blocks = [];
    let listItems = [];
    let paragraphLines = [];

    function flushParagraph() {
        if (!paragraphLines.length) return;
        blocks.push(`<p>${renderInlineMarkdown(paragraphLines.join('<br>'))}</p>`);
        paragraphLines = [];
    }

    function flushList() {
        if (!listItems.length) return;
        blocks.push(`<ul>${listItems.map(item => `<li>${renderInlineMarkdown(item)}</li>`).join('')}</ul>`);
        listItems = [];
    }

    for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line) {
            flushParagraph();
            flushList();
            continue;
        }

        // 标题
        const headingMatch = line.match(/^(#{1,3})\s+(.*)$/);
        if (headingMatch) {
            flushParagraph();
            flushList();
            const level = headingMatch[1].length;
            blocks.push(`<h${level + 1}>${renderInlineMarkdown(headingMatch[2])}</h${level + 1}>`);
            continue;
        }

        // 列表
        const listMatch = line.match(/^[-*]\s+(.*)$/);
        if (listMatch) {
            flushParagraph();
            listItems.push(listMatch[1]);
            continue;
        }

        flushList();
        paragraphLines.push(line);
    }

    flushParagraph();
    flushList();
    return blocks.join('');
}

/**
 * 提取推理部分
 */
function extractReasoning(text) {
    if (!text) return { main: '', reasoning: '' };
    
    let reasoning = '';
    let main = text;

    // 匹配括号中的推理关键词
    const reasoningMatch = text.match(/（[^）]*(根据|参考|推理|规则)[^）]*）/);
    if (reasoningMatch) {
        reasoning = reasoningMatch[0].replace(/^[（(]+|[）)]+$/g, '').trim();
        main = text.replace(reasoningMatch[0], '').trim();
    } else {
        // 查找显式标记
        const markers = ['推理：', '推断：', 'Reasoning:', '参考：', '根据：'];
        for (const marker of markers) {
            const idx = text.indexOf(marker);
            if (idx !== -1) {
                reasoning = text.slice(idx + marker.length).trim();
                main = text.slice(0, idx).trim();
                break;
            }
        }
    }
    
    return { main, reasoning };
}

/**
 * 格式化翻译结果
 */
function formatTranslationText(text) {
    if (!text) return '<div class="translation-line">暂无结果</div>';

    const { main, reasoning } = extractReasoning(text);
    const content = main || text;

    const hasZh = content.includes('中文翻译');
    const hasEn = content.includes('英文翻译');

    if (!hasZh && !hasEn) {
        const reasoningHtml = reasoning
            ? `<div class="reasoning-box"><strong>推理：</strong> ${renderMarkdown(reasoning)}</div>`
            : '';
        return `<div class="translation-markdown">${renderMarkdown(content)}</div>${reasoningHtml}`;
    }

    let enPart = '';
    let zhPart = '';
    
    if (hasZh) {
        const [left, zh] = content.split('中文翻译：');
        zhPart = zh ? zh.trim() : '';
        enPart = left || '';
    } else {
        enPart = content;
    }
    
    if (hasEn) {
        enPart = enPart.split('英文翻译：').pop() || enPart;
    }

    const lines = [];
    if (enPart.trim()) {
        lines.push(`
            <div class="translation-section">
                <div class="translation-label">英文翻译</div>
                <div class="translation-markdown">${renderMarkdown(enPart.trim())}</div>
            </div>
        `);
    }
    if (zhPart.trim()) {
        lines.push(`
            <div class="translation-section">
                <div class="translation-label">中文翻译</div>
                <div class="translation-markdown">${renderMarkdown(zhPart.trim())}</div>
            </div>
        `);
    }
    
    const reasoningHtml = reasoning
        ? `<div class="reasoning-box"><strong>推理：</strong> ${renderMarkdown(reasoning)}</div>`
        : '';
    
    return lines.join('') + reasoningHtml;
}

// ============================================================================
// Toast 提示
// ============================================================================

function showToast(message, type = 'error') {
    const { toast } = elements;
    if (!toast) return;

    toast.textContent = message || '发生未知错误';
    toast.classList.remove('hidden');

    if (state.toastTimer) clearTimeout(state.toastTimer);
    
    state.toastTimer = setTimeout(() => {
        toast.classList.add('hidden');
    }, type === 'error' ? CONFIG.TOAST_DURATION.ERROR : CONFIG.TOAST_DURATION.SUCCESS);
}

function showError(message) {
    showToast(message, 'error');
}

function showSuccess(message) {
    showToast(message, 'success');
}

// ============================================================================
// 用户 ID 管理
// ============================================================================

function getFeedbackUserId() {
    let userId = localStorage.getItem(CONFIG.STORAGE_KEYS.FEEDBACK_USER_ID);
    if (!userId) {
        userId = generateId();
        localStorage.setItem(CONFIG.STORAGE_KEYS.FEEDBACK_USER_ID, userId);
    }
    return userId;
}

// ============================================================================
// 加载状态
// ============================================================================

function setTranslateLoading(isLoading) {
    const { translateBtn } = elements;
    if (!translateBtn) return;
    
    translateBtn.disabled = isLoading;
    translateBtn.textContent = isLoading ? '翻译中…' : '翻译';
}

function setChatLoading(isLoading) {
    const { chatSendBtn, chatInput } = elements;
    if (chatSendBtn) {
        chatSendBtn.disabled = isLoading;
        chatSendBtn.textContent = isLoading ? '发送中…' : '发送';
    }
    if (chatInput) {
        chatInput.disabled = isLoading;
    }
}

// ============================================================================
// 翻译功能
// ============================================================================

async function sendTranslateRequest() {
    const { inputText } = elements;
    const text = (inputText?.value || '').trim();
    
    if (!text) {
        showError('请输入要翻译的彝语文本');
        return;
    }

    setTranslateLoading(true);

    try {
        // 发送翻译请求
        const res = await fetch('/api/translate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        
        const data = await res.json();
        
        if (!res.ok || !data.success) {
            throw new Error(data.error || '翻译请求失败');
        }

        // 清空历史，只保留最新翻译
        const conv = {
            id: generateId(),
            source: text,
            translation: data.data?.translation || '',
            timestamp: new Date().toISOString()
        };
        
        state.conversations = [conv];  // 只保留最新一条
        renderConversation();

        // 更新词典
        if (data.data?.dictionary_entries?.length) {
            renderSidebar(data.data.dictionary_entries);
        }

        // 清空输入
        if (inputText) inputText.value = '';

    } catch (err) {
        showError(err?.message || '翻译请求出错');
    } finally {
        setTranslateLoading(false);
    }
}

function renderConversation() {
    const { conversationList } = elements;
    if (!conversationList) return;

    if (!state.conversations.length) {
        conversationList.innerHTML = '';
        return;
    }

    conversationList.innerHTML = state.conversations.map(conv => {
        const feedbackStatus = conv.feedbackStatus;
        const showCorrectionForm = conv.showCorrectionForm || feedbackStatus === 'corrected';
        
        let feedbackHtml = `
            <div class="feedback-actions">
                <button class="feedback-btn good-btn ${feedbackStatus === 'accepted' ? 'active-good' : ''}" 
                        data-id="${conv.id}" 
                        onclick="handleFeedback('${conv.id}', 'good')"
                        ${feedbackStatus ? 'disabled' : ''}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
                    </svg>
                    ${feedbackStatus === 'accepted' ? '已标记正确' : '正确'}
                </button>
                <button class="feedback-btn bad-btn ${feedbackStatus === 'corrected' ? 'active-bad' : ''}" 
                        data-id="${conv.id}" 
                        onclick="toggleCorrectionForm('${conv.id}')"
                        ${feedbackStatus ? 'disabled' : ''}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/>
                    </svg>
                    ${feedbackStatus === 'corrected' ? '已提交修正' : '错误'}
                </button>
            </div>
        `;
        
        if (showCorrectionForm && feedbackStatus !== 'accepted') {
            feedbackHtml += `
                <div class="correction-form ${feedbackStatus === 'corrected' ? 'submitted' : ''}">
                    <textarea 
                        class="correction-input"
                        id="correction-${conv.id}"
                        placeholder="请将正确翻译结果输入到此框中~"
                        ${feedbackStatus === 'corrected' ? 'disabled' : ''}
                    >${conv.correctedTranslation || ''}</textarea>
                    ${feedbackStatus !== 'corrected' ? `
                        <button class="correction-submit" onclick="submitCorrection('${conv.id}')">
                            提交修正
                        </button>
                    ` : ''}
                </div>
            `;
        }
        
        return `
            <article class="conversation glass" data-id="${conv.id}">
                <div class="conversation-header">
                    <span class="source-label">彝语原文</span>
                    <span class="timestamp">${formatTime(new Date(conv.timestamp))}</span>
                </div>
                <div class="source-text">${escapeHTML(conv.source)}</div>
                <div class="translation-result">
                    ${formatTranslationText(conv.translation)}
                </div>
                ${feedbackHtml}
            </article>
        `;
    }).join('');
}

// ============================================================================
// 词典功能
// ============================================================================

function renderSidebar(entries = []) {
    const { dictionaryEntries, sidebarSubtitle } = elements;
    
    if (sidebarSubtitle) {
        sidebarSubtitle.textContent = entries.length ? `共 ${entries.length} 个条目` : '最新翻译';
    }
    
    if (!dictionaryEntries) return;
    
    if (!entries.length) {
        dictionaryEntries.innerHTML = '<div class="entry-card"><p style="color: var(--text-muted); font-size: 13px;">暂无词典条目</p></div>';
        return;
    }

    dictionaryEntries.innerHTML = entries.map(entry => `
        <div class="entry-card" role="listitem">
            <div class="entry-yi">${escapeHTML(entry.yi || '')}</div>
            <div class="entry-zh">${escapeHTML(entry.zh || '')}</div>
        </div>
    `).join('');
}

// ============================================================================
// 反馈功能
// ============================================================================

function toggleCorrectionForm(convId) {
    const conv = state.conversations.find(c => c.id === convId);
    if (!conv) return;
    
    // 检查是否登录
    if (!state.currentUser) {
        showError('请先登录后再提交反馈');
        return;
    }
    
    // 切换显示修正表单
    conv.showCorrectionForm = !conv.showCorrectionForm;
    renderConversation();
}

async function submitCorrection(convId) {
    const conv = state.conversations.find(c => c.id === convId);
    if (!conv) return;
    
    const textarea = document.getElementById(`correction-${convId}`);
    const correctedTranslation = textarea?.value?.trim();
    
    if (!correctedTranslation) {
        showError('请输入正确的翻译结果');
        return;
    }
    
    // 保存修正内容
    conv.correctedTranslation = correctedTranslation;
    
    // 禁用按钮，显示提交中状态
    const submitBtn = textarea.nextElementSibling;
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = '提交中...';
    }
    textarea.disabled = true;
    
    try {
        const res = await fetch('/api/feedback/correct', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                yi_text: conv.source,
                model_zh_translation: conv.translation,
                corrected_zh_translation: correctedTranslation,
                user_id: getFeedbackUserId()
            })
        });
        
        const data = await res.json();
        
        if (!res.ok || !data.success) {
            throw new Error(data.error || '修正翻译提交失败');
        }
        
        conv.feedbackStatus = 'corrected';
        renderConversation();
        showSuccess('感谢您的修正！');
    } catch (err) {
        showError(err?.message || '修正翻译提交失败');
        conv.showCorrectionForm = true;
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = '提交修正';
        }
        textarea.disabled = false;
    }
}

async function handleFeedback(convId, type) {
    const conv = state.conversations.find(c => c.id === convId);
    if (!conv) return;

    // 检查是否登录
    if (!state.currentUser) {
        showError('请先登录后再提交反馈');
        return;
    }

    if (type === 'good') {
        // 标记翻译正确
        const goodBtn = document.querySelector(`.good-btn[data-id="${convId}"]`);
        const badBtn = document.querySelector(`.bad-btn[data-id="${convId}"]`);
        
        if (goodBtn) goodBtn.disabled = true;
        if (badBtn) badBtn.disabled = true;

        try {
            const res = await fetch('/api/feedback/accept', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    yi_text: conv.source,
                    zh_translation: conv.translation,
                    user_id: getFeedbackUserId()
                })
            });
            
            const data = await res.json();
            
            if (!res.ok || !data.success) {
                throw new Error(data.error || '反馈提交失败');
            }
            
            conv.feedbackStatus = 'accepted';
            renderConversation();
            showSuccess('感谢您的反馈！');
        } catch (err) {
            showError(err?.message || '反馈提交失败');
            if (goodBtn) goodBtn.disabled = false;
            if (badBtn) badBtn.disabled = false;
        }
    }
}

// ============================================================================
// Chatbot 功能
// ============================================================================

function createNewSession(title = '新会话') {
    const id = generateId();
    state.chatSessions.sessions[id] = {
        id,
        title,
        messages: [],
        createdAt: new Date().toISOString()
    };
    state.chatSessions.current_session_id = id;
    saveChatStorage();
    return id;
}

function saveChatStorage() {
    try {
        localStorage.setItem(CONFIG.STORAGE_KEYS.CHAT_SESSIONS, JSON.stringify(state.chatSessions));
    } catch (e) {
        console.warn('Failed to save chat sessions', e);
    }
}

function loadChatStorage() {
    try {
        const stored = localStorage.getItem(CONFIG.STORAGE_KEYS.CHAT_SESSIONS);
        if (stored) {
            state.chatSessions = JSON.parse(stored);
        }
    } catch (e) {
        console.warn('Failed to load chat sessions', e);
    }
}

function renderSessionList() {
    const { sessionList } = elements;
    if (!sessionList) return;

    const sessions = Object.values(state.chatSessions.sessions).sort(
        (a, b) => new Date(b.createdAt) - new Date(a.createdAt)
    );

    if (!sessions.length) {
        sessionList.innerHTML = '<div class="session-item"><span class="session-title" style="color: var(--text-light);">暂无历史会话</span></div>';
        return;
    }

    sessionList.innerHTML = sessions.map(session => `
        <div class="session-item ${session.id === state.chatSessions.current_session_id ? 'active' : ''}" 
             data-id="${session.id}" 
             onclick="loadSession('${session.id}')"
             role="option"
             aria-selected="${session.id === state.chatSessions.current_session_id}">
            <div class="session-title">${escapeHTML(session.title)}</div>
            <div class="session-time">${formatDate(new Date(session.createdAt))}</div>
        </div>
    `).join('');
}

function loadSession(id) {
    if (!state.chatSessions.sessions[id]) return;
    
    state.chatSessions.current_session_id = id;
    saveChatStorage();
    renderSessionList();
    renderChatMessages();
}

function renderChatMessages() {
    const { chatMessages } = elements;
    if (!chatMessages) return;

    const currentSession = state.chatSessions.sessions[state.chatSessions.current_session_id];
    const messages = currentSession?.messages || [];

    if (!messages.length) {
        chatMessages.innerHTML = `
            <div class="bubble system">
                <div class="bubble-content">开始新的对话吧！输入彝语，我会自动翻译并与您交流。</div>
            </div>
        `;
        return;
    }

    chatMessages.innerHTML = messages.map(msg => `
        <div class="bubble ${msg.role}">
            <div class="bubble-content">${renderMarkdown(msg.content)}</div>
        </div>
    `).join('');

    // 滚动到底部
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendMessage(role, content) {
    const currentSession = state.chatSessions.sessions[state.chatSessions.current_session_id];
    if (!currentSession) return;

    currentSession.messages.push({
        role,
        content,
        timestamp: new Date().toISOString()
    });

    // 更新会话标题（使用第一条消息）
    if (currentSession.messages.length === 1 && role === 'user') {
        currentSession.title = content.slice(0, 30) + (content.length > 30 ? '…' : '');
    }

    saveChatStorage();
}

async function sendChatMessage() {
    const { chatInput } = elements;
    const text = (chatInput?.value || '').trim();
    
    if (!text) return;

    setChatLoading(true);

    try {
        // 添加用户消息
        appendMessage('user', text);
        renderChatMessages();
        renderSessionList();
        if (chatInput) chatInput.value = '';

        // 先翻译
        const tRes = await fetch('/api/translate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        const tData = await tRes.json();
        const translated = tData.translation || text;

        // 再聊天
        const cRes = await fetch('/api/chatbot', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: translated || text })
        });
        const cData = await cRes.json();
        
        if (!cRes.ok || !cData.success) {
            throw new Error(cData.error || '聊天失败');
        }

        appendMessage('assistant', cData.reply || '');
        renderChatMessages();

    } catch (err) {
        showError(err?.message || '聊天请求出错');
    } finally {
        setChatLoading(false);
    }
}

function clearHistory() {
    state.chatSessions = { sessions: {}, current_session_id: null };
    saveChatStorage();
    renderSessionList();
    renderChatMessages();
}

// ============================================================================
// 标签页切换
// ============================================================================

function switchTab(tabName) {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        const isActive = btn.dataset.tab === tabName;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-selected', isActive);
    });

    tabContents.forEach(content => {
        const isActive = content.id === `tab-${tabName}`;
        content.classList.toggle('active', isActive);
    });
}

// ============================================================================
// 主题切换
// ============================================================================

function initTheme() {
    const savedTheme = localStorage.getItem(CONFIG.STORAGE_KEYS.THEME);
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-mode');
    }
    updateThemeToggleLabel();
}

function toggleTheme() {
    document.body.classList.toggle('dark-mode');
    const isDark = document.body.classList.contains('dark-mode');
    localStorage.setItem(CONFIG.STORAGE_KEYS.THEME, isDark ? 'dark' : 'light');
    updateThemeToggleLabel();
}

function updateThemeToggleLabel() {
    const { themeToggle } = elements;
    if (!themeToggle) return;
    
    const isDark = document.body.classList.contains('dark-mode');
    themeToggle.setAttribute('aria-label', isDark ? '切换到明亮色调' : '切换到暗色调');
    themeToggle.setAttribute('title', isDark ? '切换到明亮色调' : '切换到暗色调');
}

// ============================================================================
// 侧边栏控制
// ============================================================================

function toggleSidebar() {
    const { sidebar } = elements;
    if (!sidebar) return;
    
    sidebar.classList.toggle('open');
    const isOpen = sidebar.classList.contains('open');
    elements.sidebarToggle?.setAttribute('aria-expanded', isOpen);
}

// ============================================================================
// 用户初始化
// ============================================================================

function initCurrentUser() {
    const { userArea } = elements;
    if (!userArea?.dataset.user) {
        state.currentUser = null;
        return;
    }
    
    try {
        state.currentUser = JSON.parse(userArea.dataset.user);
    } catch (e) {
        console.warn('Failed to parse current user', e);
        state.currentUser = null;
    }
}

// ============================================================================
// 事件绑定
// ============================================================================

function bindEvents() {
    // 翻译
    elements.translateBtn?.addEventListener('click', sendTranslateRequest);
    elements.inputText?.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
            e.preventDefault();
            sendTranslateRequest();
        }
    });

    // 侧边栏
    elements.sidebarToggle?.addEventListener('click', toggleSidebar);

    // Chatbot
    elements.chatSendBtn?.addEventListener('click', sendChatMessage);
    elements.chatInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });
    elements.clearHistoryBtn?.addEventListener('click', clearHistory);
    elements.newChatBtn?.addEventListener('click', () => {
        createNewSession('新会话');
        renderSessionList();
        renderChatMessages();
    });

    // 主题
    elements.themeToggle?.addEventListener('click', toggleTheme);
}

// ============================================================================
// 初始化
// ============================================================================

function init() {
    initTheme();
    initCurrentUser();
    loadChatStorage();
    
    // 确保有当前会话
    if (!state.chatSessions.current_session_id) {
        createNewSession('新会话');
    }
    
    renderSessionList();
    renderChatMessages();
    renderConversation();
    renderSidebar([]);
    bindEvents();
}

// DOM 加载完成后初始化
document.addEventListener('DOMContentLoaded', init);

// 暴露全局函数（供 HTML onclick 使用）
window.switchTab = switchTab;
window.handleFeedback = handleFeedback;
window.loadSession = loadSession;
