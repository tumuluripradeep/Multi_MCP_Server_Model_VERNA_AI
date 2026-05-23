// Chrome Extension Background Service Worker
class MCPExtensionBackground {
    constructor() {
        this.contextMenuId = 'mcp-assistant-context-menu';
        this.init();
    }
    
    init() {
        // Set up context menu
        this.setupContextMenu();
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Initialize extension
        this.initializeExtension();
    }
    
    setupContextMenu() {
        // Remove existing context menu items
        chrome.contextMenus.removeAll(() => {
            // Create main context menu
            chrome.contextMenus.create({
                id: this.contextMenuId,
                title: '🤖 Ask Verna AI',
                contexts: ['selection', 'page', 'link', 'image']
            });
            
            // Create sub-menu items
            chrome.contextMenus.create({
                id: 'mcp-explain-selection',
                parentId: this.contextMenuId,
                title: '💡 Explain this',
                contexts: ['selection']
            });
            
            chrome.contextMenus.create({
                id: 'mcp-summarize-selection',
                parentId: this.contextMenuId,
                title: '📄 Summarize this',
                contexts: ['selection']
            });
            
            chrome.contextMenus.create({
                id: 'mcp-translate-selection',
                parentId: this.contextMenuId,
                title: '🌐 Translate this',
                contexts: ['selection']
            });
            
            chrome.contextMenus.create({
                id: 'mcp-separator-1',
                parentId: this.contextMenuId,
                type: 'separator',
                contexts: ['selection', 'page']
            });
            
            chrome.contextMenus.create({
                id: 'mcp-summarize-page',
                parentId: this.contextMenuId,
                title: '📄 Summarize page',
                contexts: ['page']
            });
            
            chrome.contextMenus.create({
                id: 'mcp-analyze-page',
                parentId: this.contextMenuId,
                title: '🎯 Analyze page',
                contexts: ['page']
            });
            
            chrome.contextMenus.create({
                id: 'mcp-custom-query',
                parentId: this.contextMenuId,
                title: '❓ Custom query...',
                contexts: ['selection', 'page', 'link', 'image']
            });
        });
    }
    
