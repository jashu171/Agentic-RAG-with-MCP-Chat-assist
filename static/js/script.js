// Global variables
let isWelcomeVisible = true;
let chatHistory = [];

// Initialize the application
document.addEventListener('DOMContentLoaded', function () {
    initializeEventListeners();
    setupFileUpload();
    checkMemoryStatus();
});

function checkMemoryStatus() {
    // Check if there are documents in memory by calling health endpoint
    fetch('/health')
        .then(response => response.json())
        .then(data => {
            // Check if system has documents (you might need to adjust this based on your health endpoint response)
            const hasDocuments = data.system_health && 
                                data.system_health.coordinator && 
                                data.system_health.coordinator.stats && 
                                data.system_health.coordinator.stats.documents_processed > 0;
            updateMemoryStatus(hasDocuments);
        })
        .catch(error => {
            console.log('Could not check memory status:', error);
            // Default to empty state
            updateMemoryStatus(false);
        });
}

function initializeEventListeners() {
    // Welcome screen message input event listeners
    const messageInput = document.getElementById('messageInput');
    messageInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    messageInput.addEventListener('input', function () {
        const sendBtn = document.getElementById('sendBtn');
        if (this.value.trim()) {
            sendBtn.style.color = '#6366f1';
        } else {
            sendBtn.style.color = '#d1d5db';
        }
    });

    // Chat message input event listeners
    const chatMessageInput = document.getElementById('chatMessageInput');
    chatMessageInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });

    chatMessageInput.addEventListener('input', function () {
        const chatSendBtn = document.getElementById('chatSendBtn');
        if (this.value.trim()) {
            chatSendBtn.style.color = '#6366f1';
        } else {
            chatSendBtn.style.color = '#d1d5db';
        }
    });

    // File input change listener
    document.getElementById('fileInput').addEventListener('change', handleFileUpload);
}

function setupFileUpload() {
    const fileInput = document.getElementById('fileInput');

    // Drag and drop functionality
    document.addEventListener('dragover', function (e) {
        e.preventDefault();
    });

    document.addEventListener('drop', function (e) {
        e.preventDefault();
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            handleFileUpload();
        }
    });
}

function startNewChat() {
    // Clear chat messages
    const messagesContainer = document.getElementById('messages');
    messagesContainer.innerHTML = '';

    // Show welcome screen and hide chat input
    const welcomeScreen = document.getElementById('welcomeScreen');
    const chatInputContainer = document.getElementById('chatInputContainer');
    welcomeScreen.style.display = 'flex';
    chatInputContainer.style.display = 'none';
    isWelcomeVisible = true;

    // Clear inputs
    document.getElementById('messageInput').value = '';
    document.getElementById('chatMessageInput').value = '';

    // Reset chat history
    chatHistory = [];
}

function hideWelcomeScreen() {
    if (isWelcomeVisible) {
        const welcomeScreen = document.getElementById('welcomeScreen');
        const chatInputContainer = document.getElementById('chatInputContainer');
        welcomeScreen.style.display = 'none';
        chatInputContainer.style.display = 'block';
        isWelcomeVisible = false;
    }
}

function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();

    if (!message) return;

    hideWelcomeScreen();
    addMessage(message, 'user');
    input.value = '';

    // Show typing indicator
    showTypingIndicator();

    // Send request to backend
    sendQueryToBackend(message);
}

function sendChatMessage() {
    const input = document.getElementById('chatMessageInput');
    const message = input.value.trim();

    if (!message) return;

    addMessage(message, 'user');
    input.value = '';

    // Show typing indicator
    showTypingIndicator();

    // Send request to backend
    sendQueryToBackend(message);
}

function sendQueryToBackend(message) {
    fetch('/query', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query: message })
    })
        .then(response => response.json())
        .then(data => {
            hideTypingIndicator();

            if (data.error) {
                addMessage('Sorry, I encountered an error processing your request. Please make sure you have uploaded some documents or try asking a general question.', 'assistant');
            } else {
                addMessage(data.answer, 'assistant');

                // Add source information if available
                if (data.context_chunks && data.context_chunks.length > 0) {
                    addSourceInfo(data.context_chunks[0]);
                }
            }

            // Update chat history
            chatHistory.push({
                user: message,
                assistant: data.answer || 'Error occurred',
                timestamp: new Date()
            });
        })
        .catch(error => {
            hideTypingIndicator();
            console.error('Error:', error);
            addMessage('Sorry, I encountered a network error. Please try again.', 'assistant');
        });
}

function sendSuggestion(suggestion) {
    const input = document.getElementById('messageInput');
    input.value = suggestion;
    sendMessage();
}

function addMessage(text, sender) {
    const messagesContainer = document.getElementById('messages');

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    avatarDiv.textContent = sender === 'user' ? 'U' : 'AI';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    const textDiv = document.createElement('div');
    textDiv.className = 'message-text';
    
    // Convert markdown to HTML for better display (simple conversion)
    if (sender === 'assistant') {
        textDiv.innerHTML = convertMarkdownToHTML(text);
    } else {
        textDiv.textContent = text;
    }

    contentDiv.appendChild(textDiv);
    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentDiv);

    messagesContainer.appendChild(messageDiv);

    // Smooth scroll to bottom
    setTimeout(() => {
        messagesContainer.scrollTo({
            top: messagesContainer.scrollHeight,
            behavior: 'smooth'
        });
    }, 100);
}

