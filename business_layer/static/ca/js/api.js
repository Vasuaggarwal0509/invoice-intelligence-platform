// Fetch wrapper — same contract as the business shell's api.js.
// Kept as a separate copy so the CA shell is self-contained + each
// shell can evolve without cross-impact.

(function (global) {
    'use strict';

    function readCookie(name) {
        const rows = document.cookie.split('; ');
        for (let i = 0; i < rows.length; i++) {
            const [k, ...vs] = rows[i].split('=');
            if (k === name) return decodeURIComponent(vs.join('='));
        }
        return '';
    }

    async function request(path, options) {
        const opts = options || {};
        const method = (opts.method || 'GET').toUpperCase();
        const headers = Object.assign(
            { Accept: 'application/json' },
            opts.headers || {}
        );
        if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
        if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
            const csrf = readCookie('bl_csrf');
            if (csrf) headers['X-CSRF-Token'] = csrf;
        }

        const response = await fetch(path, {
            method,
            headers,
            credentials: 'include',
            body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
        });

        const text = await response.text();
        let payload = null;
        if (text) { try { payload = JSON.parse(text); } catch (_) {} }

        if (!response.ok) {
            const err = new Error((payload && payload.detail) || response.statusText);
            err.status = response.status;
            err.code = payload && payload.code;
            err.detail = payload && payload.detail;
            err.requestId = payload && payload.request_id;
            throw err;
        }
        return payload;
    }

    global.api = {
        get: (path) => request(path, { method: 'GET' }),
        post: (path, body) => request(path, { method: 'POST', body }),
        del: (path) => request(path, { method: 'DELETE' }),
    };
})(window);
