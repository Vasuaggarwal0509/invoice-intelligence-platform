// Auth screens — phone entry + OTP verify. Wired by app.js.

(function (global) {
    'use strict';

    function showError(form, msg) {
        const el = form.querySelector('[data-role="error"]');
        if (!el) return;
        if (msg) {
            el.textContent = msg;
            el.hidden = false;
        } else {
            el.textContent = '';
            el.hidden = true;
        }
    }

    async function handlePhoneSubmit(form, state, onNext) {
        showError(form, null);
        const phone = form.elements['phone'].value.trim();
        if (!phone) {
            showError(form, 'Enter your phone number.');
            return;
        }
        const btn = form.querySelector('button.primary');
        btn.disabled = true;
        try {
            await api.post('/api/auth/otp/request', { phone });
            state.phone = phone;
            onNext();
        } catch (err) {
            showError(form, err.detail || 'Could not send the code. Try again.');
        } finally {
            btn.disabled = false;
        }
    }

    async function handleOtpSubmit(form, state, onDone) {
        showError(form, null);
        const code = form.elements['code'].value.trim();
        const displayName = form.elements['display_name'].value.trim();
        if (!/^\d{6}$/.test(code)) {
            showError(form, 'The code is 6 digits.');
            return;
        }
        const btn = form.querySelector('button.primary');
        btn.disabled = true;
        try {
            const payload = {
                phone: state.phone,
                code,
            };
            if (displayName) payload.display_name = displayName;
            const session = await api.post('/api/auth/otp/verify', payload);
            onDone(session);
        } catch (err) {
            // Business owners don't read tax jargon; normalise messages
            // to a small set of plain-language variants.
            let msg = err.detail || 'Something went wrong. Try again.';
            if (err.code === 'authentication_failed') msg = 'That code is not right or has expired.';
            if (err.code === 'business_rule_violated') msg = 'Enter your business name to continue.';
            if (err.code === 'rate_limited') msg = 'Too many tries. Please wait a moment.';
            showError(form, msg);
        } finally {
            btn.disabled = false;
        }
    }

    global.auth = {
        handlePhoneSubmit,
        handleOtpSubmit,
    };
})(window);
