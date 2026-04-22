// Inbox view — lists inbox_messages for the workspace.

(function (global) {
    'use strict';

    const STATUS_CHIPS = {
        queued:     ['queued',   'Queued'],
        extracting: ['extract',  'Extracting…'],
        extracted:  ['ok',       'Ready'],
        failed:     ['failed',   'Failed'],
        ignored:    ['ignored',  'Ignored'],
    };

    function fmtAmount(minor, currency) {
        if (minor == null) return '';
        const whole = (minor / 100).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        return (currency === 'INR' ? '₹' : (currency + ' ')) + whole;
    }

    async function render(root) {
        const tpl = document.getElementById('view-inbox');
        root.replaceChildren(tpl.content.cloneNode(true));
        const tbody = root.querySelector('[data-role="inbox-body"]');
        const emptyHint = root.querySelector('[data-role="empty-hint"]');
        tbody.replaceChildren();

        let payload;
        try {
            payload = await window.api.get('/api/inbox?limit=100');
        } catch (err) {
            emptyHint.textContent = 'Could not load your inbox. ' + (err.detail || '');
            emptyHint.hidden = false;
            return;
        }

        if (!payload.items || payload.items.length === 0) {
            emptyHint.hidden = false;
            return;
        }
        emptyHint.hidden = true;

        for (const it of payload.items) {
            const tr = document.createElement('tr');
            if (it.invoice_id) {
                tr.className = 'row-link';
                tr.addEventListener('click', () => {
                    window.location.hash = '#/invoice/' + encodeURIComponent(it.invoice_id);
                });
            }

            const sourceTd = document.createElement('td');
            sourceTd.textContent = it.source_kind;
            tr.appendChild(sourceTd);

            const fromTd = document.createElement('td');
            fromTd.textContent = it.subject || it.sender || '—';
            tr.appendChild(fromTd);

            const vendorTd = document.createElement('td');
            vendorTd.textContent = it.vendor_name || '…';
            if (!it.vendor_name) vendorTd.classList.add('dim');
            tr.appendChild(vendorTd);

            const amountTd = document.createElement('td');
            amountTd.textContent = fmtAmount(it.total_amount_minor, it.currency) || '…';
            if (it.total_amount_minor == null) amountTd.classList.add('dim');
            tr.appendChild(amountTd);

            const statusTd = document.createElement('td');
            const [chipCls, chipText] = STATUS_CHIPS[it.status] || ['queued', it.status];
            const span = document.createElement('span');
            span.className = 'status-chip ' + chipCls;
            span.textContent = chipText;
            statusTd.appendChild(span);
            tr.appendChild(statusTd);

            tbody.appendChild(tr);
        }
    }

    global.inbox = { render };
})(window);
