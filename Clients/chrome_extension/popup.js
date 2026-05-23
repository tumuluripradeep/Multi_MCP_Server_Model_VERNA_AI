// Chrome Extension Popup JavaScript
class MCPExtensionPopup {
    constructor() {
        this.apiUrl = 'http://localhost:8001';
        this.settings = {
            apiUrl: 'http://localhost:8001',
            streamlitUrl: 'http://localhost:8501',
            autoSubmit: true,
            maxHistory: 50,
            useStreaming: true
        };
        this.connectionRetries = 3;
        this.backendHealthy = false;
        this.requestCount = 0;
        this.lastRequestTime = null;
        
        // Session management for conversation context
        this.sessionId = null;
        this.tabId = null;
        this.availableSessions = [];
        this.currentSessionIndex = 0;
        
        // UI Section states
        this.sectionStates = {
            session: true,  // expanded by default
            page: true      // expanded by default
        };
        
        this.init();
    }
    
    async init() {
        // Initialize session management
        await this.initializeSession();
        
        // Load settings
        await this.loadSettings();
        
        // Initialize DOM elements
        this.initializeElements();
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Load initial data
        await this.loadInitialData();
        
        // Check API status
        await this.checkApiStatus();
        
        // Initialize section states
        this.initializeSectionStates();
    }
    
