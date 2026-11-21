import asyncio
import datetime
from typing import Optional, Tuple
from services.sync_service import sync_daily_judgments

scheduler_state = {
    "is_running": False,
    "next_run_time": None,
    "last_run_time": None,
    "last_run_result": None
}

_scheduler_task: Optional[asyncio.Task] = None


def get_seconds_until_next_3am() -> Tuple[float, datetime.datetime]:
    now = datetime.datetime.now()
    target = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if now >= target:
        target += datetime.timedelta(days=1)
    seconds = (target - now).total_seconds()
    return seconds, target


async def run_scheduler_loop():
    global scheduler_state
    scheduler_state["is_running"] = True
    print("[scheduler] 司法院每日裁判自動排程器已啟動（預定執行時間：每日凌晨 03:00）")

    while scheduler_state["is_running"]:
        try:
            seconds_wait, next_target = get_seconds_until_next_3am()
            scheduler_state["next_run_time"] = next_target.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[scheduler] 下次同步任務預計於 {scheduler_state['next_run_time']} 執行（約待機 {seconds_wait / 3600:.1f} 小時）")

            # 等待到凌晨 3:00
            await asyncio.sleep(seconds_wait)

            # 凌晨 3:00 到達，於官方服務開放時段 (00:00~06:00) 執行每日異動 API 同步
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[scheduler] 凌晨 03:00 排程時間到達，開始呼叫司法院每日異動清單 API (JList / JDoc)...")

            # 於獨立執行緒中執行同步任務，避免阻塞非同步事件循環
            res = await asyncio.to_thread(sync_daily_judgments)

            scheduler_state["last_run_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            scheduler_state["last_run_result"] = res
            print(f"[scheduler] 每日同步作業執行完成：{res}")

        except asyncio.CancelledError:
            print("[scheduler] 排程器收到中止信號，已停止。")
            scheduler_state["is_running"] = False
            break
        except Exception as e:
            print(f"[scheduler] 排程循環發生異常：{e}")
            # 發生意外錯誤時稍微等待 60 秒後重試，防止無窮迴圈
            await asyncio.sleep(60)


def start_nightly_scheduler():
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(run_scheduler_loop())
    return _scheduler_task


def get_scheduler_status() -> dict:
    global scheduler_state
    if scheduler_state["is_running"] and not scheduler_state["next_run_time"]:
        _, next_target = get_seconds_until_next_3am()
        scheduler_state["next_run_time"] = next_target.strftime("%Y-%m-%d %H:%M:%S")
    return scheduler_state
