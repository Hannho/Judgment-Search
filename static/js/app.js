// ==========================================
// 頁面初始化
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    const courtSelect = document.getElementById('courtInput');
    for (const [code, name] of Object.entries(courtMapping)) {
        const option = document.createElement('option');
        option.value = code;
        option.textContent = name;
        courtSelect.appendChild(option);
    }
    currentSearchPayload = {};
    fetchJudgments(1);
    loadUsers();
});

function toggleAdvancedSearch() {
    const panel = document.getElementById('advancedPanel');
    const toggleText = document.getElementById('toggleText');
    if (panel.style.display === 'none') {
        panel.style.display = 'block';
        toggleText.textContent = '收起進階搜尋';
    } else {
        panel.style.display = 'none';
        toggleText.textContent = '展開進階搜尋';
    }
}

function parseKeywords(inputStr) {
    if (!inputStr) return [];
    const cleanStr = inputStr.replace(/[+\-&()]/g, ' ');
    return cleanStr.trim().split(/[\s\u3000]+/).filter(k => k.length > 0);
}

function generateHighlightedSnippet(text, keywords, maxLength = 110) {
    if (!text || text.trim() === "") return "";
    let firstMatchIndex = -1;
    for (const kw of keywords) {
        if (!kw) continue;
        const idx = text.indexOf(kw);
        if (idx !== -1 && (firstMatchIndex === -1 || idx < firstMatchIndex)) {
            firstMatchIndex = idx;
        }
    }

    let snippet = "";
    if (firstMatchIndex !== -1) {
        const start = Math.max(0, firstMatchIndex - 25);
        const end = Math.min(text.length, start + maxLength);
        snippet = text.substring(start, end);
        if (start > 0) snippet = "..." + snippet;
        if (end < text.length) snippet = snippet + "...";
    } else {
        snippet = text.length > maxLength ? text.substring(0, maxLength) + "..." : text;
    }

    for (const kw of keywords) {
        if (!kw) continue;
        const safeKw = escapeRegExp(kw);
        const regex = new RegExp(`(${safeKw})`, 'gi');
        snippet = snippet.replace(regex, `<span class="highlight-kw">$1</span>`);
    }
    return snippet;
}

function handleSortChange() {
    fetchJudgments(1, false);
}

function resetSearch() {
    isFavoritesMode = false;
    clearSearchError();
    currentSearchKeywords = [];
    document.getElementById('courtInput').value = "";
    document.getElementById('quickKeywordInput').value = "";
    document.querySelectorAll('input[name="caseCategory"]').forEach(cb => cb.checked = false);
    document.querySelector('input[name="docType"][value=""]').checked = true;
    document.getElementById('advYear').value = "";
    document.getElementById('advCaseType').value = "";
    document.getElementById('advNoStart').value = "";
    document.getElementById('advNoEnd').value = "";
    document.getElementById('startYear').value = "";
    document.getElementById('startMonth').value = "";
    document.getElementById('startDay').value = "";
    document.getElementById('endYear').value = "";
    document.getElementById('endMonth').value = "";
    document.getElementById('endDay').value = "";
    document.getElementById('advTitle').value = "";
    document.getElementById('advMainText').value = "";
    document.getElementById('advContent').value = "";
    document.getElementById('advSizeMin').value = "";
    document.getElementById('advSizeMax').value = "";

    currentSearchPayload = {};
    
    const sortSelect = document.getElementById('tableSortSelect');
    if (sortSelect) sortSelect.value = "date_desc";
    const selectAllCb = document.getElementById('selectAll');
    if (selectAllCb) selectAllCb.checked = false;

    fetchJudgments(1);
    document.getElementById('sidePanel').style.display = "none";
}