function convertMarkdownToHTML(markdown) {
    let html = markdown;
    
    // Convert headers
    html = html.replace(/^## (.*$)/gm, '<h2>$1</h2>');
    html = html.replace(/^### (.*$)/gm, '<h3>$1</h3>');
    
    // Convert bold text
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Convert bullet points
    html = html.replace(/^• (.*$)/gm, '<li>$1</li>');
    
    // Wrap consecutive list items in ul tags
    html = html.replace(/(<li>.*<\/li>)/gs, function(match) {
        return '<ul>' + match + '</ul>';
    });
    
    // Convert tables (basic support)
    html = html.replace(/\|(.+)\|/g, function(match, content) {
        const cells = content.split('|').map(cell => cell.trim());
        const cellTags = cells.map(cell => `<td>${cell}</td>`).join('');
        return `<tr>${cellTags}</tr>`;
    });
    
    // Wrap table rows in table tags
    html = html.replace(/(<tr>.*<\/tr>)/gs, function(match) {
        return '<table class="response-table">' + match + '</table>';
    });
    
    // Convert line breaks
    html = html.replace(/\n/g, '<br>');
    
    // Clean up extra br tags around headers and lists
    html = html.replace(/<br><h([1-6])>/g, '<h$1>');
    html = html.replace(/<\/h([1-6])><br>/g, '</h$1>');
    html = html.replace(/<br><ul>/g, '<ul>');
    html = html.replace(/<\/ul><br>/g, '</ul>');
    html = html.replace(/<br><table/g, '<table');
    html = html.replace(/<\/table><br>/g, '</table>');
    
    return html;
}

function addSourceInfo(sourceText) {
    const messagesContainer = document.getElementById('messages');
    const lastMessage = messagesContainer.lastElementChild;

    if (lastMessage && lastMessage.classList.contains('assistant')) {
        const contentDiv = lastMessage.querySelector('.message-content');
        const sourceDiv = document.createElement('div');
        sourceDiv.className = 'message-source';
        sourceDiv.textContent = `Source: ${sourceText.substring(0, 150)}...`;
        contentDiv.appendChild(sourceDiv);
    }
}

function showTypingIndicator() {
    const messagesContainer = document.getElementById('messages');

    const typingDiv = document.createElement('div');
    typingDiv.className = 'message assistant typing-indicator';
    typingDiv.id = 'typingIndicator';

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    avatarDiv.textContent = 'AI';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    const textDiv = document.createElement('div');
    textDiv.className = 'message-text';
    textDiv.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';

    contentDiv.appendChild(textDiv);
    typingDiv.appendChild(avatarDiv);
    typingDiv.appendChild(contentDiv);

    messagesContainer.appendChild(typingDiv);
    
    // Smooth scroll to bottom
    setTimeout(() => {
        messagesContainer.scrollTo({
            top: messagesContainer.scrollHeight,
            behavior: 'smooth'
        });
    }, 100);

    // Add typing animation CSS if not already added
    if (!document.getElementById('typingCSS')) {
        const style = document.createElement('style');
        style.id = 'typingCSS';
        style.textContent = `
            .typing-dots {
                display: flex;
                gap: 4px;
                align-items: center;
            }
            .typing-dots span {
                width: 6px;
                height: 6px;
                background-color: #b4b4b4;
                border-radius: 50%;
                animation: typing 1.4s infinite ease-in-out;
            }
            .typing-dots span:nth-child(1) { animation-delay: -0.32s; }
            .typing-dots span:nth-child(2) { animation-delay: -0.16s; }
            @keyframes typing {
                0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
                40% { transform: scale(1); opacity: 1; }
            }
        `;
        document.head.appendChild(style);
    }
}

function hideTypingIndicator() {
    const typingIndicator = document.getElementById('typingIndicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

function handleFileUpload() {
    const files = document.getElementById('fileInput').files;
    if (files.length === 0) return;

    showUploadModal();

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    fetch('/upload', {
        method: 'POST',
        body: formData
    })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showUploadStatus(`<div class="error-message">Error: ${data.error}</div>`);
            } else {
                showUploadStatus(`
                <div class="success-message">
                    Successfully uploaded and processed ${data.uploaded_files.length} files:
                    <ul style="margin-top: 8px; padding-left: 20px;">
                        ${data.uploaded_files.map(file => `<li>${file}</li>`).join('')}
                    </ul>
                </div>
            `);
                
                // Update memory status to show documents are loaded
                updateMemoryStatus(true);
            }
        })
        .catch(error => {
            console.error('Upload error:', error);
            showUploadStatus('<div class="error-message">Network error occurred during upload</div>');
        });

    // Clear file input
    document.getElementById('fileInput').value = '';
}

function showUploadModal() {
    const modal = document.getElementById('uploadModal');
    const statusDiv = document.getElementById('uploadStatus');

    statusDiv.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            <p>Processing documents...</p>
        </div>
    `;

    modal.style.display = 'block';
}

function showUploadStatus(html) {
    const statusDiv = document.getElementById('uploadStatus');
    statusDiv.innerHTML = html;
}

function closeModal() {
    const modal = document.getElementById('uploadModal');
    modal.style.display = 'none';
}

function toggleTools() {
    // Placeholder for tools functionality
    console.log('Tools functionality to be implemented');
}

function updateChatHistory() {
    const historyContainer = document.querySelector('.chat-history');

    // Clear existing history except the "New conversation" item
    const existingItems = historyContainer.querySelectorAll('.chat-history-item:not(.active)');
    existingItems.forEach(item => item.remove());

    // Add recent chats (last 10)
    const recentChats = chatHistory.slice(-10).reverse();
    recentChats.forEach((chat, index) => {
        const historyItem = document.createElement('div');
        historyItem.className = 'chat-history-item';
        historyItem.textContent = chat.user.substring(0, 30) + (chat.user.length > 30 ? '...' : '');
        historyItem.onclick = () => loadChatHistory(index);
        historyContainer.appendChild(historyItem);
    });
}

function loadChatHistory(index) {
    // Placeholder for loading specific chat history
    console.log('Loading chat history:', index);
}

// Close modal when clicking outside
window.onclick = function (event) {
    const modal = document.getElementById('uploadModal');
    if (event.target === modal) {
        closeModal();
    }
}

// Additional functions
function toggleConnectStore() {
    console.log('Connect store functionality to be implemented');
}

function exploreUsecases() {
    console.log('Explore usecases functionality to be implemented');
}

function clearMemory() {
    // Show confirmation dialog
    if (!confirm('Are you sure you want to clear all stored documents and memory? This action cannot be undone.')) {
        return;
    }

    // Show loading state
    const clearButtons = document.querySelectorAll('.clear-memory-btn, .header-clear-btn');
    clearButtons.forEach(btn => {
        btn.disabled = true;
        btn.style.opacity = '0.5';
        btn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
                <path d="M12 6v6l4 2" stroke="currentColor" stroke-width="2"/>
            </svg>
        `;
    });

    // Call the clear endpoint
    fetch('/clear', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            alert('Error clearing memory: ' + data.error);
        } else {
            // Show success message
            addMessage('✅ Memory cleared successfully! All stored documents have been removed from the database.', 'assistant');
            
            // Clear chat history
            chatHistory = [];
            
            // Update memory status indicator
            updateMemoryStatus(false);
            
            // Show success notification
            showClearSuccessNotification();
        }
    })
    .catch(error => {
        console.error('Error clearing memory:', error);
        alert('Network error occurred while clearing memory. Please try again.');
    })
    .finally(() => {
        // Reset button state
        clearButtons.forEach(btn => {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M3 6h18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <line x1="10" y1="11" x2="10" y2="17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <line x1="14" y1="11" x2="14" y2="17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
            `;
        });
    });
}

function showClearSuccessNotification() {
    // Create and show a temporary success notification
    const notification = document.createElement('div');
    notification.className = 'clear-success-notification';
    notification.innerHTML = `
        <div class="notification-content">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M9 12l2 2 4-4" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <circle cx="12" cy="12" r="10" stroke="#10b981" stroke-width="2"/>
            </svg>
            <span>Memory cleared successfully!</span>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    // Add CSS for notification if not already added
    if (!document.getElementById('clearNotificationCSS')) {
        const style = document.createElement('style');
        style.id = 'clearNotificationCSS';
        style.textContent = `
            .clear-success-notification {
                position: fixed;
                top: 20px;
                right: 20px;
                background: white;
                border: 1px solid #10b981;
                border-radius: 8px;
                padding: 12px 16px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                z-index: 1000;
                animation: slideInRight 0.3s ease-out;
            }
            
            .notification-content {
                display: flex;
                align-items: center;
                gap: 8px;
                color: #10b981;
                font-weight: 500;
            }
            
            @keyframes slideInRight {
                from {
                    transform: translateX(100%);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
        `;
        document.head.appendChild(style);
    }
    
    // Remove notification after 3 seconds
    setTimeout(() => {
        notification.style.animation = 'slideInRight 0.3s ease-out reverse';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

function updateMemoryStatus(hasDocuments) {
    const memoryStatus = document.getElementById('memoryStatus');
    if (!memoryStatus) return;
    
    if (hasDocuments) {
        memoryStatus.classList.remove('empty');
        memoryStatus.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
            </svg>
            <span>Memory Active</span>
        `;
        memoryStatus.title = "Documents are stored in memory";
    } else {
        memoryStatus.classList.add('empty');
        memoryStatus.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
                <line x1="15" y1="9" x2="9" y2="15" stroke="currentColor" stroke-width="2"/>
                <line x1="9" y1="9" x2="15" y2="15" stroke="currentColor" stroke-width="2"/>
            </svg>
            <span>Memory Empty</span>
        `;
        memoryStatus.title = "No documents stored in memory";
    }
}