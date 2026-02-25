// Claude Code Chat Browser — Main JS

function showToast(message, type = 'info') {
    const icons = { success: '\u2713', error: '\u2717', info: '\u2139' };
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span class="toast-text">${message}</span><button class="toast-close">\u00d7</button><div class="toast-progress"></div>`;
    document.body.appendChild(toast);
    toast.querySelector('.toast-close').addEventListener('click', () => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); });
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

function showConfirm(message, onConfirm) {
    const overlay = document.createElement('div');
    overlay.className = 'confirm-overlay';
    const dialog = document.createElement('div');
    dialog.className = 'confirm-dialog';
    dialog.innerHTML = `
        <div class="confirm-header">
            <span class="confirm-icon">?</span>
            <span class="confirm-title">Confirm Action</span>
        </div>
        <p class="confirm-message">${message}</p>
        <div class="confirm-actions">
            <button class="confirm-btn confirm-cancel">Cancel</button>
            <button class="confirm-btn confirm-ok">Confirm</button>
        </div>`;
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('show'));
    const close = () => { overlay.classList.remove('show'); setTimeout(() => overlay.remove(), 200); document.removeEventListener('keydown', onKey); };
    const onKey = (e) => { if (e.key === 'Escape') close(); if (e.key === 'Enter') { close(); onConfirm(); } };
    document.addEventListener('keydown', onKey);
    dialog.querySelector('.confirm-cancel').addEventListener('click', close);
    dialog.querySelector('.confirm-ok').addEventListener('click', () => { close(); onConfirm(); });
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
    dialog.querySelector('.confirm-ok').focus();
}

// Top loading bar
const _loadingBar = (() => {
    const bar = document.createElement('div');
    bar.className = 'loading-bar';
    document.documentElement.appendChild(bar);
    return {
        start() { bar.classList.remove('done'); bar.classList.add('active'); },
        done()  { bar.classList.remove('active'); bar.classList.add('done'); setTimeout(() => bar.classList.remove('done'), 400); }
    };
})();

// Smooth content swap — fades out old content, swaps HTML, fades in new content
function smoothSet(el, html) {
    el.classList.remove('content-ready');
    el.classList.add('content-enter');
    // Force reflow so the browser registers the starting state
    void el.offsetHeight;
    el.innerHTML = html;
    requestAnimationFrame(() => {
        el.classList.remove('content-enter');
        el.classList.add('content-ready');
    });
}

let currentProject = null;
let cachedSessions = [];
let projectDisplayNames = {};

document.addEventListener('DOMContentLoaded', () => {
    applyTheme(localStorage.getItem('theme') || 'dark');
    handleRoute();
    window.addEventListener('hashchange', handleRoute);

    // Mobile sidebar overlay
    const overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay';
    overlay.id = 'sidebar-overlay';
    overlay.addEventListener('click', closeSidebar);
    document.body.appendChild(overlay);

    // Scroll-to-top button
    const topBtn = document.createElement('button');
    topBtn.className = 'scroll-top-btn';
    topBtn.id = 'scroll-top-btn';
    topBtn.textContent = '\u2191';
    topBtn.addEventListener('click', () => {
        const panel = document.querySelector('.main-panel');
        if (panel && panel.scrollTop > 0) { panel.scrollTo({ top: 0, behavior: 'smooth' }); }
        else { window.scrollTo({ top: 0, behavior: 'smooth' }); }
    });
    document.body.appendChild(topBtn);

    const updateScrollBtn = () => {
        const panel = document.querySelector('.main-panel');
        const scrollY = Math.max(panel ? panel.scrollTop : 0, window.scrollY);
        topBtn.classList.toggle('show', scrollY > 400);
    };
    window.addEventListener('scroll', updateScrollBtn, true);
    window.addEventListener('scroll', updateScrollBtn);
});

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (!sidebar) return;
    sidebar.classList.toggle('open');
    if (overlay) overlay.classList.toggle('active', sidebar.classList.contains('open'));
}

function closeSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('active');
}

function setHamburgerVisible(visible) {
    const btn = document.getElementById('hamburger-btn');
    if (btn) btn.style.display = visible ? 'flex' : 'none';
}

function setWorkspaceMode(active) {
    document.body.classList.toggle('workspace-mode', active);
    const content = document.getElementById('content');
    if (content) {
        if (active) {
            content.classList.remove('container');
        } else {
            content.classList.add('container');
        }
    }
    // Switch highlight.js theme
    const hljsLink = document.getElementById('hljs-theme');
    if (hljsLink) {
        const theme = localStorage.getItem('theme') || 'dark';
        hljsLink.href = theme === 'dark'
            ? 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/vs2015.min.css'
            : 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css';
    }
}

let _navInProgress = false;

function handleRoute() {
    if (_navInProgress) return;
    const hash = window.location.hash || '#';
    if (hash.startsWith('#project/')) {
        const parts = hash.slice(9);
        const slashIdx = parts.indexOf('/');
        if (slashIdx > 0) {
            const project = decodeURIComponent(parts.slice(0, slashIdx));
            const sessionId = parts.slice(slashIdx + 1);
            // If same project already loaded, just switch session without rebuilding
            if (currentProject === project && cachedSessions.length > 0 && document.getElementById('sidebar')) {
                document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));
                const el = document.getElementById(`sidebar-${sessionId}`);
                if (el) { el.classList.add('active'); el.scrollIntoView({ block: 'nearest' }); }
                loadSession(project, sessionId);
            } else {
                showWorkspace(project, sessionId);
            }
        } else {
            showWorkspace(decodeURIComponent(parts));
        }
    } else if (hash === '#search') {
        showSearchPage();
    } else {
        showProjects();
    }
}

// ==================== Projects (home) ====================

async function showProjects() {
    currentProject = null;
    setHamburgerVisible(false);
    setWorkspaceMode(false);
    if (window.location.hash && window.location.hash !== '#') {
        _navInProgress = true;
        window.location.hash = '';
        setTimeout(() => { _navInProgress = false; }, 0);
    }
    const content = document.getElementById('content');
    content.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading projects...</p></div>';
    _loadingBar.start();

    try {
        const [projRes, stateRes] = await Promise.all([
            fetch('/api/projects'),
            fetch('/api/export/state').catch(() => null)
        ]);
        const projects = await projRes.json();
        _loadingBar.done();

        if (!projects.length) {
            smoothSet(content, '<div class="empty-state">No Claude Code projects found.<br>Make sure Claude Code has been used on this machine.</div>');
            return;
        }

        for (const p of projects) projectDisplayNames[p.name] = p.display_name || p.name;
        projects.sort((a, b) => (b.last_modified || '').localeCompare(a.last_modified || ''));

        // Page header with export controls
        let lastExportHtml = '';
        if (stateRes) {
            try {
                const state = await stateRes.json();
                if (state.last_export_time) {
                    const d = new Date(state.last_export_time);
                    if (!isNaN(d.getTime())) {
                        lastExportHtml = `<p class="text-muted text-sm" style="margin:0">Last export: ${d.toLocaleString()} (${state.export_count || 0} sessions)</p>`;
                    }
                }
            } catch(e) {}
        }

        let html = `<div class="page-header">
            <div>
                <h1>Projects</h1>
                <p class="text-muted">Browse your Claude Code conversations by project. Click on a project to view its sessions.</p>
            </div>
            <div style="display:flex;flex-direction:column;align-items:flex-end;gap:0.25rem">
                <div class="btn-group">
                    <button class="btn btn-outline btn-sm" id="btn-export-all" onclick="bulkExport()">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                        Export all
                    </button>
                </div>
                ${lastExportHtml}
            </div>
        </div>`;

        const withSessions = projects.filter(p => (p.session_count || 0) > 0);
        const noSessions   = projects.filter(p => (p.session_count || 0) === 0);

        if (withSessions.length) {
            html += `<div class="card">
                <div class="card-header">
                    <h2 class="card-title">Projects with Sessions</h2>
                    <p class="text-muted text-sm">${withSessions.length} project${withSessions.length !== 1 ? 's' : ''} with chat history</p>
                </div>
                <div class="card-body" style="padding:0">
                    <table class="table">
                        <thead><tr><th>Project</th><th>Sessions</th><th>Last Modified</th></tr></thead>
                        <tbody>`;
            for (const p of withSessions) {
                const displayName = p.display_name || p.name;
                const count = p.session_count || 0;
                html += `<tr>
                    <td><a href="#project/${encodeURIComponent(p.name)}" class="link">${esc(displayName)}</a></td>
                    <td><span class="text-success">${count} session${count !== 1 ? 's' : ''}</span></td>
                    <td>${esc(p.last_modified ? formatDate(p.last_modified) : '')}</td>
                </tr>`;
            }
            html += `</tbody></table></div></div>`;
        }

        if (noSessions.length) {
            html += `<div class="card" style="margin-top:1.5rem">
                <div class="card-header">
                    <h2 class="card-title">Projects without Sessions</h2>
                    <p class="text-muted text-sm">${noSessions.length} project${noSessions.length !== 1 ? 's' : ''} with no sessions found</p>
                </div>
                <div class="card-body">
                    <div class="alert alert-info">These projects may have no recorded sessions yet.</div>
                    <table class="table">
                        <thead><tr><th>Project</th><th>Sessions</th><th>Last Modified</th></tr></thead>
                        <tbody>`;
            for (const p of noSessions) {
                html += `<tr>
                    <td><span class="text-muted">${esc(p.display_name || p.name)}</span></td>
                    <td><span class="text-muted">0</span></td>
                    <td>${esc(p.last_modified ? formatDate(p.last_modified) : '')}</td>
                </tr>`;
            }
            html += `</tbody></table></div></div>`;
        }

        smoothSet(content, html);
    } catch (e) {
        _loadingBar.done();
        smoothSet(content, `<div class="loading"><p class="text-danger">Failed to load projects.</p></div>`);
    }
}

// ==================== Workspace (split layout) ====================

async function showWorkspace(projectName, selectedSessionId) {
    currentProject = projectName;
    setHamburgerVisible(true);
    setWorkspaceMode(true);
    const content = document.getElementById('content');
    content.innerHTML = '<div style="padding:2rem"><div class="loading"><div class="spinner"></div><p>Loading sessions...</p></div></div>';
    _loadingBar.start();

    try {
        // Ensure display name is cached
        if (!projectDisplayNames[projectName]) {
            const projRes = await fetch('/api/projects');
            const projects = await projRes.json();
            for (const p of projects) projectDisplayNames[p.name] = p.display_name || p.name;
        }
        const prettyName = projectDisplayNames[projectName] || projectName;

        const res = await fetch(`/api/projects/${encodeURIComponent(projectName)}/sessions`);
        cachedSessions = await res.json();

        // Sort by last_timestamp desc (most recently active first)
        cachedSessions.sort((a, b) => {
            const ta = a.last_timestamp || a.first_timestamp || '';
            const tb = b.last_timestamp || b.first_timestamp || '';
            return tb.localeCompare(ta);
        });

        // Group by last-active date
        const byDate = {};
        for (const s of cachedSessions) {
            const ts = s.last_timestamp || s.first_timestamp || '';
            const date = ts ? formatDate(ts) : 'Unknown';
            if (!byDate[date]) byDate[date] = [];
            byDate[date].push(s);
        }

        // Build sidebar
        let sidebar = `<div class="sidebar-header">
            <a class="btn btn-ghost btn-sm back-link" href="#" onclick="showProjects();return false;" style="padding:0.25rem 0;font-size:0.82rem">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
                Back to Projects
            </a>
        </div>`;
        sidebar += `<div class="sidebar-header" style="border-bottom:none;padding-bottom:0.25rem">Conversations <span class="text-sm text-muted" style="font-weight:400">(${cachedSessions.length})</span></div>`;
        sidebar += '<div class="sidebar-body">';

        const dates = Object.keys(byDate).sort().reverse();
        for (const date of dates) {
            sidebar += `<div class="date-label">${esc(date)}</div>`;
            for (const s of byDate[date]) {
                const title = s.title || s.id;
                const ts = formatDate(s.last_timestamp || s.first_timestamp || '');
                const models = (s.models || []).join(', ');
                const isActive = s.id === selectedSessionId ? ' active' : '';
                const errorClass = s.error ? ' sidebar-item-error' : '';
                const errorDetail = s.error_detail ? `<div class="error-detail">${esc(s.error_detail)}</div>` : '';
                const modelBadge = models ? `<span style="font-size:0.65rem;opacity:0.6;display:block;margin-top:1px">${esc(models)}</span>` : '';
                sidebar += `<button class="sidebar-item${isActive}${errorClass}" onclick="selectSession('${esc(projectName)}','${esc(s.id)}')" id="sidebar-${s.id}">
                    <div class="sidebar-item-title">${esc(title)}</div>
                    ${errorDetail}
                    <div class="sidebar-item-time">${esc(ts)}${modelBadge}</div>
                </button>`;
            }
        }
        sidebar += '</div>'; // close sidebar-body

        // Build layout
        let html = `<div class="workspace-layout">
            <div class="sidebar" id="sidebar">${sidebar}</div>
            <div class="main-panel" id="main-panel">`;

        // Project info
        html += `<div class="project-info">
            <h2>${esc(prettyName)}</h2>
            <p class="text-sm text-muted">${cachedSessions.length} session${cachedSessions.length !== 1 ? 's' : ''}</p>
        </div>`;

        html += '<div id="session-content"><div class="card" style="margin:1.5rem;padding:2rem;text-align:center"><p class="text-muted">No session selected</p></div></div></div></div>';
        smoothSet(content, html);
        _loadingBar.done();

        // Auto-select first session or specified session
        if (selectedSessionId) {
            loadSession(projectName, selectedSessionId);
        } else if (cachedSessions.length > 0) {
            selectSession(projectName, cachedSessions[0].id);
        }
    } catch (e) {
        _loadingBar.done();
        content.innerHTML = `<div class="loading">Error: ${esc(e.message)}</div>`;
    }
}

function selectSession(projectName, sessionId) {
    closeSidebar();
    // Just update the hash — handleRoute will do the rest
    window.location.hash = `#project/${encodeURIComponent(projectName)}/${sessionId}`;
}

