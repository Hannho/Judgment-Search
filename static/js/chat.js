function handleChatKeyDown(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        sendChatMessage();
    }
}

// 切換任務模式時動態更新提示字與自訂輸入框
function onTaskModeChange() {
    const modeSelect = document.getElementById('chatTaskMode');
    if (!modeSelect) return;
    const mode = modeSelect.value;
    const customBox = document.getElementById('customPromptBox');
    const input = document.getElementById('chatInput');

    if (customBox) {
        if (mode === 'custom') {
            customBox.style.display = 'block';
        } else {
            customBox.style.display = 'none';
        }
    }

    if (input) {
        const placeholders = {
            general: "例如：請比較這幾起案件的判決結果差異...",
            issues: "例如：雙方的核心攻防爭點為何？法院最後採信哪一方？",
            damages: "例如：原告請求哪些項目？哪幾項被法院駁回？原因為何？",
            criminal: "例如：這幾件詐欺案被告大多判刑多久？量刑考量為何？",
            custom: "請輸入您想對這幾篇判決提出的問題..."
        };
        input.placeholder = placeholders[mode] || "請輸入對勾選案件的提問...";
    }
}

let currentChatAbortController = null;

window.abortActiveChatRequest = function() {
    if (currentChatAbortController) {
        try {
            currentChatAbortController.abort();
        } catch (e) {}
        currentChatAbortController = null;
    }
    const chatInput = document.getElementById('chatInput');
    const sendBtn = document.getElementById('chatSendBtn');
    if (chatInput) chatInput.disabled = false;
    if (sendBtn) sendBtn.disabled = false;
};

function clearChatMessages() {
    window.abortActiveChatRequest();
    const chatMessages = document.getElementById('chatMessages');
    const chatInput = document.getElementById('chatInput');
    const sendBtn = document.getElementById('chatSendBtn');

    chatMessages.innerHTML = `
        <div class="chat-bubble-row bot">
            <div class="chat-avatar bot-avatar">AI</div>
            <div class="chat-bubble bot-bubble">
                對話記錄已清空。您可以繼續針對目前搜尋列表中的案件提出任何法律或統計問題。
            </div>
        </div>`;

    if (chatInput) {
        chatInput.disabled = false;
        chatInput.value = '';
        chatInput.focus();
    }
    if (sendBtn) {
        sendBtn.disabled = false;
    }
}

function appendChatMessage(sender, contentHtml) {
    const chatMessages = document.getElementById('chatMessages');
    const row = document.createElement('div');
    row.className = `chat-bubble-row ${sender}`;

    if (sender === 'user') {
        row.innerHTML = `
            <div class="chat-bubble user-bubble">${contentHtml}</div>
            <div class="chat-avatar user-avatar">我</div>`;
    } else {
        row.innerHTML = `
            <div class="chat-avatar bot-avatar">AI</div>
            <div class="chat-bubble bot-bubble">${contentHtml}</div>`;
    }

    chatMessages.appendChild(row);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return row;
}

