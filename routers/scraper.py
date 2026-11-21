import os
import re
import time
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

router = APIRouter()

BASE = "https://judgment.judicial.gov.tw/FJUD/"
DEBUG_DIR = "debug"          # 失敗時會把截圖與 HTML 存在這裡
DEBUG_ALWAYS = False         # 設 True 則每次都存檔（排查用）


class JudgmentRequest(BaseModel):
    id: str
    year: str
    case_type: str
    case_no: str
    date: str
    content: str = ""
    include_self: bool = True   # 預設 True：完整保留本案在內的所有歷審紀錄，與司法院官方數量一致


COURT_MAPPING = {
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
}


# ---------------------------------------------------------------------------
# JavaScript 片段
# ---------------------------------------------------------------------------

# 找出「歷審」專屬容器內的 data.aspx 連結（嚴格排除分頁導航按鈕，且不爬出至外層）
JS_FIND_HISTORY_LINKS = r"""
const cur = arguments[0];
const idOf = a => { try { return new URL(a.href, location.href).searchParams.get('id') || ''; } catch (e) { return ''; } };
const isNavButton = a => {
    const t = (a.textContent || '').trim();
    if (/^(下一筆|上一筆|第一筆|最末筆|回列表|回裁判列表|友善列印|回查詢結果)$/.test(t)) return true;
    if (a.href && (a.href.includes('&ot=in') || a.href.includes('?ot=in'))) return true;
    return false;
};
const dataLinks = root => Array.from(root.querySelectorAll('a[href*="data.aspx"]'))
    .filter(a => { const i = idOf(a); return i && i !== cur && !isNavButton(a); });

// 1. 優先直接在歷審裁判專屬容器找
const panel = document.querySelector('[id^="JudHis"], #JudHis, [id*="relaHis"], [id*="RelaHis"], .rela-his');
if (panel) {
    const ls = dataLinks(panel);
    if (ls.length) return ls.map(a => ({title: (a.textContent || '').trim(), url: a.href}));
}

// 2. 透過含「歷審」的標題元素往上找到所屬 panel，但嚴禁跳出至 panel-group 或外層主容器
const hits = Array.from(document.querySelectorAll('body *')).filter(el =>
    Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.includes('歷審')));

for (const el of hits) {
    const p = el.closest('.panel, .card, [class*="panel-"], [class*="card-"]');
    if (p && !p.classList.contains('panel-group')) {
        const ls = dataLinks(p);
        if (ls.length) return ls.map(a => ({title: (a.textContent || '').trim(), url: a.href}));
    }
}
return [];
"""

# 點擊含「歷審」字樣的元素（可能是頁籤、按鈕、折疊面板）。回傳實際點到的數量
JS_CLICK_HISTORY_TOGGLE = r"""
const max = arguments[0];
const hits = Array.from(document.querySelectorAll('body *')).filter(el =>
    Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.includes('歷審')));
let clicked = 0;
for (const el of hits) {
    const target = el.closest('a,button,[role=tab],[data-toggle],[data-bs-toggle],li,.panel-heading') || el;
    try { target.click(); clicked++; } catch (e) {}
    if (clicked >= max) break;
}
return clicked;
"""

# 取得頁面上所有 data.aspx 連結（排除自己與分頁導覽按鈕）。供「點擊前後比對」使用
JS_ALL_DATA_LINKS = r"""
const cur = arguments[0];
const idOf = a => { try { return new URL(a.href, location.href).searchParams.get('id') || ''; } catch (e) { return ''; } };
const isNavButton = a => {
    const t = (a.textContent || '').trim();
    if (/^(下一筆|上一筆|第一筆|最末筆|回列表|回裁判列表|友善列印|回查詢結果)$/.test(t)) return true;
    if (a.href && (a.href.includes('&ot=in') || a.href.includes('?ot=in'))) return true;
    return false;
};
return Array.from(document.querySelectorAll('a[href*="data.aspx"]'))
    .filter(a => { const i = idOf(a); return i && i !== cur && !isNavButton(a); })
    .map(a => ({title: (a.textContent || '').trim(), url: a.href}));
"""

