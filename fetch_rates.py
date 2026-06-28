#!/usr/bin/env python3
"""
汇率数据抓取脚本 v7 — 官方数据源 + 增量更新 + 自包含HTML + 预警系统
使用 akshare 获取人民银行官方中间价（央行中间价）
每次运行后生成自包含的 index.html，并计算预警信息
"""

import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from collections import defaultdict
import akshare as ak
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
OUTPUT_JSON = os.path.join(DATA_DIR, "rates.json")
OUTPUT_HTML = os.path.join(SCRIPT_DIR, "index.html")
EMAIL_CONFIG = os.path.join(SCRIPT_DIR, "email_config.json")
VERSION_FILE = os.path.join(SCRIPT_DIR, "version.txt")
UPDATE_LOG = os.path.join(SCRIPT_DIR, "update_log.json")

SYMBOLS = {"美元": "USD", "日元": "JPY", "港币": "HKD"}

# ---------- 预警阈值 ----------
YELLOW_DAILY   = 1.0   # 单日 ±1%
YELLOW_WEEKLY  = 3.0   # 周   ±3%
YELLOW_MONTHLY = 4.0   # 月   ±4%
RED_DAILY      = 2.0   # 单日 ±2%
RED_WEEKLY     = 5.0   # 周   ±5%
RED_MONTHLY    = 8.0   # 月   ±8%
EXTREME_MARGIN = 1.0   # 距5年极值 1% 以内

PAIR_LABELS = {
    "USD/CNY": "美元兑人民币",
    "JPY/CNY": "日元兑人民币",
    "HKD/CNY": "港币兑人民币",
    "HKD/JPY": "港币兑日元",
    "JPY/HKD": "日元兑港币",
}

# ---------- 版本 & 更新日志 ----------
def read_version_str():
    """读取当前版本字符串（上次构建的版本），如 'Ver1.0'"""
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()
    return "Ver1.0"

def bump_version():
    """递增版本号，写回文件（供下次使用），返回新版本字符串"""
    s = read_version_str().lower().replace("v", "").replace("er", "")
    parts = s.split(".")
    if len(parts) == 2:
        major, minor = int(parts[0]), int(parts[1])
    else:
        major, minor = 1, 0
    minor += 1
    ver_str = f"Ver{major}.{minor}"
    with open(VERSION_FILE, "w") as f:
        f.write(ver_str)
    return ver_str