async function loadSession(projectName, sessionId) {
    const container = document.getElementById('session-content');
    if (!container) return;
    _loadingBar.start();

    try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(projectName)}/${sessionId}`);
        if (!res.ok) {
            _loadingBar.done();
            const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
            container.innerHTML = `<div class="loading">Error loading session: ${esc(err.error || res.statusText)}</div>`;
            return;
        }
        const session = await res.json();
        if (session.error) {
            _loadingBar.done();
            container.innerHTML = `<div class="loading">Error: ${esc(session.error)}</div>`;
            return;
        }
        const meta = session.metadata;

        let html = '';

        // Panel header
        const modelsList = (meta.models_used || []).filter(m => m !== '<synthetic>');
        const totalTokens = (meta.total_input_tokens + meta.total_output_tokens).toLocaleString();
        const msgCount = session.messages.filter(m => m.role === 'user' && m.text && m.text.trim()).length;

        // Subtitle: timestamps + message count
        let subtitleParts = [];
        if (meta.first_timestamp) subtitleParts.push(formatTs(meta.first_timestamp));
        if (meta.last_timestamp && meta.last_timestamp !== meta.first_timestamp) subtitleParts.push(formatTs(meta.last_timestamp));
        const timeRange = subtitleParts.length === 2
            ? `${subtitleParts[0]} &rarr; ${subtitleParts[1]}`
            : subtitleParts[0] || '';

        let badges = '';
        if (modelsList.length === 0) badges += `<span class="stat-badge badge-model">N/A</span>`;
        else modelsList.forEach(m => { badges += `<span class="stat-badge badge-model">${esc(m)}</span>`; });
        badges += `<span class="stat-badge badge-tokens">${totalTokens} tokens</span>`;
        badges += `<span class="stat-badge badge-tools">${meta.total_tool_calls} tool calls</span>`;
        if (meta.compactions > 0) badges += `<span class="stat-badge badge-compact">${meta.compactions} compaction${meta.compactions > 1 ? 's' : ''}</span>`;
        if (meta.cwd) badges += `<span class="stat-badge badge-dir" title="${esc(meta.cwd)}">${esc(meta.cwd)}</span>`;
        if (meta.git_branch) badges += `<span class="stat-badge badge-branch">${esc(meta.git_branch)}</span>`;
        if (meta.version) badges += `<span class="stat-badge badge-version">v${esc(meta.version)}</span>`;
        if (meta.permission_mode) badges += `<span class="stat-badge badge-perm">${esc(meta.permission_mode)}</span>`;

        html += `<div class="panel-header">
            <div class="panel-header-left">
                <h2 class="panel-title">${esc(session.title)}</h2>
                <div class="panel-subtitle">
                    <span class="panel-time">${timeRange}</span>
                    <span class="panel-msg-count">${msgCount} message${msgCount !== 1 ? 's' : ''}</span>
                </div>
                <div class="stat-badges">${badges}</div>
            </div>
            <div class="btn-group">
                <button class="btn btn-outline btn-sm" onclick="copyAll()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                    Copy All
                </button>
                <button class="btn btn-outline btn-sm" onclick="downloadSession('${esc(projectName)}','${sessionId}')">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    Download
                </button>
            </div>
        </div>`;

        // Messages (chronological: old to new)
        html += '<div class="chat-bubbles">';
        for (const msg of session.messages) {
            if (msg.role === 'user') html += renderUser(msg);
            else if (msg.role === 'assistant') html += renderAssistant(msg);
            else if (msg.role === 'system') html += renderSystem(msg);
        }
        html += '</div>';

        smoothSet(container, html);
        _loadingBar.done();

        // Syntax-highlight code blocks
        container.querySelectorAll('pre code').forEach(block => {
            if (typeof hljs !== 'undefined') hljs.highlightElement(block);
        });
    } catch (e) {
        _loadingBar.done();
        container.innerHTML = `<div class="chat-bubbles"><div class="bubble bubble-system">Error: ${esc(e.message)}</div></div>`;
    }
}

// ==================== Message renderers ====================

function renderUser(msg) {
    const hasText = msg.text && msg.text.trim();
    const hasImages = msg.images && msg.images.length > 0;
    const hasToolResult = msg.tool_result_parsed;

    if (!hasText && !hasImages && !hasToolResult) return '';

    if (hasToolResult && !hasText && !hasImages) {
        if (_toolResultHasBody(msg.tool_result_parsed)) return renderToolResult(msg.tool_result_parsed);
        return '';
    }

    let html = `<div class="bubble bubble-user">`;
    html += `<div class="bubble-header"><span class="badge">You</span><span class="text-sm text-muted">${msg.timestamp ? formatDate(msg.timestamp) : ''}</span></div>`;
    if (hasImages) {
        for (const img of msg.images) {
            html += `<div class="msg-image"><img src="data:${esc(img.media_type)};base64,${img.data}" alt="User image" loading="lazy"></div>`;
        }
    }
    if (hasText) html += `<div class="bubble-text prose">${renderMarkdown(cleanContent(msg.text))}</div>`;
    if (hasToolResult) html += renderToolResult(msg.tool_result_parsed);
    html += '</div>';
    return html;
}

function renderAssistant(msg) {
    const hasText = msg.text && msg.text.trim();
    const hasThinking = msg.thinking && msg.thinking.trim();
    const hasTools = msg.tool_uses && msg.tool_uses.length > 0;
    if (!hasText && !hasThinking && !hasTools) return '';

    let html = `<div class="bubble bubble-ai">`;
    html += `<div class="bubble-header"><span class="badge badge-secondary">AI</span><span class="text-sm text-muted">${msg.timestamp ? formatDate(msg.timestamp) : ''}</span></div>`;

    // Per-message metadata
    let metaParts = [];
    if (msg.model && msg.model !== '<synthetic>') metaParts.push(esc(msg.model));
    if (msg.usage && msg.usage.output_tokens) metaParts.push(`${msg.usage.output_tokens.toLocaleString()} tokens`);
    if (metaParts.length) html += `<div class="bubble-meta">${metaParts.join(' &bull; ')}</div>`;

    if (hasThinking) {
        html += `<details class="thinking-block"><summary>Thinking</summary><div class="thinking-content">${esc(msg.thinking)}</div></details>`;
    }
    if (hasText) html += `<div class="bubble-text prose">${renderMarkdown(cleanContent(msg.text))}</div>`;
    if (hasTools) {
        for (const tool of msg.tool_uses) html += renderToolUse(tool);
    }
    html += '</div>';
    return html;
}

function renderSystem(msg) {
    if (msg.subtype === 'compact_boundary') {
        return '<div class="bubble bubble-system"><em>--- Context compacted ---</em></div>';
    }
    if (msg.content) {
        return `<div class="bubble bubble-system">${esc(msg.content)}</div>`;
    }
    return '';
}

function getToolSummary(name, inp) {
    if (name === 'Bash') return `Bash: ${truncate(inp.command || '', 80)}`;
    if (name === 'Read') return `Read: ${esc(inp.file_path || '')}`;
    if (name === 'Write') return `Write: ${esc(inp.file_path || '')}`;
    if (name === 'Edit') return `Edit: ${esc(inp.file_path || '')}`;
    if (name === 'Glob') return `Glob: ${esc(inp.pattern || '')}`;
    if (name === 'Grep') return `Grep: /${esc(inp.pattern || '')}/` + (inp.path ? ` in ${esc(inp.path)}` : '');
    if (name === 'WebFetch') return `Fetch: ${truncate(inp.url || '', 80)}`;
    if (name === 'WebSearch') return `Search: ${truncate(inp.query || '', 80)}`;
    if (name === 'Task') return `Task: ${esc(inp.subagent_type || '')} - ${esc(inp.description || '')}`;
    if (name === 'TodoWrite') return 'TodoWrite';
    if (name === 'AskUserQuestion') return 'AskUserQuestion';
    return name;
}

function renderToolUse(tool) {
    const name = tool.name || 'unknown';
    const inp = tool.input || {};
    const summary = getToolSummary(name, inp);

    let body = '';

    if (name === 'Bash') {
        body += `<div class="tool-call-section"><div class="tool-call-section-title">Command</div><pre><code>${esc(inp.command || '')}</code></pre></div>`;
        if (inp.description) body += `<div class="tool-call-section"><div class="tool-call-section-title">Description</div><div>${esc(inp.description)}</div></div>`;
    } else if (name === 'Read') {
        body += `<div class="tool-call-section">File: <code>${esc(inp.file_path || '')}</code></div>`;
    } else if (name === 'Write') {
        body += `<div class="tool-call-section">File: <code>${esc(inp.file_path || '')}</code></div>`;
        if (inp.content) body += `<div class="tool-call-section"><div class="tool-call-section-title">Content</div><pre><code>${esc(truncate(inp.content, 500))}</code></pre></div>`;
    } else if (name === 'Edit') {
        body += `<div class="tool-call-section">File: <code>${esc(inp.file_path || '')}</code></div>`;
        if (inp.old_string) body += `<div class="tool-call-section"><div class="tool-call-section-title">Old</div><pre style="border-left:3px solid var(--danger)"><code>${esc(truncate(inp.old_string, 300))}</code></pre></div>`;
        if (inp.new_string) body += `<div class="tool-call-section"><div class="tool-call-section-title">New</div><pre style="border-left:3px solid var(--success)"><code>${esc(truncate(inp.new_string, 300))}</code></pre></div>`;
    } else if (name === 'Glob') {
        body += `<div class="tool-call-section">Pattern: <code>${esc(inp.pattern || '')}</code>${inp.path ? ' in <code>' + esc(inp.path) + '</code>' : ''}</div>`;
    } else if (name === 'Grep') {
        body += `<div class="tool-call-section">Pattern: <code>${esc(inp.pattern || '')}</code>${inp.path ? ' in <code>' + esc(inp.path) + '</code>' : ''}</div>`;
    } else if (name === 'Task') {
        body += `<div class="tool-call-section">${esc(inp.subagent_type || '')} &mdash; ${esc(inp.description || '')}</div>`;
        if (inp.prompt) body += `<div class="tool-call-section"><div class="tool-call-section-title">Prompt</div><pre><code>${esc(truncate(inp.prompt, 500))}</code></pre></div>`;
    } else if (name === 'TodoWrite') {
        const todos = inp.todos || [];
        for (const t of todos) {
            const icon = {'completed': '[x]', 'in_progress': '[~]', 'pending': '[ ]'}[t.status] || '[ ]';
            body += `<div>${icon} ${esc(t.content || '')}</div>`;
        }
    } else if (name === 'AskUserQuestion') {
        const questions = inp.questions || [];
        for (const q of questions) {
            body += `<div class="tool-call-section"><strong>Q:</strong> ${esc(q.question || '')}</div>`;
        }
    } else {
        const s = JSON.stringify(inp, null, 2);
        body += `<pre><code>${esc(truncate(s, 500))}</code></pre>`;
    }

    return `<details class="tool-call"><summary class="tool-name">${esc(summary)}</summary><div class="tool-call-body">${body}</div></details>`;
}

function _toolResultHasBody(parsed) {
    const rt = parsed.result_type || 'unknown';
    if (rt === 'bash') return !!(parsed.stdout || parsed.stderr);
    if (rt === 'todo_write') return !!(parsed.todos && parsed.todos.length);
    if (rt === 'user_input') return true;
    if (rt === 'task' && (parsed.total_duration_ms || parsed.retrieval_status || parsed.description)) return true;
    return false;
}

function renderToolResult(parsed) {
    const rt = parsed.result_type || 'unknown';
    let summary = '';
    let body = '';

    if (rt === 'bash') {
        const exitCode = parsed.exit_code;
        const status = parsed.interrupted ? 'interrupted' : (parsed.is_error ? `error (exit ${exitCode})` : (exitCode === 0 ? 'success' : `exit ${exitCode}`));
        summary = `Bash Result (${status})`;
        if (parsed.stdout) body += `<div class="tool-call-section"><div class="tool-call-section-title">stdout</div><pre><code>${esc(truncate(parsed.stdout, 2000))}</code></pre></div>`;
        if (parsed.stderr) body += `<div class="tool-call-section"><div class="tool-call-section-title">stderr</div><pre style="border-left:3px solid var(--danger)"><code>${esc(truncate(parsed.stderr, 1000))}</code></pre></div>`;
    } else if (rt === 'file_read') {
        const numLines = parsed.num_lines ? ` (${parsed.num_lines} lines)` : '';
        summary = `Read: ${parsed.file_path || ''}${numLines}`;
    } else if (rt === 'file_edit') {
        summary = `Edited: ${parsed.file_path || ''}`;
    } else if (rt === 'file_write') {
        summary = `Wrote: ${parsed.file_path || ''}`;
    } else if (rt === 'glob') {
        const trunc = parsed.truncated ? ' (truncated)' : '';
        summary = `Glob: ${parsed.num_files || 0} files found${trunc}`;
    } else if (rt === 'grep') {
        summary = `Grep: ${parsed.num_files || 0} files, ${parsed.num_lines || 0} lines`;
    } else if (rt === 'web_search') {
        summary = `Search: "${parsed.query || ''}" - ${parsed.result_count || 0} results`;
    } else if (rt === 'web_fetch') {
        summary = `Fetch: ${parsed.url || ''} (${parsed.status_code || '?'})`;
    } else if (rt === 'task') {
        const status = parsed.status || 'completed';
        const dur = parsed.total_duration_ms;
        const durStr = dur ? ` (${(dur / 1000).toFixed(1)}s)` : '';
        const tokStr = parsed.total_tokens ? `, ${parsed.total_tokens.toLocaleString()} tokens` : '';
        const toolStr = parsed.total_tool_use_count ? `, ${parsed.total_tool_use_count} tool calls` : '';
        summary = `Task ${status}${durStr}${tokStr}${toolStr}`;
        if (parsed.retrieval_status) summary = `Task retrieval: ${parsed.retrieval_status}`;
        if (parsed.description) summary = `Task launched: ${parsed.description}`;
    } else if (rt === 'todo_write') {
        const count = parsed.todo_count || 0;
        summary = `Todos updated (${count} items)`;
        if (parsed.todos && parsed.todos.length) {
            for (const t of parsed.todos) {
                const icon = {'completed': '\u2705', 'in_progress': '\u23f3', 'pending': '\u2b1c'}[t.status] || '\u2b1c';
                body += `<div>${icon} ${esc(t.content || '')}</div>`;
            }
        }
    } else if (rt === 'user_input') {
        summary = 'User input received';
        const qs = parsed.questions || [];
        const ans = parsed.answers || {};
        for (const q of qs) {
            body += `<div class="tool-call-section"><strong>Q:</strong> ${esc(q.question || '')}</div>`;
        }
        const ansKeys = Object.keys(ans);
        if (ansKeys.length) {
            for (const k of ansKeys) {
                body += `<div class="tool-call-section"><strong>A:</strong> ${esc(String(ans[k]))}</div>`;
            }
        }
    } else if (rt === 'plan') {
        summary = `Plan: ${parsed.file_path || ''}`;
    } else {
        summary = `Tool result (${rt})`;
    }

    if (!body) {
        return `<div class="tool-result"><span class="tool-result-summary">${esc(summary)}</span></div>`;
    }
    return `<details class="tool-result"><summary class="tool-result-summary">${esc(summary)}</summary><div class="tool-call-body">${body}</div></details>`;
}

// ==================== Search ====================

function showSearchPage() {
    setHamburgerVisible(false);
    setWorkspaceMode(false);
    window.location.hash = '#search';
    const content = document.getElementById('content');
    content.innerHTML = `
        <div class="search-page">
            <a class="back-link" href="#" onclick="showProjects();return false;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
                Back to Projects
            </a>
            <br><br>
            <h1>Search</h1>
            <div class="search-bar">
                <input class="input" type="text" id="search-input" placeholder="Search conversations..." autofocus
                       onkeydown="if(event.key==='Enter') doSearch()">
                <button class="btn btn-primary" onclick="doSearch()">Search</button>
            </div>
            <div id="search-results"></div>
        </div>`;
    document.getElementById('search-input').focus();
}

async function doSearch() {
    const input = document.getElementById('search-input');
    if (!input) { showSearchPage(); return; }
    const query = input.value.trim();
    if (!query) return;

    const container = document.getElementById('search-results');
    container.innerHTML = '<div class="loading">Searching...</div>';

    try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=50`);
        const results = await res.json();

        let html = `<p class="text-muted text-sm">${results.length} result${results.length !== 1 ? 's' : ''}</p><br>`;
        html += '<div class="search-results">';

        for (const r of results) {
            html += `<div class="search-result" onclick="window.location.hash='#project/${encodeURIComponent(r.project)}/${r.session_id}'">
                <div><strong>${esc(r.title)}</strong> <span class="text-muted text-sm">${esc(r.project)} &bull; ${esc(r.role)}</span></div>
                <div class="snippet">...${esc(r.snippet)}...</div>
            </div>`;
        }

        if (!results.length) html += '<div class="empty-state">No results found.</div>';
        html += '</div>';
        smoothSet(container, html);
    } catch (e) {
        container.innerHTML = `<div class="loading">Error: ${esc(e.message)}</div>`;
    }
}