    setupEventListeners() {
        // Context menu click handler
        chrome.contextMenus.onClicked.addListener((info, tab) => {
            this.handleContextMenuClick(info, tab);
        });
        
        // Extension icon click handler - opens side panel
        chrome.action.onClicked.addListener((tab) => {
            this.handleExtensionIconClick(tab);
        });
        
        // Message handler for communication with content scripts and popup
        chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
            this.handleMessage(request, sender, sendResponse);
            return true; // Keep the messaging channel open for async responses
        });
        
        // Tab update handler
        chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
            if (changeInfo.status === 'complete') {
                this.handleTabUpdate(tabId, tab);
            }
        });
        
        // Installation handler
        chrome.runtime.onInstalled.addListener((details) => {
            this.handleInstallation(details);
        });
    }
    
    async handleContextMenuClick(info, tab) {
        const menuId = info.menuItemId;
        const selectedText = info.selectionText || '';
        
        let query = '';
        
        switch (menuId) {
            case 'mcp-explain-selection':
                query = `Explain this: "${selectedText}"`;
                break;
            case 'mcp-summarize-selection':
                query = `Summarize this: "${selectedText}"`;
                break;
            case 'mcp-translate-selection':
                query = `Translate this: "${selectedText}"`;
                break;
            case 'mcp-summarize-page':
                query = 'Summarize this page';
                break;
            case 'mcp-analyze-page':
                query = 'Analyze this page and provide key insights';
                break;
            case 'mcp-custom-query':
                // Open side panel for custom query
                if (chrome.sidePanel && chrome.sidePanel.open) {
                    try {
                        await chrome.sidePanel.open({ tabId: tab.id });
                    } catch (error) {
                        console.log('Side panel failed, showing notification');
                        this.showNotification(
                            'Verna AI Assistant',
                            'Click the extension icon in the toolbar to open the assistant'
                        );
                    }
                } else {
                    this.showNotification(
                        'Verna AI Assistant',
                        'Click the extension icon in the toolbar to open the assistant'
                    );
                }
                return;
            default:
                return;
        }
        
        if (query) {
            await this.processQuery(query, tab, selectedText);
        }
    }
    
    async handleExtensionIconClick(tab) {
        try {
            console.log('Extension icon clicked for tab:', tab.url);
            
            // Try to open side panel
            if (chrome.sidePanel && chrome.sidePanel.open) {
                try {
                    await chrome.sidePanel.open({ tabId: tab.id });
                    console.log('Side panel opened via extension icon');
                    return;
                } catch (error) {
                    console.log('Side panel failed to open:', error);
                }
            }
            
            // Fallback: Show notification if side panel doesn't work
            this.showNotification(
                'Verna AI Assistant',
                'Side panel not supported in this browser version. Please update Chrome to version 114 or later.'
            );
            
        } catch (error) {
            console.error('Error handling extension icon click:', error);
            this.showNotification(
                'Verna AI Error',
                'Failed to open side panel'
            );
        }
    }
    
    async handleMessage(request, sender, sendResponse) {
        try {
            switch (request.type) {
                case 'GET_TAB_INFO':
                    const tabInfo = await this.getTabInfo(sender.tab?.id);
                    sendResponse({ success: true, data: tabInfo });
                    break;
                    
                case 'GET_SELECTED_TEXT':
                    const selectedText = await this.getSelectedText(sender.tab?.id);
                    sendResponse({ success: true, data: selectedText });
                    break;
                    
                case 'PROCESS_QUERY':
                    const result = await this.processQuery(
                        request.query, 
                        sender.tab, 
                        request.selectedText
                    );
                    sendResponse({ success: true, data: result });
                    break;
                    
                case 'SHOW_NOTIFICATION':
                    this.showNotification(request.title, request.message);
                    sendResponse({ success: true });
                    break;
                    
                case 'FLOATING_BUTTON_CLICKED':
                    await this.handleFloatingButtonClick(request.context, sender.tab);
                    sendResponse({ success: true });
                    break;
                    
                case 'QUICK_ACTION':
                    const actionResult = await this.handleQuickAction(request, sender.tab);
                    sendResponse({ success: true, data: actionResult });
                    break;
                    
                default:
                    sendResponse({ success: false, error: 'Unknown message type' });
            }
        } catch (error) {
            console.error('Error handling message:', error);
            sendResponse({ success: false, error: error.message });
        }
    }
    
    handleTabUpdate(tabId, tab) {
        // Inject content script if needed
        if (tab.url && !tab.url.startsWith('chrome://') && !tab.url.startsWith('chrome-extension://')) {
            this.injectContentScript(tabId);
        }
    }
    
    handleInstallation(details) {
        if (details.reason === 'install') {
            console.log('Verna AI extension installed');
            this.showWelcomeNotification();
            
            // Enable side panel for all tabs if supported
            if (chrome.sidePanel && chrome.sidePanel.setPanelBehavior) {
                chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
                console.log('Side panel behavior set to open on action click');
            }
        } else if (details.reason === 'update') {
            console.log('Verna AI extension updated');
            
            // Ensure side panel behavior is set after update
            if (chrome.sidePanel && chrome.sidePanel.setPanelBehavior) {
                chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
            }
        }
    }
    
    async getTabInfo(tabId) {
        try {
            const tab = await chrome.tabs.get(tabId);
            return {
                title: tab.title,
                url: tab.url,
                favIconUrl: tab.favIconUrl
            };
        } catch (error) {
            console.error('Error getting tab info:', error);
            return null;
        }
    }
    
    async getSelectedText(tabId) {
        try {
            const results = await chrome.scripting.executeScript({
                target: { tabId: tabId },
                function: () => window.getSelection().toString()
            });
            return results[0]?.result || '';
        } catch (error) {
            console.error('Error getting selected text:', error);
            return '';
        }
    }
    
    async processQuery(query, tab, selectedText = '') {
        try {
            // Get page content if needed
            let pageContent = '';
            if (tab?.id) {
                try {
                    const results = await chrome.scripting.executeScript({
                        target: { tabId: tab.id },
                        function: () => {
                            const content = document.body.innerText || document.body.textContent || '';
                            return content.substring(0, 1000); // Limit content length
                        }
                    });
                    pageContent = results[0]?.result || '';
                } catch (error) {
                    console.log('Could not get page content:', error);
                }
            }
            
            // Prepare request data
            const requestData = {
                query: query,
                context: {
                    include_page_content: true,
                    include_selected_text: true
                },
                tab_url: tab?.url,
                tab_title: tab?.title,
                selected_text: selectedText,
                page_content: pageContent
            };
            
            // Send request to API
            const response = await fetch('http://localhost:8001/api/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });
            
            const result = await response.json();
            
            if (result.success) {
                // Show notification with result
                this.showNotification(
                    `Verna AI (${result.server})`,
                    result.response.substring(0, 200) + (result.response.length > 200 ? '...' : '')
                );
                
                // Store result for popup access
                await this.storeResult(result);
                
                return result;
            } else {
                this.showNotification('Verna AI Error', result.error || 'Unknown error');
                return result;
            }
            
        } catch (error) {
            console.error('Error processing query:', error);
            this.showNotification('Verna AI Error', 'Failed to connect to API');
            return { success: false, error: error.message };
        }
    }
    
    async storeResult(result) {
        try {
            // Store the latest result for popup access
            await chrome.storage.local.set({
                latestResult: {
                    ...result,
                    timestamp: Date.now()
                }
            });
        } catch (error) {
            console.error('Error storing result:', error);
        }
    }
    
    async injectContentScript(tabId) {
        try {
            await chrome.scripting.executeScript({
                target: { tabId: tabId },
                files: ['content.js']
            });
        } catch (error) {
            // Content script might already be injected or tab might not support it
            console.log('Could not inject content script:', error);
        }
    }
    
    showNotification(title, message) {
        try {
            chrome.notifications.create({
                type: 'basic',
                iconUrl: chrome.runtime.getURL('icons/icon48.png'),
                title: title,
                message: message
            });
        } catch (error) {
            console.error('Error showing notification:', error);
        }
    }
    
    showWelcomeNotification() {
        this.showNotification(
            'Verna AI Installed',
            'Right-click on any page or selected text to get AI assistance!'
        );
    }
    
    initializeExtension() {
        console.log('Verna AI Extension initialized');
        
        // Set up any initial configuration
        chrome.storage.local.get(['mcpSettings'], (result) => {
            if (!result.mcpSettings) {
                // Set default settings
                chrome.storage.local.set({
                    mcpSettings: {
                        apiUrl: 'http://localhost:8001',
                        autoSubmit: true,
                        showNotifications: true,
                        enableFloatingButton: true  // New setting to control floating button
                    }
                });
            }
        });
    }
    
    async handleFloatingButtonClick(context, tab) {
        try {
            console.log('Floating button clicked:', context);
            
            // Open side panel (Chrome 114+)
            if (chrome.sidePanel && chrome.sidePanel.open) {
                try {
                    await chrome.sidePanel.open({ tabId: tab.id });
                    console.log('Side panel opened successfully');
                    return { success: true, method: 'side_panel' };
                } catch (error) {
                    console.log('Side panel failed:', error);
                }
            }
            
            // Fallback: Show notification to use toolbar icon
            this.showNotification(
                'Verna AI Assistant', 
                'Side panel not supported. Click the extension icon in the toolbar to open the assistant'
            );
            
            return { success: false, method: 'notification' };
            
        } catch (error) {
            console.error('Error handling floating button click:', error);
            return { success: false, error: error.message };
        }
    }
    
    async handleQuickAction(request, tab) {
        try {
            const { query, action, context } = request;
            
            console.log('Processing quick action:', action, query);
            
            // Process the query using your existing logic
            const result = await this.processQuery(query, tab, context.selectedText);
            
            // Show the result in a notification or inject it into the page
            if (result) {
                // Option 1: Show notification with result
                this.showNotification(
                    `Quick Action: ${action}`,
                    result.substring(0, 100) + (result.length > 100 ? '...' : '')
                );
                
                // Option 2: Inject result into page
                chrome.tabs.sendMessage(tab.id, {
                    type: 'SHOW_QUICK_RESULT',
                    action: action,
                    result: result,
                    context: context
                });
            }
            
            return result;
            
        } catch (error) {
            console.error('Error handling quick action:', error);
            this.showNotification('Error', 'Failed to process quick action');
            return null;
        }
    }
}

// Helper functions for programmatic control
async function setFloatingButtonEnabled(enabled) {
    try {
        // Get current settings
        const result = await chrome.storage.local.get(['mcpSettings']);
        const settings = result.mcpSettings || {};
        
        // Update the floating button setting
        settings.enableFloatingButton = enabled;
        
        // Save updated settings
        await chrome.storage.local.set({ mcpSettings: settings });
        
        // Notify all tabs about the change
        const tabs = await chrome.tabs.query({});
        for (const tab of tabs) {
            try {
                await chrome.tabs.sendMessage(tab.id, {
                    type: 'FLOATING_BUTTON_SETTING_CHANGED',
                    enabled: enabled
                });
            } catch (error) {
                // Tab might not have content script, ignore
                console.log('Could not notify tab:', tab.id);
            }
        }
        
        console.log(`Floating button ${enabled ? 'enabled' : 'disabled'} programmatically`);
        return true;
    } catch (error) {
        console.error('Error setting floating button:', error);
        return false;
    }
}

// Expose functions for console access (development)
if (typeof globalThis !== 'undefined') {
    globalThis.setFloatingButtonEnabled = setFloatingButtonEnabled;
}

// Initialize the background script
new MCPExtensionBackground(); 