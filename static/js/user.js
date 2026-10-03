function isFav(id) { return Object.prototype.hasOwnProperty.call(favMap, id); }
function updateFavCount() {
    const el = document.getElementById('favCount');
    if (el) el.textContent = `(${Object.keys(favMap).length})`;
}
function updateSideStar() {
    const el = document.getElementById('sideFavStar');
    if (el && currentSideId) el.textContent = isFav(currentSideId) ? '⭐' : '☆';
}
function refreshListStars() {
    document.querySelectorAll('.fav-star').forEach(el => {
        el.textContent = isFav(el.dataset.id) ? '⭐' : '☆';
    });
}
function refreshFavUI() {
    updateFavCount();
    updateSideStar();
    if (isFavoritesMode) { showFavorites(); } else { refreshListStars(); }
}

async function loadUsers(selectId) {
    try {
        const res = await fetch('/api/users');
        usersList = (await res.json()).data || [];
    } catch (e) {
        console.error(e);
        usersList = [];
    }
    const sel = document.getElementById('userSelect');
    sel.innerHTML = '<option value="">— 選擇使用者 —</option>' +
        usersList.map(u => `<option value="${u.id}">${escapeHtml(u.name)}</option>`).join('');
    const target = (selectId !== undefined) ? selectId : localStorage.getItem('current_user_id');
    const u = usersList.find(x => String(x.id) === String(target)) || null;
    sel.value = u ? u.id : "";
    await applyUser(u);
}

async function applyUser(u) {
    currentUser = u;
    favMap = {};
    foldersList = [];
    if (u) {
        localStorage.setItem('current_user_id', u.id);
        try {
            await loadFolders();
            const res = await fetch('/api/favorites', { headers: apiHeaders() });
            ((await res.json()).data || []).forEach(f => {
                favMap[f.judgment_id] = { note: f.note, folder_id: f.folder_id, folder_name: f.folder_name };
            });
        } catch (e) { console.error(e); }
    } else {
        localStorage.removeItem('current_user_id');
    }
    refreshFavUI();
}