// ==================== Export ====================

function bulkExport() {
    showConfirm('Export all sessions as a zip file?', async () => {
        const fname = `claude-code-export-${new Date().toISOString().slice(0, 10)}.zip`;
        const handle = await getFileHandle(fname, [{ description: 'ZIP archive', accept: { 'application/zip': ['.zip'] } }]);
        if (!handle) return;
        const btn = document.querySelector('.export-all-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Exporting...'; }
        try {
            const res = await fetch('/api/export', { method: 'POST' });
            if (!res.ok) throw new Error(`Export failed: ${res.status}`);
            const blob = await res.blob();
            await writeToHandle(handle, blob, fname);
        } catch (e) {
            showToast('Export failed: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Export all'; }
        }
    });
}

async function downloadSession(project, sessionId) {
    const fname = `session-${sessionId.slice(0, 8)}.md`;
    // Get file handle BEFORE any async work (must be in user gesture)
    const handle = await getFileHandle(fname, [{ description: 'Markdown', accept: { 'text/markdown': ['.md'] } }]);
    if (!handle) return;
    try {
        const res = await fetch(`/api/export/session/${encodeURIComponent(project)}/${sessionId}`);
        if (!res.ok) throw new Error(`Download failed: ${res.status}`);
        const blob = await res.blob();
        await writeToHandle(handle, blob, fname);
    } catch (e) {
        showToast('Download failed: ' + e.message, 'error');
    }
}

