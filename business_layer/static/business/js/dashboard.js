// Dashboard — greeting + upload card. Real KPIs land in Sprint 3.

(function (global) {
    'use strict';

    function showError(form, msg) {
        const el = form.parentElement.querySelector('[data-role="error"]');
        if (!el) return;
        if (msg) { el.textContent = msg; el.hidden = false; }
        else { el.textContent = ''; el.hidden = true; }
    }

    function showStatus(form, msg) {
        const el = form.parentElement.querySelector('[data-role="upload-status"]');
        if (!el) return;
        if (msg) { el.textContent = msg; el.hidden = false; }
        else { el.textContent = ''; el.hidden = true; }
    }

    async function uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        // Read CSRF cookie for the double-submit token.
        const rows = document.cookie.split('; ');
        let csrf = '';
        for (const r of rows) {
            const [k, ...v] = r.split('=');
            if (k === 'bl_csrf') { csrf = decodeURIComponent(v.join('=')); break; }
        }

        const res = await fetch('/api/upload', {
            method: 'POST',
            credentials: 'include',
            headers: csrf ? { 'X-CSRF-Token': csrf } : {},
            body: formData,
        });
        const text = await res.text();
        let payload = null;
        try { payload = JSON.parse(text); } catch (_) { /* ignore */ }
        if (!res.ok) {
            const err = new Error((payload && payload.detail) || res.statusText);
            err.status = res.status;
            err.code = payload && payload.code;
            err.detail = payload && payload.detail;
            throw err;
        }
        return payload;
    }

    function render(root, session) {
        const tpl = document.getElementById('view-dashboard');
        const clone = tpl.content.cloneNode(true);
        const h1 = clone.querySelector('[data-role="greeting"]');
        if (session && session.workspace && session.workspace.name) {
            h1.textContent = 'Hi, ' + session.workspace.name;
        }
        root.replaceChildren(clone);

        const form = root.querySelector('#form-upload');
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            showError(form, null);
            showStatus(form, null);
            const file = form.elements['file'].files[0];
            if (!file) return;
            const btn = form.querySelector('button.primary');
            btn.disabled = true;
            showStatus(form, 'Uploading…');
            try {
                const result = await uploadFile(file);
                window.location.hash = '#/invoice/' + encodeURIComponent(result.invoice_id);
            } catch (err) {
                let msg = err.detail || 'Upload failed. Try again.';
                if (err.status === 413 || err.code === 'validation_failed') {
                    msg = err.detail || 'This file is too large or not supported.';
                }
                showError(form, msg);
                showStatus(form, null);
            } finally {
                btn.disabled = false;
                form.reset();
            }
        });
    }

    global.dashboard = { render };
})(window);