function parseRocToDateInt(y, m, d, isEndDate = false) {
    if (!y) return null;
    const rocY = parseInt(y, 10);
    if (isNaN(rocY) || rocY < 1 || rocY > 200) {
        throw new Error("民國年份格式不正確（例如請填寫 114 或 115）");
    }
    
    let month = m ? parseInt(m, 10) : (isEndDate ? 12 : 1);
    let day = d ? parseInt(d, 10) : (isEndDate ? 31 : 1);

    if (isNaN(month) || month < 1 || month > 12) {
        throw new Error("月份格式錯誤，請填寫 1 至 12 之間的數值");
    }
    if (isNaN(day) || day < 1 || day > 31) {
        throw new Error("日期格式錯誤，請填寫 1 至 31 之間的數值");
    }

    const fullYear = rocY + 1911;
    const fullMonth = String(month).padStart(2, '0');
    const fullDay = String(day).padStart(2, '0');
    return parseInt(`${fullYear}${fullMonth}${fullDay}`, 10);
}

function renderFacets(facets) {
    if (isFavoritesMode) return;
    const sidebar = document.getElementById('facetSidebar');
    sidebar.style.opacity = '1';

    if (totalItems === 0 || !facets || Object.keys(facets.courts || {}).length === 0) {
        sidebar.style.display = 'none';
        return;
    }
    
    sidebar.style.display = 'block';
    let html = `<h3 style="color: #4a148c; margin-top: 5px; font-size: 1.1em;">» 查詢結果 <span class="facet-badge" style="float:right; font-size: 0.9em;">${totalItems} 筆</span></h3>`;

    html += generateFacetGroup('依裁判法院區分', facets.courts, (code) => courtMapping[code] || code, 'court');
    html += generateFacetGroup('依裁判案號年度區分', facets.years, (year) => year, 'year');
    html += generateFacetGroup('依案件類別區分', facets.categories, (cat) => cat, 'category');

    sidebar.innerHTML = html;
}

function generateFacetGroup(title, dataObj, formatKeyFn, type) {
    if (!dataObj) return '';
    let keys = Object.keys(dataObj);
    
    if (type === 'year') {
        const yearOrder = ['今年', '去年', '前年', '其他'];
        keys.sort((a, b) => {
            let indexA = yearOrder.findIndex(y => a.includes(y));
            let indexB = yearOrder.findIndex(y => b.includes(y));
            return indexA - indexB;
        });
    } else {
        keys.sort((a, b) => dataObj[b] - dataObj[a]); 
    }

    if (keys.length === 0) return '';

    let listHtml = keys.map(k => `
        <li onclick="applyFacetFilter('${type}', '${k}')">
            <span>» ${formatKeyFn(k)}</span>
            <span class="facet-badge">${dataObj[k]}</span>
        </li>
    `).join('');

    return `
        <div class="facet-group">
            <div class="facet-header collapsed" onclick="this.classList.toggle('collapsed'); this.nextElementSibling.style.display = this.classList.contains('collapsed') ? 'none' : 'block';">
                ${title}
            </div>
            <ul class="facet-list" style="display: none;">${listHtml}</ul>
        </div>
    `;
}

function applyFacetFilter(type, value) {
    if (type === 'court') {
        document.getElementById('courtInput').value = value;
    } else if (type === 'year') {
        let actualYear = value;
        if (value.includes('(')) {
            actualYear = value.split('(')[1].replace(')', '');
        }
        document.getElementById('advYear').value = actualYear;
    } else if (type === 'category') {
        const checkboxes = document.querySelectorAll('input[name="caseCategory"]');
        checkboxes.forEach(cb => { cb.checked = (cb.value === value); });
    }
    searchJudgments();
}