# 找「相關法條」面板：定位專屬的法條容器，並嚴格排除歷審裁判與審理備註
JS_FIND_LAW_ITEMS = r"""
const isNotLaw = (text, url) => {
    if (!text) return true;
    if (url && /data\.aspx\?[^"]*ty=JD/i.test(url)) return true;
    if (/(法院|判決|裁定|歷審|字第.*號|無歷審|繫屬法院|審理中|撤回上訴)/i.test(text)) return true;
    return false;
};

// 1. 優先匹配司法院標準相關法條區塊 (#JudrelaLaw 或包含 rela-law 樣式)
const lawContainers = Array.from(document.querySelectorAll('#JudrelaLaw, [id*="relaLaw"], [id*="RelaLaw"], #JudLaw, [id*="JudLaw"]'));
for (const container of lawContainers) {
    const lis = Array.from(container.querySelectorAll('li'));
    if (lis.length) {
        const filtered = lis
            .map(li => {
                const a = li.querySelector('a[href]');
                return {
                    text: (li.textContent || '').replace(/\s+/g, ' ').trim(),
                    url: a ? a.href : ''
                };
            })
            .filter(item => !isNotLaw(item.text, item.url));
        if (filtered.length) return filtered;
    }
}

// 2. 備援：透過包含「相關法條」文字的標題元素往上找到所屬 panel，但嚴禁跳出至 .panel-group 或父層 accordion
const hits = Array.from(document.querySelectorAll('body *')).filter(el =>
    Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.includes('相關法條')));

for (const el of hits) {
    // 限制在所屬的 panel / card 內部，不得往外爬到包含歷審裁判的 panel-group
    const panel = el.closest('.panel, .card, [class*="panel-"], [class*="card-"]');
    if (panel && !panel.classList.contains('panel-group')) {
        const body = panel.querySelector('.panel-collapse, .panel-body, .card-body') || panel;
        const lis = Array.from(body.querySelectorAll('li'));
        if (lis.length) {
            const filtered = lis
                .map(li => {
                    const a = li.querySelector('a[href]');
                    return {
                        text: (li.textContent || '').replace(/\s+/g, ' ').trim(),
                        url: a ? a.href : ''
                    };
                })
                .filter(item => !isNotLaw(item.text, item.url));
            if (filtered.length) return filtered;
        }
    }
}
return [];
"""

# 若「歷審」是一個會導向別頁的連結，找出它的 href
JS_FIND_HISTORY_HREF = r"""
const hits = Array.from(document.querySelectorAll('a[href]')).filter(a =>
    a.textContent.includes('歷審') && !/^javascript:|^#/i.test(a.getAttribute('href') || ''));
return hits.length ? hits[0].href : '';
"""


# ---------------------------------------------------------------------------
# 工具函式
# ---------------------------------------------------------------------------

def parse_target_date(date_str: str) -> str:
    """把 20260731 / 2026-07-31 / 2026/7/31 或民國 115.07.31 / 1150731 轉成民國 115.07.31 格式。"""
    date_str = (date_str or "").strip()
    if not date_str:
        return ""
    if len(date_str) >= 8 and date_str[:8].isdigit():
        return f"{int(date_str[:4]) - 1911}.{date_str[4:6]}.{date_str[6:8]}"
    if len(date_str) == 7 and date_str.isdigit():
        return f"{int(date_str[:3])}.{date_str[3:5]}.{date_str[5:7]}"
    nums = re.findall(r"\d+", date_str)
    if len(nums) >= 3:
        year = int(nums[0])
        if year >= 1900:
            year -= 1911
        return f"{year}.{nums[1].zfill(2)}.{nums[2].zfill(2)}"
    return ""


def build_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-notifications")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    options.page_load_strategy = "eager"

    for path in ("/usr/bin/chromium", "/usr/bin/chromium-browser"):
        if os.path.exists(path):
            options.binary_location = path
            break

    if os.path.exists("/usr/bin/chromedriver"):
        service = Service("/usr/bin/chromedriver")
    elif os.path.exists("/usr/lib/chromium-browser/chromedriver"):
        service = Service("/usr/lib/chromium-browser/chromedriver")
    else:
        service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)
    return driver


