// Top-level hash router for the business shell.
//
// Routes:
//   #/login             — phone entry
//   #/otp               — OTP verify + (optional) business name
//   #/dashboard         — authenticated home + upload card
//   #/inbox             — inbox listing
//   #/invoice/:id       — invoice detail

(function () {
    'use strict';

    const state = { phone: '', session: null };
    const root = document.getElementById('app-root');
    const topbar = document.getElementById('topbar');
    const logoutBtn = document.getElementById('logout-btn');

    function setAuthenticatedUI(isAuth) {
        if (isAuth) topbar.removeAttribute('hidden');
        else topbar.setAttribute('hidden', '');
    }

    function markActiveNav(name) {
        const links = topbar.querySelectorAll('[data-nav]');
        links.forEach((a) => {
            if (a.getAttribute('data-nav') === name) a.classList.add('active');
            else a.classList.remove('active');
        });
    }

    function mountTemplate(id) {
        const tpl = document.getElementById(id);
        root.replaceChildren(tpl.content.cloneNode(true));
    }

    function renderLogin() {
        setAuthenticatedUI(false);
        mountTemplate('view-login');
        const form = root.querySelector('#form-phone');
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            window.auth.handlePhoneSubmit(form, state, () => navigate('#/otp'));
        });
    }

    function renderOtp() {
        setAuthenticatedUI(false);
        if (!state.phone) { navigate('#/login'); return; }
        mountTemplate('view-otp');
        const form = root.querySelector('#form-otp');
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            window.auth.handleOtpSubmit(form, state, (session) => {
                state.session = session;
                navigate('#/dashboard');
            });
        });
        const backBtn = root.querySelector('[data-action="back"]');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                state.phone = '';
                navigate('#/login');
            });
        }
    }

    async function ensureSession() {
        if (state.session) return state.session;
        try {
            const session = await window.api.get('/api/auth/me');
            state.session = session;
            return session;
        } catch (_) {
            navigate('#/login');
            return null;
        }
    }

    async function renderDashboard() {
        const session = await ensureSession();
        if (!session) return;
        setAuthenticatedUI(true);
        markActiveNav('dashboard');
        window.dashboard.render(root, session);
    }

    async function renderInbox() {
        const session = await ensureSession();
        if (!session) return;
        setAuthenticatedUI(true);
        markActiveNav('inbox');
        await window.inbox.render(root);
    }

    async function renderInvoice(invoiceId) {
        const session = await ensureSession();
        if (!session) return;
        setAuthenticatedUI(true);
        markActiveNav('inbox');
        await window.invoice.render(root, invoiceId);
    }

    function navigate(hash) {
        if (window.location.hash !== hash) window.location.hash = hash;
        else handleRoute();
    }

    function parseInvoiceRoute(hash) {
        // Expects '#/invoice/<id>'.
        const prefix = '#/invoice/';
        if (hash.startsWith(prefix)) return decodeURIComponent(hash.slice(prefix.length));
        return null;
    }

    async function handleRoute() {
        const hash = window.location.hash || '#/login';
        if (hash === '#/login') return renderLogin();
        if (hash === '#/otp') return renderOtp();
        if (hash === '#/dashboard') return renderDashboard();
        if (hash === '#/inbox') return renderInbox();
        const invoiceId = parseInvoiceRoute(hash);
        if (invoiceId) return renderInvoice(invoiceId);
        return renderLogin();
    }

    logoutBtn.addEventListener('click', async () => {
        try { await window.api.post('/api/auth/logout', {}); }
        catch (_) { /* idempotent — ignore */ }
        state.session = null;
        state.phone = '';
        navigate('#/login');
    });

    window.addEventListener('hashchange', handleRoute);

    (async function boot() {
        try {
            const session = await window.api.get('/api/auth/me');
            state.session = session;
            const initial = window.location.hash && window.location.hash !== '#/login'
                ? window.location.hash : '#/dashboard';
            navigate(initial);
        } catch (_) {
            navigate('#/login');
        }
    })();
})();