async function fetchJudgments(page = 1, refreshStats = true) {
    currentSearchPayload.page = page;
    currentSearchPayload.sort_type = document.getElementById('tableSortSelect')?.value || "date_desc";

    try {
        document.getElementById('results').innerHTML = '<p>⏳ 正在從資料庫撈取前 10 筆資料，請稍候...</p>';
        const sidebar = document.getElementById('facetSidebar');
        if (refreshStats) {
            sidebar.style.display = 'block';
            if (sidebar.innerHTML.trim() === '') {
                sidebar.innerHTML = '<p style="padding: 15px; color: #666; font-weight: bold;">⏳ 全庫資料統計中...</p>';
            } else {
                sidebar.style.opacity = '0.5';   
            }
        }

        const listResponse = await fetch('/api/judgments/list', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentSearchPayload)
        });

        if (!listResponse.ok) throw new Error("伺服器回應錯誤");
        
        const listData = await listResponse.json();
        if (listData.error) throw new Error(listData.error);
        
        judgmentsData = listData.data.filter(item => item && item.id && item.id.trim() !== "");
        currentPage = page;
        totalItems = "計算中..."; 
        
        displayResults();
        
        if (refreshStats) {
            const statsResponse = await fetch('/api/judgments/stats', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(currentSearchPayload)
            });

            const statsData = await statsResponse.json();
            totalItems = statsData.total;

            displayResults();

            if (statsData.facets) renderFacets(statsData.facets);
        }
        
    } catch(e) {
        console.error(e);
        showSearchError(e.message);
        document.getElementById('results').innerHTML = `<p style="color:red;">❌ 無法從資料庫載入裁判書資料，請確認連線狀態。</p>`;
        document.getElementById('facetSidebar').style.display = 'none';
    }
}

async function searchJudgments() {
    isFavoritesMode = false;
    clearSearchError();

    const court = document.getElementById('courtInput').value;
    const checkedCategories = Array.from(document.querySelectorAll('input[name="caseCategory"]:checked')).map(cb => cb.value);
    const selectedDocType = document.querySelector('input[name="docType"]:checked')?.value || "";

    const advYear = document.getElementById('advYear').value.trim();
    const advCaseType = document.getElementById('advCaseType').value.trim();
    const advNoStart = document.getElementById('advNoStart').value.trim();
    const advNoEnd = document.getElementById('advNoEnd').value.trim();

    const quickKeyword = document.getElementById('quickKeywordInput').value;
    const advTitle = document.getElementById('advTitle').value;
    const advMainText = document.getElementById('advMainText').value;
    const advContent = document.getElementById('advContent').value;

    currentSearchKeywords = [];
    [...parseKeywords(quickKeyword), ...parseKeywords(advTitle), ...parseKeywords(advMainText), ...parseKeywords(advContent)].forEach(kw => {
        if (kw && !currentSearchKeywords.includes(kw)) {
            currentSearchKeywords.push(kw);
        }
    });

    let backendStartDate = "";
    let backendEndDate = "";
    let startDateInt = null;
    let endDateInt = null;

    try {
        const sY = document.getElementById('startYear').value.trim();
        const sM = document.getElementById('startMonth').value.trim();
        const sD = document.getElementById('startDay').value.trim();
        const eY = document.getElementById('endYear').value.trim();
        const eM = document.getElementById('endMonth').value.trim();
        const eD = document.getElementById('endDay').value.trim();

        if (sY || sM || sD) {
            startDateInt = parseRocToDateInt(sY, sM, sD, false);
            const y = parseInt(sY, 10) + 1911;
            const m = sM ? sM.padStart(2, '0') : '01';
            const d = sD ? sD.padStart(2, '0') : '01';
            backendStartDate = `${y}${m}${d}`;
        }
        
        if (eY || eM || eD) {
            endDateInt = parseRocToDateInt(eY, eM, eD, true);
            const y = parseInt(eY, 10) + 1911;
            const m = eM ? eM.padStart(2, '0') : '12';
            const d = eD ? eD.padStart(2, '0') : '31';
            backendEndDate = `${y}${m}${d}`;
        }

        if (startDateInt && endDateInt && startDateInt > endDateInt) {
            showSearchError("裁判期間錯誤：起始日期不得晚於結束日期。");
            return;
        }
    } catch (err) {
        showSearchError(err.message);
        return;
    }

    const advSizeMin = document.getElementById('advSizeMin').value.trim();
    const advSizeMax = document.getElementById('advSizeMax').value.trim();

    currentSearchPayload = {
        court: court,
        start_date: backendStartDate,
        end_date: backendEndDate,
        keyword: quickKeyword,
        year: advYear,
        title_kw: advTitle,
        content_kw: advContent,
        main_text_kw: advMainText,
        case_categories: checkedCategories,
        doc_type: selectedDocType,
        adv_case_type: advCaseType,
        adv_no_start: advNoStart !== "" ? parseInt(advNoStart, 10) : null,
        adv_no_end: advNoEnd !== "" ? parseInt(advNoEnd, 10) : null,
        adv_size_min: advSizeMin !== "" ? parseFloat(advSizeMin) : null,
        adv_size_max: advSizeMax !== "" ? parseFloat(advSizeMax) : null
    };

    fetchJudgments(1);
    document.getElementById('sidePanel').style.display = "none"; 
}

