/**
 * 麻将战绩排行榜 - 主 JavaScript
 */

// ── Global Dialog Helpers ──────────────────────────────────────────────
/**
 * showConfirm(message, onConfirm)
 * Opens a styled modal confirmation dialog instead of system confirm().
 */
function showConfirm(message, onConfirm) {
    const modal = document.getElementById('confirmModal');
    if (!modal) { if (onConfirm && confirm(message)) onConfirm(); return; }
    document.getElementById('confirmModalMsg').innerHTML = message;
    const bsModal = bootstrap.Modal.getOrCreateInstance(modal);
    const okBtn = document.getElementById('confirmModalOk');
    // Clone to remove previous listeners
    const newOk = okBtn.cloneNode(true);
    okBtn.parentNode.replaceChild(newOk, okBtn);
    newOk.addEventListener('click', () => {
        bsModal.hide();
        if (onConfirm) onConfirm();
    });
    bsModal.show();
}

/**
 * showAlert(message)
 * Opens a styled modal alert instead of system alert().
 */
function showAlert(message) {
    const modal = document.getElementById('alertModal');
    if (!modal) { alert(message); return; }
    document.getElementById('alertModalMsg').innerHTML = message;
    bootstrap.Modal.getOrCreateInstance(modal).show();
}
// ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function () {

    // Auto-initialize Bootstrap tooltips
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
        new bootstrap.Tooltip(el, { trigger: 'hover' });
    });

    // Auto-initialize Bootstrap popovers
    document.querySelectorAll('[data-bs-toggle="popover"]').forEach(el => {
        new bootstrap.Popover(el);
    });

    // Confirm delete actions (data-confirm attribute on forms/links)
    document.querySelectorAll('form[data-confirm]').forEach(form => {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            showConfirm(this.dataset.confirm, () => {
                this.removeAttribute('data-confirm');
                this.submit();
            });
        });
    });

    // Score input: highlight when negative/positive
    document.querySelectorAll('.score-input').forEach(input => {
        function colorize() {
            const val = parseFloat(input.value);
            if (!isNaN(val)) {
                if (val > 0) {
                    input.style.color = '#2ecc71';
                } else if (val < 0) {
                    input.style.color = '#e74c3c';
                } else {
                    input.style.color = '';
                }
            }
        }
        input.addEventListener('input', colorize);
        colorize();
    });

    // Number counter animation on stat numbers
    animateCounters();

    // Navbar scroll effect
    const nav = document.getElementById('mainNav');
    if (nav) {
        window.addEventListener('scroll', function () {
            if (window.scrollY > 50) {
                nav.classList.add('scrolled');
            } else {
                nav.classList.remove('scrolled');
            }
        });
    }
});

/**
 * Animate stat counters from 0 to their value
 */
function animateCounters() {
    const counters = document.querySelectorAll('.stat-number');
    counters.forEach(counter => {
        const text = counter.textContent.trim();
        const num = parseFloat(text.replace(/[^0-9.-]/g, ''));
        if (!isNaN(num) && num > 0) {
            let start = 0;
            const duration = 800;
            const step = num / (duration / 16);
            const timer = setInterval(() => {
                start += step;
                if (start >= num) {
                    start = num;
                    clearInterval(timer);
                }
                counter.textContent = Math.floor(start).toLocaleString();
            }, 16);
        }
    });
}

/**
 * CSRF helper for fetch requests
 */
function getCsrfToken() {
    const meta = document.querySelector('[name=csrfmiddlewaretoken]');
    if (meta) return meta.value;
    const cookie = document.cookie.match(/csrftoken=([^;]+)/);
    return cookie ? cookie[1] : '';
}

/**
 * Show a toast notification
 */
function showToast(message, type = 'info') {
    const container = document.querySelector('.toast-container') || (() => {
        const c = document.createElement('div');
        c.className = 'toast-container position-fixed top-0 end-0 p-3';
        c.style.zIndex = '9999';
        c.style.marginTop = '70px';
        document.body.appendChild(c);
        return c;
    })();

    const colorMap = {
        success: 'bg-success',
        error: 'bg-danger',
        warning: 'bg-warning text-dark',
        info: 'bg-info',
    };
    const iconMap = {
        success: 'check-circle',
        error: 'x-circle',
        warning: 'exclamation-triangle',
        info: 'info-circle',
    };

    const toast = document.createElement('div');
    toast.className = `toast show align-items-center text-white border-0 ${colorMap[type] || 'bg-info'}`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <i class="bi bi-${iconMap[type] || 'info-circle'} me-2"></i>${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    container.appendChild(toast);
    new bootstrap.Toast(toast, { delay: 4000 }).show();
    toast.addEventListener('hidden.bs.toast', () => toast.remove());
}
