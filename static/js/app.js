// Claude Code Chat Browser — Main JS

let currentProject = null;
let cachedSessions = [];
let projectDisplayNames = {};

document.addEventListener('DOMContentLoaded', () => {
    applyTheme(localStorage.getItem('theme') || 'dark');
    handleRoute();
    window.addEventListener('hashchange', handleRoute);
});

function handleRoute() {
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
    window.location.hash = '';
    const content = document.getElementById('content');
    content.innerHTML = '<div class="loading">Loading projects...</div>';

    try {
        const res = await fetch('/api/projects');
        const projects = await res.json();

        if (!projects.length) {
            content.innerHTML = '<div class="empty-state">No Claude Code projects found.<br>Make sure Claude Code has been used on this machine.</div>';
            return;
        }

        let html = `
            <div class="page-header">
                <div>
                    <h1>Projects</h1>
                    <p class="text-muted text-sm">Browse your Claude Code conversations by project.</p>
                </div>
                <div class="btn-group">
                    <button class="btn btn-outline btn-sm" onclick="bulkExport()">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                        Export all
                    </button>
                </div>
            </div>`;

        html += `<div class="card"><div class="card-header">
            <h2>Projects with Sessions</h2>
            <p class="text-muted text-sm">${projects.length} project${projects.length !== 1 ? 's' : ''} with chat history</p>
        </div><div class="card-body"><table class="table">
            <thead><tr><th>Project</th><th>Sessions</th><th>Last Modified</th></tr></thead><tbody>`;

        // Cache display names
        for (const p of projects) {
            projectDisplayNames[p.name] = p.display_name || p.name;
        }

        // Sort by last modified desc
        projects.sort((a, b) => (b.last_modified || '').localeCompare(a.last_modified || ''));

        for (const p of projects) {
            html += `<tr>
                <td><a href="#project/${encodeURIComponent(p.name)}">${esc(p.display_name || p.name)}</a></td>
                <td><span class="text-success">${p.session_count} session${p.session_count !== 1 ? 's' : ''}</span></td>
                <td>${p.last_modified ? formatTs(p.last_modified) : '—'}</td>
            </tr>`;
        }

        html += '</tbody></table></div></div>';
        content.innerHTML = html;
    } catch (e) {
        content.innerHTML = `<div class="loading">Error: ${esc(e.message)}</div>`;
    }
}

// ==================== Workspace (split layout) ====================

async function showWorkspace(projectName, selectedSessionId) {
    currentProject = projectName;
    const content = document.getElementById('content');
    content.innerHTML = '<div class="loading">Loading sessions...</div>';

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

        // Sort by first_timestamp desc
        cachedSessions.sort((a, b) => {
            const ta = a.first_timestamp || '';
            const tb = b.first_timestamp || '';
            return tb.localeCompare(ta);
        });

        // Group by date
        const byDate = {};
        for (const s of cachedSessions) {
            const ts = s.first_timestamp || '';
            const date = ts.slice(0, 10) || 'Unknown';
            if (!byDate[date]) byDate[date] = [];
            byDate[date].push(s);
        }

        // Build sidebar
        let sidebar = `<div class="sidebar-header">
            <a class="back-link" href="#" onclick="showProjects();return false;">&larr; Back to Projects</a>
        </div>`;
        sidebar += `<div class="sidebar-header">Conversations (${cachedSessions.length})</div>`;

        const dates = Object.keys(byDate).sort().reverse();
        for (const date of dates) {
            sidebar += `<div class="date-label">${esc(date)}</div>`;
            for (const s of byDate[date]) {
                const title = (s.title || s.id).slice(0, 40);
                const ts = s.first_timestamp ? formatTs(s.first_timestamp) : '';
                const models = (s.models || []).join(', ');
                const isActive = s.id === selectedSessionId ? ' active' : '';
                sidebar += `<div class="sidebar-item${isActive}" onclick="selectSession('${esc(projectName)}','${esc(s.id)}')" id="sidebar-${s.id}">
                    <div class="title">${esc(title)}</div>
                    <div class="meta">${esc(ts)}<br>${esc(models)}</div>
                </div>`;
            }
        }

        // Build layout
        let html = `<div class="workspace-layout">
            <div class="sidebar" id="sidebar">${sidebar}</div>
            <div class="main-panel" id="main-panel">`;

        // Project info card
        html += `<div class="project-info">
            <h2>${esc(prettyName)}</h2>
            <div class="meta">${cachedSessions.length} conversations</div>
        </div>`;

        html += '<div id="session-content"></div></div></div>';
        content.innerHTML = html;

        // Auto-select first session or specified session
        if (selectedSessionId) {
            loadSession(projectName, selectedSessionId);
        } else if (cachedSessions.length > 0) {
            selectSession(projectName, cachedSessions[0].id);
        }
    } catch (e) {
        content.innerHTML = `<div class="loading">Error: ${esc(e.message)}</div>`;
    }
}

