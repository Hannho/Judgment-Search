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
        document.getElementById('results').innerHTML = `<p style="color:#dc2626;">無法從資料庫載入裁判書資料，請確認連線狀態。</p>`;
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
                    <span class="fav-star" data-id="${item.id}" style="cursor:pointer; font-size:1.2em; color:${isFav(item.id) ? '#f59e0b' : '#94a3b8'};" onclick="toggleFav('${item.id}')" title="加入/移除收藏">${isFav(item.id) ? '★' : '☆'}</span>
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
        <button onclick="changePage(-1)" ${currentPage === 1 ? 'disabled' : ''}>上一頁</button>
        <span style="margin: 0 15px; font-weight: bold; color: #555;"> 第 ${currentPage} 頁 / 共 ${totalPages} 頁 </span>
        <button onclick="changePage(1)" ${currentPage === totalPages ? 'disabled' : ''}>下一頁</button>
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
                <h4 style="color: #e65100; margin-top: 0;">查無符合條件的裁判書</h4>
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
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                <span>共 <strong>${totalItems}</strong> 筆符合條件 ${limitWarning}</span>
                <button type="button" class="btn-toggle" style="padding: 2px 8px; font-size: 0.82em; background: #ecfdf5; color: #047857; border-color: #a7f3d0; cursor: pointer;" onclick="exportSelectedCSV()" title="將目前勾選的案件匯出為 Excel CSV 總表">匯出勾選 CSV</button>
                <button type="button" class="btn-toggle" style="padding: 2px 8px; font-size: 0.82em; background: #e0f2fe; color: #0369a1; border-color: #bae6fd; cursor: pointer;" onclick="exportSelectedDossier()" title="將目前勾選的案件打包產生完整卷宗研究報告">匯出卷宗彙編</button>
            </div>
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

let currentDetailItem = null;
let currentHistoryData = [];
let historyViewMode = 'timeline';
let judgmentNavigationStack = [];

// ==========================================
// 承審合議庭法官自動解析
// ==========================================
function extractJudges(content) {
    if (!content) return [];
    
    // 判決書結尾署名一定在最後一個「中華民國...年」之後（若無則取最後 1500 字）
    let sigBlock = "";
    const dateMatches = [...content.matchAll(/中華民國\s*[0-9\u4e00-\u9fa5]+\s*年/g)];
    if (dateMatches.length > 0) {
        const lastIndex = dateMatches[dateMatches.length - 1].index;
        sigBlock = content.slice(lastIndex);
    } else {
        sigBlock = content.slice(-1500);
    }

    const lines = sigBlock.split('\n');
    const judges = [];
    const seenNames = new Set();
    const nonJudgeWords = /(中華民國|正本|原本|裁判|判決|裁定|理由|主文|證明|年月日|書記官|檢察官|助理|通譯|公設|辯護人|駁回|上訴|原告|被告|抗告|聲請|異議|不得|確定|告訴人|自訴人)/;
    
    for (let line of lines) {
        line = line.replace(/\u3000/g, ' ').trim();
        if (!line) continue;
        if (/(書記官|通譯|公設辯護人|檢察官|助理)/.test(line)) continue;
        
        // 匹配法官角色與名字（審判長法官、審判長、受命法官、陪席法官、法官）
        const m = line.match(/(審判長\s*法\s*官|審判長|受命\s*法\s*官|受命法官|陪席\s*法\s*官|陪席法官|法\s*官)\s*([\u4e00-\u9fa5\s]{2,10})/);
        if (m) {
            const role = m[1].replace(/\s+/g, '');
            let rawName = m[2].replace(/\s+/g, '');
            if (nonJudgeWords.test(rawName)) continue;
            if (rawName.length > 4) {
                rawName = rawName.substring(0, 3);
            }
            if (rawName.length >= 2 && rawName.length <= 4 && !seenNames.has(rawName)) {
                seenNames.add(rawName);
                judges.push({ role, name: rawName });
            }
        }
    }
    return judges;
}

function renderJudges(judges) {
    const box = document.getElementById('sideJudges');
    if (!box) return;
    if (!judges || judges.length === 0) {
        box.style.display = 'none';
        box.innerHTML = '';
        return;
    }
    let html = '<span class="judge-box-title">承審合議庭：</span>';
    judges.forEach(j => {
        html += `<div class="judge-pill-group">`
              + `<span class="judge-pill-name" onclick="searchByJudge('${escapeHtml(j.name)}')" title="點擊以搜尋此法官（${escapeHtml(j.name)}）承審之裁判">`
              + `<strong>${escapeHtml(j.name)}</strong> <small>(${escapeHtml(j.role)})</small>`
              + `</span>`
              + `<button type="button" class="judge-pill-stats-btn" onclick="openJudgeAnalytics('${escapeHtml(j.name)}')" title="查看法官心證風格與審理畫像">心證畫像</button>`
              + `</div>`;
    });
    box.innerHTML = html;
    box.style.display = 'flex';
}

