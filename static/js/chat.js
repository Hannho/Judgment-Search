function handleChatKeyDown(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        sendChatMessage();
    }
}

function clearChatMessages() {
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

function sendChatMessage() {
    const input = document.getElementById('chatInput');
    const question = input.value.trim();
    const sendBtn = document.getElementById('chatSendBtn');

    if (!question) return;

    const checkedBoxes = document.querySelectorAll('.judgment-cb:checked');
    if (checkedBoxes.length === 0) {
        alert("請先在左側搜尋結果中「勾選」您想要讓 AI 分析的判決書！");
        return;
    }

    const selectedIds = Array.from(checkedBoxes).map(cb => cb.value);
    const selectedJudgments = judgmentsData.filter(item => selectedIds.includes(item.id));

    appendChatMessage('user', escapeHtml(question));
    input.value = '';
    input.disabled = true;
    sendBtn.disabled = true;

    const loadingRow = appendChatMessage('bot', `
        <div class="chat-typing">
            <span></span><span></span><span></span>
        </div>
        <span style="color:#64748b; font-size:0.88em; margin-left:4px;">AI 正在研讀您選取的 <strong>${selectedJudgments.length}</strong> 筆案件並統整分析中...</span>
    `);

    const contentsToSent = selectedJudgments.map(item => {
        const idParts = item.id ? item.id.split(',') : [];
        const displayYear = (item.year && item.year.trim() !== "") ? item.year : (idParts[1] || "");
        const displayType = (item.case_type && item.case_type.trim() !== "") ? item.case_type : (idParts[2] || "");
        const displayNo = (item.case_no && item.case_no.trim() !== "") ? item.case_no : (idParts[3] || "");
        return `【${displayYear}年度${displayType}字第${displayNo}號】\n${item.content}`;
    });

    fetch('/api/ask_multiple', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            judgments_content: contentsToSent,
            question: question
        })
    })
    .then(res => res.json())
    .then(data => {
        const botBubble = loadingRow.querySelector('.chat-bubble');
        let rawAnswer = "";
        if (Array.isArray(data.answer)) {
            rawAnswer = data.answer.map(item => item.text || "").join("\n");
        } else if (typeof data.answer === 'string') {
            rawAnswer = data.answer;
        } else {
            rawAnswer = JSON.stringify(data.answer);
        }
        const formattedAnswer = rawAnswer.replace(/\n/g, '<br>');
        botBubble.innerHTML = formattedAnswer;
    })
    .catch(err => {
        console.error(err);
        const botBubble = loadingRow.querySelector('.chat-bubble');
        botBubble.innerHTML = `<span style="color:#d32f2f;">連線失敗：請確認後端伺服器與本機模型服務是否正常啟動。</span>`;
    })
    .finally(() => {
        if (input) {
            input.disabled = false;
            input.focus();
        }
        if (sendBtn) {
            sendBtn.disabled = false;
        }
        const chatMessages = document.getElementById('chatMessages');
        if (chatMessages) {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    });
}