function selectSession(projectName, sessionId) {
    // Just update the hash — handleRoute will do the rest
    window.location.hash = `#project/${encodeURIComponent(projectName)}/${sessionId}`;
}

async function loadSession(projectName, sessionId) {
    const container = document.getElementById('session-content');
    if (!container) return;

    try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(projectName)}/${sessionId}`);
        const session = await res.json();
        const meta = session.metadata;

        let html = '';

        // Panel header
        html += `<div class="panel-header">
            <div>
                <h2>${esc(session.title)}</h2>
                <div class="stats">
                    Models: ${esc((meta.models_used || []).join(', '))} &bull;
                    Tokens: ${(meta.total_input_tokens + meta.total_output_tokens).toLocaleString()} &bull;
                    Tool calls: ${meta.total_tool_calls}
                    ${meta.compactions > 0 ? ' &bull; Compactions: ' + meta.compactions : ''}
                </div>
                <div class="stats">
                    ${meta.cwd ? 'Dir: ' + esc(meta.cwd) + ' &bull; ' : ''}
                    ${meta.git_branch ? 'Branch: ' + esc(meta.git_branch) + ' &bull; ' : ''}
                    ${meta.version ? 'v' + esc(meta.version) : ''}
                </div>
            </div>
            <div class="btn-group">
                <button class="btn btn-outline btn-sm" onclick="copyAll()">Copy All</button>
                <button class="btn btn-outline btn-sm" onclick="downloadSession('${esc(projectName)}','${sessionId}')">Download</button>
            </div>
        </div>`;

        // Messages
        html += '<div class="messages-container">';
        for (const msg of session.messages) {
            if (msg.role === 'user') html += renderUser(msg);
            else if (msg.role === 'assistant') html += renderAssistant(msg);
            else if (msg.role === 'system') html += renderSystem(msg);
        }
        html += '</div>';

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="loading">Error: ${esc(e.message)}</div>`;
    }
}

// ==================== Message renderers ====================

function renderUser(msg) {
    if (msg.slug && !msg.text) return '';
    let html = `<div class="message user">`;
    html += `<span class="role-badge user-badge">You</span>`;
    if (msg.timestamp) html += ` <span class="msg-meta">${formatTs(msg.timestamp)}</span>`;
    html += `<div class="content">${escContent(msg.text || '')}</div>`;
    html += '</div>';
    return html;
}

function renderAssistant(msg) {
    let html = `<div class="message assistant">`;
    html += `<span class="role-badge assistant-badge">Assistant</span>`;

    let metaParts = [];
    if (msg.model) metaParts.push(msg.model);
    if (msg.usage && msg.usage.output_tokens) metaParts.push(`${msg.usage.output_tokens.toLocaleString()} tokens`);
    if (msg.timestamp) metaParts.push(formatTs(msg.timestamp));
    if (metaParts.length) html += ` <span class="msg-meta">${esc(metaParts.join(' &bull; '))}</span>`;

    if (msg.thinking) {
        html += `<details class="thinking-block"><summary>Thinking</summary><div class="content">${escContent(msg.thinking)}</div></details>`;
    }
    if (msg.text) html += `<div class="content">${escContent(msg.text)}</div>`;
    if (msg.tool_uses) {
        for (const tool of msg.tool_uses) html += renderToolUse(tool);
    }
    html += '</div>';
    return html;
}

function renderSystem(msg) {
    if (msg.subtype === 'compact_boundary') {
        return '<div class="message system"><em>--- Context compacted ---</em></div>';
    }
    if (msg.content) {
        return `<div class="message system">${esc(msg.content)}</div>`;
    }
    return '';
}