def record_update(version_str):
    """记录一次更新到 update_log.json"""
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    today = now.strftime("%Y-%m-%d")

    logs = []
    if os.path.exists(UPDATE_LOG):
        with open(UPDATE_LOG, "r", encoding="utf-8") as f:
            logs = json.load(f)

    # 统计今天已有几次更新
    today_count = sum(1 for e in logs if e.get("date", "").startswith(today))
    count_today = today_count + 1

    entry = {
        "version": version_str,
        "datetime": now_str,
        "date": today,
        "time": now.strftime("%H:%M:%S"),
        "count_today": count_today,
    }
    logs.append(entry)

    # 只保留最近 100 条
    logs = logs[-100:]

    with open(UPDATE_LOG, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

    return logs

def read_update_logs():
    """读取更新日志"""
    if os.path.exists(UPDATE_LOG):
        with open(UPDATE_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def load_existing():
    if os.path.exists(OUTPUT_JSON):
        with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def fetch_one(symbol, start_dt, end_dt):
    start_str = start_dt.strftime("%Y%m%d")
    end_str = end_dt.strftime("%Y%m%d")
    try:
        df = ak.currency_boc_sina(symbol=symbol, start_date=start_str, end_date=end_str)
        if df.empty:
            return None
        return df[["日期", "央行中间价"]].copy()
    except Exception as e:
        print(f"    错误: {e}")
        return None


def get_rates_for_range(symbol, code, start_dt, end_dt):
    all_rows = []
    current = start_dt
    while current <= end_dt:
        seg_end = min(current + timedelta(days=365), end_dt)
        df = fetch_one(symbol, current, seg_end)
        if df is not None and not df.empty:
            all_rows.append(df)
        current = seg_end + timedelta(days=1)

    if not all_rows:
        return {}

    combined = pd.concat(all_rows, ignore_index=True)
    combined["日期"] = pd.to_datetime(combined["日期"])
    combined = combined.drop_duplicates(subset=["日期"])
    combined = combined.sort_values("日期")

    result = {}
    for _, row in combined.iterrows():
        dt = row["日期"]
        if pd.isna(dt):
            continue
        val = row["央行中间价"]
        if pd.isna(val):
            continue
        ds = dt.strftime("%Y-%m-%d")
        val = float(val)
        if code == "USD":
            result[ds] = val / 100.0
        elif code == "JPY":
            result[ds] = val
        elif code == "HKD":
            result[ds] = val
    return result


def compute_pairs(usd_rates, jpy_rates, hkd_rates):
    all_dates = set()
    for d in [usd_rates, jpy_rates, hkd_rates]:
        all_dates.update(d.keys())
    all_dates = sorted(all_dates)

    daily = {p: {} for p in ["USD/CNY", "JPY/CNY", "HKD/CNY", "HKD/JPY", "JPY/HKD"]}

    for ds in all_dates:
        u = usd_rates.get(ds)
        j = jpy_rates.get(ds)
        h = hkd_rates.get(ds)
        if u is None or j is None or h is None:
            continue

        jpy_cny = j / 100.0
        hkd_cny = h / 100.0

        daily["USD/CNY"][ds] = round(u, 6)
        daily["JPY/CNY"][ds] = round(jpy_cny, 6)
        daily["HKD/CNY"][ds] = round(hkd_cny, 6)
        daily["HKD/JPY"][ds] = round(hkd_cny / jpy_cny, 6)
        daily["JPY/HKD"][ds] = round(jpy_cny / hkd_cny, 6)

    return daily


def calc_stats(daily):
    pairs = list(daily.keys())
    date_strs = sorted(set(k for p in pairs for k in daily[p].keys()))

    monthly = {}
    yearly = {}
    for pair in pairs:
        monthly[pair] = {}
        yearly[pair] = {}
        month_groups = defaultdict(list)
        year_groups = defaultdict(list)
        for ds in date_strs:
            if ds not in daily[pair] or daily[pair][ds] is None:
                continue
            dt = datetime.strptime(ds, "%Y-%m-%d")
            month_groups[f"{dt.year}-{dt.month:02d}"].append(daily[pair][ds])
            year_groups[str(dt.year)].append(daily[pair][ds])
        for mk in sorted(month_groups.keys()):
            vals = month_groups[mk]
            monthly[pair][mk] = {
                "avg": round(sum(vals)/len(vals), 6),
                "min": round(min(vals), 6),
                "max": round(max(vals), 6),
                "count": len(vals),
            }
        for yk in sorted(year_groups.keys()):
            vals = year_groups[yk]
            yearly[pair][yk] = {
                "avg": round(sum(vals)/len(vals), 6),
                "min": round(min(vals), 6),
                "max": round(max(vals), 6),
                "count": len(vals),
            }

    return daily, monthly, yearly, date_strs


def find_closest_date(dates_sorted, target_date):
    """在排序日期列表中找 <= target_date 的最大日期"""
    best = None
    for ds in dates_sorted:
        if ds <= target_date:
            best = ds
        else:
            break
    return best


def calc_alerts(daily):
    """为每个货币对计算预警信息"""
    alerts = {}
    for pair, rates in daily.items():
        dates = sorted(rates.keys())
        if len(dates) < 2:
            alerts[pair] = {"level": "none", "triggers": []}
            continue

        latest_date = dates[-1]
        latest_val = rates[latest_date]

        # 找5年极值
        vals = [rates[d] for d in dates]
        fivey_min = min(vals)
        fivey_max = max(vals)
        fivey_min_date = dates[vals.index(fivey_min)]
        fivey_max_date = dates[vals.index(fivey_max)]

        triggers = []
        level = "none"

        # 1) 单日变化
        prev_date = dates[-2]
        prev_val = rates[prev_date]
        daily_pct = (latest_val - prev_val) / prev_val * 100
        if abs(daily_pct) >= RED_DAILY:
            triggers.append({
                "type": "单日波动",
                "pct": round(daily_pct, 2),
                "threshold": RED_DAILY,
                "level": "red",
                "detail": f"较{prev_date}变动{daily_pct:+.2f}%"
            })
        elif abs(daily_pct) >= YELLOW_DAILY:
            triggers.append({
                "type": "单日波动",
                "pct": round(daily_pct, 2),
                "threshold": YELLOW_DAILY,
                "level": "yellow",
                "detail": f"较{prev_date}变动{daily_pct:+.2f}%"
            })

        # 2) 周变化（7个自然日）
        latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")
        week_target = (latest_dt - timedelta(days=7)).strftime("%Y-%m-%d")
        week_date = find_closest_date(dates, week_target)
        if week_date and week_date != latest_date:
            week_val = rates[week_date]
            weekly_pct = (latest_val - week_val) / week_val * 100
            if abs(weekly_pct) >= RED_WEEKLY:
                triggers.append({
                    "type": "周波动",
                    "pct": round(weekly_pct, 2),
                    "threshold": RED_WEEKLY,
                    "level": "red",
                    "detail": f"较{week_date}变动{weekly_pct:+.2f}%"
                })
            elif abs(weekly_pct) >= YELLOW_WEEKLY:
                triggers.append({
                    "type": "周波动",
                    "pct": round(weekly_pct, 2),
                    "threshold": YELLOW_WEEKLY,
                    "level": "yellow",
                    "detail": f"较{week_date}变动{weekly_pct:+.2f}%"
                })

        # 3) 月变化（30个自然日）
        month_target = (latest_dt - timedelta(days=30)).strftime("%Y-%m-%d")
        month_date = find_closest_date(dates, month_target)
        if month_date and month_date != latest_date:
            month_val = rates[month_date]
            monthly_pct = (latest_val - month_val) / month_val * 100
            if abs(monthly_pct) >= RED_MONTHLY:
                triggers.append({
                    "type": "月波动",
                    "pct": round(monthly_pct, 2),
                    "threshold": RED_MONTHLY,
                    "level": "red",
                    "detail": f"较{month_date}变动{monthly_pct:+.2f}%"
                })
            elif abs(monthly_pct) >= YELLOW_MONTHLY:
                triggers.append({
                    "type": "月波动",
                    "pct": round(monthly_pct, 2),
                    "threshold": YELLOW_MONTHLY,
                    "level": "yellow",
                    "detail": f"较{month_date}变动{monthly_pct:+.2f}%"
                })

        # 4) 距5年极值
        dist_to_min = (latest_val - fivey_min) / fivey_min * 100
        dist_to_max = (fivey_max - latest_val) / fivey_max * 100
        if dist_to_min < EXTREME_MARGIN:
            triggers.append({
                "type": "接近5年最低",
                "pct": round(dist_to_min, 2),
                "threshold": EXTREME_MARGIN,
                "level": "red",
                "detail": f"距5年最低({fivey_min_date} {fivey_min:.4f})仅{dist_to_min:.2f}%"
            })
        if dist_to_max < EXTREME_MARGIN:
            triggers.append({
                "type": "接近5年最高",
                "pct": round(dist_to_max, 2),
                "threshold": EXTREME_MARGIN,
                "level": "red",
                "detail": f"距5年最高({fivey_max_date} {fivey_max:.4f})仅{dist_to_max:.2f}%"
            })

        # 确定最终级别
        for t in triggers:
            if t["level"] == "red":
                level = "red"
                break
            elif t["level"] == "yellow":
                level = "yellow"

        alerts[pair] = {
            "level": level,
            "latest_date": latest_date,
            "latest_val": latest_val,
            "daily_change_pct": round(daily_pct, 2),
            "weekly_change_pct": round(weekly_pct, 2) if 'weekly_pct' in dir() else None,
            "monthly_change_pct": round(monthly_pct, 2) if 'monthly_pct' in dir() else None,
            "fivey_min": fivey_min,
            "fivey_max": fivey_max,
            "fivey_min_date": fivey_min_date,
            "fivey_max_date": fivey_max_date,
            "triggers": triggers,
        }

    # 修复 weekly/monthly 变量可能未定义的情况
    for pair in alerts:
        a = alerts[pair]
        if "weekly_pct" not in a or a.get("weekly_change_pct") is None:
            # 重新算
            dates = sorted(daily[pair].keys())
            latest_date = dates[-1]
            latest_val = daily[pair][latest_date]
            latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")
            week_date = find_closest_date(dates, (latest_dt - timedelta(days=7)).strftime("%Y-%m-%d"))
            month_date = find_closest_date(dates, (latest_dt - timedelta(days=30)).strftime("%Y-%m-%d"))
            if week_date and week_date != latest_date:
                a["weekly_change_pct"] = round((latest_val - daily[pair][week_date]) / daily[pair][week_date] * 100, 2)
            else:
                a["weekly_change_pct"] = None
            if month_date and month_date != latest_date:
                a["monthly_change_pct"] = round((latest_val - daily[pair][month_date]) / daily[pair][month_date] * 100, 2)
            else:
                a["monthly_change_pct"] = None

    return alerts


def send_email_if_needed(alerts):
    """如果存在预警，发送邮件通知"""
    if not os.path.exists(EMAIL_CONFIG):
        print("  ⚠️ 未配置邮件 (email_config.json 不存在)，跳过邮件发送")
        return

    try:
        with open(EMAIL_CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"  ⚠️ 读取邮件配置失败: {e}")
        return

    # 检查是否有需要通知的预警
    red_pairs = []
    yellow_pairs = []
    filtered_alerts = {}
    for pair, a in alerts.items():
        if a["level"] == "red":
            red_pairs.append(pair)
            filtered_alerts[pair] = a
        elif a["level"] == "yellow":
            yellow_pairs.append(pair)
            filtered_alerts[pair] = a

    if not red_pairs and not yellow_pairs:
        print("  ✅ 无预警，不发送邮件")
        return

    # 构建邮件内容
    subject_parts = []
    if red_pairs:
        subject_parts.append(f"🔴 {', '.join(red_pairs)} 红色预警")
    if yellow_pairs:
        subject_parts.append(f"🟡 {', '.join(yellow_pairs)} 黄色预警")
    subject = " ".join(subject_parts)

    body_lines = [f"汇率预警通知 — {datetime.now().strftime('%Y-%m-%d %H:%M')}", "=" * 50, ""]
    for pair, a in filtered_alerts.items():
        body_lines.append(f"【{PAIR_LABELS.get(pair, pair)}】{a['level'].upper()}")
        body_lines.append(f"  最新汇率: {a['latest_val']:.4f} ({a['latest_date']})")
        body_lines.append(f"  单日变动: {a['daily_change_pct']:+.2f}%")
        if a.get("weekly_change_pct") is not None:
            body_lines.append(f"  周变动:   {a['weekly_change_pct']:+.2f}%")
        if a.get("monthly_change_pct") is not None:
            body_lines.append(f"  月变动:   {a['monthly_change_pct']:+.2f}%")
        for t in a["triggers"]:
            body_lines.append(f"  ⚡ {t['detail']}")
        body_lines.append("")

    body = "\n".join(body_lines)

    try:
        msg = MIMEMultipart()
        msg["From"] = cfg["sender"]
        msg["To"] = ", ".join(cfg["recipients"])
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        if cfg.get("smtp_port") == 465:
            server = smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], timeout=15)
        else:
            server = smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=15)
            server.starttls()

        server.login(cfg["sender"], cfg["password"])
        server.sendmail(cfg["sender"], cfg["recipients"], msg.as_string())
        server.quit()
        print(f"  📧 预警邮件已发送至 {', '.join(cfg['recipients'])}")
    except Exception as e:
        print(f"  ❌ 邮件发送失败: {e}")