function toggleSelectAll(source) {
    const checkboxes = document.querySelectorAll('.judgment-cb');
    checkboxes.forEach(cb => {
        cb.checked = source.checked;
    });
}

function renderTableBody(data) {
    const tbody = document.getElementById('resultTableBody');
    if (!tbody) return;

    const totalNumeric = typeof totalItems === 'number' ? totalItems : 1000;
    const displayTotal = Math.min(totalNumeric, 1000);
    const totalPages = Math.ceil(displayTotal / itemsPerPage) || 1;
    const startIndex = (currentPage - 1) * itemsPerPage;

    let bodyHtml = "";
    data.forEach((item, index) => {
        const absoluteIndex = startIndex + index + 1;
        const idParts = item.id ? item.id.split(',') : [];
        const displayYear = (item.year && item.year.trim() !== "") ? item.year : (idParts[1] || "");
        const displayType = (item.case_type && item.case_type.trim() !== "") ? item.case_type : (idParts[2] || "");
        const displayNo = (item.case_no && item.case_no.trim() !== "") ? item.case_no : (idParts[3] || "");

        const courtName = getCourtName(item);
        const docKind = getDocumentKind(item);
        const fullTitle = `${courtName} ${displayYear} 年度 ${displayType} 字第 ${displayNo} 號${docKind}`;
        
        const contentText = item.content || "";
        const sizeKB = ((contentText.length * 2) / 1024).toFixed(1);
        const titleWithSize = `${fullTitle} <span style="color: #777; font-size: 0.85em; font-weight: normal;">(${sizeKB} KB)</span>`;

        const rocDate = formatROCDate(item.date);
        
        let displaySnippet = "";
        const hasKeywords = currentSearchKeywords.length > 0;

        if (!hasKeywords) {
            if (item.main_text && item.main_text.trim() !== "") {
                const cleanMainText = item.main_text.length > 130 ? item.main_text.substring(0, 130) + "..." : item.main_text;
                displaySnippet = `<span class="main-text-tag">【主文】</span> ${cleanMainText}`;
            } else if (item.content && item.content.trim() !== "") {
                const cleanContent = item.content.length > 110 ? item.content.substring(0, 110) + "..." : item.content;
                displaySnippet = `<span class="summary-tag">【摘要】</span> ${cleanContent}`;
            } else {
                displaySnippet = "<span style='color: #999;'>(此案件無內容)</span>";
            }
        } else {
            if (item.main_text && item.main_text.trim() !== "" && currentSearchKeywords.some(kw => item.main_text.includes(kw))) {
                const highlightedMain = generateHighlightedSnippet(item.main_text, currentSearchKeywords, 110);
                displaySnippet = `<span class="main-text-tag">【主文】</span> ${highlightedMain}`; 
            } else if (item.content && item.content.trim() !== "") {
                const highlightedContent = generateHighlightedSnippet(item.content, currentSearchKeywords, 110);
                displaySnippet = `<span class="summary-tag">【摘要】</span> ${highlightedContent}`;
            } else {
                displaySnippet = "<span style='color: #999;'>(此案件無內容)</span>";
            }
        }

        bodyHtml += `
            <tr>
                <td style="text-align:center;"><input type="checkbox" class="judgment-cb" value="${item.id}"></td>
                <td>${absoluteIndex}.<br>
                    <span class="fav-star" data-id="${item.id}" style="cursor:pointer; font-size:1.2em;" onclick="toggleFav('${item.id}')" title="加入/移除我的最愛">${isFav(item.id) ? '⭐' : '☆'}</span>
                </td>
                <td>
                    <a class="result-title-link" onclick="showFullContent('${item.id}')">${titleWithSize}</a>
                    <span class="snippet">${displaySnippet}</span>
                </td>
                <td>${rocDate}</td>
                <td>${item.title || "無案由"}</td>
            </tr>`;
    });
    tbody.innerHTML = bodyHtml;
    renderPaginationUI(totalPages);
}