function searchByJudge(name) {
    if (!name) return;
    const kwInput = document.getElementById('quickKeywordInput');
    if (kwInput) {
        kwInput.value = name;
        const searchBox = document.querySelector('.search-box');
        if (searchBox) {
            searchBox.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        searchJudgments();
    }
}

// 判斷審級標籤與樣式 (一審/二審/終審)
function getCourtTierInfo(title) {
    const t = title || "";
    if (t.includes("最高法院") || t.includes("最高行政法院") || t.includes("懲戒法院") || t.includes("憲法法庭")) {
        return { tier: 3, label: "終審 / 最高", badgeClass: "tier-3" };
    }
    if (t.includes("高等法院") || t.includes("高等行政法院") || t.includes("智慧財產及商業法院") || t.includes("智財法院")) {
        return { tier: 2, label: "二審 / 高等", badgeClass: "tier-2" };
    }
    if (t.includes("地方法院") || t.includes("少年及家事法院") || t.includes("行政訴訟庭")) {
        return { tier: 1, label: "一審 / 地院", badgeClass: "tier-1" };
    }
    return { tier: 1, label: "審級", badgeClass: "tier-1" };
}

// 歷審裁判渲染器：支援「審級時序樹狀圖」與「傳統清單列表」切換
function renderHistoryView(currentId) {
    const historyBox = document.getElementById('sideHistory');
    if (!historyBox) return;

    if (!currentHistoryData || currentHistoryData.length === 0) {
        historyBox.innerHTML = "此案件查無其他歷審紀錄。";
        historyBox.style.display = "block";
        return;
    }

    const curIdClean = (currentId || "").toLowerCase().trim();

    if (historyViewMode === 'timeline') {
        // 時序樹狀圖模式
        let tHtml = '<div class="history-timeline">';
        currentHistoryData.forEach(h => {
            const rawTitle = String(h.title || h.jid || h.url || "（未命名案件）");
            const dateMatch = rawTitle.match(/\((\d{2,3}\.\d{1,2}\.\d{1,2})\)/);
            const dateStr = dateMatch ? dateMatch[1] : '';
            const cleanTitle = rawTitle.replace(/\(\d{2,3}\.\d{1,2}\.\d{1,2}\)/, '').trim();
            const tierInfo = getCourtTierInfo(rawTitle);

            const hJidClean = (h.jid || "").toLowerCase().trim();
            const isCurrent = hJidClean && (hJidClean === curIdClean || decodeURIComponent(hJidClean) === curIdClean);

            let actionHtml = '';
            if (isCurrent) {
                actionHtml = `<span style="color: #1e3a8a; font-weight: bold;">${escapeHtml(cleanTitle)}</span>`;
            } else if (h.in_db && h.jid) {
                // 點擊標題直接啟動浮動速覽（不跳轉）
                actionHtml = `<a href="#" data-jid="${escapeHtml(h.jid)}" onclick="previewHistoryCase(this.dataset.jid); return false;" style="color:#1d4ed8; text-decoration:none; font-weight:600;" title="點擊快速速覽此案主文與要點（不跳轉）">${escapeHtml(cleanTitle)}</a>`;
            } else {
                actionHtml = `<a href="${escapeHtml(h.url)}" target="_blank" rel="noopener" style="color:#0369a1; text-decoration:none; font-weight:600;" title="開啟司法院官方連結">${escapeHtml(cleanTitle)}</a>`;
            }

            let badgeHtml = '';
            if (isCurrent) {
                badgeHtml += `<span class="timeline-badge-current">本案</span>`;
            }
            if (h.in_db && !isCurrent) {
                badgeHtml += `<button type="button" class="btn-toggle timeline-btn-preview" onclick="previewHistoryCase('${escapeHtml(h.jid)}'); return false;" title="不跳轉，彈窗快速速覽此案主文與要點">速覽</button>`
                           + `<button type="button" class="btn-toggle timeline-btn-compare" onclick="openCompareWithCurrent('${escapeHtml(h.jid)}'); return false;" title="與本案左右分割並列對照">對照</button>`
                           + `<button type="button" class="btn-toggle timeline-btn-full" onclick="openLocalHistory('${escapeHtml(h.jid)}'); return false;" title="跳轉至此案完整全文閱讀（支援隨時返回上一步）">全文</button>`
                           + `<span class="timeline-badge-local">本地</span>`;
            } else if (!isCurrent) {
                badgeHtml += `<span class="timeline-badge-remote">↗ 司法院</span>`;
            }

            tHtml += `
            <div class="timeline-item">
                <div class="timeline-dot ${tierInfo.badgeClass} ${isCurrent ? 'is-current' : ''}"></div>
                <div class="timeline-card ${isCurrent ? 'is-current' : ''}">
                    <div class="timeline-header">
                        <span class="timeline-tier-badge ${tierInfo.badgeClass}">${tierInfo.label}</span>
                        ${dateStr ? `<span style="font-size:0.8em; color:#64748b;">${escapeHtml(dateStr)}</span>` : ''}
                    </div>
                    <div style="font-size:0.92em; line-height:1.45; margin-top:2px;">
                        ${actionHtml}
                    </div>
                    <div class="timeline-actions">
                        ${badgeHtml}
                    </div>
                </div>
            </div>`;
        });
        tHtml += '</div>';
        historyBox.innerHTML = tHtml;
    } else {
        // 清單列表模式
        let hHtml = "<strong>相關歷審裁判紀錄：</strong><ul>";
        currentHistoryData.forEach(h => {
            const label = escapeHtml(String(h.title || h.jid || h.url || "（未命名）"));
            const hJidClean = (h.jid || "").toLowerCase().trim();
            const isCurrent = hJidClean && (hJidClean === curIdClean || decodeURIComponent(hJidClean) === curIdClean);

            if (isCurrent) {
                hHtml += `<li style="background: #eef7ed; border: 1px solid #c8e6c9;">`
                      +  `<div style="font-weight: bold; color: #2e7d32; margin-bottom: 4px;">${label}</div>`
                      +  `<div class="timeline-actions"><span class="timeline-badge-current">本案</span></div></li>`;
            } else if (h.in_db && h.jid) {
                hHtml += `<li><div style="margin-bottom: 4px;"><a href="#" data-jid="${escapeHtml(h.jid)}" onclick="previewHistoryCase(this.dataset.jid); return false;" title="點擊快速速覽（不跳轉）">${label}</a></div>`
                      +  `<div class="timeline-actions">`
                      +  `<button type="button" class="btn-toggle timeline-btn-preview" onclick="previewHistoryCase('${escapeHtml(h.jid)}'); return false;" title="不跳轉，彈窗快速速覽此案主文與要點">速覽</button>`
                      +  `<button type="button" class="btn-toggle timeline-btn-compare" onclick="openCompareWithCurrent('${escapeHtml(h.jid)}'); return false;" title="與本案左右分割並列對照">對照</button>`
                      +  `<button type="button" class="btn-toggle timeline-btn-full" onclick="openLocalHistory('${escapeHtml(h.jid)}'); return false;" title="跳轉至此案全文（支援隨時返回上一步）">全文</button>`
                      +  `<span class="timeline-badge-local">本地</span>`
                      +  `</div></li>`;
            } else {
                hHtml += `<li><div style="margin-bottom: 4px;"><a href="${escapeHtml(h.url)}" target="_blank" rel="noopener">${label}</a></div>`
                      +  `<div class="timeline-actions"><span class="timeline-badge-remote">↗ 司法院</span></div></li>`;
            }
        });
        historyBox.innerHTML = hHtml + "</ul>";
    }
    historyBox.style.display = "block";
}

// 切換歷審裁判顯示模式 (時序圖 ⇄ 清單)
function toggleHistoryView() {
    historyViewMode = (historyViewMode === 'timeline') ? 'list' : 'timeline';
    const btn = document.getElementById('historyViewToggle');
    if (btn) {
        btn.innerHTML = (historyViewMode === 'timeline') 
            ? '歷審清單' 
            : '歷審時序圖';
        btn.title = (historyViewMode === 'timeline') 
            ? '切換為傳統清單列表' 
            : '切換為審級脈絡時序圖';
    }
    renderHistoryView(currentSideId);
}

// ==========================================
// 判決書研究報告一鍵列印/匯出 (Case Dossier Export)
// ==========================================
function exportCaseReport() {
    if (!currentDetailItem) {
        alert("目前未開啟任何判決書！");
        return;
    }
    const item = currentDetailItem;
    const courtName = getCourtName(item);
    const idParts = item.id ? item.id.split(',') : [];
    const displayYear = (item.year && item.year.trim() !== "") ? item.year : (idParts[1] || "");
    const displayType = (item.case_type && item.case_type.trim() !== "") ? item.case_type : (idParts[2] || "");
    const displayNo = (item.case_no && item.case_no.trim() !== "") ? item.case_no : (idParts[3] || "");
    const docKind = getDocumentKind(item);
    const fullCaseNo = `${courtName} ${displayYear} 年度 ${displayType} 字第 ${displayNo} 號${docKind}`;
    const rocDate = formatROCDate(item.date);
    const judges = extractJudges(item.content || "");
    const judgeNames = judges.length > 0 ? judges.map(j => `${j.name} (${j.role})`).join('、') : '未登載 / 獨任';
    
    // 使用者標記與筆記
    let highlightsHtml = "";
    if (Array.isArray(currentHighlights) && currentHighlights.length > 0) {
        highlightsHtml = currentHighlights.map(hl => {
            const colorHex = hl.color || '#ffeb3b';
            const noteText = hl.note ? `<div style="margin-top:4px; font-size:0.9em; color:#1e40af; background:#eff6ff; padding:4px 8px; border-radius:4px; border-left:3px solid #3b82f6;"><strong>個人研究註解：</strong>${escapeHtml(hl.note)}</div>` : '';
            return `<li style="margin-bottom:8px; line-height:1.6;">
                <span style="background:${colorHex}; padding:1px 4px; border-radius:2px;">${escapeHtml(hl.text || '')}</span>
                ${noteText}
            </li>`;
        }).join('');
    } else {
        highlightsHtml = "<li style='color:#777;'>（此案件目前尚未劃記重點或註解）</li>";
    }

    // 歷審脈絡
    let historyHtml = "";
    if (Array.isArray(currentHistoryData) && currentHistoryData.length > 0) {
        historyHtml = currentHistoryData.map(h => {
            const label = escapeHtml(h.title || h.jid || '未命名案件');
            return `<li>${label}</li>`;
        }).join('');
    } else {
        historyHtml = "<li style='color:#777;'>查無其他歷審紀錄</li>";
    }

    // 相關法條
    const lawsBox = document.getElementById('sideLaws');
    const lawsListHtml = (lawsBox && lawsBox.innerHTML.trim()) ? lawsBox.innerHTML : "<p style='color:#777;'>無相關法條資料</p>";

    const reportHtml = `<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>判決書研究報告 - ${escapeHtml(fullCaseNo)}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif;
            line-height: 1.8;
            color: #1f2937;
            padding: 30px;
            max-width: 900px;
            margin: 0 auto;
            background: #fff;
        }
        .header {
            border-bottom: 2px solid #2563eb;
            padding-bottom: 12px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
        }
        .header h1 {
            margin: 0;
            font-size: 1.6em;
            color: #1e3a8a;
        }
        .meta-table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }
        .meta-table td {
            padding: 8px 12px;
            border: 1px solid #e2e8f0;
            font-size: 0.95em;
        }
        .meta-table td.label {
            width: 22%;
            background: #f8fafc;
            font-weight: bold;
            color: #475569;
        }
        .section-title {
            font-size: 1.15em;
            color: #1e3a8a;
            border-left: 4px solid #2563eb;
            padding-left: 8px;
            margin: 25px 0 10px 0;
            font-weight: bold;
        }
        .holding-box {
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            padding: 12px 16px;
            font-size: 1.05em;
            font-weight: 500;
            color: #0f172a;
            white-space: pre-wrap;
        }
        .full-text {
            white-space: pre-wrap;
            line-height: 1.85;
            font-size: 0.95em;
            color: #334155;
            border: 1px solid #e2e8f0;
            padding: 15px;
            border-radius: 6px;
            background: #fafafa;
        }
        .btn-print {
            padding: 8px 16px;
            background: #2563eb;
            color: #fff;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.95em;
            font-weight: bold;
        }
        @media print {
            .no-print { display: none !important; }
            body { padding: 0; }
            .full-text { background: transparent; border: none; padding: 0; }
        }
    </style>
</head>
<body>
    <div class="no-print" style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; background: #eff6ff; padding: 10px 15px; border-radius: 8px; border: 1px solid #bfdbfe;">
        <span style="color: #1e40af; font-weight: bold;">案件研究報告預覽（已整合合議庭、歷審、註解筆記）</span>
        <div>
            <button class="btn-print" onclick="window.print()">列印 / 另存為 PDF</button>
            <button class="btn-print" style="background:#64748b; margin-left: 8px;" onclick="window.close()">關閉</button>
        </div>
    </div>

    <div class="header">
        <div>
            <h1>臺灣法院裁判研究報告</h1>
            <div style="font-size: 0.9em; color: #64748b; margin-top: 4px;">產出時間：${new Date().toLocaleString('zh-TW')}</div>
        </div>
        <div style="font-size: 1.1em; font-weight: bold; color: #1e40af;">${escapeHtml(fullCaseNo)}</div>
    </div>

    <table class="meta-table">
        <tr>
            <td class="label">裁判字號</td>
            <td>${escapeHtml(fullCaseNo)}</td>
            <td class="label">裁判日期</td>
            <td>${escapeHtml(rocDate)}</td>
        </tr>
        <tr>
            <td class="label">裁判案由</td>
            <td>${escapeHtml(item.title || "無")}</td>
            <td class="label">承審合議庭法官</td>
            <td>${escapeHtml(judgeNames)}</td>
        </tr>
    </table>

    <div class="section-title">【裁判主文】</div>
    <div class="holding-box">${escapeHtml(item.main_text || "（詳見理由）")}</div>

    <div class="section-title">【法務研析重點與註記】</div>
    <ul style="padding-left: 20px;">
        ${highlightsHtml}
    </ul>

    <div class="section-title">【歷審脈絡審級紀錄】</div>
    <ul style="padding-left: 20px;">
        ${historyHtml}
    </ul>

    <div class="section-title">【相關引用法條】</div>
    <div style="padding-left: 10px;">
        ${lawsListHtml}
    </div>

    <div class="section-title">【裁判書全文內文】</div>
    <div class="full-text">${escapeHtml(item.content || "")}</div>
</body>
</html>`;

    const printWin = window.open("", "_blank");
    if (!printWin) {
        alert("快顯視窗遭瀏覽器封鎖，請允許本站開啟彈出視窗以匯出報告！");
        return;
    }
    printWin.document.open();
    printWin.document.write(reportHtml);
    printWin.document.close();
}

async function showFullContent(id, itemOverride = null, isFreshOpen = true) {
    // itemOverride：從歷審清單開啟「本地資料庫已有」的判決時使用（該筆不一定在目前搜尋結果裡）
    const item = itemOverride || judgmentsData.find(j => j.id === id);
    if (!item) return;

    if (isFreshOpen) {
        judgmentNavigationStack = [];
        updateNavBreadcrumb();
    }

    currentDetailItem = item;
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
        <span id="sideFavStar" class="side-fav-star" style="cursor:pointer; font-size:0.9em; margin-left:8px; color:${isFav(item.id) ? '#f59e0b' : '#94a3b8'};" onclick="toggleFav('${item.id}')" title="加入/移除收藏">${isFav(item.id) ? '★' : '☆'}</span>`;
        
    document.getElementById('sideMeta').innerHTML = `<strong>日期：</strong>${formatROCDate(item.date)} &nbsp;|&nbsp; <strong>案由：</strong>${item.title || "無"} &nbsp;|&nbsp; <strong>大小：</strong>${sizeKB} KB`;
    
    // 解析並渲染承審合議庭法官小卡
    const judges = extractJudges(contentText);
    renderJudges(judges);

    // 方向 B：智慧判賠與慰撫金審理看板
    renderCaseCompensationBanner(item);

    document.getElementById('sideBody').textContent = getSideText(item);
    document.getElementById('sidePanel').style.display = "block";

    // 載入重點與註解 (在 highlight.js 中)
    currentHighlights = [];
    if (typeof loadSideHighlights === "function") {
        loadSideHighlights(id);
    }

    const historyBox = document.getElementById('sideHistory');
    const loadingBox = document.getElementById('historyLoading');
    const historyEmpty = document.getElementById('historyEmpty');
    const histBadge = document.getElementById('historyCountBadge');
    const toggleBtn = document.getElementById('historyViewToggle');
    if (histBadge) histBadge.style.display = "none";
    if (historyEmpty) historyEmpty.style.display = "none";
    if (toggleBtn) toggleBtn.style.display = "none";
    renderLaws([]);
    historyBox.style.display = "none";
    loadingBox.style.display = "block";

    fetch('/api/scraper/get_history', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...item, include_self: true })
    })
    .then(res => res.json())
    .then(data => {
        // 使用者在等待期間已切換到別筆判決，就不要覆蓋畫面
        if (currentSideId !== id) return;
        loadingBox.style.display = "none";
        renderLaws(data.laws);

        currentHistoryData = data.history || [];
        const histCount = currentHistoryData.length;
        if (histBadge) {
            if (histCount > 0) {
                histBadge.textContent = histCount;
                histBadge.style.display = "inline-flex";
            } else {
                histBadge.style.display = "none";
            }
        }

        if (toggleBtn) {
            toggleBtn.style.display = (histCount > 0) ? "inline-block" : "none";
        }

        renderHistoryView(id);
    })
    .catch(err => {
        if (currentSideId !== id) return;
        loadingBox.style.display = "none";
        historyBox.innerHTML = "<span style='color:red;'>歷審爬蟲暫時無法取得資料，請確認司法院網站連線狀態。</span>";
        historyBox.style.display = "block";
    });
    updateSideStar();
}

// ==========================================
// 歷審裁判快速預覽對照 (Quick Preview Modal)
// ==========================================
async function previewHistoryCase(jid) {
    const modal = document.getElementById('historyPreviewModal');
    const titleEl = document.getElementById('prevModalTitle');
    const metaEl = document.getElementById('prevModalMeta');
    const mainTextEl = document.getElementById('prevModalMainText');
    const reasonEl = document.getElementById('prevModalReason');
    const judgesEl = document.getElementById('prevModalJudges');
    const btnOpenFull = document.getElementById('btnOpenFullFromPreview');

    if (!modal) return;

    titleEl.textContent = "載入歷審資料中...";
    metaEl.textContent = "正在自資料庫調取裁判摘要與主文...";
    mainTextEl.textContent = "載入中...";
    reasonEl.textContent = "載入中...";
    if (judgesEl) judgesEl.style.display = 'none';
    modal.style.display = 'flex';

    try {
        const res = await fetch('/api/scraper/get_judgment', {
            method: 'POST',
            headers: apiHeaders(),
            body: JSON.stringify({ id: jid })
        });
        if (!res.ok) throw new Error("本地資料庫查無此裁判");
        const item = await res.json();
        if (!item || !item.id) throw new Error("資料格式錯誤");

        const courtName = getCourtName(item);
        const idParts = item.id ? item.id.split(',') : [];
        const yr = item.year || idParts[1] || "";
        const tp = item.case_type || idParts[2] || "";
        const no = item.case_no || idParts[3] || "";
        const docKind = getDocumentKind(item);
        const fullTitle = `${courtName} ${yr} 年度 ${tp} 字第 ${no} 號${docKind}`;

        titleEl.textContent = fullTitle;
        metaEl.innerHTML = `<strong>日期：</strong>${formatROCDate(item.date)} &nbsp;|&nbsp; <strong>案由：</strong>${item.title || "無"} &nbsp;|&nbsp; <strong>字號：</strong>${escapeHtml(item.id)}`;

        // 解析法官
        const judges = extractJudges(item.content || "");
        if (judgesEl) {
            if (judges.length > 0) {
                judgesEl.innerHTML = '<span class="judge-box-title">合議庭：</span>' + judges.map(j => `<span class="judge-pill"><strong>${escapeHtml(j.name)}</strong> <small>(${escapeHtml(j.role)})</small></span>`).join('');
                judgesEl.style.display = 'flex';
            } else {
                judgesEl.style.display = 'none';
            }
        }

        mainTextEl.textContent = item.main_text || "（本裁判未單獨切分主文，請切換至全文詳閱）";
        
        // 理由要點
        if (item.reason && item.reason.trim()) {
            reasonEl.textContent = item.reason;
        } else if (item.content) {
            const cleanContent = item.content.length > 800 ? item.content.substring(0, 800) + "\n\n...(篇幅較長，欲研讀全部事實理由請點選下方切換至全文)..." : item.content;
            reasonEl.textContent = cleanContent;
        } else {
            reasonEl.textContent = "（此案無詳細理由文字）";
        }

        // 綁定「切換至此案全文」按鈕
        if (btnOpenFull) {
            btnOpenFull.onclick = () => {
                closeHistoryPreview();
                openLocalHistory(item.id);
            };
        }

        // 綁定「與本案並列對照」按鈕
        const btnCompare = document.getElementById('btnCompareFromPreview');
        if (btnCompare) {
            btnCompare.onclick = () => {
                closeHistoryPreview();
                openCompareWithCurrent(item.id, item);
            };
        }

    } catch (e) {
        titleEl.textContent = "讀取失敗";
        metaEl.textContent = "";
        mainTextEl.textContent = "";
        reasonEl.innerHTML = `<span style="color:red;">無法載入此筆歷審裁判：${escapeHtml(e.message)}</span>`;
    }
}

function closeHistoryPreview(event) {
    if (event && event.target && event.target !== event.currentTarget) return;
    const modal = document.getElementById('historyPreviewModal');
    if (modal) modal.style.display = 'none';
}

// ==========================================
// 歷審導航歷史堆疊 (Navigation History Stack)
// ==========================================
// 從歷審清單開啟「本地資料庫已有」的判決：向後端取單筆資料，並加入上一案導航堆疊
async function openLocalHistory(jid) {
    try {
        const res = await fetch('/api/scraper/get_judgment', {
            method: 'POST',
            headers: apiHeaders(),
            body: JSON.stringify({ id: jid })
        });
        if (!res.ok) throw new Error("本地資料庫查無此筆");
        const item = await res.json();
        if (!item || !item.id) throw new Error("資料格式錯誤");

        // 關閉可能開啟中的速覽彈窗
        closeHistoryPreview();

        // 儲存當前案件至導航歷史堆疊
        const panel = document.getElementById('sidePanel');
        if (currentDetailItem) {
            const idParts = currentDetailItem.id ? currentDetailItem.id.split(',') : [];
            const yr = currentDetailItem.year || idParts[1] || "";
            const tp = currentDetailItem.case_type || idParts[2] || "";
            const no = currentDetailItem.case_no || idParts[3] || "";
            const courtName = getCourtName(currentDetailItem);
            const shortTitle = `${courtName} ${yr} ${tp} ${no}`.trim();
            judgmentNavigationStack.push({
                item: currentDetailItem,
                title: shortTitle,
                scrollTop: panel ? panel.scrollTop : 0
            });
        }

        await showFullContent(item.id, item, false);
        updateNavBreadcrumb();
        if (panel) {
            panel.scrollTop = 0;
            panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    } catch (e) {
        console.error(e);
        alert("無法從本地資料庫開啟這筆判決：" + e.message);
    }
}

async function goBackJudgment() {
    if (judgmentNavigationStack.length === 0) return;
    const prev = judgmentNavigationStack.pop();
    if (!prev || !prev.item) return;

    await showFullContent(prev.item.id, prev.item, false);
    updateNavBreadcrumb();
    const panel = document.getElementById('sidePanel');
    if (panel && typeof prev.scrollTop === 'number') {
        panel.scrollTop = prev.scrollTop;
    }
}

function updateNavBreadcrumb() {
    const navHeader = document.getElementById('sideNavHeader');
    const backBtn = document.getElementById('btnBackJudgment');
    const bcSpan = document.getElementById('backJudgmentBreadcrumb');
    if (!navHeader || !backBtn) return;

    if (judgmentNavigationStack.length > 0) {
        const last = judgmentNavigationStack[judgmentNavigationStack.length - 1];
        backBtn.innerHTML = `返回上一案：<strong>${escapeHtml(last.title)}</strong>`;
        if (bcSpan) {
            const chain = judgmentNavigationStack.map(s => escapeHtml(s.title)).concat(['<span style="color:#0f766e; font-weight:bold;">當前案件</span>']);
            bcSpan.innerHTML = `歷程：${chain.join(' → ')}`;
        }
        navHeader.style.display = 'flex';
    } else {
        navHeader.style.display = 'none';
        if (bcSpan) bcSpan.innerHTML = '';
    }
}

function closeSidePanel() {
    document.getElementById('sidePanel').style.display = 'none';
    judgmentNavigationStack = [];
    updateNavBreadcrumb();
    closeHistoryPreview();
}

// ==========================================
// 右側欄：AI 助理收合 / 歷審面板重設
// ==========================================

// 點圖示開啟或收起 AI 助理
function toggleChatPanel(forceOpen) {
    const wrap = document.getElementById('chatWrapper');
    const btn = document.getElementById('chatToggleBtn');
    if (!wrap || !btn) return;

    const open = (typeof forceOpen === 'boolean') ? forceOpen : (wrap.style.display === 'none');
    wrap.style.display = open ? 'block' : 'none';
    
    // 展開聊天視窗時隱藏獨立浮動大圓鈕，由卡片標題列的關閉鈕收起；收起時恢復浮動機器人按鈕
    btn.style.display = open ? 'none' : 'block';
    btn.classList.toggle('open', open);

    if (open) {
        const input = document.getElementById('chatInput');
        if (input) setTimeout(() => input.focus(), 50);
    }
}

// 關閉詳情面板（或重新搜尋）時，歷審面板回到初始提示狀態
function resetHistoryPanel() {
    currentDetailItem = null;
    currentHistoryData = [];
    judgmentNavigationStack = [];
    updateNavBreadcrumb();
    closeHistoryPreview();
    const empty = document.getElementById('historyEmpty');
    const loading = document.getElementById('historyLoading');
    const box = document.getElementById('sideHistory');
    const histBadge = document.getElementById('historyCountBadge');
    const lawBadge = document.getElementById('lawCountBadge');
    const toggleBtn = document.getElementById('historyViewToggle');
    const judgesBox = document.getElementById('sideJudges');
    if (judgesBox) { judgesBox.style.display = 'none'; judgesBox.innerHTML = ''; }
    if (box) { box.style.display = 'none'; box.innerHTML = ''; }
    if (loading) loading.style.display = 'none';
    if (empty) empty.style.display = 'block';
    if (histBadge) histBadge.style.display = 'none';
    if (lawBadge) lawBadge.style.display = 'none';
    if (toggleBtn) toggleBtn.style.display = 'none';
    renderLaws([]);
}

// 支援鍵盤 Esc 關閉各類彈窗
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeHistoryPreview();
        closeCompareModal();
        closeJudgeAnalyticsModal();
        closeCitationGraphModal();
        closeCompensationModal();
    }
});

document.addEventListener('DOMContentLoaded', () => {
    const sidePanel = document.getElementById('sidePanel');
    if (!sidePanel) return;
    new MutationObserver(() => {
        if (sidePanel.style.display === 'none') resetHistoryPanel();
    }).observe(sidePanel, { attributes: true, attributeFilter: ['style'] });
});

// 渲染「相關法條」卡片（放在歷審下面）。沒有資料就整張卡片隱藏
function renderLaws(laws) {
    const card = document.getElementById('lawCard');
    const box = document.getElementById('sideLaws');
    const lawBadge = document.getElementById('lawCountBadge');
    if (!card || !box) return;

    if (!Array.isArray(laws) || laws.length === 0) {
        card.style.display = 'none';
        box.innerHTML = '';
        if (lawBadge) lawBadge.style.display = 'none';
        return;
    }

    if (lawBadge) {
        lawBadge.textContent = laws.length;
        lawBadge.style.display = 'inline-flex';
    }

    box.innerHTML = '<ul>' + laws.map(l => {
        const text = escapeHtml(String((l && l.text) || ''));
        return (l && l.url)
            ? `<li><a href="${escapeHtml(l.url)}" target="_blank" rel="noopener">${text}</a></li>`
            : `<li>${text}</li>`;
    }).join('') + '</ul>';
    card.style.display = 'block';
}

// ==========================================
// 方向四：一鍵複製引述、實體辨識、AI爭點攻防快萃
// ==========================================
function copyCaseCitation() {
    if (!currentDetailItem) return;
    const courtName = getCourtName(currentDetailItem);
    const idParts = currentDetailItem.id ? currentDetailItem.id.split(',') : [];
    const yr = currentDetailItem.year || idParts[1] || "";
    const tp = currentDetailItem.case_type || idParts[2] || "";
    const no = currentDetailItem.case_no || idParts[3] || "";
    const docKind = getDocumentKind(currentDetailItem);
    const citation = `${courtName} ${yr} 年度 ${tp} 字第 ${no} 號${docKind}`.replace(/\s+/g, ' ').trim();

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(citation).then(() => {
            alert("已複製標準法學引用格式：\n" + citation);
        }).catch(() => {
            prompt("請手動複製引用格式：", citation);
        });
    } else {
        prompt("請手動複製引用格式：", citation);
    }
}

let isEntitiesActive = false;
function toggleEntityHighlights() {
    const sideBody = document.getElementById('sideBody');
    if (!sideBody || !currentDetailItem) return;
    isEntitiesActive = !isEntitiesActive;

    const btn = document.getElementById('btnToggleEntities');
    if (btn) {
        btn.style.background = isEntitiesActive ? '#ca8a04' : '#fefce8';
        btn.style.color = isEntitiesActive ? '#ffffff' : '#854d0e';
    }

    if (!isEntitiesActive) {
        // 清除實體標註，恢復原始全文與使用者螢光筆
        sideBody.textContent = getSideText(currentDetailItem);
        if (typeof loadSideHighlights === "function") {
            loadSideHighlights(currentDetailItem.id);
        }
        return;
    }

    // 取得乾淨內文並標記實體
    let text = escapeHtml(getSideText(currentDetailItem));

    // 1. 爭議金額辨識 (新臺幣/新台幣...元)
    text = text.replace(/(新[台臺]幣\s*[0-9,，、\u4e00-\u9fa5\d]+元)/g, '<mark class="entity-amount" title="爭議金額">$1</mark>');

    // 2. 關鍵日期辨識 (\d{2,3}年\d{1,2}月\d{1,2}日)
    text = text.replace(/([0-9\u4e00-\u9fa5]{2,4}\s*年\s*[0-9\u4e00-\u9fa5]{1,2}\s*月\s*[0-9\u4e00-\u9fa5]{1,2}\s*日)/g, '<mark class="entity-date" title="裁判/行為時點">$1</mark>');

    // 3. 律師/辯護人辨識
    text = text.replace(/((?:選任辯護人|訴訟代理人|指定辯護人|公設辯護人)\s*[\u4e00-\u9fa5\s]{2,14}律師)/g, '<mark class="entity-lawyer" title="訴訟代理律師">$1</mark>');

    sideBody.innerHTML = text;
}

function triggerAIArgumentAnalysis() {
    if (!currentDetailItem) {
        alert("請先開啟一筆判決！");
        return;
    }
    // 展開 AI 聊天面板
    toggleChatPanel(true);

    // 切換任務模式為「訴訟爭點整理」
    const modeSelect = document.getElementById('chatTaskMode');
    if (modeSelect) {
        modeSelect.value = 'issues';
        if (typeof onTaskModeChange === 'function') onTaskModeChange();
    }

    // 自動勾選當前判決
    const cb = document.querySelector(`.judgment-cb[value="${currentDetailItem.id}"]`);
    if (cb) cb.checked = true;

    // 自動填入提問並發送
    const input = document.getElementById('chatInput');
    if (input) {
        input.value = "請為我深入萃取本案的【原告/檢察官主張】、【被告抗辯要點】、【法院核心心證與採信理由】及【關鍵法令爭點】，並以條列與對照表格呈現。";
        sendChatMessage();
    }
}

// ==========================================
// 方向二：雙案/歷審並列對照 (Side-by-Side Compare)
// ==========================================
let compareCaseA = null;
let compareCaseB = null;

async function openCompareWithCurrent(jid, itemOverride = null) {
    if (!currentDetailItem) {
        alert("目前未開啟任何基準判決！");
        return;
    }
    compareCaseA = currentDetailItem;
    
    let itemB = itemOverride;
    if (!itemB) {
        try {
            const res = await fetch('/api/scraper/get_judgment', {
                method: 'POST',
                headers: apiHeaders(),
                body: JSON.stringify({ id: jid })
            });
            if (!res.ok) throw new Error("本地資料庫查無此裁判");
            itemB = await res.json();
        } catch (e) {
            alert("無法載入對照案件：" + e.message);
            return;
        }
    }
    compareCaseB = itemB;
    renderCompareModal();
}

function renderCompareModal() {
    const modal = document.getElementById('compareModal');
    if (!modal) return;

    function fillCol(prefix, item, defaultLabel) {
        const titleEl = document.getElementById(`compareTitle${prefix}`);
        const metaEl = document.getElementById(`compareMeta${prefix}`);
        const judgesEl = document.getElementById(`compareJudges${prefix}`);
        const mainTextEl = document.getElementById(`compareMainText${prefix}`);
        const bodyEl = document.getElementById(`compareBody${prefix}`);

        if (!item) {
            titleEl.textContent = "未選擇案件";
            metaEl.textContent = "";
            judgesEl.innerHTML = "";
            mainTextEl.textContent = "";
            bodyEl.textContent = "";
            return;
        }

        const courtName = getCourtName(item);
        const idParts = item.id ? item.id.split(',') : [];
        const yr = item.year || idParts[1] || "";
        const tp = item.case_type || idParts[2] || "";
        const no = item.case_no || idParts[3] || "";
        const docKind = getDocumentKind(item);
        const fullTitle = `${courtName} ${yr} 年度 ${tp} 字第 ${no} 號${docKind}`;

        titleEl.textContent = fullTitle;
        metaEl.innerHTML = `<strong>日期：</strong>${formatROCDate(item.date)} &nbsp;|&nbsp; <strong>案由：</strong>${item.title || "無"}`;

        const judges = extractJudges(item.content || "");
        if (judges.length > 0) {
            judgesEl.innerHTML = '<span style="font-size:0.82em; color:#475569;">合議庭：</span>' + judges.map(j => `<span class="judge-pill" style="font-size:0.75em; padding:1px 5px;"><strong>${escapeHtml(j.name)}</strong> <small>(${escapeHtml(j.role)})</small></span>`).join(' ');
        } else {
            judgesEl.innerHTML = '<span style="font-size:0.8em; color:#94a3b8;">（未登載合議庭署名）</span>';
        }

        mainTextEl.textContent = item.main_text || "（詳見裁判理由）";
        bodyEl.textContent = item.content || "（無內容）";
    }

    fillCol('A', compareCaseA, "案件 A");
    fillCol('B', compareCaseB, "案件 B");

    modal.style.display = 'flex';
}

function swapCompareCases() {
    const temp = compareCaseA;
    compareCaseA = compareCaseB;
    compareCaseB = temp;
    renderCompareModal();
}

function closeCompareModal(event) {
    if (event && event.target && event.target !== event.currentTarget) return;
    const modal = document.getElementById('compareModal');
    if (modal) modal.style.display = 'none';
}

function printCompareView() {
    if (!compareCaseA || !compareCaseB) return;
    const printWin = window.open("", "_blank");
    if (!printWin) return;

    const titleA = `${getCourtName(compareCaseA)} ${compareCaseA.year || ''} ${compareCaseA.case_type || ''} ${compareCaseA.case_no || ''}`;
    const titleB = `${getCourtName(compareCaseB)} ${compareCaseB.year || ''} ${compareCaseB.case_type || ''} ${compareCaseB.case_no || ''}`;

    printWin.document.write(`
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>裁判雙案並列對照表 - ${escapeHtml(titleA)} vs ${escapeHtml(titleB)}</title>
    <style>
        body { font-family: "PingFang TC", "Microsoft JhengHei", sans-serif; padding: 20px; line-height: 1.6; color: #1e293b; }
        .grid { display: flex; gap: 20px; }
        .col { flex: 1; border: 1px solid #cbd5e1; padding: 15px; border-radius: 6px; }
        h2 { font-size: 1.2em; color: #1e3a8a; border-bottom: 2px solid #3b82f6; padding-bottom: 6px; }
        .holding { background: #f8fafc; padding: 10px; border-radius: 4px; margin-bottom: 12px; white-space: pre-wrap; font-weight: bold; }
        .content { white-space: pre-wrap; font-size: 0.9em; }
        @media print { body { padding: 0; } }
    </style>
</head>
<body>
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 15px;">
        <h1 style="margin:0; font-size:1.4em;">裁判雙案／歷審並列對照表</h1>
        <button onclick="window.print()" style="padding:6px 12px; font-weight:bold; cursor:pointer;">列印 / 存為 PDF</button>
    </div>
    <div class="grid">
        <div class="col">
            <h2>【案件 A】${escapeHtml(titleA)}</h2>
            <p><strong>日期：</strong>${formatROCDate(compareCaseA.date)} | <strong>案由：</strong>${escapeHtml(compareCaseA.title || '')}</p>
            <h3>【裁判主文】</h3>
            <div class="holding">${escapeHtml(compareCaseA.main_text || '')}</div>
            <h3>【內文摘要】</h3>
            <div class="content">${escapeHtml(compareCaseA.content || '')}</div>
        </div>
        <div class="col">
            <h2>【案件 B】${escapeHtml(titleB)}</h2>
            <p><strong>日期：</strong>${formatROCDate(compareCaseB.date)} | <strong>案由：</strong>${escapeHtml(compareCaseB.title || '')}</p>
            <h3>【裁判主文】</h3>
            <div class="holding">${escapeHtml(compareCaseB.main_text || '')}</div>
            <h3>【內文摘要】</h3>
            <div class="content">${escapeHtml(compareCaseB.content || '')}</div>
        </div>
    </div>
</body>
</html>`);
    printWin.document.close();
}

// ==========================================
// 方向五：多案件勾選批次打包匯出 (CSV / 卷宗彙編)
// ==========================================
async function getSelectedJudgments() {
    const checkedBoxes = document.querySelectorAll('.judgment-cb:checked');
    if (checkedBoxes.length === 0) {
        alert("請先在搜尋結果左側「勾選」想要匯出的判決書！");
        return [];
    }
    const selectedIds = Array.from(checkedBoxes).map(cb => cb.value);

    // 優先從目前記憶體的 judgmentsData 中取得
    const localMatches = judgmentsData.filter(item => selectedIds.includes(item.id));
    const missingIds = selectedIds.filter(id => !localMatches.some(item => item.id === id));

    if (missingIds.length > 0) {
        try {
            const res = await fetch('/api/judgments/by_ids', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ids: missingIds })
            });
            if (res.ok) {
                const data = await res.json();
                if (data.data && Array.isArray(data.data)) {
                    localMatches.push(...data.data);
                }
            }
        } catch (e) {
            console.warn("無法補齊分頁外之案件資料", e);
        }
    }

    return localMatches;
}

async function exportSelectedCSV() {
    const items = await getSelectedJudgments();
    if (!items || items.length === 0) return;

    const headers = ["序號", "裁判字號", "裁判法院", "裁判日期", "案由", "書類別", "合議庭法官", "主文摘要", "全文大小KB", "系統ID"];
    const rows = [headers];

    items.forEach((item, index) => {
        const courtName = getCourtName(item);
        const idParts = item.id ? item.id.split(',') : [];
        const yr = item.year || idParts[1] || "";
        const tp = item.case_type || idParts[2] || "";
        const no = item.case_no || idParts[3] || "";
        const docKind = getDocumentKind(item);
        const fullCaseNo = `${courtName} ${yr} 年度 ${tp} 字第 ${no} 號${docKind}`;
        const rocDate = formatROCDate(item.date);
        const judges = extractJudges(item.content || "").map(j => `${j.name}(${j.role})`).join(';');
        const cleanMainText = (item.main_text || "").replace(/[\r\n]+/g, ' ').trim();
        const sizeKB = item.content ? ((item.content.length * 2) / 1024).toFixed(1) : "0";

        rows.push([
            index + 1,
            `"${fullCaseNo.replace(/"/g, '""')}"`,
            `"${courtName.replace(/"/g, '""')}"`,
            `"${rocDate}"`,
            `"${(item.title || "").replace(/"/g, '""')}"`,
            `"${docKind}"`,
            `"${judges.replace(/"/g, '""')}"`,
            `"${cleanMainText.replace(/"/g, '""')}"`,
            sizeKB,
            `"${(item.id || "").replace(/"/g, '""')}"`
        ]);
    });

    const csvContent = "\uFEFF" + rows.map(e => e.join(",")).join("\n");
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    link.setAttribute("href", url);
    link.setAttribute("download", `裁判研究案件清單_${dateStr}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

async function exportSelectedDossier() {
    const items = await getSelectedJudgments();
    if (!items || items.length === 0) return;

    const printWin = window.open("", "_blank");
    if (!printWin) {
        alert("快顯視窗遭瀏覽器封鎖，請允許本站開啟彈出視窗以匯出卷宗！");
        return;
    }

    let tocHtml = "<ol style='padding-left: 20px; line-height: 2;'>";
    let casesHtml = "";

    items.forEach((item, index) => {
        const courtName = getCourtName(item);
        const idParts = item.id ? item.id.split(',') : [];
        const yr = item.year || idParts[1] || "";
        const tp = item.case_type || idParts[2] || "";
        const no = item.case_no || idParts[3] || "";
        const docKind = getDocumentKind(item);
        const fullCaseNo = `${courtName} ${yr} 年度 ${tp} 字第 ${no} 號${docKind}`;
        const rocDate = formatROCDate(item.date);
        const judges = extractJudges(item.content || "").map(j => `${j.name} (${j.role})`).join('、') || '未登載 / 獨任';

        tocHtml += `<li><a href="#case_${index}" style="color: #1d4ed8; text-decoration: none;"><strong>${escapeHtml(fullCaseNo)}</strong></a> &nbsp;<span style="color:#64748b;">(民國 ${rocDate} | 案由：${escapeHtml(item.title || '無')})</span></li>`;

        casesHtml += `
        <div id="case_${index}" style="page-break-before: always; margin-top: 30px; border-top: 2px dashed #94a3b8; padding-top: 25px;">
            <div style="display:flex; justify-content:space-between; align-items:flex-end; border-bottom: 2px solid #2563eb; padding-bottom: 8px;">
                <h2 style="margin:0; font-size:1.3em; color:#1e3a8a;">第 ${index + 1} 案：${escapeHtml(fullCaseNo)}</h2>
                <span style="font-size:0.9em; color:#64748b;">日期：${escapeHtml(rocDate)}</span>
            </div>
            <table style="width:100%; border-collapse:collapse; margin: 15px 0;">
                <tr>
                    <td style="padding:6px 10px; border:1px solid #e2e8f0; background:#f8fafc; font-weight:bold; width:20%;">案由</td>
                    <td style="padding:6px 10px; border:1px solid #e2e8f0;">${escapeHtml(item.title || '無')}</td>
                    <td style="padding:6px 10px; border:1px solid #e2e8f0; background:#f8fafc; font-weight:bold; width:20%;">承審合議庭</td>
                    <td style="padding:6px 10px; border:1px solid #e2e8f0;">${escapeHtml(judges)}</td>
                </tr>
            </table>
            <div style="font-weight:bold; color:#1e40af; margin-bottom: 4px;">【裁判主文】</div>
            <div style="background:#f8fafc; border:1px solid #cbd5e1; padding:10px 12px; border-radius:4px; margin-bottom:15px; white-space:pre-wrap; font-weight:500;">${escapeHtml(item.main_text || '（詳見理由）')}</div>
            <div style="font-weight:bold; color:#334155; margin-bottom: 4px;">【裁判書全文內文】</div>
            <div style="white-space:pre-wrap; font-size:0.92em; line-height:1.75; color:#334155; border:1px solid #e2e8f0; padding:12px; border-radius:4px; background:#fafafa;">${escapeHtml(item.content || '')}</div>
        </div>`;
    });
    tocHtml += "</ol>";

    const binderHtml = `
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>裁判書研究卷宗彙編 (共 ${items.length} 案)</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif; line-height: 1.8; color: #1f2937; padding: 30px; max-width: 950px; margin: 0 auto; background: #fff; }
        .no-print { margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; background: #eff6ff; padding: 10px 15px; border-radius: 8px; border: 1px solid #bfdbfe; }
        .btn-print { padding: 8px 16px; background: #2563eb; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 0.95em; font-weight: bold; }
        @media print { .no-print { display: none !important; } body { padding: 0; } }
    </style>
</head>
<body>
    <div class="no-print">
        <span style="color: #1e40af; font-weight: bold;">裁判研究卷宗彙編預覽（已整合 ${items.length} 筆案件）</span>
        <div>
            <button class="btn-print" onclick="window.print()">列印 / 存為 PDF 卷宗</button>
            <button class="btn-print" style="background:#64748b; margin-left: 8px;" onclick="window.close()">關閉</button>
        </div>
    </div>

    <div style="border-bottom: 3px solid #1e3a8a; padding-bottom: 15px; margin-bottom: 25px;">
        <h1 style="margin: 0; color: #1e3a8a; font-size: 1.8em;">裁判書研究卷宗彙編</h1>
        <div style="font-size: 0.95em; color: #64748b; margin-top: 6px;">
            彙編時間：${new Date().toLocaleString('zh-TW')} &nbsp;|&nbsp; 案件總數：共 ${items.length} 案
        </div>
    </div>

    <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 15px 20px; border-radius: 8px; margin-bottom: 25px;">
        <h2 style="margin: 0 0 10px 0; font-size: 1.15em; color: #1e40af;">卷宗目錄（點擊快速跳轉）</h2>
        ${tocHtml}
    </div>

    ${casesHtml}
</body>
</html>`;

    printWin.document.open();
    printWin.document.write(binderHtml);
    printWin.document.close();
}

// ==========================================
// 方向 B：民事判賠與慰撫金行情分析 (Compensation Benchmark)
// ==========================================
const CN_NUM_JS = {
    '零': 0, '一': 1, '二': 2, '兩': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
    '壹': 1, '貳': 2, '參': 3, '肆': 4, '伍': 5, '陸': 6, '柒': 7, '捌': 8, '玖': 9,
    '拾': 10, '十': 10, '佰': 100, '百': 100, '仟': 1000, '千': 1000, '萬': 10000, '億': 100000000
};

function parseCNAmountJS(text) {
    if (!text) return 0;
    text = String(text).replace(/[,，\s]/g, '').trim();
    const numMatch = text.match(/([0-9]+(?:\.[0-9]+)?)/);
    if (numMatch) {
        let val = parseFloat(numMatch[1]);
        if (text.includes('億')) val *= 100000000;
        else if (text.includes('萬')) val *= 10000;
        return Math.round(val);
    }
    let total = 0, currSection = 0, currNum = 0;
    for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        if (ch in CN_NUM_JS) {
            const n = CN_NUM_JS[ch];
            if (n === 10 || n === 100 || n === 1000) {
                currNum = currNum > 0 ? currNum : 1;
                currSection += currNum * n;
                currNum = 0;
            } else if (n === 10000) {
                currSection = (currSection + currNum) * 10000;
                total += currSection;
                currSection = 0;
                currNum = 0;
            } else if (n === 100000000) {
                currSection = (currSection + currNum) * 100000000;
                total += currSection;
                currSection = 0;
                currNum = 0;
            } else {
                currNum = n;
            }
        }
    }
    total += currSection + currNum;
    return total;
}

function extractCaseCompensation(item) {
    if (!item) return null;
    const mainText = item.main_text || "";
    const content = item.content || "";
    const cleanMain = mainText.replace(/[\r\n]+/g, ' ').trim();
    const title = item.title || "";

    let awarded = 0;
    let status = "其他";
    let claim = 0;
    let solatium = 0;

    // 檢查是否完全駁回
    if (/(原告之訴.*?駁回|聲請駁回|上訴駁回|全部駁回)/.test(cleanMain) && !/應給付/.test(cleanMain)) {
        awarded = 0;
        status = "完全駁回";
    } else {
        const mAward = cleanMain.match(/(?:應(?:連帶)?給付(?:原告)?|給付原告)\s*(?:新[臺台]幣)?\s*([0-9,，\u4e00-\u9fa5]{1,20})\s*元/);
        if (mAward) {
            awarded = parseCNAmountJS(mAward[1]);
            status = /其餘.*?駁回/.test(cleanMain) ? "一部准許" : "全部判准";
        }
    }

    // 檢查原告起訴請求金額
    const mClaim = (cleanMain + " " + content.slice(0, 4000)).match(/(?:原告起訴聲明(?:請求)?|聲明請求|訴之聲明).*?(?:判命)?(?:被告)?(?:應)?(?:連帶)?給付(?:原告)?\s*(?:新[臺台]幣)?\s*([0-9,，\u4e00-\u9fa5]{1,20})\s*元/);
    if (mClaim) {
        claim = parseCNAmountJS(mClaim[1]);
    }

    // 檢查慰撫金 (精神慰撫金)
    const mSol = (cleanMain + " " + content.slice(0, 4000)).match(/(?:精神)?慰撫金.*?(?:以|認|命)?\s*(?:新[臺台]幣)?\s*([0-9,，\u4e00-\u9fa5]{1,15})\s*元(?:為相當|為適當|為合理)?/);
    if (mSol) {
        solatium = parseCNAmountJS(mSol[1]);
    }

    return { awarded, status, claim, solatium, title };
}

function renderCaseCompensationBanner(item) {
    const banner = document.getElementById('sideCompensationBanner');
    const btnComp = document.getElementById('btnSideCompensation');
    if (!banner) return;

    const data = extractCaseCompensation(item);
    // 判斷是否為有金錢給付/損害賠償特徵之案件
    const isMoneyCase = data && (data.awarded > 0 || data.claim > 0 || data.solatium > 0 ||
        /損害賠償|給付|借款|工程款|侵權行為|票款|報酬/.test(item.title || "") ||
        /應給付/.test(item.main_text || ""));

    if (!isMoneyCase) {
        banner.style.display = 'none';
        banner.innerHTML = '';
        if (btnComp) btnComp.style.display = 'none';
        return;
    }

    if (btnComp) btnComp.style.display = 'inline-block';

    const claimText = data.claim > 0 ? `NT$ ${data.claim.toLocaleString()}` : '（詳見訴狀）';
    const awardText = data.awarded > 0 ? `NT$ ${data.awarded.toLocaleString()}` : (data.status === '完全駁回' ? '0 元 (原告之訴駁回)' : '見主文');
    const rateText = (data.claim > 0 && data.awarded > 0)
        ? `<span style="font-size:0.8em; background:#dcfce7; color:#15803d; border:1px solid #86efac; padding:1px 6px; border-radius:4px; font-weight:bold; margin-left:8px;">准許成數 ${((data.awarded/data.claim)*100).toFixed(1)}%</span>`
        : '';
    const solText = data.solatium > 0
        ? `<span style="font-size:0.8em; background:#fdf2f8; color:#9d174d; border:1px solid #fbcfe8; padding:1px 6px; border-radius:4px; font-weight:bold; margin-left:8px;">精神慰撫金：NT$ ${data.solatium.toLocaleString()}</span>`
        : '';

    let barHtml = '';
    if (data.claim > 0 && data.awarded > 0) {
        const pct = Math.min(100, Math.max(3, (data.awarded / data.claim) * 100));
        barHtml = `
        <div style="margin-top: 8px; background: #e2e8f0; height: 6px; border-radius: 3px; overflow: hidden; display: flex;" title="綠色：判准成數 ${pct.toFixed(1)}% | 灰色：未准許金額">
            <div style="background: #10b981; width: ${pct}%;"></div>
            <div style="background: #cbd5e1; flex: 1;"></div>
        </div>`;
    }

    banner.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <span style="font-weight: bold; color: #065f46; font-size: 0.92em;">判賠金額看板：</span>
            ${data.claim > 0 ? `<span style="font-size: 0.88em; color: #475569;">原告起訴請求：<strong>${claimText}</strong></span>` : ''}
            <span style="font-size: 0.88em; color: #065f46;">法院判准：<strong style="color: #047857; font-size: 1.08em;">${awardText}</strong></span>
            ${rateText}
            ${solText}
        </div>
        <button type="button" class="btn-toggle" style="background:#059669; color:#fff; border:none; padding:3px 10px; font-size:0.82em; font-weight:bold; cursor:pointer; border-radius:4px; box-shadow:0 1px 2px rgba(5,150,105,0.3);" onclick="openCompensationModalFromCurrent()" title="查看全台同類裁判判賠金額行情分佈與落點">分析全台判賠行情</button>
    </div>
    ${barHtml}
    `;
    banner.style.display = 'block';
}

function openCompensationModalFromCurrent() {
    if (!currentDetailItem) return;
    const data = extractCaseCompensation(currentDetailItem);
    let kw = (currentDetailItem.title || "").trim();
    if (!kw || kw === "無") kw = "車禍 骨折 慰撫金";
    openCompensationAnalytics(kw, data ? data.awarded : 0);
}

let compCurrentTargetAwarded = 0;

function openCompensationAnalytics(keyword, currentAwarded = 0) {
    compCurrentTargetAwarded = currentAwarded || 0;
    const modal = document.getElementById('compensationModal');
    const input = document.getElementById('compKeywordInput');
    if (!modal) return;
    if (input) input.value = keyword || "車禍 骨折 慰撫金";
    modal.style.display = 'flex';
    runCompensationAnalytics();
}

function setCompKeyword(kw) {
    const input = document.getElementById('compKeywordInput');
    if (input) input.value = kw;
    runCompensationAnalytics();
}

function closeCompensationModal(event) {
    if (event && event.target && event.target !== event.currentTarget) return;
    const modal = document.getElementById('compensationModal');
    if (modal) modal.style.display = 'none';
}

async function runCompensationAnalytics() {
    const input = document.getElementById('compKeywordInput');
    const loading = document.getElementById('compLoading');
    const content = document.getElementById('compAnalyticsContent');
    const kw = input ? input.value.trim() : "損害賠償";

    if (loading) loading.style.display = 'block';
    if (content) content.style.display = 'none';

    let courtCode = '';
    if (currentDetailItem && currentDetailItem.id) {
        courtCode = currentDetailItem.id.split(',')[0] || currentDetailItem.id.substring(0, 3);
    }

    try {
        const res = await fetch('/api/judgments/compensation_analytics', {
            method: 'POST',
            headers: apiHeaders(),
            body: JSON.stringify({ keyword: kw, court: courtCode, limit: 120 })
        });
        if (!res.ok) {
            let errMsg = `HTTP ${res.status}`;
            try {
                const errData = await res.json();
                if (errData && (errData.error || errData.detail)) errMsg += `: ${errData.error || errData.detail}`;
            } catch (_) {}
            if (res.status === 404) {
                errMsg = "後端尚未載入判賠行情 API (404 Not Found)。請確認後端 Python 服務已重新啟動 (python main.py)！";
            }
            throw new Error(errMsg);
        }
        const data = await res.json();

        // 填入 4 KPI
        document.getElementById('compTotalSample').textContent = `${data.total_analyzed || 0} 筆`;
        document.getElementById('compAwardRate').textContent = `${data.award_rate || 0}%`;
        document.getElementById('compAwardRateDesc').textContent = `判准 ${data.awarded_count || 0} 案 / 駁回 ${data.dismissed_count || 0} 案`;

        const dist = data.distribution || {};
        document.getElementById('compMedianAmount').textContent = dist.median > 0 ? `NT$ ${dist.median.toLocaleString()}` : '0 元';

        const sol = data.solatium_stats || {};
        document.getElementById('compSolatiumAvg').textContent = sol.average > 0 ? `NT$ ${sol.average.toLocaleString()}` : '無數據';
        document.getElementById('compSolatiumDesc').textContent = sol.median > 0 ? `中位數：NT$ ${sol.median.toLocaleString()} (${sol.count || 0} 案)` : '實務案件無明確標示';

        // 盒鬚行情條 (Boxplot Bar)
        const minVal = dist.min || 0;
        const q25Val = dist.q25 || 0;
        const medVal = dist.median || 0;
        const q75Val = dist.q75 || 0;
        const maxVal = dist.max || 1;

        document.getElementById('lblCompMin').textContent = `NT$ ${minVal.toLocaleString()}`;
        document.getElementById('lblCompQ25').textContent = `NT$ ${q25Val.toLocaleString()}`;
        document.getElementById('lblCompMedian').textContent = `NT$ ${medVal.toLocaleString()}`;
        document.getElementById('lblCompQ75').textContent = `NT$ ${q75Val.toLocaleString()}`;
        document.getElementById('lblCompMax').textContent = `NT$ ${maxVal.toLocaleString()}`;

        const rangeEl = document.getElementById('compBoxBarRange');
        const pinMedEl = document.getElementById('compBoxPinMedian');
        const pinCurEl = document.getElementById('compBoxPinCurrent');
        const pinCurLabel = document.getElementById('compCurrentCasePin');

        if (maxVal > 0 && rangeEl) {
            const leftPct = (q25Val / maxVal) * 100;
            const widthPct = Math.max(4, ((q75Val - q25Val) / maxVal) * 100);
            const medPct = (medVal / maxVal) * 100;

            rangeEl.style.left = `${leftPct}%`;
            rangeEl.style.width = `${widthPct}%`;
            if (pinMedEl) pinMedEl.style.left = `${medPct}%`;

            if (compCurrentTargetAwarded > 0 && pinCurEl) {
                const curPct = Math.min(100, Math.max(0, (compCurrentTargetAwarded / maxVal) * 100));
                pinCurEl.style.left = `${curPct}%`;
                pinCurEl.style.display = 'block';
                if (pinCurLabel) pinCurLabel.textContent = `當前案件判准：NT$ ${compCurrentTargetAwarded.toLocaleString()}`;
            } else if (pinCurEl) {
                pinCurEl.style.display = 'none';
                if (pinCurLabel) pinCurLabel.textContent = '';
            }
        }

        // 金額級距分佈長條圖
        const bracketsBox = document.getElementById('compBracketsBox');
        if (bracketsBox && data.brackets) {
            const total = data.awarded_count || 1;
            let bHtml = '';
            for (const [k, v] of Object.entries(data.brackets)) {
                const pct = Math.round((v / total) * 100);
                bHtml += `
                <div style="margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; font-size: 0.82em; color: #334155; margin-bottom: 3px;">
                        <span>${k}</span>
                        <strong style="color: #047857;">${v} 案 (${pct}%)</strong>
                    </div>
                    <div style="background: #e2e8f0; height: 8px; border-radius: 4px; overflow: hidden;">
                        <div style="background: linear-gradient(90deg, #34d399, #059669); width: ${pct}%; height: 100%;"></div>
                    </div>
                </div>`;
            }
            bracketsBox.innerHTML = bHtml;
        }

        // 類似裁判行情參考清單
        const samplesBox = document.getElementById('compSampleCasesBox');
        if (samplesBox) {
            const list = data.sample_cases || [];
            if (list.length === 0) {
                samplesBox.innerHTML = '<div style="color:#64748b; font-size:0.9em;">暫無足夠之參考裁判</div>';
            } else {
                samplesBox.innerHTML = list.map(c => `
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 10px; margin-bottom: 8px; font-size: 0.85em;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <a href="#" onclick="closeCompensationModal(); previewHistoryCase('${escapeHtml(c.id)}'); return false;" style="font-weight: bold; color: #1d4ed8; text-decoration: none;">${escapeHtml(c.full_case_no)}</a>
                        <span style="background: ${c.awarded_amount > 0 ? '#dcfce7' : '#fee2e2'}; color: ${c.awarded_amount > 0 ? '#15803d' : '#b91c1c'}; font-weight: bold; padding: 1px 6px; border-radius: 3px; font-size: 0.82em;">${escapeHtml(c.awarded_formatted)}</span>
                    </div>
                    <div style="color: #64748b; font-size: 0.8em; margin-bottom: 3px;">
                        日期：${formatROCDate(c.date)} | 案由：${escapeHtml(c.title)} ${c.solatium_amount > 0 ? `| 慰撫金: NT$ ${c.solatium_amount.toLocaleString()}` : ''}
                    </div>
                    <div style="color: #334155; font-size: 0.82em; line-height: 1.4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                        ${escapeHtml(c.main_snippet)}
                    </div>
                </div>`).join('');
            }
        }

    } catch (e) {
        console.error("行情分析失敗:", e);
        if (loading) loading.style.display = 'none';
        if (content) {
            content.style.display = 'block';
            content.innerHTML = `
                <div style="padding: 35px 20px; text-align: center;">
                    <div style="font-size: 1.8em; margin-bottom: 8px; color: #dc2626; font-weight: bold;">[提示]</div>
                    <h3 style="margin: 0 0 10px 0; color: #b91c1c; font-size: 1.15em;">分析判賠行情失敗</h3>
                    <p style="color: #475569; font-size: 0.9em; max-width: 480px; margin: 0 auto 16px auto; line-height: 1.6;">
                        ${escapeHtml(e.message)}
                    </p>
                    ${e.message.includes('404') ? `
                    <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 14px 18px; max-width: 480px; margin: 0 auto; text-align: left; font-size: 0.86em; color: #991b1b; line-height: 1.6;">
                        <strong>快速排查指引：</strong><br>
                        因為您剛剛新增了判賠行情 API，在背景執行的 Python 服務尚未載入新路由。<br>
                        請前往終端機按 <kbd>Ctrl + C</kbd> 關閉後端，再執行 <code>python main.py</code> 重啟，然後重整瀏覽器即可正常調閱！
                    </div>` : `
                    <button type="button" class="btn btn-secondary" onclick="runCompensationAnalytics()" style="padding: 6px 16px; font-size: 0.88em; cursor: pointer;">
                        重新分析
                    </button>
                    `}
                </div>
            `;
        }
    } finally {
        if (loading) loading.style.display = 'none';
    }
}

// ==========================================
// 方向 A：法官裁判心證畫像與傾向統計 (Judge Analytics)
// ==========================================
async function openJudgeAnalytics(judgeName) {
    const modal = document.getElementById('judgeAnalyticsModal');
    const loading = document.getElementById('judgeAnalyticsLoading');
    const body = document.getElementById('judgeAnalyticsBody');
    if (!modal) return;

    modal.style.display = 'flex';
    if (loading) loading.style.display = 'block';
    if (body) body.style.display = 'none';

    let courtCode = '';
    if (currentDetailItem && currentDetailItem.id) {
        courtCode = currentDetailItem.id.split(',')[0] || currentDetailItem.id.substring(0, 3);
    }

    try {
        const res = await fetch('/api/judgments/judge_analytics', {
            method: 'POST',
            headers: apiHeaders(),
            body: JSON.stringify({ judge_name: judgeName, court: courtCode, limit: 100 })
        });
        if (!res.ok) {
            let errMsg = `HTTP ${res.status}`;
            try {
                const errData = await res.json();
                if (errData && (errData.error || errData.detail)) errMsg += `: ${errData.error || errData.detail}`;
            } catch (_) {}
            if (res.status === 404) {
                errMsg = "後端尚未載入法官畫像 API (404 Not Found)。請確認後端 Python 服務已重新啟動 (python main.py)！";
            }
            throw new Error(errMsg);
        }
        const data = await res.json();

        // 綁定基本檔案
        document.getElementById('judgeProfileName').textContent = `${data.judge_name} 法官`;
        const courtNames = (data.courts || []).map(c => c.name).join('、') || '臺灣法院';
        document.getElementById('judgeProfileCourts').textContent = `主要歷任審理法院：${courtNames}`;
        document.getElementById('judgeProfileSampleCount').textContent = data.total_cases || 0;
        document.getElementById('judgeProfileYearRange').textContent = data.year_range || '近年度';

        // 核心心證指標
        const crim = data.criminal_stats || {};
        document.getElementById('kpiProbationRate').textContent = `${crim.probation_rate || 0}%`;
        document.getElementById('kpiProbationDesc').textContent = `緩刑 ${crim.probation_count || 0} 案 / 總刑事 ${crim.total || 0} 案`;

        document.getElementById('kpiCommutableRate').textContent = `${crim.commutable_rate || 0}%`;
        document.getElementById('kpiCommutableDesc').textContent = `易科罰金 ${crim.commutable_count || 0} 案`;

        document.getElementById('kpiNotGuiltyRate').textContent = `${crim.not_guilty_rate || 0}%`;
        document.getElementById('kpiNotGuiltyDesc').textContent = `無罪/免訴/不受理 ${crim.not_guilty_count || 0} 案`;

        const civ = data.civil_stats || {};
        document.getElementById('kpiCivilAwardRate').textContent = `${civ.award_rate || 0}%`;
        document.getElementById('kpiCivilAwardDesc').textContent = `判准 ${civ.award_count || 0} 案 / 駁回 ${civ.dismiss_count || 0} 案`;

        // 審理案由 TOP 排行
        const causesBox = document.getElementById('judgeTopCausesBox');
        if (causesBox) {
            const list = data.top_causes || [];
            if (list.length === 0) {
                causesBox.innerHTML = '<div style="color:#64748b; font-size:0.9em;">暫無案由統計數據</div>';
            } else {
                const maxCount = list[0].count || 1;
                causesBox.innerHTML = list.map((c, idx) => {
                    const pct = Math.round((c.count / maxCount) * 100);
                    return `
                    <div style="margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between; font-size: 0.84em; color: #334155; margin-bottom: 3px;">
                            <span><strong>${idx + 1}.</strong> ${escapeHtml(c.name)}</span>
                            <span style="color: #1e40af; font-weight: bold;">${c.count} 案</span>
                        </div>
                        <div style="background: #e2e8f0; height: 7px; border-radius: 4px; overflow: hidden;">
                            <div style="background: linear-gradient(90deg, #60a5fa, #2563eb); width: ${pct}%; height: 100%;"></div>
                        </div>
                    </div>`;
                }).join('');
            }
        }

        // 近期主審裁判精選
        const recentBox = document.getElementById('judgeRecentCasesBox');
        if (recentBox) {
            const cases = data.recent_cases || [];
            if (cases.length === 0) {
                recentBox.innerHTML = '<div style="color:#64748b; font-size:0.9em;">暫無近期裁判資料</div>';
            } else {
                recentBox.innerHTML = cases.map(c => `
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 10px; margin-bottom: 8px; font-size: 0.85em;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px;">
                        <a href="#" onclick="closeJudgeAnalyticsModal(); previewHistoryCase('${escapeHtml(c.id)}'); return false;" style="font-weight: bold; color: #1d4ed8; text-decoration: none;">${escapeHtml(c.full_title)}</a>
                        <span style="font-size: 0.78em; color: #64748b;">${formatROCDate(c.date)}</span>
                    </div>
                    <div style="color: #475569; font-size: 0.82em; margin-bottom: 3px;">案由：${escapeHtml(c.title)}</div>
                    <div style="color: #334155; font-size: 0.8em; line-height: 1.4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                        ${escapeHtml(c.main_snippet)}
                    </div>
                </div>`).join('');
            }
        }

        // 搜尋此法官所有裁判按鈕
        const searchBtn = document.getElementById('btnSearchThisJudge');
        if (searchBtn) {
            searchBtn.onclick = () => {
                closeJudgeAnalyticsModal();
                searchByJudge(data.judge_name);
            };
        }

        if (loading) loading.style.display = 'none';
        if (body) body.style.display = 'block';

    } catch (e) {
        console.error("法官心證風格載入失敗:", e);
        if (loading) loading.style.display = 'none';
        if (body) {
            body.style.display = 'block';
            body.innerHTML = `
                <div style="padding: 35px 20px; text-align: center;">
                    <div style="font-size: 1.8em; margin-bottom: 8px; color: #dc2626; font-weight: bold;">[提示]</div>
                    <h3 style="margin: 0 0 10px 0; color: #b91c1c; font-size: 1.15em;">讀取法官心證數據失敗</h3>
                    <p style="color: #475569; font-size: 0.9em; max-width: 480px; margin: 0 auto 16px auto; line-height: 1.6;">
                        ${escapeHtml(e.message)}
                    </p>
                    ${e.message.includes('404') ? `
                    <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 14px 18px; max-width: 480px; margin: 0 auto; text-align: left; font-size: 0.86em; color: #991b1b; line-height: 1.6;">
                        <strong>快速排查指引：</strong><br>
                        因為您剛剛新增了法官畫像 API，在背景執行的 Python 服務尚未載入新路由。<br>
                        請前往終端機按 <kbd>Ctrl + C</kbd> 關閉後端，再執行 <code>python main.py</code> 重啟，然後重整瀏覽器即可正常調閱！
                    </div>` : `
                    <button type="button" class="btn btn-secondary" onclick="openJudgeAnalytics('${escapeHtml(judgeName)}')" style="padding: 6px 16px; font-size: 0.88em; cursor: pointer;">
                        重新嘗試
                    </button>
                    `}
                </div>
            `;
        }
    }
}

function closeJudgeAnalyticsModal(event) {
    if (event && event.target && event.target !== event.currentTarget) return;
    const modal = document.getElementById('judgeAnalyticsModal');
    if (modal) modal.style.display = 'none';
}

// ==========================================
// 方向 A：判決引用網絡圖 (Citation Network Graph)
// ==========================================
let citationGraphState = {
    canvas: null,
    ctx: null,
    nodes: [],
    links: [],
    draggedNode: null,
    hoveredNode: null,
    scale: 1,
    offsetX: 0,
    offsetY: 0,
    animId: null
};

function extractCitationGraphData(item) {
    if (!item) return { nodes: [], links: [] };
    const content = item.content || "";
    const mainText = item.main_text || "";
    const fullText = mainText + "\n" + content;

    const courtName = getCourtName(item);
    const idParts = (item.id || "").split(',');
    const yr = item.year || idParts[1] || "";
    const tp = item.case_type || idParts[2] || "";
    const no = item.case_no || idParts[3] || "";
    const centerTitle = `${courtName} ${yr} ${tp} ${no}`.trim() || "本案判決";

    const nodes = [];
    const links = [];

    // 1. 中心節點 (本案)
    nodes.push({
        id: "center",
        label: centerTitle,
        fullText: centerTitle,
        type: "center",
        r: 26,
        color: "#f59e0b",
        x: 0,
        y: 0,
        vx: 0,
        vy: 0
    });

    // 2. 憲法法庭判決與司法院釋字 (紅色/橙色)
    const constMatches = [...fullText.matchAll(/(?:司法院)?(?:釋字第\s*(\d+)\s*號|(\d+)\s*年(?:度)?憲判字第\s*(\d+)\s*號)/g)];
    const constSet = new Set();
    constMatches.forEach(m => {
        const text = m[0].replace(/\s+/g, '');
        if (!constSet.has(text) && constSet.size < 5) {
            constSet.add(text);
            const id = `const_${text}`;
            nodes.push({
                id,
                label: text,
                fullText: `憲政指標解釋：${text}`,
                type: "const",
                r: 18,
                color: "#ef4444",
                x: (Math.random() - 0.5) * 150 - 180,
                y: (Math.random() - 0.5) * 150 - 120,
                vx: 0,
                vy: 0
            });
            links.push({ source: "center", target: id });
        }
    });

    // 3. 最高法院判例 / 裁定 / 大法庭 (紫色)
    const supremeMatches = [...fullText.matchAll(/(?:最高法院\s*(\d{2,3})\s*年(?:度)?\s*([\u4e00-\u9fa5]+)\s*字第\s*(\d+)\s*號(?:判決|裁定)?|(\d{2,3})\s*年(?:度)?台上(?:大)?字第\s*(\d+)\s*號)/g)];
    const supremeSet = new Set();
    supremeMatches.forEach(m => {
        const text = m[0].replace(/\s+/g, '');
        if (!supremeSet.has(text) && supremeSet.size < 6) {
            supremeSet.add(text);
            const id = `sup_${text}`;
            nodes.push({
                id,
                label: text.length > 14 ? text.slice(0, 14) + '...' : text,
                fullText: `最高法院實務先例：${text}`,
                type: "supreme",
                r: 17,
                color: "#8b5cf6",
                x: (Math.random() - 0.5) * 150 + 180,
                y: (Math.random() - 0.5) * 150 - 120,
                vx: 0,
                vy: 0
            });
            links.push({ source: "center", target: id });
        }
    });

    // 4. 歷審上下級裁判 (藍色)
    if (Array.isArray(currentHistoryData) && currentHistoryData.length > 0) {
        currentHistoryData.forEach((h, idx) => {
            const hTitle = (h.title || h.jid || "").replace(/\(\d{2,3}\.\d{1,2}\.\d{1,2}\)/, '').trim();
            const hId = (h.jid || `hist_${idx}`).toLowerCase();
            if (hTitle && !hId.includes((item.id || "").toLowerCase())) {
                const id = `hist_${idx}`;
                nodes.push({
                    id,
                    label: hTitle.length > 13 ? hTitle.slice(0, 13) + '...' : hTitle,
                    fullText: `歷審裁判脈絡：${hTitle}`,
                    type: "history",
                    r: 18,
                    color: "#3b82f6",
                    jid: h.jid,
                    x: (Math.random() - 0.5) * 120,
                    y: (Math.random() - 0.5) * 120 + 200,
                    vx: 0,
                    vy: 0
                });
                links.push({ source: "center", target: id });
            }
        });
    }

    // 5. 核心法條 (綠色)
    const lawMatches = [...fullText.matchAll(/(民法|刑法|民事訴訟法|刑事訴訟法|行政訴訟法|勞動基準法|公司法|消費者保護法|道路交通管理處罰條例|國家賠償法)\s*第\s*([0-9\u4e00-\u9fa5]+)\s*條(?:之[0-9\u4e00-\u9fa5]+)?/g)];
    const lawSet = new Set();
    lawMatches.forEach(m => {
        const text = m[0].replace(/\s+/g, '');
        if (!lawSet.has(text) && lawSet.size < 7) {
            lawSet.add(text);
            const id = `law_${text}`;
            nodes.push({
                id,
                label: text,
                fullText: `核心引用法條：${text}`,
                type: "law",
                r: 16,
                color: "#10b981",
                x: (Math.random() - 0.5) * 200,
                y: (Math.random() - 0.5) * 160 - 220,
                vx: 0,
                vy: 0
            });
            links.push({ source: "center", target: id });
        }
    });

    return { nodes, links };
}

function openCitationGraphModal() {
    if (!currentDetailItem) {
        alert("請先開啟一筆判決書！");
        return;
    }
    const modal = document.getElementById('citationGraphModal');
    if (!modal) return;
    modal.style.display = 'flex';

    // 建立引用資料
    const graphData = extractCitationGraphData(currentDetailItem);
    citationGraphState.nodes = graphData.nodes;
    citationGraphState.links = graphData.links;
    citationGraphState.scale = 1;
    citationGraphState.offsetX = 0;
    citationGraphState.offsetY = 0;

    // 渲染右側詳細明細清單
    renderCitationDetailsList(graphData.nodes);

    // 初始化 Canvas
    setTimeout(() => {
        initCitationCanvas();
    }, 50);
}

function closeCitationGraphModal(event) {
    if (event && event.target && event.target !== event.currentTarget) return;
    const modal = document.getElementById('citationGraphModal');
    if (modal) modal.style.display = 'none';
    if (citationGraphState.animId) {
        cancelAnimationFrame(citationGraphState.animId);
        citationGraphState.animId = null;
    }
}

function renderCitationDetailsList(nodes) {
    const box = document.getElementById('citationDetailList');
    if (!box) return;

    const constNodes = nodes.filter(n => n.type === 'const');
    const supremeNodes = nodes.filter(n => n.type === 'supreme');
    const historyNodes = nodes.filter(n => n.type === 'history');
    const lawNodes = nodes.filter(n => n.type === 'law');

    let html = '';

    if (constNodes.length > 0) {
        html += `<div class="cite-group-title">憲法法庭判決與釋字 (${constNodes.length})</div>`;
        constNodes.forEach(n => {
            html += `<div class="cite-item-card">
                <div style="font-weight:bold; color:#dc2626;">${escapeHtml(n.label)}</div>
                <div style="font-size:0.8em; color:#64748b; margin-top:3px;">
                    <a href="https://cons.judicial.gov.tw" target="_blank" rel="noopener" style="color:#2563eb; text-decoration:none;">↗ 司法院憲法法庭查詢</a>
                </div>
            </div>`;
        });
    }

    if (supremeNodes.length > 0) {
        html += `<div class="cite-group-title">最高法院實務先例 (${supremeNodes.length})</div>`;
        supremeNodes.forEach(n => {
            html += `<div class="cite-item-card">
                <div style="font-weight:bold; color:#7c3aed;">${escapeHtml(n.label)}</div>
                <div style="font-size:0.8em; color:#64748b; margin-top:3px;">
                    <a href="#" onclick="searchByJudge('${escapeHtml(n.label)}'); closeCitationGraphModal(); return false;" style="color:#2563eb; text-decoration:none;">檢索關聯裁判</a>
                </div>
            </div>`;
        });
    }

    if (historyNodes.length > 0) {
        html += `<div class="cite-group-title">歷審上下級審脈絡 (${historyNodes.length})</div>`;
        historyNodes.forEach(n => {
            html += `<div class="cite-item-card">
                <div style="font-weight:bold; color:#2563eb;">${escapeHtml(n.label)}</div>
                <div style="font-size:0.8em; color:#64748b; margin-top:3px;">
                    ${n.jid ? `<a href="#" onclick="closeCitationGraphModal(); previewHistoryCase('${escapeHtml(n.jid)}'); return false;" style="color:#059669; text-decoration:none; font-weight:bold;">快速速覽此案</a>` : '審級關聯案件'}
                </div>
            </div>`;
        });
    }

    if (lawNodes.length > 0) {
        html += `<div class="cite-group-title">關鍵實體引用法條 (${lawNodes.length})</div>`;
        lawNodes.forEach(n => {
            html += `<div class="cite-item-card">
                <div style="font-weight:bold; color:#059669;">${escapeHtml(n.label)}</div>
                <div style="font-size:0.8em; color:#64748b; margin-top:3px;">
                    <a href="https://law.moj.gov.tw/LawClass/LawAll.aspx" target="_blank" rel="noopener" style="color:#2563eb; text-decoration:none;">全國法規資料庫</a>
                </div>
            </div>`;
        });
    }

    box.innerHTML = html || '<div style="color:#64748b; font-size:0.9em; padding:10px;">本案內文暫未自動探勘出特殊先例或釋字引用</div>';
}

function initCitationCanvas() {
    const canvas = document.getElementById('citationCanvas');
    if (!canvas) return;
    citationGraphState.canvas = canvas;
    const ctx = canvas.getContext('2d');
    citationGraphState.ctx = ctx;

    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;

    // 將中心節點置中
    const centerNode = citationGraphState.nodes.find(n => n.id === 'center');
    if (centerNode) {
        centerNode.x = canvas.width / 2;
        centerNode.y = canvas.height / 2;
    }

    // 散佈其他節點
    citationGraphState.nodes.forEach(n => {
        if (n.id !== 'center') {
            n.x += canvas.width / 2;
            n.y += canvas.height / 2;
        }
    });

    // 綁定滑鼠互動
    bindCitationCanvasEvents(canvas);

    // 啟動物理彈簧動畫迴圈
    if (citationGraphState.animId) cancelAnimationFrame(citationGraphState.animId);
    let stepCount = 0;
    function loop() {
        if (stepCount < 180 || citationGraphState.draggedNode) {
            updateGraphPhysics();
            stepCount++;
        }
        drawGraph(ctx, canvas);
        citationGraphState.animId = requestAnimationFrame(loop);
    }
    citationGraphState.animId = requestAnimationFrame(loop);
}

function updateGraphPhysics() {
    const nodes = citationGraphState.nodes;
    const links = citationGraphState.links;

    // 庫倫斥力 (節點相互排斥)
    for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
            const a = nodes[i];
            const b = nodes[j];
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const dist = Math.hypot(dx, dy) || 1;
            if (dist < 260) {
                const f = (260 - dist) / dist * 0.15;
                if (a !== citationGraphState.draggedNode && a.id !== 'center') { a.vx -= dx * f; a.vy -= dy * f; }
                if (b !== citationGraphState.draggedNode && b.id !== 'center') { b.vx += dx * f; b.vy += dy * f; }
            }
        }
    }

    // 虎克彈簧引力 (相連節點相互拉近)
    links.forEach(l => {
        const src = nodes.find(n => n.id === l.source);
        const tgt = nodes.find(n => n.id === l.target);
        if (src && tgt) {
            const dx = tgt.x - src.x;
            const dy = tgt.y - src.y;
            const dist = Math.hypot(dx, dy) || 1;
            const idealDist = tgt.type === 'history' ? 140 : 180;
            const f = (dist - idealDist) * 0.02;
            if (src !== citationGraphState.draggedNode && src.id !== 'center') { src.vx += (dx / dist) * f; src.vy += (dy / dist) * f; }
            if (tgt !== citationGraphState.draggedNode && tgt.id !== 'center') { tgt.vx -= (dx / dist) * f; tgt.vy -= (dy / dist) * f; }
        }
    });

    // 速度更新與摩擦阻尼
    nodes.forEach(n => {
        if (n !== citationGraphState.draggedNode && n.id !== 'center') {
            n.vx *= 0.82;
            n.vy *= 0.82;
            n.x += n.vx;
            n.y += n.vy;
        }
    });
}