// 簡易安全且高效的 Markdown 轉 HTML 解析器（支援 Markdown 表格、標題、粗體與清單）
function parseMarkdownToHtml(markdownText) {
    if (!markdownText) return '';

    // 1. 先安全轉義 HTML 特殊字符（避免 XSS）
    let escaped = markdownText
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    const lines = escaped.split('\n');
    let output = [];
    let inTable = false;
    let tableHeader = [];
    let tableRows = [];

    function flushTable() {
        if (!inTable) return;
        let html = '<div class="ai-table-container"><table class="ai-table">';
        if (tableHeader.length > 0) {
            html += '<thead><tr>';
            tableHeader.forEach(cell => {
                html += `<th>${cell.trim()}</th>`;
            });
            html += '</tr></thead>';
        }
        if (tableRows.length > 0) {
            html += '<tbody>';
            tableRows.forEach(row => {
                html += '<tr>';
                row.forEach(cell => {
                    html += `<td>${cell.trim()}</td>`;
                });
                html += '</tr>';
            });
            html += '</tbody>';
        }
        html += '</table></div>';
        output.push(html);
        inTable = false;
        tableHeader = [];
        tableRows = [];
    }

    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();

        // 偵測 Markdown 表格行: | a | b | c |
        if (line.startsWith('|') && line.endsWith('|')) {
            const rawCells = line.slice(1, -1).split('|');
            // 判斷是否為表格分隔行: |--|--|
            const isDivider = rawCells.every(c => /^[\s\-:]+$/.test(c));
            if (isDivider) {
                continue;
            }

            if (!inTable) {
                inTable = true;
                tableHeader = rawCells;
            } else {
                tableRows.push(rawCells);
            }
            continue;
        } else {
            if (inTable) {
                flushTable();
            }
        }

        if (line === '') {
            output.push('<br>');
            continue;
        }

        // 標題轉換
        if (line.startsWith('### ')) {
            output.push(`<h5 class="ai-heading">${line.substring(4)}</h5>`);
            continue;
        } else if (line.startsWith('## ')) {
            output.push(`<h4 class="ai-heading">${line.substring(3)}</h4>`);
            continue;
        } else if (line.startsWith('# ')) {
            output.push(`<h3 class="ai-heading">${line.substring(2)}</h3>`);
            continue;
        }

        // 清單項目轉換
        if (line.startsWith('- ') || line.startsWith('* ')) {
            output.push(`• ${line.substring(2)}<br>`);
            continue;
        }

        output.push(line + '<br>');
    }

    if (inTable) {
        flushTable();
    }

    let result = output.join('');
    // 粗體轉換: **text**
    result = result.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // AI 回答段落引述錨定 (Citation Anchoring)
    result = result.replace(/【(引用[：:][^】]+)】/g, '<span class="citation-badge" onclick="locateCitation(\'$1\')" title="點擊跳轉至判決書該引述段落">[引述] $1</span>');
    result = result.replace(/【(主文|事實及理由|理由|裁判結果|量刑理由|爭點分析)】/g, '<span class="citation-badge" onclick="locateCitation(\'$1\')" title="點擊定位至判決書該段落">[段落] $1</span>');
    return result;
}