def save_and_generate(result):
    # 读取当前版本（用于本次构建），然后递增存回（供下次使用）
    version_str = read_version_str()
    bump_version()
    update_logs = record_update(version_str)

    result["meta"]["version"] = version_str
    result["meta"]["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    data_json = json.dumps(result, ensure_ascii=False)
    update_logs_json = json.dumps(update_logs, ensure_ascii=False)
    html = generate_html(data_json, version_str, update_logs_json)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ 版本 {version_str} | 数据已保存: {OUTPUT_JSON}")
    print(f"✅ 网页已生成: {OUTPUT_HTML}")
    print(f"   日期范围: {result['meta']['start_date']} ~ {result['meta']['end_date']}")
    print(f"   总交易日: {result['meta']['total_days']}")

    # 打印预警摘要 + 发送邮件
    alerts = result.get("alerts", {})
    print("\n--- 预警摘要 ---")
    alert_found = False
    for pair in result["meta"]["pairs"]:
        a = alerts.get(pair, {})
        lvl = a.get("level", "none")
        if lvl != "none":
            alert_found = True
            icon = "🔴" if lvl == "red" else "🟡"
            print(f"  {icon} {PAIR_LABELS.get(pair, pair)} [{lvl}]: {a.get('triggers', [])}")
    if not alert_found:
        print("  ✅ 当前无预警")
    send_email_if_needed(alerts)


def run_full():
    os.makedirs(DATA_DIR, exist_ok=True)
    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=5 * 365 + 10)

    print(f"=== 全量抓取（首次运行）===")
    print(f"时间范围: {start_dt.strftime('%Y-%m-%d')} ~ {end_dt.strftime('%Y-%m-%d')}")

    usd_rates = get_rates_for_range("美元", "USD", start_dt, end_dt)
    print(f"  美元: {len(usd_rates)} 条")
    jpy_rates = get_rates_for_range("日元", "JPY", start_dt, end_dt)
    print(f"  日元: {len(jpy_rates)} 条")
    hkd_rates = get_rates_for_range("港币", "HKD", start_dt, end_dt)
    print(f"  港币: {len(hkd_rates)} 条")

    daily = compute_pairs(usd_rates, jpy_rates, hkd_rates)
    _, monthly, yearly, date_strs = calc_stats(daily)
    alerts = calc_alerts(daily)

    result = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "start_date": date_strs[0] if date_strs else "",
            "end_date": date_strs[-1] if date_strs else "",
            "total_days": len(date_strs),
            "pairs": list(daily.keys()),
            "data_source": "中国人民银行官方中间价 (akshare)",
        },
        "daily": daily,
        "monthly": monthly,
        "yearly": yearly,
        "alerts": alerts,
    }

    save_and_generate(result)