function drawGraph(ctx, canvas) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();

    // 畫連線
    citationGraphState.links.forEach(l => {
        const src = citationGraphState.nodes.find(n => n.id === l.source);
        const tgt = citationGraphState.nodes.find(n => n.id === l.target);
        if (src && tgt) {
            ctx.beginPath();
            ctx.moveTo(src.x, src.y);
            ctx.lineTo(tgt.x, tgt.y);
            ctx.strokeStyle = tgt.color ? tgt.color + '55' : 'rgba(148, 163, 184, 0.2)';
            ctx.lineWidth = 2;
            ctx.stroke();
        }
    });

    // 畫節點
    citationGraphState.nodes.forEach(n => {
        const isHover = (citationGraphState.hoveredNode === n);
        ctx.save();
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r + (isHover ? 4 : 0), 0, Math.PI * 2);

        if (n.id === 'center') {
            ctx.shadowColor = '#f59e0b';
            ctx.shadowBlur = 18;
            ctx.fillStyle = '#f59e0b';
        } else {
            if (isHover) {
                ctx.shadowColor = n.color || '#fff';
                ctx.shadowBlur = 12;
            }
            ctx.fillStyle = n.color || '#3b82f6';
        }
        ctx.fill();

        ctx.lineWidth = isHover ? 3 : 2;
        ctx.strokeStyle = '#ffffff';
        ctx.stroke();
        ctx.restore();

        // 標籤文字
        ctx.fillStyle = '#ffffff';
        ctx.font = (n.id === 'center') ? 'bold 12px sans-serif' : '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';

        // 文字背景條
        const text = n.label || '';
        const tw = ctx.measureText(text).width;
        ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
        ctx.fillRect(n.x - tw / 2 - 4, n.y + n.r + 3, tw + 8, 16);

        ctx.fillStyle = '#f8fafc';
        ctx.fillText(text, n.x, n.y + n.r + 5);
    });

    ctx.restore();
}

