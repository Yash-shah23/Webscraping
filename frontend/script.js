// frontend/script.js
document.addEventListener('DOMContentLoaded', () => {
    const urlForm = document.getElementById('url-form');
    const urlInput = document.getElementById('url-input');
    const loadingStatus = document.getElementById('loading-status');
    const urlLoader = document.getElementById('url-loader');
    const chatContainer = document.getElementById('chat-container');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatWindow = document.getElementById('chat-window');
    const API_BASE_URL = 'http://127.0.0.1:8000';

    urlForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = urlInput.value.trim();
        if (!url) return;

        // --- NEW LOGIC: UPDATE UI IMMEDIATELY ---
        loadingStatus.textContent = 'Sending request to backend... The crawl will continue in the background.';
        urlForm.querySelector('button').disabled = true;

        // Optimistically switch to the chat view
        urlLoader.classList.add('hidden');
        chatContainer.classList.remove('hidden');

        // Now, send the request but don't let a timeout break the UI
        try {
            const response = await fetch(`${API_BASE_URL}/load-url`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            });
            // We don't need to do anything on success, the UI is already updated.
            if (!response.ok) {
                // If there's an immediate error (e.g., server down), show it.
                const errorData = await response.json();
                switchToErrorView(`Initial Error: ${errorData.detail || 'Failed to start loading URL'}`);
            }
            // If the request times out here, the user won't notice because the UI has already switched.
        } catch (error) {
             // This will catch network errors or timeouts
             console.error("Fetch error:", error);
             // The UI is already in chat mode, which is fine. The user will discover
             // the backend state when they try to ask a question.
        }
    });

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const question = chatInput.value.trim();
        if (!question) return;

        appendMessage(question, 'user-message');
        chatInput.value = '';
        
        const thinkingMessage = appendMessage('Thinking...', 'thinking-message');

        try {
            const response = await fetch(`${API_BASE_URL}/ask`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: question })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to get answer');
            }

            const data = await response.json();
            thinkingMessage.remove();
            appendMessage(data.answer, 'bot-message');

        } catch (error) {
            thinkingMessage.textContent = `Error: ${error.message}`;
            thinkingMessage.classList.remove('thinking-message');
            thinkingMessage.classList.add('bot-message');
        }
    });

    function appendMessage(text, className) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${className}`;
        const p = document.createElement('p');
        p.textContent = text;
        messageDiv.appendChild(p);
        chatWindow.appendChild(messageDiv);
        chatWindow.scrollTop = chatWindow.scrollHeight;
        return messageDiv;
    }

    function switchToErrorView(message) {
        chatContainer.classList.add('hidden');
        urlLoader.classList.remove('hidden');
        urlForm.querySelector('button').disabled = false;
        loadingStatus.textContent = message;
        loadingStatus.style.color = 'red';
    }
});