def run_incremental():
    existing = load_existing()
    if not existing:
        print("未有历史数据，执行全量抓取...")
        run_full()
        return

    meta = existing.get("meta", {})
    end_date_str = meta.get("end_date", "")
    if not end_date_str:
        print("无法判断最新日期，执行全量抓取...")
        run_full()
        return

    last_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
    today_dt = datetime.today()
    if last_dt.date() >= today_dt.date():
        print(f"数据已是最新，重新计算预警并生成网页...")
        # 重新计算预警（即使数据没变）
        alerts = calc_alerts(existing["daily"])
        existing["alerts"] = alerts
        existing["meta"]["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_and_generate(existing)
        return

    fetch_start = last_dt + timedelta(days=1)
    print(f"=== 增量更新 ===")
    print(f"  上次最新: {end_date_str}")
    print(f"  抓取范围: {fetch_start.strftime('%Y-%m-%d')} ~ {today_dt.strftime('%Y-%m-%d')}")

    usd_rates = get_rates_for_range("美元", "USD", fetch_start, today_dt)
    jpy_rates = get_rates_for_range("日元", "JPY", fetch_start, today_dt)
    hkd_rates = get_rates_for_range("港币", "HKD", fetch_start, today_dt)

    if not usd_rates and not jpy_rates and not hkd_rates:
        print("  期间无新数据，重新计算预警并生成网页...")
        alerts = calc_alerts(existing["daily"])
        existing["alerts"] = alerts
        existing["meta"]["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_and_generate(existing)
        return

    new_usd = {ds: float(existing["daily"]["USD/CNY"][ds])
               for ds in existing["daily"]["USD/CNY"]}
    for ds, v in usd_rates.items():
        if ds not in new_usd:
            new_usd[ds] = v

    new_jpy = {ds: float(existing["daily"]["JPY/CNY"][ds]) * 100.0
               for ds in existing["daily"]["JPY/CNY"]}
    for ds, v in jpy_rates.items():
        if ds not in new_jpy:
            new_jpy[ds] = v

    new_hkd = {ds: float(existing["daily"]["HKD/CNY"][ds]) * 100.0
               for ds in existing["daily"]["HKD/CNY"]}
    for ds, v in hkd_rates.items():
        if ds not in new_hkd:
            new_hkd[ds] = v

    daily = compute_pairs(new_usd, new_jpy, new_hkd)
    _, monthly, yearly, date_strs = calc_stats(daily)
    alerts = calc_alerts(daily)

    result = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "start_date": date_strs[0],
            "end_date": date_strs[-1],
            "total_days": len(date_strs),
            "pairs": list(daily.keys()),
            "data_source": "中国人民银行官方中间价 (akshare)",
        },
        "daily": daily,
        "monthly": monthly,
        "yearly": yearly,
        "alerts": alerts,
    }

    save_and_generate(result)
    print(f"✅ 增量更新完成，最新日期: {date_strs[-1]}")


