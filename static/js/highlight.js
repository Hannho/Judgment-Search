function getSelectionInfo() {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;

    const body = document.getElementById('sideBody');
    const range = sel.getRangeAt(0);
    if (!body.contains(range.startContainer) || !body.contains(range.endContainer)) return null;

    const pre = document.createRange();
    pre.selectNodeContents(body);
    pre.setEnd(range.startContainer, range.startOffset);
    let start = pre.toString().length;
    let text = range.toString();

    const lead = text.length - text.trimStart().length;
    text = text.trim();
    if (!text) return null;
    start += lead;

    const item = judgmentsData.find(j => j.id === currentSideId);
    const full = getSideText(item);
    if (full.substring(start, start + text.length) !== text) {
        const i = full.indexOf(text);
        if (i === -1) return null;
        start = i;
    }

    const rects = range.getClientRects();
    const rect = rects.length ? rects[rects.length - 1] : range.getBoundingClientRect();
    return { start: start, end: start + text.length, text: text, rect: rect };
}

function placeFloating(el, rect) {
    el.style.display = 'block';
    const w = el.offsetWidth, h = el.offsetHeight;
    let left = rect.left;
    let top = rect.bottom + 8;
    if (left + w > window.innerWidth - 10) left = window.innerWidth - w - 10;
    if (left < 10) left = 10;
    if (top + h > window.innerHeight - 10) top = Math.max(10, rect.top - h - 8);
    el.style.left = left + 'px';
    el.style.top = top + 'px';
}

function hideAnnUI() {
    ['annMenu', 'annNoteBox', 'annPopover'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    pendingSel = null;
    editingAnnIndex = null;
}

document.addEventListener('keydown', function (e) {
    const menu = document.getElementById('annMenu');
    if (!menu) return;
    const menuOpen = menu.style.display === 'block';

    if (e.key === 'Escape') { hideAnnUI(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    if (menuOpen) {
        const k = e.key.toLowerCase();
        if (k === 'h' || k === '1') { e.preventDefault(); applyHighlightFromMenu(); return; }
        if (k === 'n' || k === '2') { e.preventDefault(); startNoteFromMenu(); return; }
        if (e.key === ' ') { e.preventDefault(); hideAnnUI(); }
        return;
    }

    if (e.key !== ' ' || e.shiftKey) return;
    if (!currentSideId || document.getElementById('sidePanel').style.display === 'none') return;

    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || tag === 'button' || e.target.isContentEditable) return;

    const info = getSelectionInfo();
    if (!info) return;     

    e.preventDefault();
    if (!currentUser) {
        alert("請先在右上角選擇使用者，重點與註解才能儲存。");
        return;
    }
    pendingSel = info;
    placeFloating(menu, info.rect);
});

document.addEventListener('mousedown', function (e) {
    if (e.target.closest('#annMenu, #annNoteBox, #annPopover')) return;
    hideAnnUI();
});

document.getElementById('sidePanel')?.addEventListener('scroll', function () {
    const menu = document.getElementById('annMenu');
    const pop = document.getElementById('annPopover');
    if(menu) menu.style.display = 'none';
    if(pop) pop.style.display = 'none';
});

async function applyHighlightFromMenu() {
    const info = pendingSel;
    hideAnnUI();
    if (!info) return;
    currentHighlights.push({ type: 'highlight', start: info.start, end: info.end, text: info.text });
    window.getSelection().removeAllRanges();
    renderHighlights();
    await saveHighlightsToBackend();
}

function startNoteFromMenu() {
    if (!pendingSel) return;
    document.getElementById('annMenu').style.display = 'none';
    editingAnnIndex = null;
    openNoteBox(pendingSel.text, "", pendingSel.rect);
}

function openNoteBox(quoteText, noteText, rect) {
    const box = document.getElementById('annNoteBox');
    const shortQuote = quoteText.length > 60 ? quoteText.substring(0, 60) + '…' : quoteText;
    document.getElementById('annNoteQuote').textContent = shortQuote;
    document.getElementById('annNoteInput').value = noteText;
    placeFloating(box, rect);
    document.getElementById('annNoteInput').focus();
}

function handleNoteKeyDown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        saveNoteFromBox();
    }
}

async function saveNoteFromBox() {
    const note = document.getElementById('annNoteInput').value.trim();
    if (!note) { alert('請輸入註解內容'); return; }

    if (editingAnnIndex !== null) {
        const a = currentHighlights[editingAnnIndex];
        if (a && typeof a === 'object') a.note = note;
    } else if (pendingSel) {
        currentHighlights.push({
            type: 'note', start: pendingSel.start, end: pendingSel.end,
            text: pendingSel.text, note: note
        });
        window.getSelection().removeAllRanges();
    }
    hideAnnUI();
    renderHighlights();
    await saveHighlightsToBackend();
}

document.getElementById('sideBody')?.addEventListener('click', function (e) {
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) return;          
    const el = e.target.closest('.ann');
    if (!el) return;
    const idxs = (el.dataset.idx || '').split(',').filter(Boolean).map(Number);
    showAnnPopover(idxs, e.clientX, e.clientY);
});