function renderToolUse(tool) {
    const name = tool.name || 'unknown';
    const inp = tool.input || {};
    let html = `<div class="tool-call"><div class="tool-name">${esc(name)}</div>`;

    if (name === 'Bash') {
        html += `<pre><code>${esc(inp.command || '')}</code></pre>`;
    } else if (name === 'Read') {
        html += `<div>File: <code>${esc(inp.file_path || '')}</code></div>`;
    } else if (name === 'Write') {
        html += `<div>File: <code>${esc(inp.file_path || '')}</code></div>`;
        if (inp.content) html += `<pre><code>${esc(truncate(inp.content, 500))}</code></pre>`;
    } else if (name === 'Edit') {
        html += `<div>File: <code>${esc(inp.file_path || '')}</code></div>`;
        if (inp.old_string) html += `<pre style="border-left:3px solid #ef5350"><code>${esc(truncate(inp.old_string, 300))}</code></pre>`;
        if (inp.new_string) html += `<pre style="border-left:3px solid #66bb6a"><code>${esc(truncate(inp.new_string, 300))}</code></pre>`;
    } else if (name === 'Glob') {
        html += `<div>Pattern: <code>${esc(inp.pattern || '')}</code></div>`;
    } else if (name === 'Grep') {
        html += `<div>Pattern: <code>${esc(inp.pattern || '')}</code>${inp.path ? ' in <code>' + esc(inp.path) + '</code>' : ''}</div>`;
    } else if (name === 'Task') {
        html += `<div>${esc(inp.subagent_type || '')} &mdash; ${esc(inp.description || '')}</div>`;
    } else if (name === 'TodoWrite') {
        const todos = inp.todos || [];
        for (const t of todos) {
            const icon = {'completed': '[x]', 'in_progress': '[~]', 'pending': '[ ]'}[t.status] || '[ ]';
            html += `<div>${icon} ${esc(t.content || '')}</div>`;
        }
    } else {
        const s = JSON.stringify(inp, null, 2);
        html += `<pre><code>${esc(truncate(s, 500))}</code></pre>`;
    }

    html += '</div>';
    return html;
}

// ==================== Search ====================

function showSearchPage() {
    window.location.hash = '#search';
    const content = document.getElementById('content');
    content.innerHTML = `
        <div class="search-page">
            <a class="back-link" href="#" onclick="showProjects();return false;">&larr; Back to Projects</a>
            <h1>Search</h1><br>
            <input type="text" id="search-input" placeholder="Search conversations..." autofocus
                   onkeydown="if(event.key==='Enter') doSearch()">
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
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="loading">Error: ${esc(e.message)}</div>`;
    }
}

// ==================== Export ====================

async function bulkExport() {
    if (!confirm('Export all sessions as a zip file?')) return;
    const fname = `claude-code-export-${new Date().toISOString().slice(0, 10)}.zip`;
    // Get file handle BEFORE any async work (must be in user gesture)
    const handle = await getFileHandle(fname, [{ description: 'ZIP archive', accept: { 'application/zip': ['.zip'] } }]);
    if (!handle) return;
    const btn = event.target.closest('button');
    if (btn) { btn.disabled = true; btn.textContent = 'Exporting...'; }
    try {
        const res = await fetch('/api/export', { method: 'POST' });
        if (!res.ok) throw new Error(`Export failed: ${res.status}`);
        const blob = await res.blob();
        await writeToHandle(handle, blob, fname);
    } catch (e) {
        alert('Export failed: ' + e.message);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Export all'; }
    }
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
        alert('Download failed: ' + e.message);
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
    navigator.clipboard.writeText(text).then(() => alert('Copied to clipboard'));
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

function escContent(s) {
    // Strip Claude Code internal system tags before rendering
    let text = s;
    // Remove system-reminder blocks entirely (internal noise)
    text = text.replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, '');
    // Remove user-prompt-submit-hook blocks
    text = text.replace(/<user-prompt-submit-hook>[\s\S]*?<\/user-prompt-submit-hook>/g, '');
    // Remove claude_background_info, fast_mode_info, env blocks
    text = text.replace(/<claude_background_info>[\s\S]*?<\/claude_background_info>/g, '');
    text = text.replace(/<fast_mode_info>[\s\S]*?<\/fast_mode_info>/g, '');
    text = text.replace(/<env>[\s\S]*?<\/env>/g, '');
    // Remove ide_opened_file blocks (IDE noise)
    text = text.replace(/<ide_opened_file>[\s\S]*?<\/ide_opened_file>/g, '');
    // Convert ide_selection to a fenced block
    text = text.replace(/<ide_selection>([\s\S]*?)<\/ide_selection>/g, '```\n$1\n```');
    // Convert local-command-stdout/stderr to fenced blocks
    text = text.replace(/<local-command-stdout>([\s\S]*?)<\/local-command-stdout>/g, '```\n$1\n```');
    text = text.replace(/<local-command-stderr>([\s\S]*?)<\/local-command-stderr>/g, '```\n$1\n```');
    // Strip any remaining known Claude Code tags (opening and closing)
    text = text.replace(/<\/?(command-name|antml:[a-z_]+|function_calls|example[^>]*)>/g, '');
    // Clean up excess blank lines left after stripping
    text = text.replace(/\n{3,}/g, '\n\n');
    text = text.trim();

    let out = esc(text);
    out = out.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
    return out;
}

function formatTs(ts) {
    try { return new Date(ts).toLocaleString(); } catch { return ts; }
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