function renderPaginationUI(totalPages) {
    let paginationDiv = document.getElementById('paginationControls');
    if (!paginationDiv) {
        paginationDiv = document.createElement('div');
        paginationDiv.id = 'paginationControls';
        paginationDiv.className = 'pagination-controls';
        document.getElementById('results').appendChild(paginationDiv);
    }

    if (judgmentsData.length === 0) {
        paginationDiv.innerHTML = "";
        return;
    }

    paginationDiv.innerHTML = `
        <button onclick="changePage(-1)" ${currentPage === 1 ? 'disabled' : ''}>⬅️ 上一頁</button>
        <span style="margin: 0 15px; font-weight: bold; color: #555;"> 第 ${currentPage} 頁 / 共 ${totalPages} 頁 </span>
        <button onclick="changePage(1)" ${currentPage === totalPages ? 'disabled' : ''}>下一頁 ➡️</button>
    `;
}

function changePage(delta) {
    const totalNumeric = typeof totalItems === 'number' ? totalItems : 1000;
    const displayTotal = Math.min(totalNumeric, 1000);
    const totalPages = Math.ceil(displayTotal / itemsPerPage) || 1;
    let newPage = currentPage + delta;
    
    if (newPage < 1) newPage = 1;
    if (newPage > totalPages) newPage = totalPages;
    
    if (newPage !== currentPage) {
        fetchJudgments(newPage,false).then(() => {
            document.querySelector('.search-box').scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }
}

function displayResults() {
    if (isFavoritesMode) return;
    const resultsDiv = document.getElementById('results');
    
    if (judgmentsData.length === 0) {
        resultsDiv.innerHTML = `
            <div style="background: #fff3e0; border: 1px solid #ffe0b2; padding: 25px; border-radius: 6px; text-align: center; margin-top: 10px;">
                <h4 style="color: #e65100; margin-top: 0;">🔍 查無符合條件的裁判書</h4>
                <p style="color: #6d4c41; margin-bottom: 8px;">可能原因如下：</p>
                <ul style="display: inline-block; text-align: left; color: #5d4037; font-size: 0.92em; line-height: 1.8;">
                    <li>輸入的多個關鍵字無法在同一筆案件中同時滿足 (AND 關係)</li>
                    <li>指定的書類別 (判決/裁定) 與勾選的案件類別衝突</li>
                    <li>指定的法院或年度查無此字號或號數</li>
                    <li>可點擊上方「<strong>重設</strong>」按鈕清空條件重新搜尋</li>
                </ul>
            </div>`;
        return;
    }

    const currentSortVal = currentSearchPayload.sort_type || "date_desc";
    const limitWarning = (typeof totalItems === 'number' && totalItems > 1000) ? '<span style="color:#e65100; font-size:0.9em; margin-left: 8px;">(系統僅開放瀏覽前 1000 筆)</span>' : '';
    let html = `
        <div class="table-toolbar">
            <span>共 <strong>${totalItems}</strong> 筆符合條件 ${limitWarning}</span>
            <div>
                <label for="tableSortSelect">排序方式：</label>
                <select id="tableSortSelect" class="sort-select" onchange="handleSortChange()">
                    <option value="date_desc" ${currentSortVal === 'date_desc' ? 'selected' : ''}>裁判日期 (新到舊)</option>
                    <option value="date_asc" ${currentSortVal === 'date_asc' ? 'selected' : ''}>裁判日期 (舊到新)</option>
                    <option value="no_desc" ${currentSortVal === 'no_desc' ? 'selected' : ''}>裁判案號 (大到小)</option>
                    <option value="no_asc" ${currentSortVal === 'no_asc' ? 'selected' : ''}>裁判案號 (小到大)</option>
                    <option value="size_desc" ${currentSortVal === 'size_desc' ? 'selected' : ''}>全文大小 (大到小)</option>
                    <option value="size_asc" ${currentSortVal === 'size_asc' ? 'selected' : ''}>全文大小 (小到大)</option>
                </select>
            </div>
        </div>`;

    html += `<table class="result-table">
                <thead>
                    <tr>
                        <th width="4%" style="text-align:center;"><input type="checkbox" id="selectAll" onclick="toggleSelectAll(this)" title="全選/取消全選"></th>
                        <th width="6%">序號</th>
                        <th width="60%">裁判字號 (主文摘要)</th>
                        <th width="15%">日期</th>
                        <th width="15%">案由</th>
                    </tr>
                </thead>
                <tbody id="resultTableBody"></tbody>
                </table>`;
    
    resultsDiv.innerHTML = html;
    renderTableBody(judgmentsData);
}

async function showFullContent(id) {
    const item = judgmentsData.find(j => j.id === id);
    if (!item) return;

    const idParts = item.id ? item.id.split(',') : [];
    const displayYear = (item.year && item.year.trim() !== "") ? item.year : (idParts[1] || "");
    const displayType = (item.case_type && item.case_type.trim() !== "") ? item.case_type : (idParts[2] || "");
    const displayNo = (item.case_no && item.case_no.trim() !== "") ? item.case_no : (idParts[3] || "");
    const courtName = getCourtName(item);
    const docKind = getDocumentKind(item);
    const fullTitle = `${courtName} ${displayYear} 年度 ${displayType} 字第 ${displayNo} 號${docKind}`;

    const contentText = item.content || "";
    const sizeKB = ((contentText.length * 2) / 1024).toFixed(1);

    currentSideId = id;
    document.getElementById('sideTitle').innerHTML = `${fullTitle} <span style="color: #777; font-size: 0.75em; font-weight: normal;">(${sizeKB} KB)</span>
        <span id="sideFavStar" style="cursor:pointer; font-size:0.9em;" onclick="openFavModal('${item.id}')" title="加入/移除我的最愛">${isFav(item.id) ? '⭐' : '☆'}</span>`;
    document.getElementById('sideMeta').innerHTML = `<strong>日期：</strong>${formatROCDate(item.date)} &nbsp;|&nbsp; <strong>案由：</strong>${item.title || "無"} &nbsp;|&nbsp; <strong>大小：</strong>${sizeKB} KB`;
    
    document.getElementById('sideBody').textContent = getSideText(item);
    document.getElementById('sidePanel').style.display = "block";

    // 載入重點與註解 (在 highlight.js 中)
    currentHighlights = [];
    if (typeof loadSideHighlights === "function") {
        loadSideHighlights(id);
    }

    const historyBox = document.getElementById('sideHistory');
    const loadingBox = document.getElementById('historyLoading');
    historyBox.style.display = "none";
    loadingBox.style.display = "block";

    fetch('/api/get_history', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item)
    })
    .then(res => res.json())
    .then(data => {
        loadingBox.style.display = "none";
        if (data.history && data.history.length > 0) {
            let hHtml = "<strong>🔗 相關歷審裁判紀錄：</strong><ul>";
            data.history.forEach(h => {
                hHtml += `<li><a href="${h.url}" target="_blank">${h.title}</a></li>`;
            });
            historyBox.innerHTML = hHtml + "</ul>";
        } else {
            historyBox.innerHTML = "此案件查無其他歷審紀錄。";
        }
        historyBox.style.display = "block";
    })
    .catch(err => {
        loadingBox.style.display = "none";
        historyBox.innerHTML = "<span style='color:red;'>歷審爬蟲暫時無法取得資料，請確認司法院網站連線狀態。</span>";
        historyBox.style.display = "block";
    });
}

function closeSidePanel() {
    document.getElementById('sidePanel').style.display = 'none';
}