    async initializeSession() {
        try {
            // Get current tab to create session context
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab) {
                this.tabId = tab.id;
                
                // Load existing sessions from storage
                await this.loadExistingSessions();
                
                // Check if there's an active session for this tab
                const activeSession = this.availableSessions.find(s => s.tabId === tab.id && s.isActive);
                
                if (activeSession) {
                    // Use existing active session
                    this.sessionId = activeSession.sessionId;
                    this.currentSessionIndex = this.availableSessions.indexOf(activeSession);
                    console.log(`Resumed session: ${this.sessionId} for tab ${tab.id}`);
                } else {
                    // Create new session
                    await this.createNewSession(tab);
                }
            }
        } catch (error) {
            console.error('Error initializing session:', error);
            // Fallback to simple session ID
            this.sessionId = `session_${Date.now()}`;
        }
    }
    
    async loadExistingSessions() {
        try {
            const result = await chrome.storage.local.get(['verna_sessions']);
            this.availableSessions = result.verna_sessions || [];
            
            // Clean up old sessions (older than 7 days)
            const weekAgo = Date.now() - (7 * 24 * 60 * 60 * 1000);
            this.availableSessions = this.availableSessions.filter(session => 
                session.startTime > weekAgo
            );
            
            // Save cleaned sessions back
            await chrome.storage.local.set({ verna_sessions: this.availableSessions });
            
        } catch (error) {
            console.error('Error loading sessions:', error);
            this.availableSessions = [];
        }
    }
    
    async createNewSession(tab) {
        const newSession = {
            sessionId: `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            tabId: tab.id,
            startTime: Date.now(),
            tabUrl: tab.url,
            tabTitle: tab.title,
            isActive: true,
            firstQuestion: null,
            lastActivity: Date.now(),
            questionCount: 0
        };
        
        // Deactivate other sessions for this tab
        this.availableSessions.forEach(session => {
            if (session.tabId === tab.id) {
                session.isActive = false;
            }
        });
        
        this.availableSessions.push(newSession);
        this.sessionId = newSession.sessionId;
        this.currentSessionIndex = this.availableSessions.length - 1;
        
        // Save to storage
        await chrome.storage.local.set({ verna_sessions: this.availableSessions });
        
        console.log(`New session created: ${this.sessionId} for tab ${tab.id}`);
    }
    
    async updateSessionDisplay() {
        // Update session info
        const currentSession = this.availableSessions[this.currentSessionIndex];
        if (currentSession) {
            const sessionTitle = currentSession.firstQuestion 
                ? `${currentSession.firstQuestion.substring(0, 30)}...`
                : `Session ${new Date(currentSession.startTime).toLocaleTimeString()}`;
            
            // Update session name
            if (this.elements.sessionInfo) {
                this.elements.sessionInfo.textContent = sessionTitle;
            }
            
            // Update session stats
            if (this.elements.sessionStats) {
                this.elements.sessionStats.textContent = `${currentSession.questionCount} questions`;
            }
            
            // Update session time
            if (this.elements.sessionTime) {
                const timeSince = this.getTimeSince(currentSession.startTime);
                this.elements.sessionTime.textContent = timeSince;
            }
        }
        
        // Populate session selector
        this.populateSessionSelector();
    }
    
    getTimeSince(timestamp) {
        const now = Date.now();
        const diff = now - timestamp;
        const minutes = Math.floor(diff / (1000 * 60));
        const hours = Math.floor(diff / (1000 * 60 * 60));
        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        
        if (minutes < 1) return 'Just now';
        if (minutes < 60) return `${minutes}m ago`;
        if (hours < 24) return `${hours}h ago`;
        return `${days}d ago`;
    }
    
    populateSessionSelector() {
        if (!this.elements.sessionSelect) return;
        
        // Clear existing options
        this.elements.sessionSelect.innerHTML = '';
        
        // Add current sessions
        this.availableSessions.forEach((session, index) => {
            const option = document.createElement('option');
            option.value = session.sessionId;
            
            const isActive = session.sessionId === this.sessionId ? '🟢 ' : '';
            const sessionTitle = session.firstQuestion 
                ? session.firstQuestion.substring(0, 25) + '...'
                : `Session ${new Date(session.startTime).toLocaleTimeString()}`;
            
            option.textContent = `${isActive}${sessionTitle} (${session.questionCount})`;
            option.selected = session.sessionId === this.sessionId;
            
            this.elements.sessionSelect.appendChild(option);
        });
        
        // Add "New Session" option
        const newOption = document.createElement('option');
        newOption.value = 'new';
        newOption.textContent = '➕ Create New Session';
        this.elements.sessionSelect.appendChild(newOption);
    }
    
    async switchToSession(sessionId) {
        if (sessionId === 'new') {
            await this.createNewSessionManually();
            return;
        }
        
        if (!sessionId) return;
        
        const sessionIndex = this.availableSessions.findIndex(s => s.sessionId === sessionId);
        if (sessionIndex === -1) return;
        
        // Update current session
        this.sessionId = sessionId;
        this.currentSessionIndex = sessionIndex;
        
        // Mark as active session for this tab
        this.availableSessions.forEach(session => {
            session.isActive = session.sessionId === sessionId && session.tabId === this.tabId;
        });
        
        // Save to storage
        await chrome.storage.local.set({ verna_sessions: this.availableSessions });
        
        // Update UI
        await this.updateSessionDisplay();
        
        // Clear current response to indicate session switch
        this.clearResponse();
        
        console.log(`Switched to session: ${sessionId}`);
    }
    
    async createNewSessionManually() {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab) {
            await this.createNewSession(tab);
            await this.updateSessionDisplay();
        }
    }
    
    async clearCurrentSession() {
        const currentSession = this.availableSessions[this.currentSessionIndex];
        if (currentSession) {
            // Reset session data
            currentSession.questionCount = 0;
            currentSession.firstQuestion = null;
            currentSession.lastActivity = Date.now();
            
            // Save to storage
            await chrome.storage.local.set({ verna_sessions: this.availableSessions });
            
            // Update UI
            await this.updateSessionDisplay();
            this.clearResponse();
        }
    }
    
    showSessionSwitcher() {
        // Implementation for showing session switcher modal if needed
        console.log('Session switcher requested');
    }
    
    async updateSessionAfterQuery(query) {
        const currentSession = this.availableSessions[this.currentSessionIndex];
        if (currentSession) {
            currentSession.questionCount++;
            currentSession.lastActivity = Date.now();
            
            // Set first question if not already set
            if (!currentSession.firstQuestion) {
                currentSession.firstQuestion = query.length > 50 ? query.substring(0, 50) + '...' : query;
            }
            
            // Save to storage
            await chrome.storage.local.set({ verna_sessions: this.availableSessions });
            
            // Update UI
            await this.updateSessionDisplay();
        }
    }
    
    initializeElements() {
        // Session management elements
        this.elements = {
            sessionInfo: document.getElementById('sessionInfo'),
            sessionStats: document.getElementById('sessionStats'),
            sessionTime: document.getElementById('sessionTime'),
            sessionSelect: document.getElementById('sessionSelect'),
            clearSessionBtn: document.getElementById('clearSessionBtn'),
            sessionToggle: document.getElementById('sessionToggle'),
            sessionContent: document.getElementById('sessionContent'),
            sessionManagementSection: document.getElementById('sessionManagementSection'),
            
            // Page context elements
            pageTitle: document.getElementById('pageTitle'),
            pageUrl: document.getElementById('pageUrl'),
            selectedText: document.getElementById('selectedText'),
            selectedContext: document.getElementById('selectedContext'),
            pageContext: document.getElementById('pageContext'),
            includePageContent: document.getElementById('includePageContent'),
            includeSelectedText: document.getElementById('includeSelectedText'),
            pageToggle: document.getElementById('pageToggle'),
            pageContent: document.getElementById('pageContent'),
            currentPageSection: document.getElementById('currentPageSection'),
            
            // Header elements
            openFullTabBtn: document.getElementById('openFullTabBtn'),
            
            // Query elements
            queryInput: document.getElementById('queryInput'),
            serverSelect: document.getElementById('serverSelect'),
            submitBtn: document.getElementById('submitBtn'),
            
            // Response elements
            responseSection: document.getElementById('responseSection'),
            responseContent: document.getElementById('responseContent'),
            serverUsed: document.getElementById('serverUsed'),
            copyBtn: document.getElementById('copyBtn'),
            clearBtn: document.getElementById('clearBtn'),
            
            // Status elements
            statusDot: document.getElementById('statusDot'),
            statusText: document.getElementById('statusText'),
            
            // History and settings
            historyBtn: document.getElementById('historyBtn'),
            settingsBtn: document.getElementById('settingsBtn'),
            helpBtn: document.getElementById('helpBtn'),
            
            // Stats
            requestCount: document.getElementById('requestCount'),
            lastRequestTime: document.getElementById('lastRequestTime'),
            
            // Modals
            historyModal: document.getElementById('historyModal'),
            settingsModal: document.getElementById('settingsModal'),
            historyContent: document.getElementById('historyContent'),
            closeHistoryBtn: document.getElementById('closeHistoryBtn'),
            closeSettingsBtn: document.getElementById('closeSettingsBtn'),
            
            // Settings
            apiUrl: document.getElementById('apiUrl'),
            streamlitUrl: document.getElementById('streamlitUrl'),
            autoSubmit: document.getElementById('autoSubmit'),
            maxHistory: document.getElementById('maxHistory'),
            enableFloatingButton: document.getElementById('enableFloatingButton'),
            
            // Playwright Automation elements
            screenshotBtn: document.getElementById('screenshotBtn'),
            fillFormBtn: document.getElementById('fillFormBtn'),
            extractDataBtn: document.getElementById('extractDataBtn'),
            testLinksBtn: document.getElementById('testLinksBtn'),
            compareBtn: document.getElementById('compareBtn'),
            monitorBtn: document.getElementById('monitorBtn'),
            testPlaywrightBtn: document.getElementById('testPlaywrightBtn'),
            saveSettingsBtn: document.getElementById('saveSettingsBtn'),
            
            // Quick authentication elements
            authStatusSection: document.getElementById('authStatusSection'),
            quickLoginBtn: document.getElementById('quickLoginBtn')
        };
    }
    
    setupEventListeners() {
        // Session management listeners
        if (this.elements.sessionSelect) {
            this.elements.sessionSelect.addEventListener('change', async (e) => {
                await this.switchToSession(e.target.value);
            });
        }
        
        if (this.elements.clearSessionBtn) {
            this.elements.clearSessionBtn.addEventListener('click', async () => {
                if (confirm('Clear current session history?')) {
                    await this.clearCurrentSession();
                }
            });
        }
        
        // Header action listeners
        if (this.elements.openFullTabBtn) {
            this.elements.openFullTabBtn.addEventListener('click', () => {
                this.openFullTab();
            });
        }
        
        // Section toggle listeners
        if (this.elements.sessionToggle) {
            this.elements.sessionToggle.addEventListener('click', () => {
                this.toggleSection('session');
            });
        }
        
        if (this.elements.pageToggle) {
            this.elements.pageToggle.addEventListener('click', () => {
                this.toggleSection('page');
            });
        }
        
        // Server selection listener
        if (this.elements.serverSelect) {
            this.elements.serverSelect.addEventListener('change', async (e) => {
                await this.handleServerSelection(e.target.value);
            });
        }
        
        // Quick authentication listener
        if (this.elements.quickLoginBtn) {
            this.elements.quickLoginBtn.addEventListener('click', async () => {
                await this.handleQuickAuth();
            });
        }
        
        // Query listeners
        if (this.elements.submitBtn) {
            this.elements.submitBtn.addEventListener('click', () => this.handleSubmit());
        
        // Playwright Automation event listeners
        if (this.elements.screenshotBtn) {
            this.elements.screenshotBtn.addEventListener('click', () => this.handlePlaywrightAction('screenshot'));
        }
        if (this.elements.fillFormBtn) {
            this.elements.fillFormBtn.addEventListener('click', () => this.handlePlaywrightAction('fillForm'));
        }
        if (this.elements.extractDataBtn) {
            this.elements.extractDataBtn.addEventListener('click', () => this.handlePlaywrightAction('extractData'));
        }
        if (this.elements.testLinksBtn) {
            this.elements.testLinksBtn.addEventListener('click', () => this.handlePlaywrightAction('testLinks'));
        }
        if (this.elements.compareBtn) {
            this.elements.compareBtn.addEventListener('click', () => this.handlePlaywrightAction('compare'));
        }
        if (this.elements.monitorBtn) {
            this.elements.monitorBtn.addEventListener('click', () => this.handlePlaywrightAction('monitor'));
        }
        if (this.elements.testPlaywrightBtn) {
            this.elements.testPlaywrightBtn.addEventListener('click', () => this.testPlaywrightServer());
        }
        }
        
        if (this.elements.queryInput) {
            this.elements.queryInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    this.handleSubmit();
                }
            });
        }
        
        // Response action listeners
        if (this.elements.copyBtn) {
            this.elements.copyBtn.addEventListener('click', () => this.copyResponse());
        }
        
        if (this.elements.clearBtn) {
            this.elements.clearBtn.addEventListener('click', () => this.clearResponse());
        }
        
        // Quick action listeners
        document.querySelectorAll('.quick-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const query = btn.dataset.query;
                if (query) {
                    this.elements.queryInput.value = query;
                    this.handleSubmit();
                }
            });
        });
        
        // Modal listeners
        if (this.elements.historyBtn) {
            this.elements.historyBtn.addEventListener('click', () => this.showHistory());
        }
        
        if (this.elements.settingsBtn) {
            this.elements.settingsBtn.addEventListener('click', async () => await this.showSettings());
        }
        
        if (this.elements.helpBtn) {
            this.elements.helpBtn.addEventListener('click', () => this.showHelp());
        }
        
        if (this.elements.closeHistoryBtn) {
            this.elements.closeHistoryBtn.addEventListener('click', () => this.hideModal('historyModal'));
        }
        
        if (this.elements.closeSettingsBtn) {
            this.elements.closeSettingsBtn.addEventListener('click', () => this.hideModal('settingsModal'));
        }
        
        if (this.elements.saveSettingsBtn) {
            this.elements.saveSettingsBtn.addEventListener('click', () => this.saveSettings());
        }
        
        // Close modals when clicking outside
        [this.elements.historyModal, this.elements.settingsModal].forEach(modal => {
            if (modal) {
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) {
                        this.hideModal(modal.id);
                    }
                });
            }
        });
    }
    
    initializeSectionStates() {
        // Load section states from storage
        chrome.storage.local.get(['sectionStates'], (result) => {
            if (result.sectionStates) {
                this.sectionStates = { ...this.sectionStates, ...result.sectionStates };
            }
            
            // Apply section states
            this.applySectionStates();
        });
    }
    
    applySectionStates() {
        if (!this.sectionStates.session) {
            this.elements.sessionManagementSection?.classList.add('collapsed');
        }
        
        if (!this.sectionStates.page) {
            this.elements.currentPageSection?.classList.add('collapsed');
        }
    }
    
    toggleSection(sectionName) {
        const sectionElement = sectionName === 'session' 
            ? this.elements.sessionManagementSection 
            : this.elements.currentPageSection;
        
        if (sectionElement) {
            sectionElement.classList.toggle('collapsed');
            this.sectionStates[sectionName] = !sectionElement.classList.contains('collapsed');
            
            // Save section states
            chrome.storage.local.set({ sectionStates: this.sectionStates });
        }
    }
    
    openFullTab() {
        const streamlitUrl = this.settings.streamlitUrl || 'http://localhost:8501';
        
        // Open Streamlit app in a new tab
        chrome.tabs.create({ 
            url: streamlitUrl,
            active: true 
        }).then(() => {
            // Optionally close the popup after opening the full tab
            window.close();
        }).catch(error => {
            console.error('Error opening full tab:', error);
            // Fallback to window.open if chrome.tabs.create fails
            try {
                window.open(streamlitUrl, '_blank');
                window.close();
            } catch (fallbackError) {
                console.error('Fallback method also failed:', fallbackError);
                alert(`Please manually open: ${streamlitUrl}`);
            }
        });
    }
    
    async loadInitialData() {
        // Load available servers
        await this.loadAvailableServers();
        
        // Load page context
        await this.loadPageContext();
        
        // Update session display
        await this.updateSessionDisplay();
        
        // Load request stats
        this.updateStats();
    }
    
    async loadPageContext() {
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab) {
                // Update page title and URL
                if (this.elements.pageTitle) {
                    this.elements.pageTitle.textContent = tab.title || 'Unknown Page';
                }
                
                if (this.elements.pageUrl) {
                    this.elements.pageUrl.textContent = tab.url || 'Unknown URL';
                }
                
                // Try to get selected text
                try {
                    const results = await chrome.tabs.sendMessage(tab.id, { type: 'GET_SELECTED_TEXT' });
                    if (results && results.success && results.data) {
                        // Truncate selected text for display (keep first 100 characters)
                        const selectedText = results.data;
                        const displayText = selectedText.length > 100 
                            ? selectedText.substring(0, 100) + '...' 
                            : selectedText;
                        this.elements.selectedText.textContent = displayText;
                        this.elements.selectedContext.style.display = 'block';
                    } else {
                        this.elements.selectedContext.style.display = 'none';
                    }
                } catch (error) {
                    console.log('Could not get selected text:', error);
                    this.elements.selectedContext.style.display = 'none';
                }
            }
        } catch (error) {
            console.error('Error loading page context:', error);
        }
    }
    
    async loadAvailableServers() {
        try {
            const url = `${this.apiUrl}/api/servers${this.sessionId ? `?session_id=${this.sessionId}` : ''}`;
            const response = await fetch(url);
            const data = await response.json();
            
            if (data.servers) {
                this.populateServerSelect(data.servers);
            }
        } catch (error) {
            console.error('Error loading servers:', error);
        }
    }
    
    populateServerSelect(servers) {
        if (!this.elements.serverSelect) return;
        
        // Clear existing options except the first one
        this.elements.serverSelect.innerHTML = '<option value="">🔄 Auto-select server</option>';
        
        // Add server options
        Object.entries(servers).forEach(([serverName, serverInfo]) => {
            const option = document.createElement('option');
            option.value = serverName;
            
            // Add authentication indicator
            let authIndicator = '';
            if (serverInfo.auth_config && serverInfo.auth_config.requires_auth) {
                authIndicator = serverInfo.is_authenticated ? ' 🔓' : ' 🔒';
            }
            
            option.textContent = `${this.getServerIcon(serverName)} ${serverName}${authIndicator}`;
            
            this.elements.serverSelect.appendChild(option);
        });
    }
    
    getServerIcon(serverName) {
        const icons = {
            // Core system servers
            'service_system': '🛠️',
            'sales_system': '💼',
            'accounting_system': '💰',
            'hr_system': '👥',
            'csm_system': '🎯',
            'marketing_system': '📊',
            'jarvis_system': '🤖',
            
            // Third-party integrations
            'slack': '💬',
            'mcp-atlassian': '🔧',
            'microsoft.docs.mcp': '📚',
            'playwright': '🎭',
            
            // Content and media
            'youtube': '📺',
            'audio_video_rag': '🎬',
            'web_search_scrape_rag': '🔍',
            'intelli_web_search': '🔍',
            
            // Data sources
            'weather': '🌤️',
            'weather_analysis': '🌤️',
            'twitter_analytics': '🐦',
            'social': '📱',
            'vector_db': '🗄️',
            'sap_hana': '🏢',
            's4_hana': '🏢',
            
            // Legacy mappings for backward compatibility
            'weather_system': '🌤️',
            'web_search': '🔍',
            'jarvis': '🤖',
            'accounting': '💰',
            'hr': '👥',
            'csm': '🎯',
            'marketing': '📊',
            'sales': '💼',
            'service': '🛠️',
            'social': '📱',
            'sap_hana': '🏢'
        };
        return icons[serverName] || '⚡';
    }
    
    async handleSubmit() {
        const query = this.elements.queryInput?.value?.trim();
        if (!query) return;
        
        // Check backend health before submitting
        if (!this.backendHealthy) {
            this.showError('Backend server is not running. Please start chrome_extension_client.py first.');
            this.showBackendStartupInstructions();
            return;
        }
        
        const selectedServer = this.elements.serverSelect?.value || null;
        
        // Check authentication if a specific server is selected
        if (selectedServer) {
            const authRequired = await this.checkServerAuthRequired(selectedServer);
            if (authRequired && !await this.isServerAuthenticated(selectedServer)) {
                this.showAuthenticationModal(selectedServer);
                return;
            }
        }
        
        this.setLoading(true);
        
        try {
            // Get current tab info
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            
            // Get selected text if available
            let selectedText = '';
            try {
                const results = await chrome.tabs.sendMessage(tab.id, { type: 'GET_SELECTED_TEXT' });
                if (results && results.success && results.data) {
                    selectedText = results.data;
                }
            } catch (error) {
                console.log('Could not get selected text:', error);
            }
            
            // Get page content if requested
            let pageContent = '';
            if (this.elements.includePageContent?.checked) {
                try {
                    const results = await chrome.tabs.sendMessage(tab.id, { type: 'GET_PAGE_CONTENT' });
                    if (results && results.success && results.data) {
                        pageContent = results.data;
                    }
                } catch (error) {
                    console.log('Could not get page content:', error);
                }
            }
            
            // Prepare request data
            const requestData = {
                query: query,
                server: selectedServer,
                context: {
                    includePageContent: this.elements.includePageContent?.checked || false,
                    includeSelectedText: this.elements.includeSelectedText?.checked || false
                },
                tab_url: tab.url,
                tab_title: tab.title,
                page_content: pageContent,
                selected_text: selectedText,
                session_id: this.sessionId,
                tab_id: String(this.tabId),
                youtube_video_id: this.isYouTubeQuery(query) ? this.extractYouTubeVideoId(query) : null
            };
            
            const useStream = this.settings.useStreaming !== false;
            if (useStream) {
                const streamed = await this.submitQueryStream(requestData, selectedServer);
                if (streamed) {
                    await this.updateSessionAfterQuery(query);
                } else {
                    await this.submitQueryNonStream(requestData, selectedServer, query);
                }
            } else {
                await this.submitQueryNonStream(requestData, selectedServer, query);
            }
            
            // Update stats
            this.requestCount++;
            this.lastRequestTime = new Date();
            this.updateStats();
            
        } catch (error) {
            console.error('Error processing query:', error);
            
            // Provide specific error messages
            if (error.name === 'TypeError' || error.message.includes('Failed to fetch')) {
                this.showError('Connection failed: Backend server may be offline');
                this.showBackendStartupInstructions();
                this.backendHealthy = false;
            } else if (error.name === 'TimeoutError') {
                this.showError('Request timeout: Backend server is taking too long to respond');
            } else {
                this.showError(`Network error: ${error.message}`);
            }
        } finally {
            this.setLoading(false);
        }
    }

    async submitQueryNonStream(requestData, selectedServer, query) {
        const response = await fetch(`${this.apiUrl}/api/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData),
        });
        const result = await response.json();
        if (result.success) {
            this.showResponse(result.response, result.server);
            await this.updateSessionAfterQuery(query);
        } else if (result.error && result.error.includes('Authentication required')) {
            this.showAuthenticationModal(result.server || selectedServer);
        } else {
            this.showError(result.error || 'Unknown error occurred');
        }
    }

    async submitQueryStream(requestData, selectedServer) {
        try {
            const response = await fetch(`${this.apiUrl}/api/query/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData),
            });
            if (!response.ok || !response.body) {
                return false;
            }
            this.showResponse('', selectedServer || 'streaming');
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let fullText = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    let payload;
                    try {
                        payload = JSON.parse(line.slice(6));
                    } catch {
                        continue;
                    }
                    if (payload.type === 'token' && payload.content) {
                        fullText += payload.content;
                        this.showResponse(fullText, selectedServer || 'auto');
                    } else if (payload.type === 'done' && payload.content) {
                        fullText = payload.content || fullText;
                        this.showResponse(fullText, selectedServer || 'auto');
                    } else if (payload.type === 'error') {
                        this.showError(payload.content);
                        return false;
                    }
                }
            }
            return true;
        } catch (e) {
            console.warn('Streaming failed, falling back:', e);
            return false;
        }
    }
    
    showResponse(response, server) {
        if (this.elements.responseContent) {
            this.elements.responseContent.innerHTML = this.parseMarkdown(response);
        }
        
        if (this.elements.serverUsed) {
            this.elements.serverUsed.textContent = server || 'Unknown';
        }
        
        if (this.elements.responseSection) {
            this.elements.responseSection.style.display = 'block';
        }
    }
    
    parseMarkdown(text) {
        if (!text) return '';
        
        // Simple markdown parsing
        return text
            // Headers
            .replace(/^### (.*$)/gm, '<h3>$1</h3>')
            .replace(/^## (.*$)/gm, '<h2>$1</h2>')
            .replace(/^# (.*$)/gm, '<h1>$1</h1>')
            
            // Bold and italic
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            
            // Code blocks
            .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            
            // Links
            .replace(/\[([^\]]+)\]\(([^\)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
            
            // Lists
            .replace(/^\* (.+)$/gm, '<li>$1</li>')
            .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
            
            // Line breaks
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>')
            
            // Wrap in paragraphs
            .replace(/^(.+)$/gm, '<p>$1</p>')
            
            // Clean up extra paragraph tags
            .replace(/<p><\/p>/g, '')
            .replace(/<p>(<h[1-6]>.*?<\/h[1-6]>)<\/p>/g, '$1')
            .replace(/<p>(<ul>.*?<\/ul>)<\/p>/g, '$1')
            .replace(/<p>(<pre>.*?<\/pre>)<\/p>/g, '$1');
    }
    
    showError(message) {
        if (this.elements.responseContent) {
            this.elements.responseContent.innerHTML = `<div class="error">❌ ${message}</div>`;
        }
        
        if (this.elements.responseSection) {
            this.elements.responseSection.style.display = 'block';
        }
    }
    
    async handlePlaywrightAction(action) {
        // Check backend health before executing automation
        if (!this.backendHealthy) {
            this.showError('Backend server is not running. Please start chrome_extension_client.py first.');
            this.showBackendStartupInstructions();
            return;
        }
        
        // Set loading state for the specific button
        const buttonElement = this.elements[action + 'Btn'];
        if (buttonElement) {
            buttonElement.disabled = true;
            const originalText = buttonElement.textContent;
            buttonElement.textContent = '⏳ Processing...';
            
            // Restore button after timeout
            setTimeout(() => {
                buttonElement.disabled = false;
                buttonElement.textContent = originalText;
            }, 10000);
        }
        
        try {
            // Get current tab info
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            
            // Get page content and selected text
            let selectedText = '';
            let pageContent = '';
            
            try {
                const selectedResults = await chrome.tabs.sendMessage(tab.id, { type: 'GET_SELECTED_TEXT' });
                if (selectedResults && selectedResults.success && selectedResults.data) {
                    selectedText = selectedResults.data;
                }
                
                const contentResults = await chrome.tabs.sendMessage(tab.id, { type: 'GET_PAGE_CONTENT' });
                if (contentResults && contentResults.success && contentResults.data) {
                    pageContent = contentResults.data;
                }
            } catch (error) {
                console.log('Could not get page context:', error);
            }
            
                         // Build automation-specific execution queries with explicit Playwright commands
             const automationQueries = {
                 screenshot: `Execute screenshot automation: Navigate to ${tab.url} and capture a full-page screenshot.`,
                 fillForm: `Execute form automation: Navigate to ${tab.url}, identify all form fields, and fill them with appropriate test data.`,
                 extractData: `Execute data extraction: Navigate to ${tab.url}, extract all tables, lists, links, text content, and structured data.`,
                 testLinks: `Execute link testing: Navigate to ${tab.url}, find all links on the page, test each link's HTTP status, measure response times, and report broken links.`,
                 compare: `Execute comparison automation: Navigate to ${tab.url}, extract product/service information, then search and compare with competitors.`,
                 monitor: `Execute monitoring setup: Navigate to ${tab.url}, capture baseline screenshots, and identify key elements for change monitoring.`
             };
             
             const query = automationQueries[action] || `Execute ${action} automation on this page.`;
            
            // Prepare request data for Playwright automation
            const requestData = {
                query: query,
                context: {
                    action: action,
                    includePageContent: true,
                    includeSelectedText: true,
                    automationType: 'playwright'
                },
                tab_url: tab.url,
                tab_title: tab.title,
                page_content: pageContent,
                selected_text: selectedText,
                session_id: this.sessionId,
                tab_id: String(this.tabId)
            };
            
            // Send request to Playwright execution endpoint for direct automation
            const response = await fetch(`${this.apiUrl}/api/playwright/execute`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });
            
            const result = await response.json();
            
            if (result.success) {
                // Check if we got actual execution results or just instructions
                const responseText = result.response.toLowerCase();
                const executionIndicators = ['executed', 'screenshot saved', 'links tested', 'data extracted', 'navigation complete'];
                const instructionIndicators = ['create a script', 'you can', 'below is a sample', 'here\'s how', 'follow these steps'];
                
                const isExecution = executionIndicators.some(indicator => responseText.includes(indicator));
                const isInstructions = instructionIndicators.some(indicator => responseText.includes(indicator));
                
                if (isInstructions && !isExecution) {
                    // We got instructions instead of execution
                    this.showError(`❌ Playwright ${action} returned instructions instead of executing the automation. The Playwright server may need configuration or the command needs to be more specific.`);
                    console.warn('Received instructions instead of execution:', result.response);
                } else {
                    // Show result with special styling for automation
                    this.showPlaywrightResponse(result.response, action);
                    await this.updateSessionAfterQuery(`Playwright ${action}: ${query}`);
                }
            } else {
                this.showError(`Playwright ${action} failed: ${result.error || 'Unknown error occurred'}`);
            }
            
            // Update stats
            this.requestCount++;
            this.lastRequestTime = new Date();
            this.updateStats();
            
        } catch (error) {
            console.error(`Error in Playwright ${action}:`, error);
            
            if (error.name === 'TypeError' || error.message.includes('Failed to fetch')) {
                this.showError('Connection failed: Backend server may be offline');
                this.showBackendStartupInstructions();
                this.backendHealthy = false;
            } else {
                this.showError(`Playwright ${action} error: ${error.message}`);
            }
        } finally {
            // Restore button state
            if (buttonElement) {
                buttonElement.disabled = false;
                const automationLabels = {
                    screenshot: '📸 Screenshot',
                    fillForm: '📝 Fill Form',
                    extractData: '📊 Extract Data',
                    testLinks: '🔗 Test Links',
                    compare: '⚖️ Compare',
                    monitor: '👁️ Monitor'
                };
                buttonElement.textContent = automationLabels[action] || buttonElement.textContent;
            }
        }
    }
    
    showPlaywrightResponse(response, action) {
        if (this.elements.responseContent) {
            const actionEmojis = {
                screenshot: '📸',
                fillForm: '📝',
                extractData: '📊',
                testLinks: '🔗',
                compare: '⚖️',
                monitor: '👁️'
            };
            
            const emoji = actionEmojis[action] || '🎭';
            const header = `<div class="automation-response-header">${emoji} Playwright ${action.charAt(0).toUpperCase() + action.slice(1)} Result</div>`;
            this.elements.responseContent.innerHTML = header + this.parseMarkdown(response);
        }
        
        if (this.elements.serverUsed) {
            this.elements.serverUsed.textContent = 'Playwright Automation';
        }
        
        if (this.elements.responseSection) {
            this.elements.responseSection.style.display = 'block';
        }
    }
    
    async testPlaywrightServer() {
        // Check backend health before testing
        if (!this.backendHealthy) {
            this.showError('Backend server is not running. Please start chrome_extension_client.py first.');
            this.showBackendStartupInstructions();
            return;
        }
        
        // Set loading state
        const testBtn = this.elements.testPlaywrightBtn;
        if (testBtn) {
            testBtn.disabled = true;
            testBtn.textContent = '🧪 Testing...';
        }
        
        try {
            // Test Playwright server execution
            const response = await fetch(`${this.apiUrl}/api/test/playwright`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            const result = await response.json();
            
            if (result.error) {
                this.showError(`Playwright test failed: ${result.error}`);
            } else {
                // Display test results
                let testSummary = `🧪 **Playwright Server Test Results**\n\n`;
                testSummary += `**Total Commands Tested:** ${result.total_commands}\n\n`;
                
                result.results.forEach((test, index) => {
                    testSummary += `**Test ${index + 1}:** ${test.success ? '✅ Success' : '❌ Failed'}\n`;
                    testSummary += `**Command:** ${test.command}\n`;
                    if (test.response_type) {
                        testSummary += `**Response Type:** ${test.response_type === 'execution' ? '✅ Execution' : '⚠️ Instructions'}\n`;
                    }
                    if (test.error) {
                        testSummary += `**Error:** ${test.error}\n`;
                    } else if (test.response_preview) {
                        testSummary += `**Response Preview:** ${test.response_preview}\n`;
                    }
                    testSummary += `\n`;
                });
                
                this.showPlaywrightResponse(testSummary, 'test');
            }
            
        } catch (error) {
            console.error('Playwright test error:', error);
            this.showError(`Playwright test error: ${error.message}`);
        } finally {
            // Restore button state
            if (testBtn) {
                testBtn.disabled = false;
                testBtn.textContent = '🧪 Test Playwright';
            }
        }
    }
    
    clearResponse() {
        if (this.elements.responseSection) {
            this.elements.responseSection.style.display = 'none';
        }
        
        if (this.elements.queryInput) {
            this.elements.queryInput.value = '';
        }
    }
    
    async copyResponse() {
        if (this.elements.responseContent) {
            try {
                await navigator.clipboard.writeText(this.elements.responseContent.textContent);
                // Show temporary success message
                const originalText = this.elements.copyBtn.textContent;
                this.elements.copyBtn.textContent = '✓ Copied!';
                setTimeout(() => {
                    this.elements.copyBtn.textContent = originalText;
                }, 2000);
            } catch (error) {
                console.error('Could not copy text:', error);
            }
        }
    }
    
    setLoading(loading) {
        if (this.elements.submitBtn) {
            this.elements.submitBtn.disabled = loading;
            this.elements.submitBtn.querySelector('.btn-text').style.display = loading ? 'none' : 'inline';
            this.elements.submitBtn.querySelector('.btn-loading').style.display = loading ? 'inline' : 'none';
        }
    }
    
    updateStatus(status, message) {
        if (this.elements.statusDot) {
            this.elements.statusDot.className = `status-dot ${status}`;
        }
        if (this.elements.statusText) {
            this.elements.statusText.textContent = message;
        }
    }
    
    updateStats() {
        if (this.elements.requestCount) {
            this.elements.requestCount.textContent = `${this.requestCount} requests`;
        }
        if (this.elements.lastRequestTime) {
            this.elements.lastRequestTime.textContent = this.lastRequestTime 
                ? this.lastRequestTime.toLocaleTimeString()
                : 'Never';
        }
    }
    
    async checkApiStatus() {
        let retryCount = 0;
        
        while (retryCount < this.connectionRetries) {
            try {
                // First try the health endpoint for detailed status
                const healthResponse = await fetch(`${this.apiUrl}/api/health`, {
                    method: 'GET',
                    signal: AbortSignal.timeout(20000) // allow cold MCP/Azure; /api/health is fast now
                });
                
                if (healthResponse.ok) {
                    const healthData = await healthResponse.json();
                    this.backendHealthy = true;
                    const serverCount = healthData.available_servers?.length || 0;
                    this.updateStatus('online', `✅ Connected (${serverCount} servers)`);
                    console.log('Backend health:', healthData);
                    return;
                } else {
                    throw new Error(`Health check failed: ${healthResponse.status}`);
                }
            } catch (healthError) {
                // Fallback: hit FastAPI (not / — nginx sends / to Streamlit, which may 403 extension fetches)
                try {
                    const response = await fetch(`${this.apiUrl}/openapi.json`, {
                        method: 'GET',
                        signal: AbortSignal.timeout(10000)
                    });
                    
                    if (response.ok) {
                        this.backendHealthy = true;
                        this.updateStatus('online', '✅ Connected (limited info)');
                        console.log('Basic connection successful');
                        return;
                    } else {
                        throw new Error(`Backend returned ${response.status}`);
                    }
                } catch (basicError) {
                    retryCount++;
                    console.warn(`Connection attempt ${retryCount} failed:`, basicError);
                    
                    if (retryCount < this.connectionRetries) {
                        await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1 second before retry
                    } else {
                        this.backendHealthy = false;
                        
                        // Provide helpful error messages
                        if (basicError.name === 'TypeError' || basicError.message.includes('Failed to fetch')) {
                            this.updateStatus('offline', '❌ Backend not running');
                            this.showBackendStartupInstructions();
                        } else if (basicError.name === 'TimeoutError') {
                            this.updateStatus('offline', '❌ Connection timeout');
                        } else {
                            this.updateStatus('offline', `❌ Error: ${basicError.message}`);
                        }
                    }
                }
            }
        }
    }
    
    showBackendStartupInstructions() {
        // Show instructions in the response area if no successful queries yet
        const responseElement = document.getElementById('response');
        if (responseElement && !responseElement.innerHTML.trim()) {
            const instructions = `
            <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 4px; padding: 12px; margin: 10px 0; font-size: 13px;">
                <strong>⚠️ Chrome Extension Backend Not Running</strong><br><br>
                To use this extension, please start the backend server:<br>
                <code style="background: #f8f9fa; padding: 4px 6px; border-radius: 3px; font-family: 'Courier New', monospace; display: block; margin: 8px 0;">
                    python Clients/chrome_extension_client.py
                </code>
                <small style="color: #666;">The backend should start on port 8001</small>
            </div>
            `;
            responseElement.innerHTML = instructions;
            responseElement.style.display = 'block';
        }
    }
    
    async showHistory() {
        try {
            const response = await fetch(`${this.apiUrl}/api/history`);
            const data = await response.json();
            
            if (data.history && data.history.length > 0) {
                const historyHtml = data.history.map(item => `
                    <div class="history-item">
                        <div class="history-query">${item.query}</div>
                        <div class="history-response">${item.response}</div>
                        <div class="history-meta">
                            <span>${new Date(item.timestamp).toLocaleString()}</span>
                            <span class="history-server">${item.server}</span>
                        </div>
                    </div>
                `).join('');
                
                // Add session switcher
                let sessionOptions = '';
                this.availableSessions.forEach(session => {
                    const sessionTitle = session.firstQuestion || `Session ${new Date(session.startTime).toLocaleTimeString()}`;
                    sessionOptions += `<option value="${session.sessionId}">${sessionTitle}</option>`;
                });
                
                const sessionSwitcher = `
                    <div class="history-session-switcher">
                        <strong>🔗 Current Session History</strong>
                        <select class="history-session-select">
                            ${sessionOptions}
                        </select>
                        <button class="history-switch-btn">Switch Session</button>
                    </div>
                `;
                
                this.elements.historyContent.innerHTML = sessionSwitcher + historyHtml;
                
                // Add event listener for session switch
                const switchBtn = this.elements.historyContent.querySelector('.history-switch-btn');
                const sessionSelect = this.elements.historyContent.querySelector('.history-session-select');
                
                if (switchBtn && sessionSelect) {
                    switchBtn.addEventListener('click', async () => {
                        await this.switchToSession(sessionSelect.value);
                        this.hideModal('historyModal');
                    });
                }
            } else {
                this.elements.historyContent.innerHTML = '<div class="no-history">No history available</div>';
            }
        } catch (error) {
            console.error('Error loading history:', error);
            this.elements.historyContent.innerHTML = '<div class="error">Error loading history</div>';
        }
        
        this.showModal('historyModal');
    }
    
    async showSettings() {
        // Load current settings
        if (this.elements.apiUrl) {
            this.elements.apiUrl.value = this.settings.apiUrl;
        }
        if (this.elements.streamlitUrl) {
            this.elements.streamlitUrl.value = this.settings.streamlitUrl;
        }
        if (this.elements.autoSubmit) {
            this.elements.autoSubmit.checked = this.settings.autoSubmit;
        }
        if (this.elements.maxHistory) {
            this.elements.maxHistory.value = this.settings.maxHistory;
        }
        if (this.elements.enableFloatingButton) {
            this.elements.enableFloatingButton.checked = this.settings.enableFloatingButton;
        }
        
        this.showModal('settingsModal');
    }
    
    showHelp() {
        alert(`Verna AI Assistant Help:
        
• Ask questions about any webpage
• Use Ctrl+Enter to submit queries
• Select text on page for context
• Session management tracks conversations
• Toggle sections to customize layout
• Use quick actions for common tasks
        
Keyboard Shortcuts:
• Ctrl+Enter: Submit query
• Escape: Close modals
        
Tips:
• Select text before asking for better context
• Use specific server selection for targeted responses
• Session history persists across page reloads`);
    }
    
    showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'flex';
        }
    }
    
    hideModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'none';
        }
    }
    
    async saveSettings() {
        // Get settings from form
        const newSettings = {
            apiUrl: this.elements.apiUrl?.value || 'http://localhost:8001',
            streamlitUrl: this.elements.streamlitUrl?.value || 'http://localhost:8501',
            autoSubmit: this.elements.autoSubmit?.checked || false,
            maxHistory: parseInt(this.elements.maxHistory?.value) || 50,
            enableFloatingButton: this.elements.enableFloatingButton?.checked || false
        };
        
        // Update instance settings
        this.settings = newSettings;
        this.apiUrl = newSettings.apiUrl;
        
        // Save to storage
        await chrome.storage.local.set({ settings: newSettings });
        
        // Notify content script about floating button change
        if (this.elements.enableFloatingButton) {
            await this.notifyFloatingButtonChange(newSettings.enableFloatingButton);
        }
        
        // Update status
        const saveBtn = this.elements.saveSettingsBtn;
        if (saveBtn) {
            const originalText = saveBtn.textContent;
            saveBtn.textContent = '✓ Saved!';
            setTimeout(() => {
                saveBtn.textContent = originalText;
            }, 2000);
        }
        
        // Check API status with new URL
        await this.checkApiStatus();
    }
    
    async loadSettings() {
        try {
            const result = await chrome.storage.local.get(['settings']);
            if (result.settings) {
                this.settings = { ...this.settings, ...result.settings };
                this.apiUrl = this.settings.apiUrl;
            }
        } catch (error) {
            console.error('Error loading settings:', error);
        }
    }
    
    async notifyFloatingButtonChange(enabled) {
        try {
            // Get all tabs to notify all of them
            const tabs = await chrome.tabs.query({});
            
            for (const tab of tabs) {
                try {
                    // Only send to tabs with valid URLs (not chrome:// pages)
                    if (tab.url && !tab.url.startsWith('chrome://') && !tab.url.startsWith('chrome-extension://')) {
                        await chrome.tabs.sendMessage(tab.id, {
                            type: 'FLOATING_BUTTON_SETTING_CHANGED',
                            enabled: enabled
                        });
                    }
                } catch (error) {
                    // Tab might not have content script, ignore
                    console.log('Could not notify tab:', tab.id, error);
                }
            }
            
            console.log(`Floating button ${enabled ? 'enabled' : 'disabled'} on all tabs`);
        } catch (error) {
            console.error('Error notifying floating button change:', error);
        }
    }
    
    isYouTubeQuery(query) {
        const youtubeIndicators = [
            'youtube.com/watch',
            'youtu.be/',
            'youtube video',
            'video analysis',
            'analyze video',
            'video summary'
        ];
        
        return youtubeIndicators.some(indicator => 
            query.toLowerCase().includes(indicator.toLowerCase())
        );
    }
    
    extractYouTubeVideoId(query) {
        const patterns = [
            /youtube\.com\/watch\?v=([a-zA-Z0-9_-]+)/,
            /youtu\.be\/([a-zA-Z0-9_-]+)/,
            /youtube\.com\/embed\/([a-zA-Z0-9_-]+)/
        ];
        
        for (const pattern of patterns) {
            const match = query.match(pattern);
            if (match) {
                return match[1];
            }
        }
        
        return null;
    }
    
    async checkServerAuthRequired(serverName) {
        try {
            const response = await fetch(`${this.apiUrl}/api/auth/status?session_id=${this.sessionId}`);
            const data = await response.json();
            
            if (data.auth_status && data.auth_status[serverName]) {
                return data.auth_status[serverName].requires_auth;
            }
            
            return false;
        } catch (error) {
            console.error('Error checking auth status:', error);
            return false;
        }
    }
    
    async isServerAuthenticated(serverName) {
        try {
            const response = await fetch(`${this.apiUrl}/api/auth/status?session_id=${this.sessionId}`);
            const data = await response.json();
            
            if (data.auth_status && data.auth_status[serverName]) {
                return data.auth_status[serverName].is_authenticated;
            }
            
            return false;
        } catch (error) {
            console.error('Error checking auth status:', error);
            return false;
        }
    }
    
    async handleServerSelection(serverName) {
        if (!serverName) {
            // Hide authentication section for auto-select
            this.hideAuthSection();
            return;
        }
        
        try {
            const authRequired = await this.checkServerAuthRequired(serverName);
            if (authRequired) {
                const isAuthenticated = await this.isServerAuthenticated(serverName);
                this.showAuthSection(serverName, isAuthenticated);
            } else {
                this.hideAuthSection();
            }
        } catch (error) {
            console.error('Error checking server auth status:', error);
            this.hideAuthSection();
        }
    }
    
    showAuthSection(serverName, isAuthenticated) {
        const authSection = this.elements.authStatusSection;
        const authCard = authSection?.querySelector('.auth-status-card');
        const authText = authSection?.querySelector('.auth-status-text');
        const loginBtn = this.elements.quickLoginBtn;
        
        if (!authSection || !authCard || !authText || !loginBtn) return;
        
        if (isAuthenticated) {
            authCard.className = 'auth-status-card authenticated';
            authText.textContent = 'Authenticated ✓';
            loginBtn.textContent = 'Logout';
            loginBtn.setAttribute('data-action', 'logout');
        } else {
            authCard.className = 'auth-status-card';
            authText.textContent = 'Authentication required';
            loginBtn.textContent = 'Login';
            loginBtn.setAttribute('data-action', 'login');
        }
        
        loginBtn.setAttribute('data-server', serverName);
        authSection.style.display = 'block';
    }
    
    hideAuthSection() {
        const authSection = this.elements.authStatusSection;
        if (authSection) {
            authSection.style.display = 'none';
        }
    }
    
    async handleQuickAuth() {
        const loginBtn = this.elements.quickLoginBtn;
        const action = loginBtn?.getAttribute('data-action');
        const serverName = loginBtn?.getAttribute('data-server');
        
        if (!action || !serverName) return;
        
        try {
            if (action === 'login') {
                await this.showAuthenticationModal(serverName);
            } else if (action === 'logout') {
                const response = await fetch(`${this.apiUrl}/api/auth/logout`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        server: serverName,
                        session_id: this.sessionId
                    })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    // Update authentication display
                    this.showAuthSection(serverName, false);
                    
                    // Refresh server list
                    await this.loadAvailableServers();
                    
                    // Show success message
                    this.showTemporaryMessage('✅ Successfully logged out');
                } else {
                    this.showTemporaryMessage('❌ Logout failed');
                }
            }
        } catch (error) {
            console.error('Error handling quick auth:', error);
            this.showTemporaryMessage('❌ Authentication action failed');
        }
    }
    
    showTemporaryMessage(message) {
        // Create a temporary message near the auth section
        const authSection = this.elements.authStatusSection;
        if (!authSection) return;
        
        const messageEl = document.createElement('div');
        messageEl.style.cssText = `
            background: #4CAF50;
            color: white;
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 12px;
            margin-top: 8px;
            text-align: center;
            animation: slideDown 0.3s ease;
        `;
        messageEl.textContent = message;
        
        authSection.appendChild(messageEl);
        
        setTimeout(() => {
            messageEl.remove();
        }, 3000);
    }
    

    
    async showAuthenticationModal(serverName) {
        try {
            const response = await fetch(`${this.apiUrl}/api/auth/status?session_id=${this.sessionId}`);
            const data = await response.json();
            
            const authConfig = data.auth_status && data.auth_status[serverName];
            if (!authConfig) return;
            
            const displayName = authConfig.display_name || serverName;
            const authType = authConfig.auth_type || 'generic';
            
            // Create authentication modal HTML
            const modalHtml = this.createAuthModalHtml(serverName, displayName, authType);
            
            // Show modal
            const existingModal = document.getElementById('auth-modal');
            if (existingModal) {
                existingModal.remove();
            }
            
            const modalElement = document.createElement('div');
            modalElement.innerHTML = modalHtml;
            document.body.appendChild(modalElement.firstElementChild);
            
            // Setup modal event listeners
            this.setupAuthModalEventListeners(serverName, authType);
            
        } catch (error) {
            console.error('Error showing auth modal:', error);
        }
    }
    
    createAuthModalHtml(serverName, displayName, authType) {
        // Authentication methods mapping
        const authMethods = {
            "basic": "🔑 Basic Auth (Username/Password)",
            "oauth2": "🌐 OAuth 2.0",
            "api_key": "🔐 API Key",
            "token": "🎫 Bearer Token",
            "azure_ad": "☁️ Azure AD (Microsoft)",
            "google_oauth": "🔍 Google OAuth",
            "github_oauth": "🐙 GitHub OAuth",
            "slack_oauth": "💬 Slack OAuth",
            "custom": "⚙️ Custom"
        };

        // Determine default auth method based on system type
        let defaultAuth = authType;
        if (authType === 'dynamics_crm' || authType === 'dynamics_365') {
            defaultAuth = 'azure_ad';
        } else if (authType === 'slack_oauth') {
            defaultAuth = 'slack_oauth';
        } else if (authType === 'atlassian_api') {
            defaultAuth = 'api_key';
        } else if (authType === 'databricks') {
            defaultAuth = 'token';
        } else {
            defaultAuth = 'basic';
        }

        // Create dropdown options
        const authOptions = Object.entries(authMethods).map(([key, label]) => 
            `<option value="${key}" ${key === defaultAuth ? 'selected' : ''}>${label}</option>`
        ).join('');

        return `
            <div id="auth-modal" style="
                position: fixed; 
                top: 0; 
                left: 0; 
                width: 100%; 
                height: 100%; 
                background: rgba(0,0,0,0.7); 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                z-index: 10000;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            ">
                <div style="
                    background: white; 
                    padding: 0; 
                    border-radius: 12px; 
                    width: 90%; 
                    max-width: 500px;
                    max-height: 80vh;
                    overflow-y: auto;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                ">
                    <!-- Header -->
                    <div style="
                        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
                        color: white;
                        padding: 20px 24px;
                        border-radius: 12px 12px 0 0;
                        text-align: center;
                    ">
                        <h3 style="margin: 0 0 8px 0; font-weight: 600; font-size: 18px;">
                            🔐 Authenticate to ${displayName}
                        </h3>
                        <p style="margin: 0; opacity: 0.9; font-size: 14px;">
                            Choose your preferred authentication method
                        </p>
                    </div>

                    <!-- Content -->
                    <div style="padding: 24px;">
                        <!-- Auth Method Selector -->
                        <div style="margin-bottom: 20px;">
                            <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">
                                Authentication Method
                            </label>
                            <select id="auth-method-select" style="
                                width: 100%;
                                padding: 10px 12px;
                                border: 2px solid #e5e7eb;
                                border-radius: 8px;
                                font-size: 14px;
                                background: white;
                                cursor: pointer;
                                transition: border-color 0.2s ease;
                            ">
                                ${authOptions}
                            </select>
                        </div>

                        <hr style="border: none; height: 1px; background: #e5e7eb; margin: 20px 0;">

                        <!-- Dynamic Auth Fields Container -->
                        <div id="auth-fields-container">
                            ${this.generateAuthFields(defaultAuth)}
                        </div>

                        <!-- Action Buttons -->
                        <div style="display: flex; gap: 12px; margin-top: 24px;">
                            <button id="auth-test-btn" style="
                                flex: 1;
                                background: #6b7280; 
                                color: white; 
                                border: none; 
                                padding: 12px 16px; 
                                border-radius: 8px; 
                                cursor: pointer;
                                font-weight: 500;
                                font-size: 14px;
                                transition: background 0.2s ease;
                            ">🧪 Test</button>
                            <button id="auth-login-btn" style="
                                flex: 2;
                                background: #10b981; 
                                color: white; 
                                border: none; 
                                padding: 12px 16px; 
                                border-radius: 8px; 
                                cursor: pointer;
                                font-weight: 600;
                                font-size: 14px;
                                transition: background 0.2s ease;
                            ">🔐 Connect</button>
                            <button id="auth-cancel-btn" style="
                                flex: 1;
                                background: #ef4444; 
                                color: white; 
                                border: none; 
                                padding: 12px 16px; 
                                border-radius: 8px; 
                                cursor: pointer;
                                font-weight: 500;
                                font-size: 14px;
                                transition: background 0.2s ease;
                            ">✖️ Cancel</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    generateAuthFields(authMethod) {
        switch (authMethod) {
            case 'basic':
                return `
                    <h4 style="margin: 0 0 16px 0; color: #1f2937; font-size: 16px;">🔑 Basic Authentication</h4>
                    <div style="display: grid; gap: 12px;">
                        <input type="text" id="auth-username" placeholder="Username" required style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="password" id="auth-password" placeholder="Password" required style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="text" id="auth-domain" placeholder="Domain (optional)" style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                    </div>
                `;

            case 'oauth2':
                return `
                    <h4 style="margin: 0 0 16px 0; color: #1f2937; font-size: 16px;">🌐 OAuth 2.0 Authentication</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                        <input type="text" id="auth-client-id" placeholder="Client ID" required style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="password" id="auth-client-secret" placeholder="Client Secret" required style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="text" id="auth-redirect-uri" placeholder="Redirect URI" style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="text" id="auth-scope" placeholder="Scope" value="read" style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                    </div>
                    <div style="display: grid; gap: 12px; margin-top: 12px;">
                        <input type="text" id="auth-auth-url" placeholder="Authorization URL" style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="text" id="auth-token-url" placeholder="Token URL" style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                    </div>
                `;

            case 'api_key':
                return `
                    <h4 style="margin: 0 0 16px 0; color: #1f2937; font-size: 16px;">🔐 API Key Authentication</h4>
                    <div style="display: grid; gap: 12px;">
                        <div style="display: flex; gap: 12px; align-items: center;">
                            <label style="margin: 0; font-weight: 500;">Type:</label>
                            <label style="display: flex; align-items: center; gap: 6px; margin: 0;">
                                <input type="radio" name="auth-api-type" value="header" checked> Header
                            </label>
                            <label style="display: flex; align-items: center; gap: 6px; margin: 0;">
                                <input type="radio" name="auth-api-type" value="query"> Query Parameter
                            </label>
                        </div>
                        <input type="password" id="auth-api-key" placeholder="API Key" required style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="text" id="auth-header-name" placeholder="Header Name" value="X-API-Key" style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                    </div>
                `;

            case 'token':
                return `
                    <h4 style="margin: 0 0 16px 0; color: #1f2937; font-size: 16px;">🎫 Bearer Token Authentication</h4>
                    <div style="display: grid; gap: 12px;">
                        <textarea id="auth-token" placeholder="Enter your bearer token..." required style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                            min-height: 80px; resize: vertical; font-family: monospace;
                        "></textarea>
                        <p style="margin: 0; color: #6b7280; font-size: 12px;">
                            💡 Bearer tokens are typically JWT tokens or long-lived access tokens
                        </p>
                    </div>
                `;

            case 'azure_ad':
                return `
                    <h4 style="margin: 0 0 16px 0; color: #1f2937; font-size: 16px;">☁️ Azure Active Directory</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                        <input type="text" id="auth-tenant-id" placeholder="Tenant ID" required style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="text" id="auth-client-id" placeholder="Client ID" required style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="password" id="auth-client-secret" placeholder="Client Secret" required style="
                            grid-column: 1 / -1; padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="text" id="auth-resource" placeholder="Resource (optional)" style="
                            grid-column: 1 / -1; padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                    </div>
                `;

            case 'slack_oauth':
                return `
                    <h4 style="margin: 0 0 16px 0; color: #1f2937; font-size: 16px;">💬 Slack OAuth</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                        <input type="text" id="auth-workspace-url" placeholder="Workspace URL" required style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="password" id="auth-bot-token" placeholder="Bot Token (xoxb-...)" required style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="password" id="auth-app-token" placeholder="App Token (xapp-...)" style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="password" id="auth-signing-secret" placeholder="Signing Secret" style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                    </div>
                `;

            case 'google_oauth':
                return `
                    <h4 style="margin: 0 0 16px 0; color: #1f2937; font-size: 16px;">🔍 Google OAuth 2.0</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                        <input type="text" id="auth-google-client" placeholder="Client ID" required style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="password" id="auth-google-secret" placeholder="Client Secret" required style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="text" id="auth-google-scope" placeholder="Scopes (comma separated)" value="profile,email" style="
                            grid-column: 1 / -1; padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                    </div>
                `;

            case 'github_oauth':
                return `
                    <h4 style="margin: 0 0 16px 0; color: #1f2937; font-size: 16px;">🐙 GitHub OAuth</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                        <input type="text" id="auth-github-client" placeholder="Client ID" required style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="password" id="auth-github-secret" placeholder="Client Secret" required style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                        <input type="text" id="auth-github-scope" placeholder="Scopes (comma separated)" value="repo,user" style="
                            grid-column: 1 / -1; padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                    </div>
                `;

            case 'custom':
                return `
                    <h4 style="margin: 0 0 16px 0; color: #1f2937; font-size: 16px;">⚙️ Custom Authentication</h4>
                    <div style="display: grid; gap: 12px;">
                        <select id="auth-custom-type" style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                        ">
                            <option value="headers">Custom Headers</option>
                            <option value="params">Custom Parameters</option>
                            <option value="certificate">Certificate</option>
                            <option value="saml">SAML</option>
                            <option value="ldap">LDAP</option>
                        </select>
                        <textarea id="auth-custom-data" placeholder='{"Authorization": "Bearer token", "X-Custom": "value"}' style="
                            padding: 10px 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px;
                            min-height: 80px; resize: vertical; font-family: monospace;
                        "></textarea>
                    </div>
                `;

            default:
                return this.generateAuthFields('basic');
        }
    }
    
    setupAuthModalEventListeners(serverName, authType) {
        const modal = document.getElementById('auth-modal');
        const loginBtn = document.getElementById('auth-login-btn');
        const cancelBtn = document.getElementById('auth-cancel-btn');
        const testBtn = document.getElementById('auth-test-btn');
        const methodSelect = document.getElementById('auth-method-select');
        
        // Auth method selector
        methodSelect.addEventListener('change', (e) => {
            const selectedMethod = e.target.value;
            const fieldsContainer = document.getElementById('auth-fields-container');
            fieldsContainer.innerHTML = this.generateAuthFields(selectedMethod);
        });

        // Test button
        testBtn.addEventListener('click', async () => {
            await this.handleAuthTest(serverName, authType);
        });
        
        loginBtn.addEventListener('click', async () => {
            await this.handleAuthentication(serverName, authType);
        });
        
        cancelBtn.addEventListener('click', () => {
            modal.remove();
        });
        
        // Close modal when clicking outside
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
            }
        });

        // Handle API key type radio buttons
        document.addEventListener('change', (e) => {
            if (e.target.name === 'auth-api-type') {
                const headerField = document.getElementById('auth-header-name');
                if (headerField) {
                    if (e.target.value === 'header') {
                        headerField.placeholder = 'Header Name';
                        headerField.value = 'X-API-Key';
                    } else {
                        headerField.placeholder = 'Parameter Name';
                        headerField.value = 'api_key';
                    }
                }
            }
        });
    }
    
    async handleAuthTest(serverName, authType) {
        try {
            const credentials = this.getAuthCredentials();
            
            // Show loading state
            const testBtn = document.getElementById('auth-test-btn');
            const originalText = testBtn.textContent;
            testBtn.textContent = '🔄 Testing...';
            testBtn.disabled = true;
            
            // Send test request
            const response = await fetch(`${this.apiUrl}/api/auth/test`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    server: serverName,
                    session_id: this.sessionId,
                    credentials: credentials
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showTemporaryMessage('✅ Connection test successful!');
            } else {
                this.showTemporaryMessage(`❌ Test failed: ${result.error}`);
            }
            
        } catch (error) {
            console.error('Test error:', error);
            this.showTemporaryMessage('❌ Test failed: Network error');
        } finally {
            // Restore button
            const testBtn = document.getElementById('auth-test-btn');
            testBtn.textContent = '🧪 Test';
            testBtn.disabled = false;
        }
    }

    getAuthCredentials() {
        const credentials = {};
        const selectedMethod = document.getElementById('auth-method-select').value;
        
        switch (selectedMethod) {
            case 'basic':
                credentials.username = document.getElementById('auth-username')?.value || '';
                credentials.password = document.getElementById('auth-password')?.value || '';
                credentials.domain = document.getElementById('auth-domain')?.value || '';
                break;
                
            case 'oauth2':
                credentials.client_id = document.getElementById('auth-client-id')?.value || '';
                credentials.client_secret = document.getElementById('auth-client-secret')?.value || '';
                credentials.redirect_uri = document.getElementById('auth-redirect-uri')?.value || '';
                credentials.scope = document.getElementById('auth-scope')?.value || '';
                credentials.auth_url = document.getElementById('auth-auth-url')?.value || '';
                credentials.token_url = document.getElementById('auth-token-url')?.value || '';
                break;
                
            case 'api_key':
                credentials.api_key = document.getElementById('auth-api-key')?.value || '';
                credentials.header_name = document.getElementById('auth-header-name')?.value || '';
                const apiTypeRadio = document.querySelector('input[name="auth-api-type"]:checked');
                credentials.api_type = apiTypeRadio ? apiTypeRadio.value : 'header';
                break;
                
            case 'token':
                credentials.token = document.getElementById('auth-token')?.value || '';
                break;
                
            case 'azure_ad':
                credentials.tenant_id = document.getElementById('auth-tenant-id')?.value || '';
                credentials.client_id = document.getElementById('auth-client-id')?.value || '';
                credentials.client_secret = document.getElementById('auth-client-secret')?.value || '';
                credentials.resource = document.getElementById('auth-resource')?.value || '';
                break;
                
            case 'slack_oauth':
                credentials.workspace_url = document.getElementById('auth-workspace-url')?.value || '';
                credentials.bot_token = document.getElementById('auth-bot-token')?.value || '';
                credentials.app_token = document.getElementById('auth-app-token')?.value || '';
                credentials.signing_secret = document.getElementById('auth-signing-secret')?.value || '';
                break;
                
            case 'google_oauth':
                credentials.client_id = document.getElementById('auth-google-client')?.value || '';
                credentials.client_secret = document.getElementById('auth-google-secret')?.value || '';
                credentials.scope = document.getElementById('auth-google-scope')?.value || '';
                break;
                
            case 'github_oauth':
                credentials.client_id = document.getElementById('auth-github-client')?.value || '';
                credentials.client_secret = document.getElementById('auth-github-secret')?.value || '';
                credentials.scope = document.getElementById('auth-github-scope')?.value || '';
                break;
                
            case 'custom':
                credentials.custom_type = document.getElementById('auth-custom-type')?.value || '';
                credentials.custom_data = document.getElementById('auth-custom-data')?.value || '';
                break;
                
            default:
                // Fallback to basic
                credentials.username = document.getElementById('auth-username')?.value || '';
                credentials.password = document.getElementById('auth-password')?.value || '';
                break;
        }
        
        // Add method type to credentials
        credentials.auth_method = selectedMethod;
        
        return credentials;
    }

    async handleAuthentication(serverName, authType) {
        try {
            const credentials = this.getAuthCredentials();
            
            // Send authentication request
            const response = await fetch(`${this.apiUrl}/api/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    server: serverName,
                    session_id: this.sessionId,
                    credentials: credentials
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                // Close modal
                document.getElementById('auth-modal').remove();
                
                // Refresh server list to show authentication status
                await this.loadAvailableServers();
                
                // Update inline authentication status
                this.showAuthSection(serverName, true);
                
                // Show success message
                this.showTemporaryMessage(`✅ Successfully authenticated to ${serverName}`);
            } else {
                alert(`❌ Authentication failed: ${result.error}`);
            }
            
        } catch (error) {
            console.error('Authentication error:', error);
            alert('❌ Authentication failed: Network error');
        }
    }
}

// Initialize the popup when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.popup = new MCPExtensionPopup();
}); 