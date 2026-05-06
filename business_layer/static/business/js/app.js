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

    // CA-invite link handling: if the user lands on `/business?ca=<gstin>`,
    // stash the gstin so the dashboard can pre-fill the "Link your CA"
    // form. We read it once on boot (before signup) so it survives the
    // full OTP signup flow.
    (function readInviteParam() {
        try {
            const params = new URLSearchParams(window.location.search);
            const ca = params.get('ca');
            if (ca && /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]$/.test(ca)) {
                window.localStorage.setItem('pending_ca_invite', ca);
            }
        } catch (_) { /* localStorage / URL parsing failures are non-fatal */ }
    })();
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
        // Force-clear any stale session so the topbar stays hidden and a
        // refresh doesn't auto-bounce the user to /dashboard.
        state.session = null;
        state.phone = '';
        // Best-effort logout — ignored if there's no cookie.
        window.api.post('/api/auth/logout', {}).catch(() => {});
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
        if (state.session) {
            // Cross-persona gate: a CA session sitting in the business
            // shell should be redirected to its own shell instead of
            // 403'ing every API call below.
            if (state.session.user && state.session.user.role !== 'business') {
                window.location.replace('/ca');
                return null;
            }
            return state.session;
        }
        try {
            const session = await window.api.get('/api/auth/me');
            if (session.user && session.user.role !== 'business') {
                window.location.replace('/ca');
                return null;
            }
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
        // Respect the URL hash. If the user explicitly typed `#/login`,
        // show the login form even if a session cookie is still alive
        // — renderLogin clears it. Previously we overrode `#/login` to
        // `#/dashboard` here, which leaked the topbar onto the login
        // page when a stale session was present.
        const hash = window.location.hash;
        if (hash === '#/login' || hash === '#/otp') {
            navigate(hash);
            return;
        }
        try {
            const session = await window.api.get('/api/auth/me');
            // Cross-persona: don't try to render a CA session on the
            // business shell; redirect to /ca synchronously.
            if (session.user && session.user.role !== 'business') {
                window.location.replace('/ca');
                return;
            }
            state.session = session;
            navigate(hash || '#/dashboard');
        } catch (_) {
            navigate('#/login');
        }
    })();
})();
