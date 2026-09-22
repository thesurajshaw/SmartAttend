// ===== Dark Mode Toggle =====
function initTheme() {
    const saved = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    updateToggleIcon(saved);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    updateToggleIcon(next);
}

function updateToggleIcon(theme) {
    const btn = document.getElementById('theme-toggle');
    if (btn) {
        btn.textContent = theme === 'dark' ? '☀️' : '🌙';
    }
}

// ===== Toast Notifications =====
function showToast(message, type) {
    type = type || 'info';
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.innerHTML = '<span>' + message + '</span><button class="toast-close" onclick="this.parentElement.remove()">&times;</button>';
    container.appendChild(toast);

    setTimeout(function () {
        if (toast.parentElement) toast.remove();
    }, 4000);
}

// ===== Mobile Sidebar Toggle =====
function toggleSidebar() {
    var sidebar = document.getElementById('sidebar');
    if (sidebar) {
        sidebar.classList.toggle('open');
    }
}

// ===== Init on page load =====
document.addEventListener('DOMContentLoaded', function () {
    initTheme();
});
