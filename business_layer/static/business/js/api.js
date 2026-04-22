// Thin fetch() wrapper for the business shell.
//
// Responsibilities:
//   * Set Content-Type + Accept on every request.
//   * Echo the CSRF cookie in X-CSRF-Token for state-changing calls.
//   * Send cookies with every request (credentials: 'include' is
//     implicit on same-origin; we set it explicitly for clarity).
//   * Normalise the error envelope — every non-2xx throws an
//     {status, code, detail, request_id} object so callers render
//     useful messages instead of poking at raw Response objects.

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

        if (opts.body !== undefined) {
            headers['Content-Type'] = 'application/json';
        }

        // CSRF double-submit: the middleware sets bl_csrf on any
        // response that didn't carry it in. Echo back in the header
        // for every state-changing call.
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
        if (text) {
            try { payload = JSON.parse(text); } catch (_) { /* ignore — payload stays null */ }
        }

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