function sendChatMessage(directItem = null) {
    const input = document.getElementById('chatInput');
    const question = input.value.trim();
    const sendBtn = document.getElementById('chatSendBtn');

    if (!question) return;

    let selectedJudgments = [];

    if (directItem) {
        selectedJudgments = [directItem];
    } else {
        if (typeof selectedCasesMap !== 'undefined' && selectedCasesMap.size > 0) {
            selectedJudgments = Array.from(selectedCasesMap.values());
        } else {
            const checkedBoxes = document.querySelectorAll('.judgment-cb:checked');
            const selectedIds = Array.from(checkedBoxes).map(cb => cb.value);
            if (selectedIds.length > 0 && typeof judgmentsData !== 'undefined') {
                selectedJudgments = judgmentsData.filter(item => selectedIds.includes(item.id));
            }
        }
        
        // 若依然未勾選任何案件，但右側詳情頁開啟中，自動以當前開啟判決為分析目標
        if (selectedJudgments.length === 0 && typeof currentDetailItem !== 'undefined' && currentDetailItem) {
            selectedJudgments = [currentDetailItem];
        }
    }

    if (selectedJudgments.length === 0) {
        alert("請先在左側搜尋結果中「勾選」想要讓 AI 分析的判決書，或先在右側開啟一筆判決！");
        return;
    }

    // 取得當前任務模式與自訂指令
    const taskMode = document.getElementById('chatTaskMode') ? document.getElementById('chatTaskMode').value : 'general';
    const customInstruction = document.getElementById('customInstruction') ? document.getElementById('customInstruction').value.trim() : '';

    // 若已有進行中的請求，先中止舊請求避免背景資源浪費
    window.abortActiveChatRequest();
    const controller = new AbortController();
    currentChatAbortController = controller;

    appendChatMessage('user', escapeHtml(question));
    input.value = '';
    input.disabled = true;
    sendBtn.disabled = true;

    const loadingRow = appendChatMessage('bot', `
        <div class="chat-typing">
            <span></span><span></span><span></span>
        </div>
        <span style="color:#64748b; font-size:0.88em; margin-left:4px;">AI 正在以 <strong>${getTaskModeLabel(taskMode)}</strong> 模式研讀您選取的 <strong>${selectedJudgments.length}</strong> 筆案件中...</span>
        <button type="button" class="btn-toggle" style="margin-left:8px; padding:1px 8px; font-size:0.76em; color:#dc2626; border-color:#fecaca; background:#fef2f2;" onclick="window.abortActiveChatRequest()">停止生成</button>
    `);

    const contentsToSent = selectedJudgments.map((item, idx) => {
        const idParts = item.id ? item.id.split(',') : [];
        const yr = item.year || idParts[1] || "";
        const tp = item.case_type || idParts[2] || "";
        const no = item.case_no || idParts[3] || "";
        
        let caseText = `【案件 ${idx + 1}】${yr}年度${tp}字第${no}號\n`;
        
        // 優先讀取 main_text 與 reason，如果為空則退回 content
        const main = (item.main_text || "").trim();
        const rsn = (item.reason || "").trim();
        const cnt = (item.content || "").trim();

        if (main) {
            caseText += `【主文】\n${main}\n\n`;
        }
        if (rsn) {
            caseText += `【理由】\n${rsn}`;
        } else if (cnt) {
            caseText += `【判決全文】\n${cnt}`;
        } else {
            caseText += `【判決內容】\n(查無具體內文)`;
        }
        
        return caseText;
    });

    // 關鍵除錯印出：請打開瀏覽器 Console (F12) 觀察
    console.log("=== 準備送往 AI 的內容 ===", contentsToSent);

    const payload = {
        judgments_content: contentsToSent,
        question: question,
        task_mode: taskMode,
        custom_instruction: customInstruction
    };

    const botBubble = loadingRow.querySelector('.chat-bubble');
    let fullAnswer = "";

    // 優先使用 SSE 串流以達到即時逐字輸出與防超時
    (async () => {
        try {
            const response = await fetch('/api/ai/ask_stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                signal: controller.signal
            });

            if (!response.ok || !response.body) {
                throw new Error("串流端點回應異常，退回傳統模式");
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = "";

            while (true) {
                if (controller.signal.aborted) {
                    try { await reader.cancel(); } catch (e) {}
                    throw new DOMException('Aborted', 'AbortError');
                }
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (trimmed.startsWith('data: ')) {
                        const jsonStr = trimmed.slice(6);
                        if (!jsonStr) continue;
                        try {
                            const data = JSON.parse(jsonStr);
                            if (data.type === 'status') {
                                botBubble.innerHTML = `<span style="color:#666;">${escapeHtml(data.text)}</span> <button type="button" class="btn-toggle" style="margin-left:6px; padding:1px 7px; font-size:0.75em; color:#dc2626; border-color:#fecaca; background:#fef2f2;" onclick="window.abortActiveChatRequest()">停止</button>`;
                            } else if (data.type === 'token') {
                                fullAnswer += data.text;
                                botBubble.innerHTML = parseMarkdownToHtml(fullAnswer);
                            } else if (data.type === 'error') {
                                botBubble.innerHTML = `<span style="color:#d32f2f;">錯誤：${escapeHtml(data.text)}</span>`;
                            }
                        } catch (pe) {
                            console.error("JSON 解析失敗:", pe);
                        }
                    }
                }
                const chatMessages = document.getElementById('chatMessages');
                if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
            }

            if (!fullAnswer && !botBubble.innerHTML.includes('<strong>')) {
                botBubble.innerHTML = `<span style="color:#666;">模型分析完畢，未產生具體文字。</span>`;
            }
        } catch (streamErr) {
            if (streamErr.name === 'AbortError' || controller.signal.aborted) {
                if (!fullAnswer) {
                    botBubble.innerHTML = `<span style="color:#64748b;">已停止 AI 生成。</span>`;
                } else {
                    botBubble.innerHTML = parseMarkdownToHtml(fullAnswer) + `<div style="margin-top:6px; font-size:0.8em; color:#94a3b8;">（已手動停止後續生成）</div>`;
                }
                return;
            }
            console.warn("串流嘗試失敗，退回傳統模式呼叫:", streamErr);
            try {
                const res = await fetch('/api/ai/ask_multiple', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                    signal: controller.signal
                });
                const data = await res.json();
                let rawAnswer = "";
                if (Array.isArray(data.answer)) {
                    rawAnswer = data.answer.map(item => item.text || "").join("\n");
                } else if (typeof data.answer === 'string') {
                    rawAnswer = data.answer;
                } else {
                    rawAnswer = JSON.stringify(data.answer);
                }
                botBubble.innerHTML = parseMarkdownToHtml(rawAnswer);
            } catch (err) {
                if (err.name === 'AbortError' || controller.signal.aborted) {
                    botBubble.innerHTML = `<span style="color:#64748b;">已停止 AI 生成。</span>`;
                    return;
                }
                console.error(err);
                botBubble.innerHTML = `<span style="color:#d32f2f;">連線失敗：請確認後端伺服器與本機模型服務是否正常啟動。</span>`;
            }
        } finally {
            if (currentChatAbortController === controller) {
                currentChatAbortController = null;
            }
            if (input) {
                input.disabled = false;
                input.focus();
            }
            if (sendBtn) {
                sendBtn.disabled = false;
            }
            const chatMessages = document.getElementById('chatMessages');
            if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    })();
}