function bindCitationCanvasEvents(canvas) {
    let isDragging = false;

    function getNodeAt(x, y) {
        return citationGraphState.nodes.find(n => Math.hypot(n.x - x, n.y - y) <= n.r + 6);
    }

    canvas.onmousedown = (e) => {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const target = getNodeAt(mx, my);
        if (target) {
            citationGraphState.draggedNode = target;
            isDragging = true;
        }
    };

    canvas.onmousemove = (e) => {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        if (isDragging && citationGraphState.draggedNode) {
            citationGraphState.draggedNode.x = mx;
            citationGraphState.draggedNode.y = my;
            citationGraphState.draggedNode.vx = 0;
            citationGraphState.draggedNode.vy = 0;
        } else {
            citationGraphState.hoveredNode = getNodeAt(mx, my);
            canvas.style.cursor = citationGraphState.hoveredNode ? 'pointer' : 'default';
        }
    };

    canvas.onmouseup = () => {
        isDragging = false;
        citationGraphState.draggedNode = null;
    };

    canvas.onclick = (e) => {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const target = getNodeAt(mx, my);
        if (target && target.type === 'history' && target.jid) {
            closeCitationGraphModal();
            previewHistoryCase(target.jid);
        } else if (target && target.type === 'supreme') {
            closeCitationGraphModal();
            searchByJudge(target.label);
        }
    };
}

function resetCitationCanvasView() {
    const canvas = citationGraphState.canvas;
    if (!canvas) return;
    const centerNode = citationGraphState.nodes.find(n => n.id === 'center');
    if (centerNode) {
        centerNode.x = canvas.width / 2;
        centerNode.y = canvas.height / 2;
    }
    citationGraphState.nodes.forEach((n, idx) => {
        if (n.id !== 'center') {
            const angle = (idx / (citationGraphState.nodes.length - 1)) * Math.PI * 2;
            n.x = (canvas.width / 2) + Math.cos(angle) * 180;
            n.y = (canvas.height / 2) + Math.sin(angle) * 160;
            n.vx = 0;
            n.vy = 0;
        }
    });
}