async function editUser() {
    if (!currentUser) {
        alert("請先在下拉選單選擇一位要編輯的使用者！");
        return;
    }
    
    const newName = prompt("請輸入新的使用者名稱：", currentUser.name);
    if (!newName || !newName.trim() || newName.trim() === currentUser.name) {
        return;
    }
    
    try {
        const res = await fetch(`/api/users/${currentUser.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName.trim() })
        });
        const data = await res.json();
        if (data.error) { alert(data.error); return; }
        
        await loadUsers(currentUser.id);
        if (isFavoritesMode) showFavorites();
        
    } catch (e) {
        alert('編輯使用者失敗，請稍後再試');
    }
}

async function deleteUser() {
    if (!currentUser) {
        alert("請先在下拉選單選擇一位要刪除的使用者！");
        return;
    }
    
    const confirmMsg = `⚠️ 警告：確定要永久刪除使用者「${currentUser.name}」嗎？\n\n這項操作將會清空該帳號底下的【所有資料夾】與【所有收藏紀錄】，且無法復原！`;
    if (!confirm(confirmMsg)) return;
    
    try {
        const res = await fetch(`/api/users/${currentUser.id}`, {
            method: 'DELETE'
        });
        const data = await res.json();
        if (data.error) { alert(data.error); return; }
        
        localStorage.removeItem('current_user_id');
        currentUser = null;
        isFavoritesMode = false; 
        
        await loadUsers(""); 
        document.getElementById('sidePanel').style.display = 'none';
        fetchJudgments(1);
        
        alert("使用者與其所有資料已成功刪除！");
    } catch (e) {
        alert('刪除使用者失敗，請稍後再試');
    }
}

function onUserChange(sel) {
    applyUser(usersList.find(x => String(x.id) === sel.value) || null);
}

async function addUser() {
    const name = prompt("輸入新使用者名稱：");
    if (!name || !name.trim()) return;
    try {
        const res = await fetch('/api/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name.trim() })
        });
        const data = await res.json();
        if (data.error) { alert(data.error); return; }
        await loadUsers(data.user.id);
    } catch (e) {
        alert('新增使用者失敗，請稍後再試');
    }
}

async function loadFolders() {
    try {
        const res = await fetch('/api/folders', { headers: apiHeaders() });
        foldersList = (await res.json()).data || [];
    } catch (e) { console.error(e); }
}

async function createNewFolder() {
    const name = prompt("輸入新資料夾名稱：");
    if (!name || !name.trim()) return;
    try {
        const res = await fetch('/api/folders', {
            method: 'POST',
            headers: apiHeaders(),
            body: JSON.stringify({ name: name.trim() })
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        await loadFolders();
        updateFolderSelect(data.folder.id);
    } catch (e) {
        alert('建立資料夾失敗: ' + e.message);
    }
}

function updateFolderSelect(selectedId = null) {
    const sel = document.getElementById('favFolderSelect');
    sel.innerHTML = '<option value="">（未分類）</option>' +
        foldersList.map(f => `<option value="${f.id}">${escapeHtml(f.name)}</option>`).join('');
    if (selectedId) sel.value = selectedId;
}

function openFavModal(id) {
    if (!currentUser) { alert("請先在右上角選擇使用者"); return; }
    
    const item = judgmentsData.find(j => j.id === id);
    if (!item) return;

    const idParts = item.id.split(',');
    const yr = item.year || idParts[1] || "";
    const tp = item.case_type || idParts[2] || "";
    const no = item.case_no || idParts[3] || "";
    const title = `${getCourtName(item)} ${yr} 年度 ${tp} 字第 ${no} 號`;

    document.getElementById('favJudgmentId').value = id;
    document.getElementById('favTitleDisplay').value = title;
    
    updateFolderSelect();

    const isEditing = isFav(id);
    document.getElementById('favModalTitle').textContent = isEditing ? '編輯書籤' : '新增書籤';
    document.getElementById('btnRemoveFav').style.display = isEditing ? 'block' : 'none';

    if (isEditing) {
        const favData = favMap[id];
        document.getElementById('favFolderSelect').value = favData.folder_id || "";
        document.getElementById('favNoteInput').value = favData.note || "";
    } else {
        document.getElementById('favFolderSelect').value = "";
        document.getElementById('favNoteInput').value = "";
    }

    document.getElementById('favModal').style.display = 'flex';
}

function closeFavModal() {
    document.getElementById('favModal').style.display = 'none';
}

async function saveFavFromModal() {
    const id = document.getElementById('favJudgmentId').value;
    const folderIdStr = document.getElementById('favFolderSelect').value;
    const note = document.getElementById('favNoteInput').value.trim();
    const folderId = folderIdStr ? parseInt(folderIdStr, 10) : null;

    try {
        const res = await fetch('/api/favorites', {
            method: 'POST',
            headers: apiHeaders(),
            body: JSON.stringify({ judgment_id: id, folder_id: folderId, note: note })
        });
        if (!res.ok) throw new Error('伺服器回應錯誤');
        
        const folderName = folderId ? foldersList.find(f => f.id === folderId)?.name : null;
        favMap[id] = { note: note, folder_id: folderId, folder_name: folderName };
        
        closeFavModal();
        refreshFavUI();
    } catch (e) {
        alert('儲存失敗，請稍後再試');
    }
}

async function removeFavFromModal() {
    const id = document.getElementById('favJudgmentId').value;
    if (!confirm("確定要移除此收藏嗎？")) return;
    
    try {
        const res = await fetch('/api/favorites?judgment_id=' + encodeURIComponent(id), { 
            method: 'DELETE', 
            headers: apiHeaders() 
        });
        if (!res.ok) throw new Error('伺服器回應錯誤');
        
        delete favMap[id];
        closeFavModal();
        refreshFavUI();
    } catch (e) {
        alert('移除失敗，請稍後再試');
    }
}

function toggleFav(id) {
    openFavModal(id);
}

function enterFavorites() {
    if (!currentUser) { alert("請先在右上角選擇使用者"); return; }
    isFavoritesMode = true;
    document.getElementById('facetSidebar').style.display = 'none';
    document.getElementById('sidePanel').style.display = 'none';
    showFavorites();
}

async function showFavorites(filterFolderId = 'ALL') {
    const resultsDiv = document.getElementById('results');
    resultsDiv.innerHTML = '<p>⏳ 載入收藏中...</p>';
    try {
        const favRes = await fetch('/api/favorites', { headers: apiHeaders() });
        const favListRaw = (await favRes.json()).data || [];
        
        favMap = {};
        favListRaw.forEach(f => favMap[f.judgment_id] = { note: f.note, folder_id: f.folder_id, folder_name: f.folder_name });
        updateFavCount();

        let favList = favListRaw;
        if (filterFolderId === 'NONE') {
            favList = favListRaw.filter(f => !f.folder_id);
        } else if (filterFolderId !== 'ALL') {
            favList = favListRaw.filter(f => String(f.folder_id) === String(filterFolderId));
        }

        if (favList.length === 0) {
            judgmentsData = [];
            resultsDiv.innerHTML = `
                <div class="table-toolbar">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span>📁 ${escapeHtml(currentUser.name)} 的案件</span>
                        ${renderFolderFilter(filterFolderId)}
                    </div>
                    <button class="btn-toggle" onclick="exitFavorites()">← 回到搜尋結果</button>
                </div>
                <p style="padding:20px; color:#666;">此資料夾尚未收藏任何判決。</p>`;
            return;
        }

        const res = await fetch('/api/judgments/by_ids', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: favList.map(f => f.judgment_id) })
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        judgmentsData = data.data;

        let html = `
            <div class="table-toolbar">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span>📁 ${escapeHtml(currentUser.name)} 的案件，共 <strong>${judgmentsData.length}</strong> 筆</span>
                    ${renderFolderFilter(filterFolderId)}
                </div>
                <div>
                    <button class="btn-primary" style="padding: 6px 14px; background: #2e7d32;" onclick="exportSelectedJudgments()">📥 匯出選取判決</button>
                    <button class="btn-toggle" onclick="exitFavorites()">← 回到搜尋結果</button>
                </div>
            </div>
            <table class="result-table"><thead><tr>
                <th width="4%" style="text-align:center;"><input type="checkbox" id="selectAll" onclick="toggleSelectAll(this)" title="全選/取消全選"></th>
                <th width="6%" style="text-align:center;">收藏</th>
                <th width="50%">裁判字號 (資料夾/備註)</th>
                <th width="15%">日期</th>
                <th width="25%">案由</th></tr></thead><tbody>`;

        judgmentsData.forEach(item => {
            const idParts = item.id.split(',');
            const yr = item.year || idParts[1] || "";
            const tp = item.case_type || idParts[2] || "";
            const no = item.case_no || idParts[3] || "";
            const title = `${getCourtName(item)} ${yr} 年度 ${tp} 字第 ${no} 號${getDocumentKind(item)}`;
            
            const favData = favMap[item.id] || {};
            const folderLabel = favData.folder_name ? `<span style="background:#e3f2fd; padding:2px 6px; border-radius:4px; font-size:0.85em; margin-right:5px;">📁 ${escapeHtml(favData.folder_name)}</span>` : '';
            const noteLabel = favData.note ? `<span style="color:#e65100; word-break: break-all; white-space: pre-wrap; display: inline-block;">📝 ${escapeHtml(favData.note)}</span>` : `<span style="color:#aaa;">（無備註）</span>`;
            html += `<tr>
                <td style="text-align:center;"><input type="checkbox" class="judgment-cb" value="${item.id}"></td>
                <td style="text-align:center;">
                    <span style="cursor:pointer; font-size:1.3em;" onclick="openFavModal('${item.id}')" title="編輯收藏">⭐</span>
                </td>
                <td>
                    <a class="result-title-link" onclick="showFullContent('${item.id}')">${title}</a>
                    <div class="snippet">${folderLabel}${noteLabel}
                        <a style="cursor:pointer; color:#1976d2; font-size:0.9em; margin-left:8px;" onclick="openFavModal('${item.id}')">[編輯]</a>
                    </div>
                </td>
                <td>${formatROCDate(item.date)}</td>
                <td>${item.title || "無案由"}</td>
            </tr>`;
        });
        resultsDiv.innerHTML = html + '</tbody></table>';
    } catch (e) {
        resultsDiv.innerHTML = `<p style="color:red;">❌ 載入收藏失敗：${escapeHtml(e.message)}</p>`;
    }
}

function renderFolderFilter(currentVal) {
    let opts = `<option value="ALL" ${currentVal==='ALL'?'selected':''}>全部收藏</option>
                <option value="NONE" ${currentVal==='NONE'?'selected':''}>（未分類）</option>`;
    foldersList.forEach(f => {
        opts += `<option value="${f.id}" ${String(currentVal)===String(f.id)?'selected':''}>📁 ${escapeHtml(f.name)}</option>`;
    });
    return `<select style="margin-left: 15px; padding: 5px;" onchange="showFavorites(this.value)">${opts}</select>`;
}

function exitFavorites() {
    isFavoritesMode = false;
    fetchJudgments(1);
}

function exportSelectedJudgments() {
    const checkedBoxes = document.querySelectorAll('.judgment-cb:checked');
    if (checkedBoxes.length === 0) {
        alert("請先勾選想要匯出的判決書！");
        return;
    }

    const selectedIds = Array.from(checkedBoxes).map(cb => cb.value);
    const selectedItems = judgmentsData.filter(item => selectedIds.includes(item.id));

    let exportText = `=================================================\n`;
    exportText += `  裁判書選取匯出清單\n`;
    exportText += `  匯出使用者：${currentUser ? currentUser.name : "未知"}\n`;
    exportText += `  匯出筆數：${selectedItems.length} 筆\n`;
    exportText += `  匯出日期：${new Date().toLocaleDateString()}\n`;
    exportText += `=================================================\n\n`;

    selectedItems.forEach((item, idx) => {
        const idParts = item.id.split(',');
        const yr = item.year || idParts[1] || "";
        const tp = item.case_type || idParts[2] || "";
        const no = item.case_no || idParts[3] || "";
        const courtName = getCourtName(item);
        const docKind = getDocumentKind(item);
        const fullTitle = `${courtName} ${yr} 年度 ${tp} 字第 ${no} 號${docKind}`;

        const mainText = item.main_text && item.main_text.trim() ? item.main_text.trim() : "（無記載主文）";
        const reason = item.reason && item.reason.trim() ? item.reason.trim() : (item.content || "（無內文）");

        exportText += `-------------------------------------------------\n`;
        exportText += `【案件 ${idx + 1}】\n`;
        exportText += `【裁判案號】：${fullTitle}\n`;
        exportText += `【裁判日期】：${formatROCDate(item.date)}\n`;
        exportText += `【裁判案由】：${item.title || "無案由"}\n`;
        exportText += `【主文】：\n${mainText}\n\n`;
        exportText += `【理由】：\n${reason}\n`;
        exportText += `-------------------------------------------------\n\n`;
    });

    const blob = new Blob([exportText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `裁判書匯出_${currentUser ? currentUser.name : "案件"}_${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}