function getTaskModeLabel(mode) {
    const labels = {
        general: "綜合判決比對",
        issues: "訴訟爭點整理",
        damages: "損害賠償與准駁",
        criminal: "量刑趨勢分析",
        custom: "自訂指令"
    };
    return labels[mode] || "智能分析";
}

// ==========================================
// AI 回答段落引述錨定跳轉 (Citation Anchoring)
// ==========================================
window.locateCitation = function(keyword) {
    const sidePanel = document.getElementById('sidePanel');
    const sideBody = document.getElementById('sideBody');
    if (!sidePanel || sidePanel.style.display === 'none') {
        alert("請先在左側搜尋結果中點選一筆判決開啟全文，再點選引述進行段落定位！");
        return;
    }
    const cleanKw = keyword.replace(/^[【§\uD83D\uDCCD\uD83D\uDCCC]|\[(引述|段落)\]|引用[：:]/g, '').replace(/[】]$/g, '').trim();
    if (!cleanKw) return;

    const bodyText = sideBody.textContent;
    const targetIdx = bodyText.indexOf(cleanKw);
    if (targetIdx === -1) {
        // 嘗試關鍵詞子字串
        const sub = cleanKw.substring(0, Math.min(8, cleanKw.length));
        if (bodyText.indexOf(sub) !== -1) {
            flashHighlightInSideBody(sub);
            return;
        }
        alert(`在目前開啟的判決書內文中未找到「${cleanKw}」段落。`);
        return;
    }
    flashHighlightInSideBody(cleanKw);
};

function flashHighlightInSideBody(term) {
    const sideBody = document.getElementById('sideBody');
    if (!sideBody) return;

    // 清除舊的臨時閃爍高亮
    sideBody.querySelectorAll('.temp-citation-flash').forEach(el => {
        const textNode = document.createTextNode(el.textContent);
        el.parentNode.replaceChild(textNode, el);
    });

    const innerHtml = sideBody.innerHTML;
    const escapedTerm = escapeHtml(term);
    const regex = new RegExp(escapedTerm, 'g');
    
    // 替換第一個出現位置為高亮閃爍標記
    let replaced = false;
    sideBody.innerHTML = innerHtml.replace(regex, (match) => {
        if (!replaced) {
            replaced = true;
            return `<mark class="temp-citation-flash" style="background:#fef08a; color:#854d0e; padding:2px 4px; border-radius:3px; font-weight:bold; box-shadow:0 0 10px rgba(234,179,8,0.7);">${match}</mark>`;
        }
        return match;
    });

    const target = sideBody.querySelector('.temp-citation-flash');
    if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // 3.5 秒後淡出高亮
        setTimeout(() => {
            if (target && target.parentNode) {
                target.style.transition = 'background-color 1s ease, box-shadow 1s ease';
                target.style.background = 'transparent';
                target.style.boxShadow = 'none';
            }
        }, 3500);
    }
}