function showAnnPopover(idxs, x, y) {
    const pop = document.getElementById('annPopover');
    const html = idxs.map(i => {
        const a = currentHighlights[i];
        if (a === undefined) return '';
        const isStr = typeof a === 'string';
        const type = isStr ? 'highlight' : (a.type || 'highlight');
        const txt = isStr ? a : (a.text || '');
        const q = escapeHtml(txt.length > 40 ? txt.substring(0, 40) + '…' : txt);

        if (type === 'note') {
            return `<div class="ann-pop-item">
                <div class="ann-pop-head">📝 文字註解 <span class="ann-pop-quote">「${q}」</span></div>
                <div class="ann-pop-note">${escapeHtml(a.note || '')}</div>
                <div class="ann-pop-actions">
                    <a onclick="editAnnotation(${i})">編輯</a>
                    <a onclick="removeAnnotation(${i})" style="color:#d32f2f;">刪除</a>
                </div>
            </div>`;
        }
        return `<div class="ann-pop-item">
            <div class="ann-pop-head">🖍️ 螢光筆 <span class="ann-pop-quote">「${q}」</span></div>
            <div class="ann-pop-actions">
                <a onclick="removeAnnotation(${i})" style="color:#d32f2f;">取消重點</a>
            </div>
        </div>`;
    }).join('');
    if (!html) return;
    pop.innerHTML = html;
    placeFloating(pop, { left: x, top: y, bottom: y });
}

function editAnnotation(idx) {
    const a = currentHighlights[idx];
    if (!a || typeof a !== 'object') return;
    const pop = document.getElementById('annPopover');
    const rect = pop.getBoundingClientRect();
    hideAnnUI();
    editingAnnIndex = idx;
    openNoteBox(a.text || '', a.note || '', rect);
}

async function removeAnnotation(idx) {
    const a = currentHighlights[idx];
    if (a === undefined) return;
    const isNote = (typeof a === 'object' && a.type === 'note');
    if (!confirm(isNote ? "確定要刪除這則文字註解嗎？" : "確定要取消這段重點嗎？")) return;
    currentHighlights.splice(idx, 1);
    hideAnnUI();
    renderHighlights();
    await saveHighlightsToBackend();
}

async function removeHighlight(index) {
    await removeAnnotation(index);
}

async function loadSideHighlights(id) {
    if (!currentUser) return;
    try {
        const res = await fetch(`/api/highlights/${encodeURIComponent(id)}`, { headers: apiHeaders() });
        const data = await res.json();
        if (currentSideId !== id) return;        
        currentHighlights = (data && Array.isArray(data.data)) ? data.data : [];
        renderHighlights();
    } catch (e) {
        console.error("載入重點失敗", e);
    }
}

function resolveAnnotations(text) {
    const out = [];
    currentHighlights.forEach((h, idx) => {
        if (typeof h === 'string') {
            const trimmed = h.trim();
            if (!trimmed) return;
            const pattern = escapeRegExp(trimmed).replace(/\s+/g, '\\s+');
            let re;
            try { re = new RegExp(pattern, 'g'); } catch (e) { return; }
            for (const m of text.matchAll(re)) {
                if (m[0].length === 0) continue;
                out.push({ idx: idx, s: m.index, e: m.index + m[0].length, type: 'highlight' });
            }
            return;
        }
        if (!h || typeof h !== 'object' || !h.text) return;
        let s = h.start, e = h.end;
        if (!(Number.isInteger(s) && Number.isInteger(e) && s >= 0 && e > s && e <= text.length && text.substring(s, e) === h.text)) {
            const i = text.indexOf(h.text);
            if (i === -1) return;
            s = i; e = i + h.text.length;
        }
        out.push({ idx: idx, s: s, e: e, type: h.type === 'note' ? 'note' : 'highlight' });
    });
    return out;
}

function renderHighlights() {
    if (!currentSideId) return;
    const item = judgmentsData.find(j => j.id === currentSideId);
    if (!item) return;

    const body = document.getElementById('sideBody');
    const panel = document.getElementById('sidePanel');
    const scrollTop = panel.scrollTop;
    const text = getSideText(item);
    const anns = resolveAnnotations(text);

    if (anns.length === 0) {
        body.textContent = text;
        panel.scrollTop = scrollTop;
        return;
    }

    const cuts = new Set([0, text.length]);
    anns.forEach(a => { cuts.add(a.s); cuts.add(a.e); });
    const points = Array.from(cuts).sort((x, y) => x - y);

    let html = "";
    for (let i = 0; i < points.length - 1; i++) {
        const s = points[i], e = points[i + 1];
        if (s >= e) continue;
        const piece = escapeHtml(text.substring(s, e));
        const cover = anns.filter(a => a.s <= s && a.e >= e);
        if (cover.length === 0) { html += piece; continue; }

        const hasHighlight = cover.some(a => a.type === 'highlight');
        const notes = cover.filter(a => a.type === 'note');
        const cls = ['ann'];
        if (hasHighlight) cls.push('highlight-mark');
        if (notes.length > 0) cls.push('ann-note');
        if (notes.some(a => a.e === e)) cls.push('ann-note-end');

        const tagName = hasHighlight ? 'mark' : 'span';
        const idxs = Array.from(new Set(cover.map(a => a.idx))).join(',');
        html += `<${tagName} class="${cls.join(' ')}" data-idx="${idxs}">${piece}</${tagName}>`;
    }
    body.innerHTML = html;
    panel.scrollTop = scrollTop;
}

async function clearAllHighlights() {
    if (!currentSideId || !currentUser) return;
    if (currentHighlights.length === 0) return;
    if (!confirm("確定要清除這篇判決的所有重點與文字註解嗎？")) return;

    currentHighlights = [];
    hideAnnUI();
    renderHighlights();
    await saveHighlightsToBackend();
}

async function saveHighlightsToBackend() {
    if (!currentSideId || !currentUser) return;
    try {
        await fetch(`/api/highlights/${encodeURIComponent(currentSideId)}`, {
            method: 'POST',
            headers: apiHeaders(),
            body: JSON.stringify({ highlights: currentHighlights })
        });
    } catch (e) {
        console.error("重點儲存失敗", e);
    }
}