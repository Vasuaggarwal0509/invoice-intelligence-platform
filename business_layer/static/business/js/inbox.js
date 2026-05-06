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
        const actionBar = root.querySelector('[data-role="inbox-actionbar"]');
        const checkAll = root.querySelector('[data-role="check-all"]');
        const selectionCountEl = root.querySelector('[data-role="selection-count"]');
        const extractSelectedBtn = root.querySelector('[data-role="extract-selected"]');
        const extractAllBtn = root.querySelector('[data-role="extract-all"]');
        const extractStatusEl = root.querySelector('[data-role="extract-status"]');
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
        actionBar.hidden = false;

        const selected = new Set();
        function updateSelectionUi() {
            const n = selected.size;
            selectionCountEl.textContent = n + (n === 1 ? ' selected' : ' selected');
            extractSelectedBtn.disabled = n === 0;
            const eligibleBoxes = tbody.querySelectorAll('input.row-check:not(:disabled)');
            const allChecked = eligibleBoxes.length > 0 &&
                Array.from(eligibleBoxes).every((el) => el.checked);
            checkAll.checked = allChecked;
        }

        for (const it of payload.items) {
            const tr = document.createElement('tr');
            // Checkbox cell — click on the cell itself shouldn't open the
            // detail page even though the row otherwise navigates.
            const checkTd = document.createElement('td');
            checkTd.className = 'col-check';
            checkTd.addEventListener('click', (e) => e.stopPropagation());
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.className = 'row-check';
            cb.dataset.id = it.id;
            // Allow checking ANY row — extract is also a re-extract
            // affordance for already-extracted/failed rows.
            cb.addEventListener('change', () => {
                if (cb.checked) selected.add(it.id);
                else selected.delete(it.id);
                updateSelectionUi();
            });
            checkTd.appendChild(cb);
            tr.appendChild(checkTd);

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
            // Plain-language reason for failed/ignored rows. Renders
            // under the chip so the user can see WHY without clicking
            // through. failure_message is server-translated — never
            // raw rule names or technical slugs.
            if (it.failure_message) {
                const why = document.createElement('div');
                why.className = 'status-failure-msg';
                why.textContent = it.failure_message;
                statusTd.appendChild(why);
            }
            tr.appendChild(statusTd);

            tbody.appendChild(tr);
        }

        updateSelectionUi();

        checkAll.addEventListener('change', () => {
            const want = checkAll.checked;
            selected.clear();
            for (const cb of tbody.querySelectorAll('input.row-check:not(:disabled)')) {
                cb.checked = want;
                if (want) selected.add(cb.dataset.id);
            }
            updateSelectionUi();
        });

        function setExtractStatus(text, klass) {
            extractStatusEl.textContent = text || '';
            extractStatusEl.className = 'extract-status ' + (klass || '');
            extractStatusEl.hidden = !text;
        }
        async function runExtract(body, busyLabel) {
            extractSelectedBtn.disabled = true;
            extractAllBtn.disabled = true;
            setExtractStatus(busyLabel, 'busy');
            try {
                const r = await window.api.post('/api/inbox/extract', body);
                if (r.queued === 0) {
                    setExtractStatus('Nothing to extract — every bill is already done.', 'empty');
                } else {
                    setExtractStatus(
                        'Queued ' + r.queued + ' bill' + (r.queued === 1 ? '' : 's') +
                        ' — refreshing in a moment…',
                        'success'
                    );
                    setTimeout(() => render(root), 1800);
                }
            } catch (err) {
                setExtractStatus(err.detail || 'Could not start extraction.', 'error');
            } finally {
                extractAllBtn.disabled = false;
                updateSelectionUi();
            }
        }
        extractSelectedBtn.addEventListener('click', () => {
            if (selected.size === 0) return;
            runExtract({ message_ids: Array.from(selected) }, 'Queueing selected…');
        });
        extractAllBtn.addEventListener('click', () => {
            runExtract({ all_pending: true }, 'Queueing all pending bills…');
        });
    }

    global.inbox = { render };
})(window);
