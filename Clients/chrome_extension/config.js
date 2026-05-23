// Verna AI Chrome Extension Configuration
// ==============================================
// 
// This file contains configuration options for the Verna AI extension.
// Modify the values below to customize the extension behavior.

const VERNA_CONFIG = {
    // FLOATING BUTTON CONFIGURATION
    // Set to true to show the floating button on all web pages
    // Set to false to disable the floating button
    ENABLE_FLOATING_BUTTON: true,
    
    // API CONFIGURATION
    API_URL: 'http://localhost:8001',
    
    // UI CONFIGURATION
    AUTO_SUBMIT: true,
    SHOW_NOTIFICATIONS: true,
    MAX_HISTORY: 50,
    
    // FLOATING BUTTON APPEARANCE
    FLOATING_BUTTON_POSITION: {
        bottom: '20px',
        right: '20px'
    },
    
    // KEYBOARD SHORTCUTS
    ENABLE_KEYBOARD_SHORTCUTS: true,
    
    // CONTEXT MENU
    ENABLE_CONTEXT_MENU: true
};

// Apply configuration on load
if (typeof chrome !== 'undefined' && chrome.storage) {
    chrome.storage.local.set({
        mcpSettings: {
            apiUrl: VERNA_CONFIG.API_URL,
            autoSubmit: VERNA_CONFIG.AUTO_SUBMIT,
            showNotifications: VERNA_CONFIG.SHOW_NOTIFICATIONS,
            enableFloatingButton: VERNA_CONFIG.ENABLE_FLOATING_BUTTON,
            maxHistory: VERNA_CONFIG.MAX_HISTORY
        }
    });
    
    console.log('Verna AI configuration applied:', VERNA_CONFIG);
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = VERNA_CONFIG;
} 