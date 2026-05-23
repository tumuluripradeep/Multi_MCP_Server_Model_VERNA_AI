// Chrome Extension Content Script - Prevent multiple declarations
if (typeof window.MCPExtensionContent === 'undefined') {
    
class MCPExtensionContent {
    constructor() {
        this.isInitialized = false;
        this.init();
    }
    
    async init() {
        // Prevent multiple initializations
        if (this.isInitialized) return;
        this.isInitialized = true;
        
        console.log('Verna AI content script loaded');
        
        // Set up message listener
        this.setupMessageListener();
        
        // Check settings and conditionally add floating button
        await this.checkFloatingButtonSettings();
        
        // Add visual indicators if needed
        this.addVisualIndicators();
        
        // Set up keyboard shortcuts
        this.setupKeyboardShortcuts();
    }
    
    async checkFloatingButtonSettings() {
        try {
            // Get settings from storage
            const result = await chrome.storage.local.get(['settings']);
            const settings = result.settings || { enableFloatingButton: true };
            
            // Add floating button only if enabled
            if (settings.enableFloatingButton !== false) {
                this.addFloatingButton();
                console.log('Floating button enabled');
            } else {
                console.log('Floating button disabled by user setting');
            }
        } catch (error) {
            console.error('Error checking floating button settings:', error);
            // Default to showing button if there's an error
            this.addFloatingButton();
        }
    }
    
    setupMessageListener() {
        // Listen for messages from background script and popup
        chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
            this.handleMessage(request, sender, sendResponse);
            return true; // Keep the messaging channel open for async responses
        });
    }
    
    async handleMessage(request, sender, sendResponse) {
        try {
            switch (request.type) {
                case 'GET_PAGE_CONTENT':
                    const content = this.getPageContent(request.maxLength || 1000);
                    sendResponse({ success: true, data: content });
                    break;
                    
                case 'GET_SELECTED_TEXT':
                    const selectedText = this.getSelectedText();
                    sendResponse({ success: true, data: selectedText });
                    break;
                    
                case 'HIGHLIGHT_TEXT':
                    this.highlightText(request.text);
                    sendResponse({ success: true });
                    break;
                    
                case 'SHOW_OVERLAY':
                    this.showOverlay(request.content);
                    sendResponse({ success: true });
                    break;
                    
                case 'HIDE_OVERLAY':
                    this.hideOverlay();
                    sendResponse({ success: true });
                    break;
                    
                case 'INJECT_RESPONSE':
                    this.injectResponse(request.response, request.position);
                    sendResponse({ success: true });
                    break;
                    
                case 'SHOW_FLOATING_MODAL':
                    this.showFloatingModal(request.context);
                    sendResponse({ success: true });
                    break;
                    
                case 'SHOW_QUICK_RESULT':
                    this.showQuickResult(request.action, request.result, request.context);
                    sendResponse({ success: true });
                    break;
                    
                case 'FLOATING_BUTTON_SETTING_CHANGED':
                    this.handleFloatingButtonSettingChange(request.enabled);
                    sendResponse({ success: true });
                    break;
                    
                default:
                    sendResponse({ success: false, error: 'Unknown message type' });
            }
        } catch (error) {
            console.error('Error in content script:', error);
            sendResponse({ success: false, error: error.message });
        }
    }
    
    getPageContent(maxLength = 1000) {
        try {
            // Get clean text content from the page
            const textContent = document.body.innerText || document.body.textContent || '';
            
            // Clean up the content
            const cleanContent = textContent
                .replace(/\s+/g, ' ') // Replace multiple whitespace with single space
                .trim();
            
            // Return limited length content
            return cleanContent.substring(0, maxLength);
        } catch (error) {
            console.error('Error getting page content:', error);
            return '';
        }
    }
    
    getSelectedText() {
        try {
            const selection = window.getSelection();
            return selection.toString().trim();
        } catch (error) {
            console.error('Error getting selected text:', error);
            return '';
        }
    }
    
    highlightText(text) {
        try {
            if (!text) return;
            
            // Remove existing highlights
            this.removeHighlights();
            
            // Create a text walker to find and highlight text
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                null,
                false
            );
            
            const textNodes = [];
            let node;
            
            while (node = walker.nextNode()) {
                if (node.textContent.toLowerCase().includes(text.toLowerCase())) {
                    textNodes.push(node);
                }
            }
            
            // Highlight matching text nodes
            textNodes.forEach(textNode => {
                const parent = textNode.parentNode;
                const regex = new RegExp(`(${text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
                const highlightedText = textNode.textContent.replace(regex, '<mark class="mcp-highlight">$1</mark>');
                
                if (highlightedText !== textNode.textContent) {
                    const wrapper = document.createElement('span');
                    wrapper.innerHTML = highlightedText;
                    parent.replaceChild(wrapper, textNode);
                }
            });
            
            // Scroll to first highlight
            const firstHighlight = document.querySelector('.mcp-highlight');
            if (firstHighlight) {
                firstHighlight.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            
        } catch (error) {
            console.error('Error highlighting text:', error);
        }
    }
    
    removeHighlights() {
        try {
            const highlights = document.querySelectorAll('.mcp-highlight');
            highlights.forEach(highlight => {
                const parent = highlight.parentNode;
                parent.replaceChild(document.createTextNode(highlight.textContent), highlight);
                parent.normalize();
            });
        } catch (error) {
            console.error('Error removing highlights:', error);
        }
    }
    
    showOverlay(content) {
        try {
            // Remove existing overlay
            this.hideOverlay();
            
            // Create overlay element
            const overlay = document.createElement('div');
            overlay.id = 'mcp-assistant-overlay';
            overlay.innerHTML = `
                <div class="mcp-overlay-content">
                    <div class="mcp-overlay-header">
                        <span class="mcp-overlay-title">🤖 Verna AI</span>
                        <button class="mcp-overlay-close">&times;</button>
                    </div>
                    <div class="mcp-overlay-body">
                        ${content}
                    </div>
                </div>
            `;
            
            // Add styles
            this.addOverlayStyles();
            
            // Add event listeners
            overlay.querySelector('.mcp-overlay-close').addEventListener('click', () => {
                this.hideOverlay();
            });
            
            // Click outside to close
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    this.hideOverlay();
                }
            });
            
            // Add to page
            document.body.appendChild(overlay);
            
            // Animate in
            setTimeout(() => {
                overlay.classList.add('mcp-overlay-visible');
            }, 10);
            
        } catch (error) {
            console.error('Error showing overlay:', error);
        }
    }
    
    hideOverlay() {
        try {
            const overlay = document.getElementById('mcp-assistant-overlay');
            if (overlay) {
                overlay.classList.remove('mcp-overlay-visible');
                setTimeout(() => {
                    if (overlay.parentNode) {
                        overlay.parentNode.removeChild(overlay);
                    }
                }, 300);
            }
        } catch (error) {
            console.error('Error hiding overlay:', error);
        }
    }
    
    addOverlayStyles() {
        // Check if styles already exist
        if (document.getElementById('mcp-overlay-styles')) return;
        
        const styles = document.createElement('style');
        styles.id = 'mcp-overlay-styles';
        styles.textContent = `
            #mcp-assistant-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                z-index: 999999;
                display: flex;
                align-items: center;
                justify-content: center;
                opacity: 0;
                transition: opacity 0.3s ease;
            }
            
            #mcp-assistant-overlay.mcp-overlay-visible {
                opacity: 1;
            }
            
            .mcp-overlay-content {
                background: white;
                border-radius: 8px;
                max-width: 600px;
                max-height: 80vh;
                width: 90%;
                box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3);
                overflow: hidden;
                transform: scale(0.9);
                transition: transform 0.3s ease;
            }
            
            #mcp-assistant-overlay.mcp-overlay-visible .mcp-overlay-content {
                transform: scale(1);
            }
            
            .mcp-overlay-header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 16px 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .mcp-overlay-title {
                font-weight: 600;
                font-size: 16px;
            }
            
            .mcp-overlay-close {
                background: rgba(255, 255, 255, 0.2);
                border: none;
                color: white;
                width: 24px;
                height: 24px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: background-color 0.2s ease;
            }
            
            .mcp-overlay-close:hover {
                background: rgba(255, 255, 255, 0.3);
            }
            
            .mcp-overlay-body {
                padding: 20px;
                max-height: 60vh;
                overflow-y: auto;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: #333;
            }
            
            .mcp-highlight {
                background: #ffeb3b;
                padding: 2px 4px;
                border-radius: 2px;
                font-weight: 500;
            }
        `;
        
        document.head.appendChild(styles);
    }
    
    injectResponse(response, position = 'cursor') {
        try {
            // Create response element
            const responseEl = document.createElement('div');
            responseEl.className = 'mcp-injected-response';
            responseEl.innerHTML = `
                <div class="mcp-response-header">
                    <span>🤖 Verna AI</span>
                    <button class="mcp-response-close">&times;</button>
                </div>
                <div class="mcp-response-content">${response}</div>
            `;
            
            // Add styles for injected response
            this.addResponseStyles();
            
            // Position the response
            if (position === 'cursor') {
                this.positionAtCursor(responseEl);
            } else if (position === 'selection') {
                this.positionAtSelection(responseEl);
            } else {
                this.positionAtTop(responseEl);
            }
            
            // Add close functionality
            responseEl.querySelector('.mcp-response-close').addEventListener('click', () => {
                if (responseEl.parentNode) {
                    responseEl.parentNode.removeChild(responseEl);
                }
            });
            
            // Auto-remove after 10 seconds
            setTimeout(() => {
                if (responseEl.parentNode) {
                    responseEl.parentNode.removeChild(responseEl);
                }
            }, 10000);
            
        } catch (error) {
            console.error('Error injecting response:', error);
        }
    }
    
    positionAtCursor(element) {
        // Position at top-right of viewport as fallback
        element.style.position = 'fixed';
        element.style.top = '20px';
        element.style.right = '20px';
        element.style.zIndex = '999999';
        document.body.appendChild(element);
    }
    
    positionAtSelection(element) {
        const selection = window.getSelection();
        if (selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);
            const rect = range.getBoundingClientRect();
            
            element.style.position = 'fixed';
            element.style.top = (rect.bottom + 10) + 'px';
            element.style.left = rect.left + 'px';
            element.style.zIndex = '999999';
            document.body.appendChild(element);
        } else {
            this.positionAtCursor(element);
        }
    }
    
    positionAtTop(element) {
        element.style.position = 'fixed';
        element.style.top = '20px';
        element.style.left = '50%';
        element.style.transform = 'translateX(-50%)';
        element.style.zIndex = '999999';
        document.body.appendChild(element);
    }
    
    addResponseStyles() {
        if (document.getElementById('mcp-response-styles')) return;
        
        const styles = document.createElement('style');
        styles.id = 'mcp-response-styles';
        styles.textContent = `
            .mcp-injected-response {
                background: white;
                border: 1px solid #e1e5e9;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                max-width: 400px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                animation: mcpSlideIn 0.3s ease;
            }
            
            .mcp-response-header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 8px 12px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 12px;
                font-weight: 600;
                border-radius: 8px 8px 0 0;
            }
            
            .mcp-response-close {
                background: rgba(255, 255, 255, 0.2);
                border: none;
                color: white;
                width: 20px;
                height: 20px;
                border-radius: 3px;
                cursor: pointer;
                font-size: 12px;
            }
            
            .mcp-response-content {
                padding: 12px;
                font-size: 13px;
                line-height: 1.4;
                color: #333;
                max-height: 200px;
                overflow-y: auto;
            }
            
            @keyframes mcpSlideIn {
                from {
                    opacity: 0;
                    transform: translateY(-10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
        `;
        
        document.head.appendChild(styles);
    }
    
    addVisualIndicators() {
        // Add any visual indicators if needed
        // This could include highlighting, overlays, etc.
    }
    
    addFloatingButton() {
        // Check if button already exists
        if (document.getElementById('verna-ai-fab')) {
            return;
        }
        
        // Create the floating action button
        const fab = document.createElement('div');
        fab.id = 'verna-ai-fab';
        fab.innerHTML = `
            <div class="verna-fab-icon">
                🤖
            </div>
            <div class="verna-fab-tooltip">
                Verna AI Assistant
            </div>
        `;
        
        // Add styles
        this.addFloatingButtonStyles();
        
        // Add click handler
        fab.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.handleFloatingButtonClick();
        });
        
        // Add hover effects
        fab.addEventListener('mouseenter', () => {
            fab.classList.add('verna-fab-hover');
        });
        
        fab.addEventListener('mouseleave', () => {
            fab.classList.remove('verna-fab-hover');
        });
        
        // Add to page
        document.body.appendChild(fab);
        
        // Animate in
        setTimeout(() => {
            fab.classList.add('verna-fab-show');
        }, 100);
    }
    
    addFloatingButtonStyles() {
        // Check if styles already added
        if (document.getElementById('verna-ai-fab-styles')) {
            return;
        }
        
        const style = document.createElement('style');
        style.id = 'verna-ai-fab-styles';
        style.textContent = `
            #verna-ai-fab {
            position: fixed;
            bottom: 20px;
            right: 20px;
                width: 56px;
                height: 56px;
                background: linear-gradient(135deg, #007cba 0%, #005a8b 100%);
            border-radius: 50%;
                box-shadow: 0 4px 12px rgba(0, 124, 186, 0.3);
                cursor: pointer;
                z-index: 2147483647;
            display: flex;
            align-items: center;
            justify-content: center;
                transition: all 0.3s ease;
                transform: scale(0);
                opacity: 0;
                user-select: none;
                border: 2px solid rgba(255, 255, 255, 0.1);
            }
            
            #verna-ai-fab.verna-fab-show {
                transform: scale(1);
                opacity: 1;
            }
            
            #verna-ai-fab:hover,
            #verna-ai-fab.verna-fab-hover {
                transform: scale(1.1);
                box-shadow: 0 6px 16px rgba(0, 124, 186, 0.4);
                background: linear-gradient(135deg, #0090d4 0%, #006699 100%);
            }
            
            #verna-ai-fab:active {
                transform: scale(0.95);
            }
            
            .verna-fab-icon {
                font-size: 24px;
                line-height: 1;
                pointer-events: none;
            }
            
            .verna-fab-tooltip {
                position: absolute;
                right: 70px;
                top: 50%;
                transform: translateY(-50%);
                background: rgba(0, 0, 0, 0.8);
                color: white;
                padding: 8px 12px;
                border-radius: 6px;
            font-size: 14px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                white-space: nowrap;
                opacity: 0;
                visibility: hidden;
                transition: all 0.3s ease;
            pointer-events: none;
                z-index: 2147483648;
            }
            
            .verna-fab-tooltip::after {
                content: '';
                position: absolute;
                top: 50%;
                left: 100%;
                transform: translateY(-50%);
                border: 6px solid transparent;
                border-left-color: rgba(0, 0, 0, 0.8);
            }
            
            #verna-ai-fab:hover .verna-fab-tooltip {
                opacity: 1;
                visibility: visible;
                transform: translateY(-50%) translateX(-5px);
            }
            
            /* Responsive design */
            @media (max-width: 768px) {
                #verna-ai-fab {
                    width: 48px;
                    height: 48px;
                    bottom: 16px;
                    right: 16px;
                }
                
                .verna-fab-icon {
                    font-size: 20px;
                }
                
                .verna-fab-tooltip {
                    display: none;
                }
            }
            
            /* Hide on very small screens to avoid interference */
            @media (max-width: 480px) {
                #verna-ai-fab {
                    width: 44px;
                    height: 44px;
                    bottom: 12px;
                    right: 12px;
                }
            }
        `;
        
        document.head.appendChild(style);
    }
    
    async handleFloatingButtonClick() {
        try {
            // Add click animation
            const fab = document.getElementById('verna-ai-fab');
            if (fab) {
                fab.style.transform = 'scale(0.9)';
        setTimeout(() => {
                    fab.style.transform = '';
                }, 150);
            }
            
            // Get current page context
            const context = {
                url: window.location.href,
                title: document.title,
                selectedText: this.getSelectedText(),
                timestamp: new Date().toISOString()
            };
            
            // Send message to background script to open side panel
            chrome.runtime.sendMessage({
                type: 'FLOATING_BUTTON_CLICKED',
                context: context
            }, (response) => {
                // If side panel opening failed, show modal as fallback
                if (!response || !response.success) {
                    console.log('Side panel unavailable, showing modal fallback');
                    this.showFloatingModal(context);
                }
            });
            
        } catch (error) {
            console.error('Error handling floating button click:', error);
        }
    }
    
    showQuickActions() {
        // Remove existing quick actions
        const existing = document.getElementById('verna-quick-actions');
        if (existing) {
            existing.remove();
            return;
        }
        
        // Create quick actions overlay
        const quickActions = document.createElement('div');
        quickActions.id = 'verna-quick-actions';
        quickActions.innerHTML = `
            <div class="verna-quick-actions-content">
                <div class="verna-quick-actions-header">
                    <span>🤖 Quick Actions</span>
                    <button class="verna-quick-close">&times;</button>
                </div>
                <div class="verna-quick-actions-body">
                    <button class="verna-quick-btn" data-action="summarize">📄 Summarize Page</button>
                    <button class="verna-quick-btn" data-action="explain">💡 Explain Selected</button>
                    <button class="verna-quick-btn" data-action="translate">🌐 Translate</button>
                    <button class="verna-quick-btn" data-action="custom">✨ Custom Query</button>
                </div>
            </div>
        `;
        
        // Add quick actions styles
        this.addQuickActionsStyles();
        
        // Add event listeners
        quickActions.addEventListener('click', (e) => {
            if (e.target.classList.contains('verna-quick-close')) {
                quickActions.remove();
            } else if (e.target.classList.contains('verna-quick-btn')) {
                const action = e.target.getAttribute('data-action');
                this.handleQuickAction(action);
                quickActions.remove();
            }
        });
        
        // Click outside to close
        quickActions.addEventListener('click', (e) => {
            if (e.target === quickActions) {
                quickActions.remove();
            }
        });
        
        document.body.appendChild(quickActions);
        
        // Animate in
                setTimeout(() => {
            quickActions.classList.add('verna-quick-show');
        }, 10);
    }
    
    addQuickActionsStyles() {
        if (document.getElementById('verna-quick-actions-styles')) {
            return;
        }
        
        const style = document.createElement('style');
        style.id = 'verna-quick-actions-styles';
        style.textContent = `
            #verna-quick-actions {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                z-index: 2147483647;
                display: flex;
                align-items: center;
                justify-content: center;
                opacity: 0;
                visibility: hidden;
                transition: all 0.3s ease;
            }
            
            #verna-quick-actions.verna-quick-show {
                opacity: 1;
                visibility: visible;
            }
            
            .verna-quick-actions-content {
                background: white;
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                min-width: 300px;
                max-width: 400px;
                margin: 20px;
                transform: scale(0.9);
                transition: transform 0.3s ease;
            }
            
            #verna-quick-actions.verna-quick-show .verna-quick-actions-content {
                transform: scale(1);
            }
            
            .verna-quick-actions-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 16px 20px;
                border-bottom: 1px solid #eee;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-weight: 600;
                font-size: 16px;
            }
            
            .verna-quick-close {
                background: none;
                border: none;
                font-size: 24px;
                cursor: pointer;
                color: #666;
                padding: 0;
                width: 30px;
                height: 30px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
                transition: background-color 0.2s;
            }
            
            .verna-quick-close:hover {
                background-color: #f5f5f5;
            }
            
            .verna-quick-actions-body {
                padding: 16px 20px;
            }
            
            .verna-quick-btn {
                display: block;
                width: 100%;
                padding: 12px 16px;
                margin-bottom: 8px;
                background: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 8px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.2s ease;
                text-align: left;
            }
            
            .verna-quick-btn:hover {
                background: #007cba;
                color: white;
                border-color: #007cba;
            }
            
            .verna-quick-btn:last-child {
                margin-bottom: 0;
            }
        `;
        
        document.head.appendChild(style);
    }
    
    async handleQuickAction(action) {
        const selectedText = this.getSelectedText();
        const pageContent = this.getPageContent(500);
        
        let query = '';
        switch (action) {
            case 'summarize':
                query = `Summarize this page: ${pageContent}`;
                break;
            case 'explain':
                query = selectedText ? `Explain this text: ${selectedText}` : 'Please select some text first';
                break;
            case 'translate':
                query = selectedText ? `Translate this text: ${selectedText}` : `Translate this page content: ${pageContent}`;
                break;
            case 'custom':
                query = prompt('Enter your custom query:') || '';
                break;
        }
        
        if (query) {
            // Send to background script
            chrome.runtime.sendMessage({
                type: 'QUICK_ACTION',
                query: query,
                action: action,
                context: {
                    url: window.location.href,
                    title: document.title,
                    selectedText: selectedText
                }
            });
        }
    }
    
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl+Shift+M or Cmd+Shift+M to open Verna AI
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'M') {
                e.preventDefault();
                chrome.runtime.sendMessage({
                    type: 'SHOW_NOTIFICATION',
                    title: 'Verna AI Assistant',
                    message: 'Click the extension icon in the toolbar to open the assistant'
                });
            }
        });
    }
    
    showFloatingModal(context) {
        // Create a floating modal that acts like a mini popup
        const existing = document.getElementById('verna-floating-modal');
        if (existing) {
            existing.remove();
        }
        
        const modal = document.createElement('div');
        modal.id = 'verna-floating-modal';
        modal.innerHTML = `
            <div class="verna-modal-content">
                <div class="verna-modal-header">
                    <span>🤖 Verna AI Assistant</span>
                    <button class="verna-modal-close">&times;</button>
                </div>
                <div class="verna-modal-body">
                    <div class="verna-context-info">
                        <div class="verna-context-item">
                            <strong>Page:</strong> ${context.title || 'Untitled'}
                        </div>
                        ${context.selectedText ? `<div class="verna-context-item"><strong>Selected:</strong> ${context.selectedText.substring(0, 100)}${context.selectedText.length > 100 ? '...' : ''}</div>` : ''}
                    </div>
                    <textarea class="verna-modal-input" placeholder="Ask me anything about this page..."></textarea>
                    <div class="verna-modal-actions">
                        <button class="verna-modal-btn verna-btn-primary" data-action="submit">Ask Assistant</button>
                        <button class="verna-modal-btn verna-btn-secondary" data-action="toolbar">Open Full Interface</button>
                    </div>
                </div>
            </div>
        `;
        
        this.addFloatingModalStyles();
        
        // Add event listeners
        modal.addEventListener('click', (e) => {
            if (e.target === modal || e.target.classList.contains('verna-modal-close')) {
                modal.remove();
            } else if (e.target.classList.contains('verna-modal-btn')) {
                const action = e.target.getAttribute('data-action');
                if (action === 'submit') {
                    const input = modal.querySelector('.verna-modal-input');
                    const query = input.value.trim();
                    if (query) {
                        this.handleModalQuery(query, context);
                        modal.remove();
                    }
                } else if (action === 'toolbar') {
                    // Send message to show toolbar notification
                    chrome.runtime.sendMessage({
                        type: 'SHOW_NOTIFICATION',
                        title: 'Verna AI',
                        message: 'Click the extension icon in the toolbar for full interface'
                    });
                    modal.remove();
                }
            }
        });
        
        // Handle Enter key in textarea
        const textarea = modal.querySelector('.verna-modal-input');
        textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                const query = textarea.value.trim();
                if (query) {
                    this.handleModalQuery(query, context);
                    modal.remove();
                }
            }
        });
        
        document.body.appendChild(modal);
        
        // Animate in and focus
        setTimeout(() => {
            modal.classList.add('verna-modal-show');
            textarea.focus();
        }, 10);
    }
    
    addFloatingModalStyles() {
        if (document.getElementById('verna-floating-modal-styles')) {
            return;
        }
        
        const style = document.createElement('style');
        style.id = 'verna-floating-modal-styles';
        style.textContent = `
            #verna-floating-modal {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                z-index: 2147483647;
                display: flex;
                align-items: center;
                justify-content: center;
                opacity: 0;
                visibility: hidden;
                transition: all 0.3s ease;
            }
            
            #verna-floating-modal.verna-modal-show {
                opacity: 1;
                visibility: visible;
            }
            
            .verna-modal-content {
                background: white;
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                width: 90%;
                max-width: 500px;
                max-height: 80vh;
                overflow: hidden;
                transform: scale(0.9);
                transition: transform 0.3s ease;
            }
            
            #verna-floating-modal.verna-modal-show .verna-modal-content {
                transform: scale(1);
            }
            
            .verna-modal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 16px 20px;
                border-bottom: 1px solid #eee;
                background: linear-gradient(135deg, #007cba 0%, #005a8b 100%);
                color: white;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-weight: 600;
                font-size: 16px;
            }
            
            .verna-modal-close {
                background: none;
                border: none;
                font-size: 24px;
                cursor: pointer;
                color: white;
                padding: 0;
                width: 30px;
                height: 30px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
                transition: background-color 0.2s;
            }
            
            .verna-modal-close:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
            
            .verna-modal-body {
                padding: 20px;
            }
            
            .verna-context-info {
                margin-bottom: 16px;
                padding: 12px;
                background: #f8f9fa;
                border-radius: 8px;
                font-size: 14px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }
            
            .verna-context-item {
                margin-bottom: 8px;
            }
            
            .verna-context-item:last-child {
                margin-bottom: 0;
            }
            
            .verna-modal-input {
                width: 100%;
                min-height: 80px;
                padding: 12px;
                border: 2px solid #e9ecef;
                border-radius: 8px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-size: 14px;
                resize: vertical;
                outline: none;
                transition: border-color 0.2s;
                box-sizing: border-box;
            }
            
            .verna-modal-input:focus {
                border-color: #007cba;
            }
            
            .verna-modal-actions {
                display: flex;
                gap: 12px;
                margin-top: 16px;
            }
            
            .verna-modal-btn {
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s ease;
                flex: 1;
            }
            
            .verna-btn-primary {
                background: #007cba;
                color: white;
            }
            
            .verna-btn-primary:hover {
                background: #005a8b;
            }
            
            .verna-btn-secondary {
                background: #f8f9fa;
                color: #495057;
                border: 1px solid #dee2e6;
            }
            
            .verna-btn-secondary:hover {
                background: #e9ecef;
            }
        `;
        
        document.head.appendChild(style);
    }
    
    async handleModalQuery(query, context) {
        try {
            // Show loading state on floating button
            const fab = document.getElementById('verna-ai-fab');
            if (fab) {
                fab.innerHTML = '<div class="verna-fab-icon">⏳</div>';
            }
            
            // Send query to background script
            chrome.runtime.sendMessage({
                type: 'QUICK_ACTION',
                query: query,
                action: 'modal_query',
                context: context
            });
            
        } catch (error) {
            console.error('Error processing modal query:', error);
        }
    }
    
    showQuickResult(action, result, context) {
        // Show result in a toast notification style
        const existing = document.getElementById('verna-result-toast');
        if (existing) {
            existing.remove();
        }
        
        const toast = document.createElement('div');
        toast.id = 'verna-result-toast';
        toast.innerHTML = `
            <div class="verna-toast-header">
                <span>🤖 ${this.getActionTitle(action)}</span>
                <button class="verna-toast-close">&times;</button>
            </div>
            <div class="verna-toast-body">
                ${this.formatResult(result)}
            </div>
            <div class="verna-toast-actions">
                <button class="verna-toast-btn" data-action="copy">📋 Copy</button>
                <button class="verna-toast-btn" data-action="more">💬 More</button>
            </div>
        `;
        
        this.addResultToastStyles();
        
        // Add event listeners
        toast.addEventListener('click', (e) => {
            if (e.target.classList.contains('verna-toast-close')) {
                toast.remove();
            } else if (e.target.classList.contains('verna-toast-btn')) {
                const actionType = e.target.getAttribute('data-action');
                if (actionType === 'copy') {
                    navigator.clipboard.writeText(result);
                    e.target.textContent = '✅ Copied';
                    setTimeout(() => {
                        e.target.textContent = '📋 Copy';
                    }, 2000);
                } else if (actionType === 'more') {
                    // Try to open side panel first
                    chrome.runtime.sendMessage({
                        type: 'FLOATING_BUTTON_CLICKED',
                        context: context
                    });
                }
            }
        });
        
        document.body.appendChild(toast);
        
        // Animate in
        setTimeout(() => {
            toast.classList.add('verna-toast-show');
        }, 10);
        
        // Auto-hide after 10 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.classList.remove('verna-toast-show');
                setTimeout(() => {
                    if (toast.parentNode) {
                        toast.remove();
                    }
                }, 300);
            }
        }, 10000);
        
        // Reset floating button
        const fab = document.getElementById('verna-ai-fab');
        if (fab) {
            fab.innerHTML = `
                <div class="verna-fab-icon">🤖</div>
                <div class="verna-fab-tooltip">Verna AI Assistant</div>
            `;
        }
    }
    
    getActionTitle(action) {
        const titles = {
            'summarize': 'Page Summary',
            'explain': 'Explanation',
            'translate': 'Translation',
            'modal_query': 'AI Response',
            'custom': 'Custom Query'
        };
        return titles[action] || 'AI Response';
    }
    
    formatResult(result) {
        if (!result) return 'No result available';
        
        // Basic markdown to HTML conversion for display
        return result
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/\n/g, '<br>')
            .substring(0, 300) + (result.length > 300 ? '...' : '');
    }
    
    addResultToastStyles() {
        if (document.getElementById('verna-result-toast-styles')) {
            return;
        }
        
        const style = document.createElement('style');
        style.id = 'verna-result-toast-styles';
        style.textContent = `
            #verna-result-toast {
                position: fixed;
                top: 20px;
                right: 20px;
                width: 400px;
                max-width: calc(100vw - 40px);
                background: white;
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
                z-index: 2147483646;
                transform: translateX(100%);
                transition: transform 0.3s ease;
                border: 1px solid #e9ecef;
            }
            
            #verna-result-toast.verna-toast-show {
                transform: translateX(0);
            }
            
            .verna-toast-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 12px 16px;
                border-bottom: 1px solid #eee;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-weight: 600;
                font-size: 14px;
                background: #f8f9fa;
                border-radius: 12px 12px 0 0;
            }
            
            .verna-toast-close {
                background: none;
                border: none;
                font-size: 18px;
                cursor: pointer;
                color: #666;
                padding: 0;
                width: 24px;
                height: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
                transition: background-color 0.2s;
            }
            
            .verna-toast-close:hover {
                background-color: #e9ecef;
            }
            
            .verna-toast-body {
                padding: 16px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-size: 14px;
                line-height: 1.5;
                max-height: 200px;
                overflow-y: auto;
            }
            
            .verna-toast-actions {
                display: flex;
                gap: 8px;
                padding: 12px 16px;
                border-top: 1px solid #eee;
                background: #f8f9fa;
                border-radius: 0 0 12px 12px;
            }
            
            .verna-toast-btn {
                padding: 6px 12px;
                background: white;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-size: 12px;
                cursor: pointer;
                transition: all 0.2s ease;
                flex: 1;
            }
            
            .verna-toast-btn:hover {
                background: #007cba;
                color: white;
                border-color: #007cba;
            }
        `;
        
        document.head.appendChild(style);
    }
    
    handleFloatingButtonSettingChange(enabled) {
        const existingButton = document.getElementById('verna-ai-fab');
        
        if (enabled) {
            // Add floating button if it doesn't exist
            if (!existingButton) {
                this.addFloatingButton();
                console.log('Floating button enabled via settings');
            }
        } else {
            // Remove floating button if it exists
            if (existingButton) {
                existingButton.remove();
                console.log('Floating button disabled via settings');
            }
        }
    }
}

// Attach class to window to prevent redeclaration
window.MCPExtensionContent = MCPExtensionContent;

} // End of conditional class declaration

// Initialize content script only if not already initialized
if (!window.mcpExtensionContent) {
    window.mcpExtensionContent = new window.MCPExtensionContent();
} 