async function getFileHandle(suggestedName, fileTypes) {
    if (window.showSaveFilePicker) {
        try {
            return await window.showSaveFilePicker({ suggestedName, types: fileTypes });
        } catch (e) {
            if (e.name === 'AbortError') return null;
        }
    }
    return 'fallback';
}

async function writeToHandle(handle, blob, fallbackName) {
    if (handle !== 'fallback') {
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
    } else {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fallbackName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
}

function copyAll() {
    const msgs = document.querySelector('.messages-container');
    if (!msgs) return;
    const text = msgs.innerText;
    navigator.clipboard.writeText(text).then(() => showToast('Copied to clipboard', 'success'));
}

// ==================== Theme ====================

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    const moon = document.getElementById('icon-moon');
    const sun = document.getElementById('icon-sun');
    if (moon && sun) {
        moon.style.display = theme === 'dark' ? 'block' : 'none';
        sun.style.display = theme === 'light' ? 'block' : 'none';
    }
    const hljsLink = document.getElementById('hljs-theme');
    if (hljsLink) {
        hljsLink.href = theme === 'dark'
            ? 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/vs2015.min.css'
            : 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css';
    }
}

function toggleTheme() {
    const current = localStorage.getItem('theme') || 'dark';
    applyTheme(current === 'dark' ? 'light' : 'dark');
}