def dump(driver, tag: str):
    """存截圖與 HTML 方便除錯（含 iframe 內容）。"""
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        stamp = time.strftime("%H%M%S")
        base = os.path.join(DEBUG_DIR, f"{stamp}_{tag}")
        driver.switch_to.default_content()
        driver.save_screenshot(base + ".png")
        with open(base + "_top.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        try:
            driver.switch_to.frame(driver.find_element(By.ID, "iframe-data"))
            with open(base + "_iframe.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
        except Exception:
            pass
        driver.switch_to.default_content()
        print(f"[debug] 已存檔 {base}.* | url={driver.current_url}")
    except Exception as e:
        print(f"[debug] 存檔失敗: {e}")


def enter_content_frame(driver):
    """若頁面有 iframe#iframe-data（搜尋結果流程）就切進去，否則留在最上層。"""
    driver.switch_to.default_content()
    try:
        frame = driver.find_element(By.ID, "iframe-data")
        driver.switch_to.frame(frame)
    except Exception:
        pass


def reconstruct_judgment_title_from_jid(jid: str) -> str:
    """從 JID 解析並重建標準判決字號，防止爬蟲抓回空標題或分頁導覽文字。"""
    if not jid:
        return ""
    parts = jid.split(",")
    if len(parts) < 4:
        return jid
    court_code = parts[0][:3].upper()
    court_name = COURT_MAPPING.get(court_code, "")
    year = parts[1]
    case_type = parts[2]
    case_no = parts[3]
    date_str = parts[4] if len(parts) > 4 else ""
    date_formatted = parse_target_date(date_str)

    # 判斷判決或裁定
    doc_kind = "裁判"
    if "裁定" in case_type or any(k in case_type for k in ("聲", "抗", "執", "司票", "救", "保")):
        doc_kind = "裁定"
    elif any(k in case_type for k in ("訴", "上", "易", "簡")):
        doc_kind = "判決"

    title = f"{court_name} {year} 年度 {case_type} 字第 {case_no} 號{doc_kind}"
    if date_formatted:
        title += f"({date_formatted})"
    return title.strip()


def normalize(items):
    """清理標題、排除分頁導覽按鈕雜訊、去重，並在標題遺失時由 JID 自動還原。"""
    INVALID_TITLES = {"下一筆", "上一筆", "第一筆", "最末筆", "回列表", "回裁判列表", "友善列印", "回查詢結果", "本件無歷審裁判", "無歷審"}
    seen, out = set(), []
    for it in items or []:
        url = (it.get("url") or "").strip()
        if not url:
            continue
        if not url.startswith("http"):
            url = BASE + url.lstrip("/")

        # 嚴格排除搜尋分頁瀏覽參數 (&ot=in)
        if "ot=in" in url:
            continue

        jid = jid_from_url(url)
        if url in seen or (jid and jid in seen):
            continue
        seen.add(url)
        if jid:
            seen.add(jid)

        raw_title = re.sub(r"\s+", " ", (it.get("title") or "")).strip()

        # 若抓回的標題是「下一筆」、「最末筆」等分頁按鈕，或標題為空/僅為網址，自動還原
        if not raw_title or raw_title in INVALID_TITLES or raw_title.startswith("http") or "data.aspx" in raw_title:
            if jid:
                title = reconstruct_judgment_title_from_jid(jid)
            else:
                continue
        else:
            title = raw_title

        out.append({"title": title, "url": url, "jid": jid})
    return out


def wait_ready(driver, timeout=10):
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 抓歷審的核心邏輯
# ---------------------------------------------------------------------------

def extract_history(driver, cur_id: str):
    """
    目前停留在判決內頁。依序嘗試：
      1. 歷審區塊已經顯示 → 直接抓
      2. 點擊「歷審」頁籤/面板後再抓（含點擊前後連結比對）
      3. 「歷審」是導向別頁的連結 → 前往後抓
      4. 最後手段：用 regex 掃整份 HTML
    """
    # 司法院的「歷審裁判」清單本身就包含目前這一筆判決（例如顯示 2 筆就是一審 + 本案），
    # 所以不要排除目前的 JID，讓前端拿到完整的歷審清單。
    cur_id = ""

    # 1. 直接抓
    enter_content_frame(driver)
    links = normalize(driver.execute_script(JS_FIND_HISTORY_LINKS, cur_id))
    if links:
        print(f"[history] 方法1 直接抓到 {len(links)} 筆")
        return links

    # 2. 點擊展開
    enter_content_frame(driver)
    before = {x["url"] for x in normalize(driver.execute_script(JS_ALL_DATA_LINKS, cur_id))}
    for _ in range(3):  # 最多嘗試點 3 個含「歷審」的元素
        enter_content_frame(driver)
        clicked = driver.execute_script(JS_CLICK_HISTORY_TOGGLE, 1)
        if not clicked:
            break
        time.sleep(1.5)
        wait_ready(driver, 5)
        enter_content_frame(driver)

        links = normalize(driver.execute_script(JS_FIND_HISTORY_LINKS, cur_id))
        if links:
            print(f"[history] 方法2 點擊後抓到 {len(links)} 筆")
            return links

        after = normalize(driver.execute_script(JS_ALL_DATA_LINKS, cur_id))
        diff = [x for x in after if x["url"] not in before]
        if diff:
            print(f"[history] 方法2 前後比對抓到 {len(diff)} 筆")
            return diff

    # 3. 導向別頁的「歷審」連結
    enter_content_frame(driver)
    href = driver.execute_script(JS_FIND_HISTORY_HREF)
    if href:
        print(f"[history] 方法3 前往歷審頁 {href}")
        driver.get(href)
        wait_ready(driver)
        time.sleep(1.5)
        enter_content_frame(driver)
        links = normalize(driver.execute_script(JS_ALL_DATA_LINKS, cur_id))
        if links:
            return links

    # 4. regex 掃 HTML（最後手段）
    enter_content_frame(driver)
    html = driver.page_source
    found = re.findall(r'href="([^"]*data\.aspx\?[^"]*id=[^"]+)"', html, flags=re.I)
    items = []
    for h in found:
        if "ot=in" in h:
            continue
        h = h.replace("&amp;", "&")
        absolute = urllib.parse.urljoin(driver.current_url, h)
        qid = urllib.parse.parse_qs(urllib.parse.urlparse(absolute).query).get("id", [""])[0]
        if qid and qid != cur_id:
            items.append({"title": "", "url": absolute})
    links = normalize(items)
    if links:
        print(f"[history] 方法4 regex 抓到 {len(links)} 筆（標題可能是空的）")
    return links


def is_valid_law_item(text: str, url: str) -> bool:
    if not text:
        return False
    # 判決書連結或含有判決/法院/歷審資訊，絕非法條
    if "data.aspx?ty=JD" in url or "ty=JD" in url:
        return False
    invalid_keywords = ["法院", "判決", "裁定", "歷審", "無歷審", "繫屬法院", "審理中", "撤回上訴", "字第", "本件無"]
    if any(k in text for k in invalid_keywords):
        return False
    return True


def extract_laws(driver):
    """抓判決頁右側「相關法條」清單。回傳 [{"text": "...", "url": "..."}]；沒有該面板或無合法條文就回傳空陣列。"""
    try:
        enter_content_frame(driver)
        items = driver.execute_script(JS_FIND_LAW_ITEMS) or []
    except Exception as e:
        print(f"[laws] 抓取相關法條失敗: {e}")
        return []

    seen, out = set(), []
    for it in items:
        text = re.sub(r"\s+", " ", (it.get("text") or "")).strip()
        url = (it.get("url") or "").strip()
        if not text or text in seen:
            continue
        if not is_valid_law_item(text, url):
            continue
        seen.add(text)
        out.append({"text": text, "url": url})
    print(f"[laws] 抓到 {len(out)} 筆合法相關法條")
    return out


def open_by_search(driver, req: JudgmentRequest, court_name: str, target_date_str: str):
    """備援流程：走首頁搜尋框 → 列表頁比對日期 → 進判決內頁。"""
    wait = WebDriverWait(driver, 12)
    driver.get(BASE + "default.aspx")

    search_query = f"{court_name} {req.year} {req.case_type} {req.case_no}"
    search_input = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='可輸入法院名稱']"))
    )
    search_input.clear()
    search_input.send_keys(search_query)
    search_input.send_keys(Keys.RETURN)

    wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "iframe-data")))
    time.sleep(1.5)

    # 若停在列表頁，點擊日期相符的那一筆；若已自動跳轉到內頁則沒有列表連結
    if target_date_str:
        try:
            xpath = f"//tr[td[contains(normalize-space(.), '{target_date_str}')]]//a"
            link = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            driver.execute_script("arguments[0].click();", link)
            time.sleep(2)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 資料庫比對：歷審裁判先查自己的資料庫，沒有才用司法院連結
