/**
 * DocuTrust — Frontend Application Logic
 * Handles PDF upload, SSE streaming, agent pipeline visualization, answer rendering,
 * client profiles, document outlines, and search history logs.
 */

(() => {
    'use strict';

    // ══════════════════════════════════════
    // Configuration
    // ══════════════════════════════════════

    const API_BASE = window.location.origin || 'http://localhost:8000';
    const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

    // ══════════════════════════════════════
    // State
    // ══════════════════════════════════════

    const state = {
        documents: [],
        profiles: [],
        sessions: [],
        activeProfile: null,
        currentSession: null,
        isQuerying: false,
        pipelineSteps: [],
    };

    // ══════════════════════════════════════
    // DOM Elements
    // ══════════════════════════════════════

    const $  = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const els = {
        // Header & Profiles
        connectionBadge: $('#connection-badge'),
        btnClearAll: $('#btn-clear-all'),
        apiKeyWarning: $('#api-key-warning'),
        profileSelect: $('#profile-select'),
        btnAddProfile: $('#btn-add-profile'),

        // Profile Modal
        profileModal: $('#profile-modal'),
        btnCloseModal: $('#btn-close-modal'),
        btnCancelProfile: $('#btn-cancel-profile'),
        btnSaveProfile: $('#btn-save-profile'),
        inputProfileId: $('#input-profile-id'),
        inputProfileName: $('#input-profile-name'),
        selectProfileProvider: $('#select-profile-provider'),
        inputProfileModel: $('#input-profile-model'),
        inputProfileThreshold: $('#input-profile-threshold'),

        // Left pane
        dropZone: $('#drop-zone'),
        fileInput: $('#file-input'),
        uploadProgress: $('#upload-progress'),
        progressFill: $('.progress-ring-fill'),
        progressPercent: $('.progress-percent'),
        documentsList: $('#documents-list'),
        historyToggle: $('#history-toggle'),
        historyList: $('#history-list'),
        queryInput: $('#query-input'),
        btnQuery: $('#btn-query'),

        // Center pane
        pipelineStatus: $('#pipeline-status'),
        agentLog: $('#agent-log'),
        agentEmpty: $('#agent-empty'),
        pipelineSteps: $('#pipeline-steps'),
        pipelineFlow: $('#pipeline-flow'),

        // Right pane
        answerEmpty: $('#answer-empty'),
        answerContent: $('#answer-content'),
        gaugeFill: $('#gauge-fill'),
        confidenceValue: $('#confidence-value'),
        confidenceDesc: $('#confidence-desc'),
        webSearchBadge: $('#web-search-badge'),
        answerText: $('#answer-text'),
        citationsList: $('#citations-list'),

        // Toast
        toastContainer: $('#toast-container'),
    };

    // ══════════════════════════════════════
    // Toast Notifications
    // ══════════════════════════════════════

    function showToast(message, type = 'info', duration = 4000) {
        const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || icons.info}</span>
            <span>${message}</span>
        `;
        els.toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('exiting');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    // ══════════════════════════════════════
    // File Upload
    // ══════════════════════════════════════

    function initDropZone() {
        const dz = els.dropZone;

        // Click to browse
        dz.addEventListener('click', (e) => {
            if (!e.target.closest('.upload-progress')) {
                els.fileInput.click();
            }
        });

        // File input change
        els.fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files);
            els.fileInput.value = '';
        });

        // Drag events
        ['dragenter', 'dragover'].forEach(evt => {
            dz.addEventListener(evt, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dz.classList.add('drag-over');
            });
        });

        ['dragleave', 'drop'].forEach(evt => {
            dz.addEventListener(evt, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dz.classList.remove('drag-over');
            });
        });

        dz.addEventListener('drop', (e) => {
            handleFiles(e.dataTransfer.files);
        });
    }

    async function handleFiles(fileList) {
        const files = Array.from(fileList).filter(f => f.name.toLowerCase().endsWith('.pdf'));

        if (files.length === 0) {
            showToast('Please select PDF files only.', 'warning');
            return;
        }

        for (const file of files) {
            await uploadFile(file);
        }
    }

    async function uploadFile(file) {
        if (file.size > MAX_FILE_SIZE) {
            showToast(`"${file.name}" exceeds 50MB limit.`, 'error');
            return;
        }

        // Show progress
        els.uploadProgress.classList.remove('hidden');
        setUploadProgress(0);

        const formData = new FormData();
        formData.append('file', file);

        try {
            // Simulate progress during upload
            const progressInterval = setInterval(() => {
                const current = parseInt(els.progressPercent.textContent);
                if (current < 85) {
                    setUploadProgress(current + Math.random() * 15);
                }
            }, 300);

            const response = await fetch(`${API_BASE}/api/upload`, {
                method: 'POST',
                body: formData,
            });

            clearInterval(progressInterval);

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.detail || 'Upload failed');
            }

            setUploadProgress(100);
            const data = await response.json();

            // Add to state
            state.documents.push(data);
            renderDocumentsList();
            updateQueryButton();

            showToast(`"${data.filename}" processed: ${data.page_count} pages, ${data.chunk_count} chunks`, 'success');

            // Hide progress after brief delay
            setTimeout(() => {
                els.uploadProgress.classList.add('hidden');
            }, 600);

        } catch (err) {
            showToast(`Upload failed: ${err.message}`, 'error');
            els.uploadProgress.classList.add('hidden');
        }
    }

    function setUploadProgress(percent) {
        const p = Math.min(100, Math.round(percent));
        els.progressPercent.textContent = `${p}%`;
        // Circumference = 2 * π * 34 = 213.6
        const offset = 213.6 - (213.6 * p / 100);
        els.progressFill.style.strokeDashoffset = offset;
    }

    // ══════════════════════════════════════
    // Documents List & Outlines Accordion
    // ══════════════════════════════════════

    function renderDocumentsList() {
        if (state.documents.length === 0) {
            els.documentsList.innerHTML = '';
            return;
        }

        els.documentsList.innerHTML = state.documents.map((doc, i) => {
            const index = doc.structural_index || [];
            const hasOutline = index.length > 0;
            const outlineHtml = hasOutline
                ? `<div class="doc-outline-toggle" onclick="window._toggleOutline('${doc.document_id}')">
                     <span>Outline (${index.length} chapters)</span>
                     <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
                   </div>
                   <div id="outline-${doc.document_id}" class="doc-outline-list">
                     ${index.map(item => `
                       <div class="outline-item level-${item.level || 1}" onclick="window._searchOutline('${escapeHtml(item.title)}', ${item.page_number})">
                         <div class="outline-title-wrapper">
                           <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
                           <span>${escapeHtml(item.title)}</span>
                         </div>
                         <span class="outline-item-page">p. ${item.page_number}</span>
                       </div>
                     `).join('')}
                   </div>`
                : '';

            return `
                <div class="doc-item-container" style="animation-delay: ${i * 0.08}s">
                    <div class="doc-item" data-doc-id="${doc.document_id}">
                        <div class="doc-item-icon">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                <polyline points="14 2 14 8 20 8"/>
                            </svg>
                        </div>
                        <div class="doc-item-info">
                            <div class="doc-item-name" title="${doc.filename}">${doc.filename}</div>
                            <div class="doc-item-meta">${doc.page_count} pages • ${doc.chunk_count} chunks</div>
                        </div>
                        <div class="doc-item-status ${doc.status === 'processing' ? 'processing' : ''}"></div>
                        <button class="doc-item-delete" onclick="window._deleteDoc('${doc.document_id}')" title="Remove document">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                    </div>
                    ${outlineHtml}
                </div>
            `;
        }).join('');
    }

    window._toggleOutline = function(docId) {
        const toggle = document.querySelector(`[onclick="window._toggleOutline('${docId}')"]`);
        const list = document.getElementById(`outline-${docId}`);
        if (toggle && list) {
            toggle.classList.toggle('expanded');
            list.classList.toggle('expanded');
        }
    };

    window._searchOutline = function(title, pageNumber) {
        els.queryInput.value = `Find information about "${title}" (from page ${pageNumber})`;
        updateQueryButton();
        executeQuery();
    };

    window._deleteDoc = async function(docId) {
        try {
            await fetch(`${API_BASE}/api/documents/${docId}`, { method: 'DELETE' });
            state.documents = state.documents.filter(d => d.document_id !== docId);
            renderDocumentsList();
            updateQueryButton();
            showToast('Document removed.', 'info');
        } catch (err) {
            showToast('Failed to delete document.', 'error');
        }
    };

    // ══════════════════════════════════════
    // Client Profiles Switcher & Modal
    // ══════════════════════════════════════

    async function loadProfiles() {
        try {
            const res = await fetch(`${API_BASE}/api/profiles`);
            if (res.ok) {
                const data = await res.json();
                state.profiles = data.profiles || [];
                state.activeProfile = state.profiles.find(p => p.is_active) || state.profiles[0];
                
                // Populate dropdown
                els.profileSelect.innerHTML = state.profiles.map(p => `
                    <option value="${p.profile_id}" ${state.activeProfile && p.profile_id === state.activeProfile.profile_id ? 'selected' : ''}>
                        👤 ${p.name}
                    </option>
                `).join('');

                updateOfflineBadge();
            }
        } catch (e) {
            console.error('Failed to load profiles:', e);
        }
    }

    function updateOfflineBadge() {
        if (!state.activeProfile) return;
        const isMock = state.activeProfile.llm_provider === 'mock';
        if (isMock) {
            els.apiKeyWarning.classList.remove('hidden');
            els.apiKeyWarning.title = "Running in Local Offline Mode. Answers will be generated locally via extractive summaries.";
            els.apiKeyWarning.querySelector('span:last-child').textContent = "Local Extractive";
        } else {
            els.apiKeyWarning.classList.add('hidden');
        }
    }

    async function changeActiveProfile(profileId) {
        try {
            const res = await fetch(`${API_BASE}/api/profiles/${profileId}/activate`, {
                method: 'PUT'
            });
            if (res.ok) {
                showToast(`Switched active profile`, 'success');
                await loadProfiles();
            } else {
                throw new Error('Activation failed');
            }
        } catch (e) {
            showToast(`Failed to switch profile: ${e.message}`, 'error');
        }
    }

    function openProfileModal() {
        els.inputProfileId.value = '';
        els.inputProfileName.value = '';
        els.inputProfileModel.value = 'gemini-1.5-flash';
        els.inputProfileThreshold.value = '0.5';
        els.profileModal.classList.add('open');
    }

    function closeProfileModal() {
        els.profileModal.classList.remove('open');
    }

    async function saveProfile() {
        const id = els.inputProfileId.value.trim().toLowerCase().replace(/[^a-z0-9\-]/g, '');
        const name = els.inputProfileName.value.trim();
        const provider = els.selectProfileProvider.value;
        const model = els.inputProfileModel.value.trim();
        const threshold = parseFloat(els.inputProfileThreshold.value);

        if (!id || !name || !model) {
            showToast('Please fill out all fields.', 'warning');
            return;
        }

        try {
            const res = await fetch(`${API_BASE}/api/profiles`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    profile_id: id,
                    name,
                    llm_provider: provider,
                    llm_model: model,
                    relevance_threshold: threshold,
                    is_active: true
                })
            });

            if (res.ok) {
                showToast('Settings profile created successfully!', 'success');
                closeProfileModal();
                await loadProfiles();
            } else {
                const err = await res.json();
                throw new Error(err.detail || 'Creation failed');
            }
        } catch (e) {
            showToast(`Failed to save profile: ${e.message}`, 'error');
        }
    }

    // ══════════════════════════════════════
    // Session History Toggle & Restoration
    // ══════════════════════════════════════

    function toggleHistory() {
        const header = els.historyToggle;
        const list = els.historyList;
        header.classList.toggle('collapsed');
        list.classList.toggle('collapsed');
    }

    async function loadHistory() {
        try {
            const res = await fetch(`${API_BASE}/api/sessions`);
            if (res.ok) {
                const data = await res.json();
                state.sessions = data.sessions || [];
                renderHistoryList();
            }
        } catch (e) {
            console.log('Failed to load history:', e.message);
        }
    }

    function renderHistoryList() {
        if (state.sessions.length === 0) {
            els.historyList.innerHTML = '<p style="color:var(--text-muted);font-size:0.68rem;padding:12px;text-align:center;">No recent sessions.</p>';
            return;
        }

        els.historyList.innerHTML = state.sessions.map((sess, i) => {
            const date = new Date(sess.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            return `
                <div class="history-item" onclick="window._loadPastSession('${sess.session_id}')" style="animation-delay: ${i * 0.05}s">
                    <div class="history-query" title="${escapeHtml(sess.query)}">${escapeHtml(sess.query)}</div>
                    <div class="history-date">Session: ${sess.session_id} • ${date}</div>
                </div>
            `;
        }).join('');
    }

    window._loadPastSession = async function(sessionId) {
        showToast(`Loading session logs: ${sessionId}...`, 'info');
        setConnectionStatus('processing');
        setPipelineStatus('running');
        clearAgentLog();
        clearAnswer();
        els.pipelineFlow.classList.remove('hidden');

        try {
            const resTrace = await fetch(`${API_BASE}/api/sessions/${sessionId}/trace`);
            if (!resTrace.ok) throw new Error('Trace not found');
            const dataTrace = await resTrace.json();
            const traceSteps = dataTrace.trace || [];

            const nodeInfo = {
                "Retrieve": {"label": "Vector Retrieval", "icon": "🔍", "description": "Searching document vectors..."},
                "Grade Documents": {"label": "Document Grading", "icon": "📊", "description": "Evaluating relevance with CrossEncoder..."},
                "Rewrite Query": {"label": "Query Rewriter", "icon": "✏️", "description": "Reformulating query for better results..."},
                "Web Search": {"label": "Web Search Fallback", "icon": "🌐", "description": "Searching the web for supplementary info..."},
                "Generate": {"label": "Answer Generation", "icon": "🤖", "description": "Generating validated response with citations..."},
            };

            // Replay steps dynamically
            for (const step of traceSteps) {
                const nodeNameNormalized = step.step_name.replace(/ /g, "_").toLowerCase();
                const info = nodeInfo[step.step_name] || {"label": step.step_name, "icon": "⚙️", "description": ""};
                
                // Live visual representation
                addPipelineStep({
                    node: nodeNameNormalized,
                    label: info["label"],
                    icon: info["icon"],
                    description: info["description"]
                }, 'running');
                updateFlowNode(nodeNameNormalized, 'active');

                await new Promise(r => setTimeout(r, 150));

                completePipelineStep({
                    node: nodeNameNormalized,
                    trace: step
                });
                updateFlowNode(nodeNameNormalized, 'completed');
            }

            const sessionObj = state.sessions.find(s => s.session_id === sessionId);
            if (sessionObj) {
                els.queryInput.value = sessionObj.query;
                updateQueryButton();
                
                if (sessionObj.final_response) {
                    renderAnswer(sessionObj.final_response);
                } else {
                    const genStep = traceSteps.find(s => s.step_name === "Generate");
                    renderAnswer({
                        answer: genStep?.data?.answer || "No response recorded.",
                        citations: genStep?.data?.citations || [],
                        confidence_score: genStep?.data?.confidence || 0.5,
                        web_search_triggered: false
                    });
                }
            }

            setPipelineStatus('completed');
            setConnectionStatus('ready');
            showToast('Logs loaded successfully', 'success');

        } catch (e) {
            console.error(e);
            showToast('Failed to load past trace: ' + e.message, 'error');
            setPipelineStatus('error');
            setConnectionStatus('error');
        }
    };

    // ══════════════════════════════════════
    // Query Execution (SSE)
    // ══════════════════════════════════════

    function updateQueryButton() {
        const hasQuery = els.queryInput.value.trim().length > 0;
        const hasDocs = state.documents.length > 0;
        els.btnQuery.disabled = !hasQuery || !hasDocs || state.isQuerying;
    }

    async function executeQuery() {
        const query = els.queryInput.value.trim();
        if (!query || state.isQuerying) return;

        state.isQuerying = true;
        state.pipelineSteps = [];

        // UI updates
        els.btnQuery.classList.add('loading');
        updateQueryButton();
        setConnectionStatus('processing');
        setPipelineStatus('running');
        clearAgentLog();
        clearAnswer();

        // Show pipeline flow
        els.pipelineFlow.classList.remove('hidden');

        const body = JSON.stringify({
            query,
            document_ids: state.documents.map(d => d.document_id),
        });

        try {
            const response = await fetch(`${API_BASE}/api/query`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body,
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            // Parse SSE stream
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                let eventType = '';
                let eventData = '';

                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        eventType = line.slice(7).trim();
                    } else if (line.startsWith('data: ')) {
                        eventData = line.slice(6);
                        if (eventType && eventData) {
                            try {
                                const data = JSON.parse(eventData);
                                handleSSEEvent(eventType, data);
                            } catch (e) {
                                console.warn('Failed to parse SSE event:', e);
                            }
                        }
                        eventType = '';
                        eventData = '';
                    }
                }
            }

        } catch (err) {
            showToast(`Query failed: ${err.message}`, 'error');
            setPipelineStatus('error');
            setConnectionStatus('error');
        } finally {
            state.isQuerying = false;
            els.btnQuery.classList.remove('loading');
            updateQueryButton();
            // Refresh history log list
            await loadHistory();
        }
    }

    function handleSSEEvent(type, data) {
        switch (type) {
            case 'session':
                state.currentSession = data.session_id;
                break;

            case 'step_start':
                addPipelineStep(data, 'running');
                updateFlowNode(data.node, 'active');
                break;

            case 'step_complete':
                completePipelineStep(data);
                updateFlowNode(data.node, 'completed');
                break;

            case 'answer':
                renderAnswer(data);
                setPipelineStatus('completed');
                setConnectionStatus('ready');
                break;

            case 'error':
                showToast(data.message || 'Pipeline error', 'error');
                setPipelineStatus('error');
                setConnectionStatus('error');
                break;

            case 'done':
                if (data.status === 'error') {
                    setPipelineStatus('error');
                }
                break;
        }
    }

    // ══════════════════════════════════════
    // Agent Pipeline Visualization
    // ══════════════════════════════════════

    function clearAgentLog() {
        els.pipelineSteps.innerHTML = '';
        els.agentEmpty.style.display = 'none';

        // Reset flow nodes
        document.querySelectorAll('.flow-node').forEach(n => {
            n.classList.remove('active', 'completed');
        });
        document.querySelectorAll('.flow-connector').forEach(c => {
            c.classList.remove('active');
        });
    }

    function addPipelineStep(data, status) {
        const stepId = `step-${data.node}`;
        const existing = document.getElementById(stepId);
        if (existing) existing.remove();

        const step = document.createElement('div');
        step.id = stepId;
        step.className = `step-card active`;
        step.style.animationDelay = `${state.pipelineSteps.length * 0.05}s`;

        step.innerHTML = `
            <div class="step-header" onclick="this.parentElement.classList.toggle('expanded')">
                <div class="step-icon">${data.icon || '⚙️'}</div>
                <div class="step-info">
                    <div class="step-label">${data.label || data.node}</div>
                    <div class="step-description">${data.description || 'Processing...'}</div>
                </div>
                <div class="step-status-indicator">
                    <div class="step-spinner"></div>
                </div>
            </div>
            <div class="step-detail">
                <div class="step-detail-content">Waiting for results...</div>
            </div>
        `;

        els.pipelineSteps.appendChild(step);
        state.pipelineSteps.push(data.node);

        // Scroll into view
        step.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function completePipelineStep(data) {
        const stepId = `step-${data.node}`;
        const step = document.getElementById(stepId);
        if (!step) return;

        step.classList.remove('active');
        step.classList.add('completed');

        // Update status indicator
        const indicator = step.querySelector('.step-status-indicator');
        indicator.innerHTML = `
            <div class="step-check">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="20 6 9 17 4 12"/>
                </svg>
            </div>
        `;

        // Update description with trace info
        const desc = step.querySelector('.step-description');
        if (data.trace && data.trace.detail) {
            desc.textContent = data.trace.detail;
        }

        // Populate detail panel
        const detailContent = step.querySelector('.step-detail-content');
        if (data.trace && data.trace.data) {
            detailContent.innerHTML = formatTraceData(data.trace.data);
        }
    }

    function formatTraceData(data) {
        if (!data || typeof data !== 'object') return '<span class="value">No data</span>';

        const lines = [];
        for (const [key, value] of Object.entries(data)) {
            const formattedKey = `<span class="key">${key}</span>`;

            if (typeof value === 'number') {
                lines.push(`${formattedKey}: <span class="number">${value}</span>`);
            } else if (typeof value === 'string') {
                const truncated = value.length > 120 ? value.slice(0, 120) + '…' : value;
                lines.push(`${formattedKey}: <span class="value">"${escapeHtml(truncated)}"</span>`);
            } else if (Array.isArray(value)) {
                if (value.length > 0 && typeof value[0] === 'object') {
                    lines.push(`${formattedKey}: [${value.length} items]`);
                    value.slice(0, 4).forEach(item => {
                        const itemStr = Object.entries(item)
                            .map(([k, v]) => `<span class="key">${k}</span>: <span class="number">${typeof v === 'number' ? v : `"${v}"`}</span>`)
                            .join(', ');
                        lines.push(`  • {${itemStr}}`);
                    });
                } else {
                    lines.push(`${formattedKey}: <span class="value">[${value.join(', ')}]</span>`);
                }
            } else {
                lines.push(`${formattedKey}: <span class="value">${JSON.stringify(value)}</span>`);
            }
        }
        return lines.join('\n');
    }

    function updateFlowNode(nodeName, status) {
        const node = document.querySelector(`.flow-node[data-node="${nodeName}"]`);
        if (node) {
            node.classList.remove('active', 'completed');
            node.classList.add(status);
        }
    }

    // ══════════════════════════════════════
    // Answer Rendering
    // ══════════════════════════════════════

    function clearAnswer() {
        els.answerEmpty.style.display = 'flex';
        els.answerContent.classList.add('hidden');
        els.answerText.innerHTML = '';
        els.citationsList.innerHTML = '';
        els.webSearchBadge.classList.add('hidden');
    }

    function renderAnswer(data) {
        els.answerEmpty.style.display = 'none';
        els.answerContent.classList.remove('hidden');

        // Confidence gauge
        const confidence = Math.round((data.confidence_score || 0) * 100);
        animateGauge(confidence);

        // Web search badge
        if (data.web_search_triggered) {
            els.webSearchBadge.classList.remove('hidden');
        }

        // Answer text with citation highlighting
        let answerHtml = formatAnswerText(data.answer || '', data.citations || []);
        els.answerText.innerHTML = answerHtml;

        // Citations
        renderCitations(data.citations || []);
    }

    function animateGauge(percent) {
        const circumference = 2 * Math.PI * 50; // r=50
        const offset = circumference - (circumference * percent / 100);

        const gaugeFill = els.gaugeFill;
        gaugeFill.classList.remove('medium', 'low');

        if (percent < 40) {
            gaugeFill.classList.add('low');
            els.confidenceDesc.textContent = 'Low confidence — review sources carefully';
        } else if (percent < 70) {
            gaugeFill.classList.add('medium');
            els.confidenceDesc.textContent = 'Moderate confidence — partially sourced';
        } else {
            els.confidenceDesc.textContent = 'High confidence — well-sourced answer';
        }

        // Animate
        requestAnimationFrame(() => {
            gaugeFill.style.strokeDashoffset = offset;
        });

        // Animate counter
        let current = 0;
        const step = percent / 30;
        const counter = setInterval(() => {
            current += step;
            if (current >= percent) {
                current = percent;
                clearInterval(counter);
            }
            els.confidenceValue.textContent = Math.round(current);
        }, 30);
    }

    function formatAnswerText(text, citations) {
        // Convert line breaks to paragraphs
        let html = text
            .split(/\n\n+/)
            .filter(p => p.trim())
            .map(p => `<p>${escapeHtml(p.trim())}</p>`)
            .join('');

        // Highlight [Source N] references
        html = html.replace(/\[Source\s*(\d+)\]/gi, (match, num) => {
            return `<a class="citation-ref" href="#citation-${num}" onclick="window._scrollToCitation(${num})">[${num}]</a>`;
        });

        return html;
    }

    window._scrollToCitation = function(num) {
        const card = document.querySelector(`#citation-${num}`);
        if (card) {
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
            card.style.transition = 'box-shadow 0.3s';
            card.style.boxShadow = '0 0 0 2px var(--accent-blue), 0 0 16px rgba(59, 130, 246, 0.2)';
            setTimeout(() => {
                card.style.boxShadow = '';
            }, 2000);
        }
    };

    function renderCitations(citations) {
        if (!citations.length) {
            els.citationsList.innerHTML = '<p style="color:var(--text-muted);font-size:0.75rem;">No citations available.</p>';
            return;
        }

        els.citationsList.innerHTML = citations.map((c, i) => {
            const scoreClass = c.relevance_score >= 0.7 ? 'high' : c.relevance_score >= 0.4 ? 'medium' : 'low';
            const isWeb = c.source_type === 'web';

            return `
                <div class="citation-card ${isWeb ? 'web-source' : ''}" id="citation-${c.source_id || i + 1}" style="animation-delay: ${i * 0.08}s">
                    <div class="citation-number">${c.source_id || i + 1}</div>
                    <div class="citation-body">
                        <div class="citation-meta">
                            <span class="citation-source">${escapeHtml(isWeb ? (c.source_document || 'Web Result') : (c.source_document || 'Document'))}</span>
                            ${!isWeb && c.page_number ? `<span class="citation-page">Page ${c.page_number}</span>` : ''}
                            <span class="citation-score ${scoreClass}">${(c.relevance_score * 100).toFixed(0)}%</span>
                        </div>
                        <div class="citation-text">${escapeHtml(c.chunk_text || '')}</div>
                        ${c.url ? `<a href="${escapeHtml(c.url)}" target="_blank" rel="noopener" class="citation-url">${escapeHtml(c.url)}</a>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }

    // ══════════════════════════════════════
    // Status Helpers
    // ══════════════════════════════════════

    function setConnectionStatus(status) {
        const badge = els.connectionBadge;
        badge.classList.remove('processing', 'error');
        const textEl = badge.querySelector('.status-text');

        switch (status) {
            case 'processing':
                badge.classList.add('processing');
                textEl.textContent = 'Processing';
                break;
            case 'error':
                badge.classList.add('error');
                textEl.textContent = 'Error';
                break;
            default:
                textEl.textContent = 'Ready';
        }
    }

    function setPipelineStatus(status) {
        const badge = els.pipelineStatus;
        badge.classList.remove('running', 'completed', 'error');
        const span = badge.querySelector('span');

        switch (status) {
            case 'running':
                badge.classList.add('running');
                span.textContent = 'Running';
                break;
            case 'completed':
                badge.classList.add('completed');
                span.textContent = 'Complete';
                break;
            case 'error':
                badge.classList.add('error');
                span.textContent = 'Error';
                break;
            default:
                span.textContent = 'Idle';
        }
    }

    // ══════════════════════════════════════
    // Utilities
    // ══════════════════════════════════════

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ══════════════════════════════════════
    // Reset / Clear
    // ══════════════════════════════════════

    function resetAll() {
        state.documents = [];
        state.currentSession = null;
        state.isQuerying = false;
        state.pipelineSteps = [];

        renderDocumentsList();
        els.queryInput.value = '';
        updateQueryButton();
        setConnectionStatus('ready');
        setPipelineStatus('idle');

        // Center pane
        els.pipelineSteps.innerHTML = '';
        els.agentEmpty.style.display = 'flex';
        els.pipelineFlow.classList.add('hidden');

        // Right pane
        clearAnswer();

        showToast('Session cleared.', 'info');
    }

    // ══════════════════════════════════════
    // Load existing documents
    // ══════════════════════════════════════

    async function loadExistingDocuments() {
        try {
            const res = await fetch(`${API_BASE}/api/documents`);
            if (res.ok) {
                const data = await res.json();
                state.documents = (data.documents || []).map(d => ({
                    document_id: d.document_id,
                    filename: d.filename,
                    page_count: d.page_count,
                    chunk_count: d.chunk_count,
                    status: d.status,
                    structural_index: d.structural_index || [],
                }));
                renderDocumentsList();
                updateQueryButton();
            }
        } catch (e) {
            console.log('Backend not reachable:', e.message);
        }
    }

    // ══════════════════════════════════════
    // Initialize
    // ══════════════════════════════════════

    function init() {
        // Drop zone
        initDropZone();

        // Query input
        els.queryInput.addEventListener('input', updateQueryButton);
        els.queryInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (!els.btnQuery.disabled) executeQuery();
            }
        });

        // Query button
        els.btnQuery.addEventListener('click', executeQuery);

        // Clear all
        els.btnClearAll.addEventListener('click', resetAll);

        // Profile select
        els.profileSelect.addEventListener('change', (e) => {
            changeActiveProfile(e.target.value);
        });

        // Profile modals
        els.btnAddProfile.addEventListener('click', openProfileModal);
        els.btnCloseModal.addEventListener('click', closeProfileModal);
        els.btnCancelProfile.addEventListener('click', closeProfileModal);
        els.btnSaveProfile.addEventListener('click', saveProfile);
        
        // Settings triggers
        els.selectProfileProvider.addEventListener('change', (e) => {
            const val = e.target.value;
            if (val === 'mock') {
                els.inputProfileModel.value = 'local-extractive';
            } else if (val === 'openai') {
                els.inputProfileModel.value = 'gpt-4o-mini';
            } else {
                els.inputProfileModel.value = 'gemini-1.5-flash';
            }
        });

        // History toggling
        els.historyToggle.addEventListener('click', toggleHistory);

        // Load configurations
        loadProfiles();
        loadExistingDocuments();
        loadHistory();

        console.log('🛡️ DocuTrust initialized');
    }

    // Boot
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