// ==================== Helpers ====================

function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Strip Claude Code internal XML noise before markdown rendering
function cleanContent(s) {
    if (!s) return '';
    let text = s;
    text = text.replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, '');
    text = text.replace(/<user-prompt-submit-hook>[\s\S]*?<\/user-prompt-submit-hook>/g, '');
    text = text.replace(/<claude_background_info>[\s\S]*?<\/claude_background_info>/g, '');
    text = text.replace(/<fast_mode_info>[\s\S]*?<\/fast_mode_info>/g, '');
    text = text.replace(/<env>[\s\S]*?<\/env>/g, '');
    text = text.replace(/<ide_opened_file>[\s\S]*?<\/ide_opened_file>/g, '');
    text = text.replace(/<ide_selection>([\s\S]*?)<\/ide_selection>/g, '```\n$1\n```');
    text = text.replace(/<local-command-stdout>([\s\S]*?)<\/local-command-stdout>/g, '```\n$1\n```');
    text = text.replace(/<local-command-stderr>([\s\S]*?)<\/local-command-stderr>/g, '```\n$1\n```');
    text = text.replace(/<\/?(command-name|antml:[a-z_]+|function_calls|example[^>]*)>/g, '');
    text = text.replace(/\n{3,}/g, '\n\n');
    return text.trim();
}

