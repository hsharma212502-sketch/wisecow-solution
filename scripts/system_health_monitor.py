#!/usr/bin/env python3
"""
System Health Monitoring Script  (PS2 - Objective 1)

Monitors CPU, memory, disk usage and the top resource-consuming processes on a
Linux system. When any metric crosses its configured threshold the script emits
an ALERT to the console and appends it to a log file.

Usage:
    python3 system_health_monitor.py                 # one-shot check
    python3 system_health_monitor.py --watch 10      # repeat every 10 seconds
    python3 system_health_monitor.py --cpu 70 --mem 75 --disk 85

Thresholds default to: CPU 80%, Memory 80%, Disk 80%.

Implemented with only the Python standard library so it runs anywhere without
extra packages (reads /proc and uses shutil/os).
"""

import argparse
import logging
import os
import shutil
import time
from datetime import datetime

LOG_FILE = os.environ.get("HEALTH_LOG", "system_health.log")


def setup_logging():
    logger = logging.getLogger("health")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s")
    fh = logging.FileHandler(LOG_FILE)
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def read_cpu_times():
    """Return (idle, total) jiffies from /proc/stat aggregate cpu line."""
    with open("/proc/stat") as f:
        for line in f:
            if line.startswith("cpu "):
                parts = [int(x) for x in line.split()[1:]]
                idle = parts[3] + (parts[4] if len(parts) > 4 else 0)  # idle + iowait
                total = sum(parts)
                return idle, total
    return 0, 0


def cpu_usage_percent(interval=0.5):
    """Sample CPU utilisation over a short interval."""
    idle1, total1 = read_cpu_times()
    time.sleep(interval)
    idle2, total2 = read_cpu_times()
    didle = idle2 - idle1
    dtotal = total2 - total1
    if dtotal <= 0:
        return 0.0
    return round((1.0 - didle / dtotal) * 100.0, 1)


def memory_usage_percent():
    """Parse /proc/meminfo for used-memory percentage."""
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, val = line.split(":", 1)
            info[key.strip()] = int(val.strip().split()[0])  # kB
    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", info.get("MemFree", 0))
    if total == 0:
        return 0.0, 0, 0
    used_pct = round((total - available) / total * 100.0, 1)
    return used_pct, total // 1024, (total - available) // 1024  # pct, total MB, used MB


def disk_usage_percent(path="/"):
    usage = shutil.disk_usage(path)
    used_pct = round(usage.used / usage.total * 100.0, 1)
    return used_pct, usage.total // (1024**3), usage.used // (1024**3)  # pct, total GB, used GB


def top_processes(n=5):
    """Return the top-n processes by RSS memory, reading /proc directly."""
    procs = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                name = f.read().strip()
            with open(f"/proc/{pid}/statm") as f:
                rss_pages = int(f.read().split()[1])
            rss_mb = rss_pages * (os.sysconf("SC_PAGE_SIZE")) // (1024 * 1024)
            procs.append((rss_mb, pid, name))
        except (FileNotFoundError, ProcessLookupError, PermissionError, IndexError):
            continue
    procs.sort(reverse=True)
    return procs[:n]


def run_check(thresholds, logger):
    alerts = 0

    cpu = cpu_usage_percent()
    line = f"CPU usage: {cpu}%  (threshold {thresholds['cpu']}%)"
    if cpu > thresholds["cpu"]:
        logger.warning("ALERT - HIGH CPU - " + line)
        alerts += 1
    else:
        logger.info(line)

    mem_pct, mem_total, mem_used = memory_usage_percent()
    line = f"Memory usage: {mem_pct}%  ({mem_used}/{mem_total} MB, threshold {thresholds['mem']}%)"
    if mem_pct > thresholds["mem"]:
        logger.warning("ALERT - HIGH MEMORY - " + line)
        alerts += 1
    else:
        logger.info(line)

    disk_pct, disk_total, disk_used = disk_usage_percent("/")
    line = f"Disk usage (/): {disk_pct}%  ({disk_used}/{disk_total} GB, threshold {thresholds['disk']}%)"
    if disk_pct > thresholds["disk"]:
        logger.warning("ALERT - HIGH DISK - " + line)
        alerts += 1
    else:
        logger.info(line)

    tops = top_processes()
    top_str = ", ".join(f"{name}(pid {pid}, {rss}MB)" for rss, pid, name in tops)
    logger.info(f"Top processes by memory: {top_str}")

    if alerts:
        logger.warning(f"Health check completed with {alerts} alert(s).")
    else:
        logger.info("Health check completed: all metrics within thresholds.")
    return alerts


def main():
    p = argparse.ArgumentParser(description="Linux system health monitor")
    p.add_argument("--cpu", type=float, default=80.0, help="CPU%% alert threshold")
    p.add_argument("--mem", type=float, default=80.0, help="Memory%% alert threshold")
    p.add_argument("--disk", type=float, default=80.0, help="Disk%% alert threshold")
    p.add_argument("--watch", type=int, metavar="SECONDS",
                   help="Repeat the check every N seconds (Ctrl-C to stop)")
    args = p.parse_args()

    thresholds = {"cpu": args.cpu, "mem": args.mem, "disk": args.disk}
    logger = setup_logging()
    logger.info("=== System Health Monitor started at %s ===",
                datetime.now().isoformat(timespec="seconds"))

    try:
        if args.watch:
            while True:
                run_check(thresholds, logger)
                time.sleep(args.watch)
        else:
            run_check(thresholds, logger)
    except KeyboardInterrupt:
        logger.info("Stopped by user.")


if __name__ == "__main__":
    main()