# ---------------------------------------------------------------------------

# 共用專案既有的連線池（database.py）。judgments.id 存的就是 JID，
# 例如 STEV,108,店小,1032,20190912,1，與司法院連結裡的 id 參數格式一致。
import json
from database import run_sql, get_cached_crawler_data, set_cached_crawler_data


LAW_EXTRACT_REGEX = re.compile(
    r'((?:中華民國)?(?:刑法|民法|刑事訴訟法|民事訴訟法|行政訴訟法|強制執行法|家事事件法|勞動基準法|消費者保護法|組織犯罪防制條例|洗錢防制法|毒品危害防制條例|道路交通管理處罰條例|證券交易法|保險法|公司法|票據法|著作權法|商標法|專利法|個人資料保護法|國家賠償法|少年事件處理法|貪污治罪條例|槍砲彈藥刀械管制條例|政府採購法|破產法|土地法|公寓大廈管理條例|戶籍法|入出國及移民法|憲法訴訟法)\s*第\s*[0-9一二三四五六七八九十百千]+(?:\s*條之\s*[0-9一二三四五六七八九十]+|\s*條)(?:\s*第\s*[0-9一二三四五六七八九十]+\s*項)?(?:\s*第\s*[0-9一二三四五六七八九十]+\s*款)?)'
)

