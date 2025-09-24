document.addEventListener('DOMContentLoaded', () => {
    const API_BASE_URL = 'http://127.0.0.1:8000';
    let activeSessionId = null;

    // --- Element Getters ---
    const newChatBtn = document.getElementById('new-chat-btn');
    const sessionList = document.getElementById('session-list');
    const urlSection = document.getElementById('url-section');
    const urlForm = document.getElementById('url-form');
    const urlInput = document.getElementById('url-input');
    const processUrlBtn = document.getElementById('process-url-btn');
    const statusMessage = document.getElementById('status-message');
    const chatSection = document.getElementById('chat-section');
    const chatTitle = document.getElementById('chat-title');
    const chatWindow = document.getElementById('chat-window');
    const messageForm = document.getElementById('message-form');
    const messageInput = document.getElementById('message-input');
    const typingIndicator = document.getElementById('typing-indicator');

    // --- Helper Functions ---
    const addMessage = (text, sender) => {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', sender);
        messageElement.textContent = text;
        chatWindow.appendChild(messageElement);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    };

    const addSessionToSidebar = (session, prepend = false) => {
        const listItem = document.createElement('li');
        listItem.classList.add('session-item');
        listItem.dataset.sessionId = session.session_id;
        listItem.textContent = session.title;
        listItem.addEventListener('click', () => activateSession(session.session_id, session.title));
        if (prepend) sessionList.prepend(listItem);
        else sessionList.appendChild(listItem);
    };

    // --- API Functions ---
    const fetchSessions = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/sessions`);
            if (!response.ok) throw new Error('Failed to fetch sessions.');
            const sessions = await response.json();
            sessionList.innerHTML = '';
            sessions.forEach(session => addSessionToSidebar(session));
        } catch (error) { console.error('Error fetching sessions:', error); }
    };

    const activateSession = async (sessionId, title) => {
        if (activeSessionId === sessionId) return;
        activeSessionId = sessionId;
        chatTitle.textContent = title;
        chatWindow.innerHTML = '<div class="status">Loading chat history...</div>';
        urlSection.classList.add('hidden');
        chatSection.classList.remove('hidden');
        document.querySelectorAll('.session-item').forEach(item => {
            item.classList.toggle('active', item.dataset.sessionId === sessionId);
        });
        try {
            const response = await fetch(`${API_BASE_URL}/session/${sessionId}`);
            if (!response.ok) throw new Error('Failed to fetch session history.');
            const sessionDetails = await response.json();
            chatWindow.innerHTML = '';
            if (sessionDetails.conversation && sessionDetails.conversation.length > 0) {
                sessionDetails.conversation.forEach(turn => {
                    addMessage(turn.question, 'user');
                    addMessage(turn.answer, 'bot');
                });
            } else {
                addMessage(`This is the start of your conversation about "${title}". Ask a question!`, 'bot');
            }
        } catch (error) {
            chatWindow.innerHTML = '';
            addMessage(`Error loading chat history: ${error.message}`, 'bot');
        }
        messageInput.focus();
    };

    // --- Event Handlers ---
    const handleNewChatClick = () => {
        activeSessionId = null;
        urlSection.classList.remove('hidden');
        urlForm.classList.remove('hidden');
        statusMessage.textContent = '';
        urlInput.value = '';
        urlInput.focus();
        chatSection.classList.add('hidden');
        document.querySelectorAll('.session-item.active').forEach(item => item.classList.remove('active'));
    };
    
    const handleUrlSubmit = async (e) => {
        e.preventDefault();
        const url = urlInput.value.trim();
        if (!url) return;
        statusMessage.textContent = 'Crawling entire site... This may take several minutes.';
        processUrlBtn.disabled = true;
        urlInput.disabled = true;

        try {
            const response = await fetch(`${API_BASE_URL}/process-url`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to process URL.');
            }
            const newSession = await response.json();
            addSessionToSidebar(newSession, true);
            activateSession(newSession.session_id, newSession.title);
        } catch (error) {
            statusMessage.textContent = `Error: ${error.message}`;
        } finally {
            processUrlBtn.disabled = false;
            urlInput.disabled = false;
        }
    };

    const handleMessageSubmit = async (e) => {
        e.preventDefault();
        const question = messageInput.value.trim();
        if (!question || !activeSessionId) return;
        addMessage(question, 'user');
        messageInput.value = '';
        typingIndicator.classList.remove('hidden');
        try {
            const response = await fetch(`${API_BASE_URL}/ask`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: activeSessionId, question }),
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to get an answer.');
            }
            const data = await response.json();
            addMessage(data.answer, 'bot');
        } catch (error) {
            addMessage(`Sorry, an error occurred: ${error.message}`, 'bot');
        } finally {
            typingIndicator.classList.add('hidden');
        }
    };
    
    // --- Initial Setup ---
    newChatBtn.addEventListener('click', handleNewChatClick);
    urlForm.addEventListener('submit', handleUrlSubmit);
    messageForm.addEventListener('submit', handleMessageSubmit);
    fetchSessions(); // Load existing sessions on startup
});