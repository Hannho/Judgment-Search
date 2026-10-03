// ==========================================
// 全域狀態變數
// ==========================================
let judgmentsData = [];
let currentSearchKeywords = [];
let currentPage = 1;
const itemsPerPage = 10;
let totalItems = 0;
let currentSearchPayload = {};

let isFavoritesMode = false;
let currentUser = null;
let usersList = [];
let foldersList = [];       
let favMap = {};            
let currentSideId = null;

let currentHighlights = [];
let pendingSel = null;          
let editingAnnIndex = null;     

// ==========================================
// 基礎工具函式
// ==========================================
function apiHeaders() {
    const h = { 'Content-Type': 'application/json' };
    if (currentUser) h['X-User-Id'] = String(currentUser.id);
    return h;
}

function escapeHtml(text) {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return text.replace(/[&<>"']/g, m => map[m]);
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function showSearchError(msg) {
    const errBox = document.getElementById('searchErrorMessage');
    errBox.textContent = `⚠️ ${msg}`;
    errBox.style.display = 'block';
}

function clearSearchError() {
    const errBox = document.getElementById('searchErrorMessage');
    errBox.textContent = '';
    errBox.style.display = 'none';
}

function getSideText(item) {
    return (item && item.content ? item.content : "").replace(/\r\n?/g, "\n");
}

function formatROCDate(dateStr) {
    if (!dateStr) return dateStr;
    if (dateStr.includes('-')) {
        const parts = dateStr.split('-');
        if (parts.length === 3) {
            const year = parseInt(parts[0], 10) - 1911;
            return `${year}.${parts[1]}.${parts[2]}`;
        }
    }
    if (dateStr.length === 8) {
        const year = parseInt(dateStr.substring(0, 4)) - 1911;
        return `${year}.${dateStr.substring(4, 6)}.${dateStr.substring(6, 8)}`;
    }
    return dateStr;
}

// 法院對照表
const courtMapping = {
    "TPS": "最高法院", "TPA": "最高行政法院", "TPC": "懲戒法院", "CPC": "司法院憲法法庭",
    "TPH": "臺灣高等法院", "TCH": "臺灣高等法院臺中分院", "TNH": "臺灣高等法院臺南分院",
    "KSH": "臺灣高等法院高雄分院", "HLH": "臺灣高等法院花蓮分院", "KMH": "福建高等法院金門分院",
    "TPB": "臺北高等行政法院", "TCB": "臺中高等行政法院", "KSB": "高雄高等行政法院",
    "TPD": "臺灣臺北地方法院", "SLD": "臺灣士林地方法院", "PCD": "臺灣新北地方法院",
    "TYD": "臺灣桃園地方法院", "SCD": "臺灣新竹地方法院", "MLD": "臺灣苗栗地方法院",
    "TCD": "臺灣臺中地方法院", "CHD": "臺灣彰化地方法院", "NTD": "臺灣南投地方法院",
    "YLD": "臺灣雲林地方法院", "CYD": "臺灣嘉義地方法院", "TND": "臺灣臺南地方法院",
    "KSD": "臺灣高雄地方法院", "PTD": "臺灣屏東地方法院", "TTD": "臺灣臺東地方法院",
    "HLD": "臺灣花蓮地方法院", "ILD": "臺灣宜蘭地方法院", "KLD": "臺灣基隆地方法院",
    "PHD": "臺灣澎湖地方法院", "KMD": "福建金門地方法院", "LCD": "福建連江地方法院",
    "CTD": "臺灣橋頭地方法院", "ULD": "臺灣雲林地方法院", 
    "TPE": "臺灣臺北地方法院臺北簡易庭", "SDE": "臺灣臺北地方法院新店簡易庭",
    "SLE": "臺灣士林地方法院士林簡易庭", "NIE": "臺灣士林地方法院內湖簡易庭", "NHE": "臺灣臺北地方法院內湖簡易庭",
    "PCE": "臺灣新北地方法院板橋簡易庭", "STE": "臺灣新北地方法院三重簡易庭",
    "KLE": "臺灣基隆地方法院基隆簡易庭", 
    "TYE": "臺灣桃園地方法院桃園簡易庭", "CLE": "臺灣桃園地方法院中壢簡易庭",
    "SJE": "臺灣新竹地方法院新竹簡易庭", "CDE": "臺灣新竹地方法院竹東簡易庭",
    "MLE": "臺灣苗栗地方法院苗栗簡易庭",
    "TCE": "臺灣臺中地方法院臺中簡易庭", "FYE": "臺灣臺中地方法院豐原簡易庭", "CSE": "臺灣臺中地方法院清水簡易庭", 
    "CHE": "臺灣彰化地方法院彰化簡易庭", "YLE": "臺灣彰化地方法院員林簡易庭", "PDE": "臺灣彰化地方法院北斗簡易庭", "OLE": "臺灣彰化地方法院員林簡易庭",
    "NTE": "臺灣南投地方法院南投簡易庭", "PLE": "臺灣南投地方法院埔里簡易庭",
    "ULE": "臺灣雲林地方法院雲林簡易庭", "TLE": "臺灣雲林地方法院斗六簡易庭", "HUE": "臺灣雲林地方法院虎尾簡易庭", "PKE": "臺灣雲林地方法院北港簡易庭",
    "CYE": "臺灣嘉義地方法院嘉義簡易庭", "PZE": "臺灣嘉義地方法院朴子簡易庭",
    "TNE": "臺灣臺南地方法院臺南簡易庭", "SYE": "臺灣臺南地方法院新營簡易庭", "SSE": "臺灣臺南地方法院新市簡易庭", "LYE": "臺灣臺南地方法院柳營簡易庭",
    "KSE": "臺灣高雄地方法院高雄簡易庭", "FSE": "臺灣高雄地方法院鳳山簡易庭", "GSE": "臺灣橋頭地方法院岡山簡易庭", "CCE": "臺灣橋頭地方法院橋頭簡易庭", "CTE": "臺灣橋頭地方法院橋頭簡易庭",
    "PTE": "臺灣屏東地方法院屏東簡易庭", "CPE": "臺灣屏東地方法院潮州簡易庭",
    "ILE": "臺灣宜蘭地方法院宜蘭簡易庭", "LTE": "臺灣宜蘭地方法院羅東簡易庭",
    "HLE": "臺灣花蓮地方法院花蓮簡易庭", 
    "TTE": "臺灣臺東地方法院臺東簡易庭",
    "MKE": "臺灣澎湖地方法院馬公簡易庭", 
    "KME": "福建金門地方法院金城簡易庭", 
    "LCE": "福建連江地方法院連江簡易庭",
    "KSY": "臺灣高雄少年及家事法院", "IPC": "智慧財產及商業法院"
};

function getCourtName(item) {
    if (!item) return "未知法院";
    const content = item.content || "";
    const firstLine = content.split('\n')[0] || "";
    const matchCourt = firstLine.match(/([^\s]+(?:法院|法庭))/);
    if (matchCourt && matchCourt[1]) return matchCourt[1].trim();

    const id = item.id || "";
    const firstSegment = id.split(',')[0] || "";
    const prefix3 = firstSegment.substring(0, 3);
    if (courtMapping[prefix3]) return courtMapping[prefix3];
    if (courtMapping[firstSegment]) return courtMapping[firstSegment];
    return prefix3 || "未知法院";
}

function getDocumentKind(item) {
    const content = item.content || "";
    const firstLine = content.split('\n')[0] || "";
    if (firstLine.includes("裁定") || content.includes("裁定如下") || firstLine.includes("支付命令")) return "裁定";
    if (firstLine.includes("判決") || content.includes("判決如下")) return "判決";
    return "裁判";
}