def generate_html(data_json, version_str, update_logs_json):
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>汇率追踪面板 — 央行中间价</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f0f2f5; color: #333; }
  .header { background: linear-gradient(135deg, #1a237e, #283593); color: white; padding: 20px 32px; }
  .header h1 { font-size: 22px; font-weight: 600; }
  .header p { font-size: 13px; opacity: 0.85; margin-top: 4px; }
  .container { max-width: 1200px; margin: 0 auto; padding: 24px; }

  /* 预警面板 */
  .alert-panel { margin-bottom: 20px; border-radius: 12px; padding: 16px 20px; display: none; }
  .alert-panel.show { display: block; }
  .alert-panel.red {
    background: linear-gradient(135deg, #d32f2f, #c62828); color: white;
    box-shadow: 0 4px 12px rgba(198,40,40,0.3);
  }
  .alert-panel.yellow {
    background: linear-gradient(135deg, #f9a825, #f57f17); color: #333;
    box-shadow: 0 4px 12px rgba(245,127,23,0.3);
  }
  .alert-panel.normal {
    background: linear-gradient(135deg, #43a047, #2e7d32); color: white; display: block;
    box-shadow: 0 2px 8px rgba(46,125,50,0.2);
  }
  .alert-panel h3 { font-size: 16px; margin-bottom: 8px; }
  .alert-panel .alert-list { list-style: none; padding: 0; }
  .alert-panel .alert-list li { font-size: 13px; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.15); }
  .alert-panel .alert-list li:last-child { border-bottom: none; }
  .alert-panel.yellow .alert-list li { border-bottom-color: rgba(0,0,0,0.08); }
  .alert-badge { display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 11px; font-weight: 600; margin-right: 6px; }
  .alert-badge.red { background: #fff; color: #c62828; }
  .alert-badge.yellow { background: #fff; color: #e65100; }

  .controls { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; align-items: center; }
  .controls label { font-size: 14px; font-weight: 500; }
  select, button {
    padding: 8px 16px; border-radius: 8px; border: 1px solid #d9d9d9;
    font-size: 14px; background: white; cursor: pointer; transition: all 0.2s;
  }
  select:focus, button:focus { outline: none; border-color: #4361ee; box-shadow: 0 0 0 2px rgba(67,97,238,0.2); }
  button { background: #4361ee; color: white; border: none; font-weight: 500; }
  button:hover { background: #3a56d4; }
  button.active { background: #1a237e; }
  .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-card {
    background: white; border-radius: 12px; padding: 16px 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }
  .stat-card .label { font-size: 12px; color: #888; margin-bottom: 4px; }
  .stat-card .value { font-size: 24px; font-weight: 700; color: #1a237e; }
  .stat-card .sub { font-size: 12px; color: #666; margin-top: 2px; }
  .chart-card {
    background: white; border-radius: 12px; padding: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 24px;
    position: relative; min-height: 200px;
  }
  .chart-card h3 { font-size: 15px; margin-bottom: 12px; color: #333; }
  .chart-card canvas { max-height: 400px; }
  .table-card {
    background: white; border-radius: 12px; padding: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); overflow-x: auto;
  }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { background: #f5f7fa; padding: 10px 12px; text-align: left; font-weight: 600; border-bottom: 2px solid #e8e8e8; }
  td { padding: 9px 12px; border-bottom: 1px solid #f0f0f0; }
  tr:hover td { background: #f9f9ff; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
  .badge-up { background: #ffebee; color: #c62828; }
  .badge-down { background: #e8f5e9; color: #2e7d32; }
  .tabs { display: flex; gap: 0; margin-bottom: 16px; }
  .tabs button { border-radius: 0; margin: 0; }
  .tabs button:first-child { border-radius: 8px 0 0 8px; }
  .tabs button:last-child { border-radius: 0 8px 8px 0; }
  .section-title { font-size: 16px; font-weight: 600; margin: 24px 0 12px; color: #333; }
  .last-update { font-size: 12px; color: #999; text-align: right; margin-top: 8px; }

  /* 密钥门禁 */
  .gate-overlay {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: linear-gradient(135deg, #1a237e, #283593);
    display: flex; align-items: center; justify-content: center;
    z-index: 9999; flex-direction: column;
  }
  .gate-box {
    background: white; border-radius: 16px; padding: 40px 36px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.25); text-align: center;
    max-width: 400px; width: 90%;
  }
  .gate-box h2 { font-size: 20px; color: #1a237e; margin-bottom: 6px; }
  .gate-box p { font-size: 13px; color: #888; margin-bottom: 20px; }
  .gate-box input {
    width: 100%; padding: 12px 16px; border-radius: 8px;
    border: 2px solid #d9d9d9; font-size: 16px; text-align: center;
    letter-spacing: 4px; outline: none; transition: border 0.2s;
  }
  .gate-box input:focus { border-color: #4361ee; }
  .gate-box button {
    width: 100%; margin-top: 16px; padding: 12px; border-radius: 8px;
    background: #4361ee; color: white; border: none; font-size: 16px;
    font-weight: 600; cursor: pointer; transition: background 0.2s;
  }
  .gate-box button:hover { background: #3a56d4; }
  .gate-error { color: #c62828; font-size: 13px; margin-top: 10px; min-height: 20px; }
  .gate-footer { color: rgba(255,255,255,0.6); font-size: 12px; margin-top: 20px; }

  /* 版本 & 更新日志 */
  .header { display: flex; align-items: center; justify-content: space-between; background: linear-gradient(135deg, #1a237e, #283593); color: white; padding: 20px 32px; }
  .header-left h1 { font-size: 22px; font-weight: 600; }
  .header-left p { font-size: 13px; opacity: 0.85; margin-top: 4px; }
  .header-right { text-align: right; }
  .version-badge {
    display: inline-block; background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.3);
    border-radius: 20px; padding: 6px 16px; font-size: 14px; font-weight: 600; letter-spacing: 1px;
  }
  .version-badge span { color: #ffd54f; }
  .update-btn {
    display: block; margin-top: 8px; background: none; border: 1px solid rgba(255,255,255,0.3);
    color: rgba(255,255,255,0.8); border-radius: 6px; padding: 4px 12px;
    font-size: 12px; cursor: pointer; width: 100%;
  }
  .update-btn:hover { background: rgba(255,255,255,0.1); color: white; }

  .log-panel {
    background: white; border-radius: 12px; padding: 0; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    margin-bottom: 20px; overflow: hidden; display: none;
  }
  .log-panel.show { display: block; }
  .log-header {
    background: #1a237e; color: white; padding: 12px 20px; font-size: 14px; font-weight: 600;
    display: flex; justify-content: space-between; align-items: center; cursor: pointer;
  }
  .log-header:hover { background: #283593; }
  .log-body { max-height: 320px; overflow-y: auto; }
  .log-item {
    display: flex; align-items: center; padding: 10px 20px; border-bottom: 1px solid #f0f0f0;
    font-size: 13px; gap: 16px;
  }
  .log-item:last-child { border-bottom: none; }
  .log-item:nth-child(odd) { background: #fafbfc; }
  .log-version { font-weight: 700; color: #1a237e; min-width: 60px; }
  .log-datetime { color: #555; min-width: 160px; font-family: monospace; }
  .log-count { color: #888; font-size: 12px; }
  .log-empty { padding: 20px; text-align: center; color: #999; font-size: 13px; }
</style>
<script>
// ===== 访问密钥配置 =====
// 修改此值可更换访问密钥，分享链接时需一并告知密钥
var ACCESS_KEY = "cl2026";
</script>
</head>
<body>

<!-- 密钥门禁 -->
<div class="gate-overlay" id="gateOverlay">
  <div class="gate-box">
    <h2>&#x1f512; 汇率追踪面板</h2>
    <p>请输入访问密钥</p>
    <input type="password" id="gateInput" placeholder="输入密钥" maxlength="20" onkeydown="if(event.key==='Enter')unlock()">
    <button onclick="unlock()">验证进入</button>
    <div class="gate-error" id="gateError"></div>
  </div>
  <div class="gate-footer">数据来源：中国人民银行 | 汇率追踪系统</div>
</div>

<!-- ====== 主内容（验证通过后显示）====== -->
<div id="mainContent" style="display:none">

<div class="header">
  <div class="header-left">
    <h1>&#x1f4b1; 汇率追踪面板</h1>
    <p>数据来源：中国人民银行官方中间价 | 预警规则：日±1%/周±3%/月±4% &#x1f7e1; | 日±2%/周±5%/月±8%/近极值 &#x1f534;</p>
  </div>
  <div class="header-right">
    <div class="version-badge">版本 <span id="versionDisplay">{VERSION_STR}</span></div>
    <button class="update-btn" onclick="toggleLog()">&#x1f4dc; 更新记录</button>
  </div>
</div>

<div class="container">
  <!-- 更新日志面板 -->
  <div class="log-panel" id="logPanel">
    <div class="log-header" onclick="toggleLog()">
      <span>&#x1f4dc; 更新记录</span>
      <span id="logToggleIcon">&#x25b2; 收起</span>
    </div>
    <div class="log-body" id="logBody"></div>
  </div>

  <!-- 全局预警面板 -->
  <div class="alert-panel" id="alertPanel"></div>

  <div class="controls">
    <label>货币对：</label>
    <select id="pairSelect">
      <option value="USD/CNY">美元 / 人民币 (USD/CNY)</option>
      <option value="JPY/CNY">日元 / 人民币 (JPY/CNY)</option>
      <option value="HKD/CNY">港币 / 人民币 (HKD/CNY)</option>
      <option value="HKD/JPY">港币 / 日元 (HKD/JPY)</option>
      <option value="JPY/HKD">日元 / 港币 (JPY/HKD)</option>
    </select>

    <label>视图：</label>
    <div class="tabs">
      <button id="tabDaily" class="active" onclick="switchView('daily')">每日汇率</button>
      <button id="tabMonthly" onclick="switchView('monthly')">月度均值</button>
      <button id="tabYearly" onclick="switchView('yearly')">年度均值</button>
    </div>

    <button onclick="downloadData()">&#x1f4e5; 下载全部数据</button>
  </div>

  <!-- 统计卡片 -->
  <div class="stats-grid" id="statsGrid"></div>

  <!-- 主图表 -->
  <div class="chart-card">
    <h3 id="chartTitle">每日中间汇率</h3>
    <canvas id="mainChart"></canvas>
  </div>

  <!-- 月度高低区间 -->
  <div class="section-title" id="rangeTitle">月度汇率区间</div>
  <div class="chart-card">
    <canvas id="rangeChart"></canvas>
  </div>

  <!-- 数据表格 -->
  <div class="section-title">历史数据明细（最近200条）</div>
  <div class="table-card">
    <table id="dataTable">
      <thead><tr id="tableHead"></tr></thead>
      <tbody id="tableBody"></tbody>
    </table>
  </div>

  <div class="last-update" id="lastUpdate"></div>
</div>

<script>
var DATA = """ + data_json + """;
var UPDATE_LOGS = """ + update_logs_json + """;

var currentPair = "USD/CNY";
var currentView = "daily";
var mainChart = null;
var rangeChart = null;

var PAIR_LABELS = {
  "USD/CNY": "美元兑人民币",
  "JPY/CNY": "日元兑人民币",
  "HKD/CNY": "港币兑人民币",
  "HKD/JPY": "港币兑日元",
  "JPY/HKD": "日元兑港币"
};

(function init() {
  if (!DATA || !DATA.meta) {
    document.querySelector(".container").innerHTML =
      '<div style="color:#c62828;padding:40px;text-align:center;font-size:14px">数据加载失败，请运行 fetch_rates.py 生成数据。</div>';
    return;
  }
  renderUpdateLogs();
})();

function renderUpdateLogs() {
  var body = document.getElementById("logBody");
  if (!UPDATE_LOGS || UPDATE_LOGS.length === 0) {
    body.innerHTML = '<div class="log-empty">暂无更新记录</div>';
    return;
  }
  var html = "";
  for (var i = UPDATE_LOGS.length - 1; i >= 0; i--) {
    var e = UPDATE_LOGS[i];
    html += '<div class="log-item">' +
      '<span class="log-version">' + (e.version || "") + '</span>' +
      '<span class="log-datetime">' + (e.datetime || "") + '</span>' +
      '<span class="log-count">当日第 ' + (e.count_today || "?") + ' 次更新</span>' +
    '</div>';
  }
  body.innerHTML = html;
}

function toggleLog() {
  var panel = document.getElementById("logPanel");
  var icon = document.getElementById("logToggleIcon");
  if (panel.classList.contains("show")) {
    panel.classList.remove("show");
    icon.innerHTML = '&#x25bc; 展开';
  } else {
    panel.classList.add("show");
    icon.innerHTML = '&#x25b2; 收起';
  }
}

// ===== 预警面板 =====
function renderAlertPanel() {
  var panel = document.getElementById("alertPanel");
  var alerts = DATA.alerts || {};

  // 收集所有预警
  var redItems = [], yellowItems = [];
  for (var pair in alerts) {
    var a = alerts[pair];
    if (!a || a.level === "none") continue;
    var label = PAIR_LABELS[pair] || pair;
    var trs = a.triggers || [];
    for (var t = 0; t < trs.length; t++) {
      var item = { pair: pair, label: label, detail: trs[t].detail };
      if (trs[t].level === "red") redItems.push(item);
      else yellowItems.push(item);
    }
  }

  panel.className = "alert-panel";
  if (redItems.length > 0) {
    panel.className += " red show";
    var html = "<h3>&#x1f534; 红色预警</h3><ul class='alert-list'>";
    for (var i = 0; i < redItems.length; i++) {
      html += "<li><span class='alert-badge red'>RED</span>[" + redItems[i].label + "] " + redItems[i].detail + "</li>";
    }
    if (yellowItems.length > 0) {
      for (var j = 0; j < yellowItems.length; j++) {
        html += "<li><span class='alert-badge yellow'>YEL</span>[" + yellowItems[j].label + "] " + yellowItems[j].detail + "</li>";
      }
    }
    html += "</ul>";
    panel.innerHTML = html;
  } else if (yellowItems.length > 0) {
    panel.className += " yellow show";
    var html2 = "<h3>&#x1f7e1; 黄色预警</h3><ul class='alert-list'>";
    for (var k = 0; k < yellowItems.length; k++) {
      html2 += "<li><span class='alert-badge yellow'>YEL</span>[" + yellowItems[k].label + "] " + yellowItems[k].detail + "</li>";
    }
    html2 += "</ul>";
    panel.innerHTML = html2;
  } else {
    panel.className += " normal";
    panel.innerHTML = "<h3>&#x2705; 当前无预警，所有货币对波动正常</h3>";
  }
}

function switchView(view) {
  currentView = view;
  document.getElementById("tabDaily").classList.toggle("active", view === "daily");
  document.getElementById("tabMonthly").classList.toggle("active", view === "monthly");
  document.getElementById("tabYearly").classList.toggle("active", view === "yearly");
  render();
}

document.getElementById("pairSelect").addEventListener("change", function () {
  currentPair = this.value;
  render();
});

function render() {
  renderStats();
  renderMainChart();
  renderRangeChart();
  renderTable();
}

function renderStats() {
  var daily = DATA.daily[currentPair] || {};
  var monthly = DATA.monthly[currentPair] || {};
  var yearly = DATA.yearly[currentPair] || {};
  var dates = Object.keys(daily).sort();
  var grid = document.getElementById("statsGrid");
  grid.innerHTML = "";

  if (dates.length > 0) {
    var last = dates[dates.length - 1];
    var val = daily[last];

    // 最新汇率 + 变化标记
    var lastHtml = '<div class="label">最新汇率</div>';
    var prevDate = dates.length > 1 ? dates[dates.length - 2] : null;
    if (prevDate && daily[prevDate]) {
      var chg = ((val - daily[prevDate]) / daily[prevDate] * 100);
      var arrow = chg >= 0 ? '<span style="color:#f44336;font-size:16px">&#x25b2;</span>' :
                             '<span style="color:#4caf50;font-size:16px">&#x25bc;</span>';
      lastHtml += '<div class="value">' + val.toFixed(4) + '</div>';
      lastHtml += '<div class="sub">' + last + ' | ' + arrow + ' ' + chg.toFixed(2) + '%</div>';
    } else {
      lastHtml += '<div class="value">' + val.toFixed(4) + '</div>';
      lastHtml += '<div class="sub">' + last + '</div>';
    }
    var card = document.createElement("div");
    card.className = "stat-card";
    card.innerHTML = lastHtml;
    grid.appendChild(card);
  }

  var now = new Date();
  var mk = now.getFullYear() + "-" + (now.getMonth()+1).toString().padStart(2,'0');
  if (monthly[mk]) {
    var m = monthly[mk];
    var mMinPct = ((m.min - m.avg) / m.avg * 100);
    var mMaxPct = ((m.max - m.avg) / m.avg * 100);
    grid.appendChild(makeCard("当月均值", m.avg.toFixed(4),
      "最低 " + m.min.toFixed(4) + " (" + (mMinPct >= 0 ? "+" : "") + mMinPct.toFixed(2) + "%) / 最高 " + m.max.toFixed(4) + " (" + (mMaxPct >= 0 ? "+" : "") + mMaxPct.toFixed(2) + "%)"));
  }

  var yk = String(now.getFullYear());
  if (yearly[yk]) {
    var y = yearly[yk];
    var yMinPct = ((y.min - y.avg) / y.avg * 100);
    var yMaxPct = ((y.max - y.avg) / y.avg * 100);
    grid.appendChild(makeCard("当年均值", y.avg.toFixed(4),
      "最低 " + y.min.toFixed(4) + " (" + (yMinPct >= 0 ? "+" : "") + yMinPct.toFixed(2) + "%) / 最高 " + y.max.toFixed(4) + " (" + (yMaxPct >= 0 ? "+" : "") + yMaxPct.toFixed(2) + "%)"));
  }

  // 周/月变化
  var a = (DATA.alerts || {})[currentPair] || {};
  if (a.weekly_change_pct != null) {
    var wColor = Math.abs(a.weekly_change_pct) >= 5 ? "#c62828" :
                 Math.abs(a.weekly_change_pct) >= 3 ? "#e65100" : "#333";
    grid.appendChild(makeCard("近7天变化", (a.weekly_change_pct >= 0 ? "+" : "") + a.weekly_change_pct + "%", ""));
  }
  if (a.monthly_change_pct != null) {
    var mColor = Math.abs(a.monthly_change_pct) >= 8 ? "#c62828" :
                 Math.abs(a.monthly_change_pct) >= 4 ? "#e65100" : "#333";
    grid.appendChild(makeCard("近30天变化", (a.monthly_change_pct >= 0 ? "+" : "") + a.monthly_change_pct + "%", ""));
  }

  // 5年极值
  if (dates.length > 0) {
    var minVal = daily[dates[0]], maxVal = daily[dates[0]];
    var minDate = dates[0], maxDate = dates[0];
    for (var i = 1; i < dates.length; i++) {
      var ds = dates[i], v = daily[ds];
      if (v < minVal) { minVal = v; minDate = ds; }
      if (v > maxVal) { maxVal = v; maxDate = ds; }
    }
    var nowVal = daily[dates[dates.length - 1]];
    var distMin = ((nowVal - minVal) / minVal * 100).toFixed(2);
    var distMax = ((maxVal - nowVal) / maxVal * 100).toFixed(2);
    grid.appendChild(makeCard("5年最低", minVal.toFixed(4), minDate + " (距当前 " + distMin + "%)"));
    grid.appendChild(makeCard("5年最高", maxVal.toFixed(4), maxDate + " (距当前 " + distMax + "%)"));
  }
}

function makeCard(label, value, sub) {
  var div = document.createElement("div");
  div.className = "stat-card";
  div.innerHTML = '<div class="label">' + label +
    '</div><div class="value">' + value +
    '</div>' + (sub ? '<div class="sub">' + sub + '</div>' : '');
  return div;
}

function renderMainChart() {
  var ctx = document.getElementById("mainChart").getContext("2d");
  var labels = [], data = [], title = "";

  if (currentView === "daily") {
    var daily = DATA.daily[currentPair] || {};
    var dates = Object.keys(daily).sort();
    labels = dates;
    data = dates.map(function(d) { return daily[d]; });
    title = currentPair + " — 每日汇率";
  } else if (currentView === "monthly") {
    var monthly = DATA.monthly[currentPair] || {};
    var keys = Object.keys(monthly).sort();
    labels = keys;
    data = keys.map(function(k) { return monthly[k].avg; });
    title = currentPair + " — 月度平均汇率";
  } else {
    var yearly = DATA.yearly[currentPair] || {};
    var keys = Object.keys(yearly).sort();
    labels = keys;
    data = keys.map(function(k) { return yearly[k].avg; });
    title = currentPair + " — 年度平均汇率";
  }

  document.getElementById("chartTitle").textContent = title;

  if (mainChart) mainChart.destroy();

  mainChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [{
        label: currentPair,
        data: data,
        borderColor: "#4361ee",
        backgroundColor: "rgba(67,97,238,0.08)",
        fill: true,
        tension: 0.3,
        pointRadius: currentView === "daily" ? 0 : 3,
        pointHoverRadius: 5,
        borderWidth: 2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: "index",
          intersect: false,
          callbacks: {
            label: function(ctx) {
              return currentPair + ": " + ctx.parsed.y.toFixed(4);
            }
          }
        }
      },
      scales: {
        x: {
          ticks: {
            maxTicksLimit: currentView === "daily" ? 12 : 20,
            font: { size: 11 }
          },
          grid: { display: false }
        },
        y: {
          ticks: { font: { size: 11 } },
          grid: { color: "#f0f0f0" }
        }
      }
    }
  });
}

function renderRangeChart() {
  var ctx = document.getElementById("rangeChart").getContext("2d");
  var monthly = DATA.monthly[currentPair] || {};
  var keys = Object.keys(monthly).sort();
  var now = new Date();
  var cut = (now.getFullYear() - 2) + "-01";
  var filtered = keys.filter(function(k) { return k >= cut; });

  document.getElementById("rangeTitle").textContent = "月度汇率区间（近2年）";

  if (rangeChart) rangeChart.destroy();

  rangeChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: filtered,
      datasets: [
        {
          label: "最高",
          data: filtered.map(function(k) { return monthly[k].max; }),
          backgroundColor: "rgba(244,67,54,0.15)",
          borderColor: "#f44336",
          borderWidth: 1,
        },
        {
          label: "平均",
          data: filtered.map(function(k) { return monthly[k].avg; }),
          backgroundColor: "rgba(67,97,238,0.25)",
          borderColor: "#4361ee",
          borderWidth: 2,
          type: "line",
          fill: false,
          tension: 0.3,
        },
        {
          label: "最低",
          data: filtered.map(function(k) { return monthly[k].min; }),
          backgroundColor: "rgba(76,175,80,0.15)",
          borderColor: "#4caf50",
          borderWidth: 1,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "top", labels: { font: { size: 12 } } }
      },
      scales: {
        x: { ticks: { font: { size: 10 }, maxTicksLimit: 24 } },
        y: { ticks: { font: { size: 11 } }, grid: { color: "#f0f0f0" } }
      }
    }
  });
}

function renderTable() {
  var daily = DATA.daily[currentPair] || {};
  var monthly = DATA.monthly[currentPair] || {};
  var yearly = DATA.yearly[currentPair] || {};
  var dates = Object.keys(daily).sort().reverse();

  var thead = document.getElementById("tableHead");
  thead.innerHTML = "<th>日期</th><th>汇率</th><th>月度均值</th><th>月度区间(距均值%)</th><th>年度均值</th><th>年度区间(距均值%)</th>";

  var tbody = document.getElementById("tableBody");
  tbody.innerHTML = "";
  var show = dates.slice(0, 200);

  for (var i = 0; i < show.length; i++) {
    var ds = show[i];
    var dt = new Date(ds);
    var mk = dt.getFullYear() + "-" + (dt.getMonth()+1).toString().padStart(2,'0');
    var yk = String(dt.getFullYear());
    var m = monthly[mk];
    var y = yearly[yk];

    var tr = document.createElement("tr");
    var mRange = m
      ? '<span class="badge badge-down">' + m.min.toFixed(4) + '</span>(' + ((m.min - m.avg) / m.avg * 100).toFixed(1) + '%) ~ <span class="badge badge-up">' + m.max.toFixed(4) + '</span>(+' + ((m.max - m.avg) / m.avg * 100).toFixed(1) + '%)'
      : '-';
    var yRange = y
      ? '<span class="badge badge-down">' + y.min.toFixed(4) + '</span>(' + ((y.min - y.avg) / y.avg * 100).toFixed(1) + '%) ~ <span class="badge badge-up">' + y.max.toFixed(4) + '</span>(+' + ((y.max - y.avg) / y.avg * 100).toFixed(1) + '%)'
      : '-';
    tr.innerHTML =
      '<td>' + ds + '</td>' +
      '<td><strong>' + daily[ds].toFixed(4) + '</strong></td>' +
      '<td>' + (m ? m.avg.toFixed(4) : '-') + '</td>' +
      '<td>' + mRange + '</td>' +
      '<td>' + (y ? y.avg.toFixed(4) : '-') + '</td>' +
      '<td>' + yRange + '</td>';
    tbody.appendChild(tr);
  }
}

function downloadData() {
  var blob = new Blob([JSON.stringify(DATA, null, 2)], {type: "application/json"});
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "rates_all_pairs_" + new Date().toISOString().slice(0,10) + ".json";
  a.click();
}

// ===== 密钥门禁 =====
function unlock() {
  var input = document.getElementById("gateInput").value.trim();
  if (input === ACCESS_KEY) {
    sessionStorage.setItem("fx_gate_key", input);
    document.getElementById("gateOverlay").style.display = "none";
    document.getElementById("mainContent").style.display = "block";
    // 初始化页面
    if (DATA && DATA.meta) {
      document.getElementById("lastUpdate").textContent =
        "数据生成时间: " + (DATA.meta.generated_at || "") +
        " | 数据来源: " + (DATA.meta.data_source || "");
      renderAlertPanel();
      render();
    }
  } else {
    document.getElementById("gateError").textContent = "密钥错误，请重试";
    document.getElementById("gateInput").value = "";
    document.getElementById("gateInput").focus();
  }
}

// 检查是否已验证过（同会话内免重新输入）
(function checkGate() {
  if (sessionStorage.getItem("fx_gate_key") === ACCESS_KEY) {
    document.getElementById("gateOverlay").style.display = "none";
    document.getElementById("mainContent").style.display = "block";
  }
})();
</script>

</div><!-- mainContent -->

</body>
</html>"""


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "full":
        run_full()
    else:
        run_incremental()