def extract_laws_from_text(content: str) -> list:
    """當司法院外部網站未載明相關法條時，自動從判決書內文精準萃取援引法條"""
    if not content:
        return []
    matches = LAW_EXTRACT_REGEX.findall(content)
    seen = set()
    out = []
    for m in matches:
        clean = re.sub(r'\s+', '', m).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        encoded = urllib.parse.quote(clean)
        out.append({
            "text": clean,
            "url": f"https://law.moj.gov.tw/LawClass/LawSearchContent.aspx?pcode=&kw={encoded}"
        })
    return out


def jid_from_url(url: str) -> str:
    """從司法院連結取出 id 參數（即 JID）。"""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return urllib.parse.unquote(q.get("id", [""])[0]).strip()


def find_existing_jids(jids):
    """回傳這些 JID 中，已存在於自己資料庫的集合。DB 出錯時回傳空集合（等於全部走外部連結）。"""
    jids = [j for j in jids if j]
    if not jids:
        return set()
    try:
        rows = run_sql(
            "SELECT id FROM judgments WHERE id = ANY(%s)",
            (jids,),
            fetch=True,
        )
        return {r["id"] for r in rows}
    except Exception as e:
        print(f"[db] 查詢本地資料庫失敗，全部改用外部連結: {e}")
        return set()


def attach_db_status(items):
    """每筆歷審加上 jid 與 in_db。in_db=True 代表自己的資料庫已有，前端可直接開本地那筆。"""
    existing = find_existing_jids([jid_from_url(h["url"]) for h in items])
    for h in items:
        h["jid"] = jid_from_url(h["url"])
        h["in_db"] = h["jid"] in existing
    return items


class JudgmentIdRequest(BaseModel):
    id: str


@router.post("/get_judgment")
def get_judgment(req: JudgmentIdRequest):
    """依 JID 取回本地資料庫的單筆判決（欄位同搜尋結果列表），供歷審清單在站內開啟。"""
    rows = run_sql("SELECT * FROM judgments WHERE id = %s", (req.id,), fetch=True)
    if not rows:
        raise HTTPException(status_code=404, detail="local judgment not found")
    return rows[0]