function renderMarkdown(text) {
    if (!text) return '';
    if (typeof marked !== 'undefined') {
        try { return marked.parse(text, { breaks: true, gfm: true }); } catch(e) {}
    }
    // Fallback: escape + basic code block conversion
    let out = esc(text);
    out = out.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
    return out;
}

function formatTs(ts) {
    try {
        const d = new Date(ts);
        const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
        const dd = String(d.getUTCDate()).padStart(2, '0');
        const yyyy = d.getUTCFullYear();
        let hh = d.getUTCHours();
        const ampm = hh >= 12 ? 'PM' : 'AM';
        hh = hh % 12 || 12;
        const hhStr = String(hh).padStart(2, '0');
        const min = String(d.getUTCMinutes()).padStart(2, '0');
        const ss = String(d.getUTCSeconds()).padStart(2, '0');
        return `${mm}/${dd}/${yyyy} ${hhStr}:${min}:${ss} ${ampm}`;
    } catch { return ts; }
}

function formatDate(ts) {
    try {
        const d = new Date(ts);
        const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
        const dd = String(d.getUTCDate()).padStart(2, '0');
        const yyyy = d.getUTCFullYear();
        return `${mm}/${dd}/${yyyy}`;
    } catch { return ts ? ts.slice(0, 10) : ''; }
}

function formatSize(bytes) {
    if (!bytes) return '?';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

function truncate(s, max) {
    if (!s) return '';
    return s.length > max ? s.slice(0, max) + '...' : s;
}

