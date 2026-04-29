// CA signup + login screens.

(function (global) {
    'use strict';

    function showError(form, msg) {
        const el = form.querySelector('[data-role="error"]');
        if (!el) return;
        if (msg) { el.textContent = msg; el.hidden = false; }
        else { el.textContent = ''; el.hidden = true; }
    }

    async function handleSignup(form, onDone) {
        showError(form, null);
        const data = new FormData(form);
        const payload = {
            display_name: data.get('display_name').trim(),
            email: data.get('email').trim(),
            password: data.get('password'),
            gstin: data.get('gstin').trim().toUpperCase(),
        };
        if (payload.password.length < 12) {
            showError(form, 'Password must be at least 12 characters.');
            return;
        }
        const btn = form.querySelector('button.primary');
        btn.disabled = true;
        try {
            const session = await window.api.post('/api/ca/auth/signup', payload);
            onDone(session);
        } catch (err) {
            let msg = err.detail || 'Signup failed. Try again.';
            if (err.code === 'conflict') msg = err.detail;
            if (err.code === 'validation_failed') msg = err.detail;
            showError(form, msg);
        } finally {
            btn.disabled = false;
        }
    }

    async function handleLogin(form, onDone) {
        showError(form, null);
        const data = new FormData(form);
        const payload = {
            email: data.get('email').trim(),
            password: data.get('password'),
        };
        const btn = form.querySelector('button.primary');
        btn.disabled = true;
        try {
            const session = await window.api.post('/api/ca/auth/login', payload);
            onDone(session);
        } catch (err) {
            let msg = 'Could not sign in.';
            if (err.code === 'authentication_failed') msg = 'Invalid email or password.';
            if (err.code === 'rate_limited') msg = 'Too many tries. Wait a moment and retry.';
            showError(form, msg);
        } finally {
            btn.disabled = false;
        }
    }

    global.caAuth = { handleSignup, handleLogin };
})(window);