@router.post("/get_history")
def get_history(req: JudgmentRequest):
    # ---- 優先查閱本地快取（含負向快取：查無歷審亦直接回傳，防止無謂重啟 Chrome）----
    cached = get_cached_crawler_data(req.id)
    if cached:
        try:
            cached_history = json.loads(cached.get("history_json") or "[]")
            cached_laws = json.loads(cached.get("laws_json") or "[]")
            if not req.include_self and cached_history:
                me = urllib.parse.unquote(req.id).strip().lower()
                cached_history = [
                    h for h in cached_history
                    if urllib.parse.unquote(
                        urllib.parse.parse_qs(urllib.parse.urlparse(h["url"]).query).get("id", [""])[0]
                    ).strip().lower() != me
                ]
            if not cached_laws:
                raw_content = req.content
                if not raw_content:
                    c_rows = run_sql("SELECT content FROM judgments WHERE id = %s", (req.id,), fetch=True)
                    if c_rows and c_rows[0].get("content"):
                        raw_content = c_rows[0]["content"]
                if raw_content:
                    cached_laws = extract_laws_from_text(raw_content)
                    if cached_laws:
                        try:
                            set_cached_crawler_data(req.id, json.dumps(cached_history), json.dumps(cached_laws))
                        except Exception:
                            pass
            cached_history = attach_db_status(cached_history)
            print(f"[get_history] 命中本地快取: {req.id} (共 {len(cached_history)} 筆歷審, {len(cached_laws)} 筆法條)")
            return {"history": cached_history, "laws": cached_laws, "cached": True}
        except Exception as e:
            print(f"[get_history] 快取解析失敗，退回現場爬蟲模式: {e}")

    # ---- 完整 Selenium 瀏覽器流程（司法院歷審折疊面板必須透過 JS 點擊展開）----
    court_code = req.id.split(",")[0][:3]
    court_name = COURT_MAPPING.get(court_code, "未知法院")
    target_date_str = parse_target_date(req.date)

    driver = None
    history_results = []
    law_results = []
    debug_note = ""

    try:
        driver = build_driver()

        # ---- 策略 A：用 JID 直接開判決內頁（最快、最穩）----
        direct_url = BASE + "data.aspx?ty=JD&id=" + urllib.parse.quote(req.id, safe="")
        print(f"[get_history] 直接開啟 {direct_url}")
        try:
            driver.get(direct_url)
            wait_ready(driver)
            time.sleep(2)
            # 先抓相關法條（歷審流程可能會點擊或換頁，所以法條要先抓）
            law_results = extract_laws(driver) or law_results
            history_results = extract_history(driver, req.id)
        except Exception as e:
            print(f"[get_history] 策略A失敗: {e}")
            debug_note = f"A: {e}"

        # ---- 策略 B：搜尋流程備援 ----
        if not history_results:
            print("[get_history] 策略A沒結果，改走搜尋流程")
            try:
                open_by_search(driver, req, court_name, target_date_str)
                law_results = extract_laws(driver) or law_results
                history_results = extract_history(driver, req.id)
            except Exception as e:
                print(f"[get_history] 策略B失敗: {e}")
                debug_note += f" | B: {e}"

        if DEBUG_ALWAYS:
            dump(driver, "final")

    except Exception as e:
        print(f"[crawler] 爬蟲發生錯誤: {e}")
        debug_note += f" | fatal: {e}"
        if driver:
            dump(driver, "fatal")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    # 司法院的歷審清單會把本案自己也列進去，預設把它濾掉
    if not req.include_self:
        me = urllib.parse.unquote(req.id).strip().lower()
        history_results = [
            h for h in history_results
            if urllib.parse.unquote(
                urllib.parse.parse_qs(urllib.parse.urlparse(h["url"]).query).get("id", [""])[0]
            ).strip().lower() != me
        ]

    # 若司法院線上法條為空，從判決書內文萃取援引法條
    if not law_results:
        raw_content = req.content
        if not raw_content:
            c_rows = run_sql("SELECT content FROM judgments WHERE id = %s", (req.id,), fetch=True)
            if c_rows and c_rows[0].get("content"):
                raw_content = c_rows[0]["content"]
        if raw_content:
            law_results = extract_laws_from_text(raw_content)

    # 成功爬取後寫入快取（包含空紀錄負向快取，杜絕無歷審案件重複啟動瀏覽器）
    if "fatal:" not in debug_note:
        try:
            set_cached_crawler_data(req.id, json.dumps(history_results), json.dumps(law_results))
            print(f"[get_history] 成功爬取並寫入快取: {req.id} (共 {len(history_results)} 筆歷審, {len(law_results)} 筆法條)")
        except Exception as ce:
            print(f"[crawler] 寫入快取失敗: {ce}")

    history_results = attach_db_status(history_results)

    result = {"history": history_results, "laws": law_results}
    if not history_results:
        result["debug"] = debug_note or "no history links found (case may have no history)"
    return result