// CA-shell top-level router.
//
// Routes:
//   #/login                                   — email/password
//   #/signup                                  — CA firm registration
//   #/clients                                 — client list (default authenticated home)
//   #/clients/:id                             — one client's invoices
//   #/clients/:id/invoices/:invoice_id        — full CA invoice detail

(function () {
    'use strict';

    const root = document.getElementById('app-root');
    const topbar = document.getElementById('topbar');
    const logoutBtn = document.getElementById('logout-btn');

    function setAuthenticatedUI(isAuth) {
        if (isAuth) topbar.removeAttribute('hidden');
        else topbar.setAttribute('hidden', '');
    }

    function navigate(hash) {
        if (window.location.hash !== hash) window.location.hash = hash;
        else handleRoute();
    }

    function mountTemplate(id) {
        const tpl = document.getElementById(id);
        root.replaceChildren(tpl.content.cloneNode(true));
    }

    function renderLogin() {
        setAuthenticatedUI(false);
        mountTemplate('view-login');
        const form = root.querySelector('#form-login');
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            window.caAuth.handleLogin(form, () => navigate('#/clients'));
        });
    }

    function renderSignup() {
        setAuthenticatedUI(false);
        mountTemplate('view-signup');
        const form = root.querySelector('#form-signup');
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            window.caAuth.handleSignup(form, () => navigate('#/clients'));
        });
    }

    async function renderClients() {
        if (!(await ensureAuthed())) return;
        setAuthenticatedUI(true);
        await window.caClients.renderClients(root);
    }

    async function renderClientInvoices(businessId) {
        if (!(await ensureAuthed())) return;
        setAuthenticatedUI(true);
        await window.caClients.renderClientInvoices(root, businessId);
    }

    async function renderInvoice(businessId, invoiceId) {
        if (!(await ensureAuthed())) return;
        setAuthenticatedUI(true);
        await window.caInvoice.render(root, businessId, invoiceId);
    }

    async function ensureAuthed() {
        try {
            const me = await window.api.get('/api/auth/me');
            if (me.user.role !== 'ca') {
                // Business session on the CA shell — bounce to landing.
                window.location.replace('/');
                return false;
            }
            return true;
        } catch (_) {
            navigate('#/login');
            return false;
        }
    }

    function parseRoute(hash) {
        // #/clients/:id/invoices/:iid
        let m = hash.match(/^#\/clients\/([^/]+)\/invoices\/([^/]+)$/);
        if (m) return { kind: 'invoice', businessId: decodeURIComponent(m[1]), invoiceId: decodeURIComponent(m[2]) };
        // #/clients/:id
        m = hash.match(/^#\/clients\/([^/]+)$/);
        if (m) return { kind: 'client-invoices', businessId: decodeURIComponent(m[1]) };
        if (hash === '#/clients') return { kind: 'clients' };
        if (hash === '#/signup') return { kind: 'signup' };
        return { kind: 'login' };
    }

    async function handleRoute() {
        const hash = window.location.hash || '#/login';
        const parsed = parseRoute(hash);
        switch (parsed.kind) {
            case 'login': return renderLogin();
            case 'signup': return renderSignup();
            case 'clients': return renderClients();
            case 'client-invoices': return renderClientInvoices(parsed.businessId);
            case 'invoice': return renderInvoice(parsed.businessId, parsed.invoiceId);
        }
    }

    logoutBtn.addEventListener('click', async () => {
        try { await window.api.post('/api/auth/logout', {}); } catch (_) {}
        navigate('#/login');
    });

    window.addEventListener('hashchange', handleRoute);

    (async function boot() {
        try {
            const me = await window.api.get('/api/auth/me');
            if (me.user.role !== 'ca') {
                window.location.replace('/');
                return;
            }
            const target = window.location.hash && window.location.hash !== '#/login'
                ? window.location.hash : '#/clients';
            navigate(target);
        } catch (_) {
            navigate('#/login');
        }
    })();
})();
