#!/usr/bin/env python3
"""Supermicro X10 (aws-gpu01 / aws-gpu02) 用 温度連動ファン制御デーモン。

背景:
    X10 系 BMC は Fan mode が Full(0x01) のときだけ手動 duty 指定を保持する。
    Optimal/Standard では BMC が自分の目標値へ数十秒〜数分で戻してしまう。
    そのため「Full mode に固定し、温度に応じた duty をソフトウェア側で与える」構成にする。
    Full mode 中は BMC の自動制御が止まるので、本デーモンが唯一の冷却制御になる。
    → 停止・異常時は必ず Optimal(0x02) に戻して BMC へ制御を返す（fail-safe）。

対象機の実測（2026-08-17）:
    - cooling zone は 0..3 の 4 つ（zone4 以降は無効）。全 zone に同じ duty を与える。
    - duty 8%→2100rpm / 16%→2900rpm / 24%→3800rpm / 32%→4600rpm / 100%→11900rpm
    - Optimal 時の BMC 既定は 50% 前後 = 6300-6800rpm（アイドルでも下がらない）
    - BMC が GPU1-GPU10 Temp を持つので nvidia-smi は不要

使い方:
    # in-band（サーバ上、root。systemd から使う本番形態）
    smc-fanctl.py --transport open

    # out-of-band（WS から検証用）
    smc-fanctl.py --transport lan --host 10.11.12.1 --user claude --password xxx

    # 1 回だけ評価して表示（設定は書かない）
    smc-fanctl.py --transport open --oneshot --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import signal
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# IPMI raw コマンド（Supermicro X10 系）
#   fan mode 取得 : 0x30 0x45 0x00        → 00=Standard 01=Full 02=Optimal 04=HeavyIO
#   fan mode 設定 : 0x30 0x45 0x01 <mode>
#   duty 取得     : 0x30 0x70 0x66 0x00 <zone>
#   duty 設定     : 0x30 0x70 0x66 0x01 <zone> <duty(0-100)>
# ---------------------------------------------------------------------------
MODE_STANDARD, MODE_FULL, MODE_OPTIMAL, MODE_HEAVY_IO = 0x00, 0x01, 0x02, 0x04
ZONES = (0, 1, 2, 3)

# 温度 → duty(%) の多段テーブル。「この温度以下ならこの duty」を昇順で並べる。
# 最終エントリを超えたら 100%。センサ種別ごとに引き、最大値を採用する。
# 各グループの平常値（duty 16% / 2900rpm 時の実測、2026-08-17）:
#   cpu 42-60℃ / gpu 48-58℃ / sys 39-45℃ / pch 50-52℃
# → 平常域はすべて最下段 16% に収まり、そこから上がったぶんだけ回転を上げる形にする。
CURVES: dict[str, list[tuple[int, int]]] = {
    # max(CPU1 Temp, CPU2 Temp)。Xeon E5v4 の Tcase は 80-85℃
    "cpu": [(62, 16), (68, 28), (73, 44), (78, 64), (83, 85)],
    # max(GPU1..GPU10 Temp)。P100 は passive 冷却でシャーシ風量に完全依存、
    # thermal slowdown が 82-85℃ なので 70℃ 台から積極的に上げる
    "gpu": [(60, 16), (65, 28), (70, 44), (75, 64), (80, 85)],
    # System / Peripheral（吸気・基板周り）
    "sys": [(50, 16), (55, 28), (60, 44), (65, 64), (70, 85)],
    # PCH は独立ヒートシンクで風量の影響が小さく、6500rpm でも 50℃ 前後だった
    "pch": [(65, 16), (72, 28), (78, 44), (84, 64), (88, 85)],
}
SENSOR_GROUPS: dict[str, tuple[str, ...]] = {
    "cpu": ("CPU1 Temp", "CPU2 Temp"),
    "sys": ("System Temp", "Peripheral Temp"),
    "pch": ("PCH Temp",),
}
GPU_SENSOR_RE = re.compile(r"^GPU\d+ Temp$")

# 下限 16%（=2900rpm）は 2026-08-17 の実測で決めた値。8%（2100rpm）まで下げると
# アイドルでも CPU が 61℃ まで上がり続けたため採用しない。
DUTY_MIN, DUTY_MAX = 16, 100
# これを超えたら duty を 100% にしてもなお危険 → BMC(Optimal) に制御を返す
CRITICAL = {"cpu": 85, "gpu": 85, "sys": 75, "pch": 92}
HYSTERESIS_C = 3.0  # duty を下げるのは、その段の閾値を 3℃ 下回ってから
POLL_SEC = 10
MODE_CHECK_SEC = 60
MODE_SETTLE_SEC = 5  # Full mode 切替後、BMC の内部処理が落ち着くまでの待ち
IPMI_FAIL_LIMIT = 5

log = logging.getLogger("smc-fanctl")


class IpmiError(RuntimeError):
    pass


class Ipmi:
    """ipmitool のラッパ（in-band=open / out-of-band=lanplus）。"""

    def __init__(self, transport: str, host: str | None, user: str | None,
                 password: str | None, timeout: int = 20):
        if transport == "open":
            self.base = ["ipmitool", "-I", "open"]
        else:
            if not (host and user and password is not None):
                raise SystemExit("--transport lan には --host/--user/--password が必要です")
            self.base = ["ipmitool", "-I", "lanplus", "-H", host, "-U", user, "-P", password]
        self.timeout = timeout

    def run(self, *args: str) -> str:
        try:
            p = subprocess.run(self.base + list(args), capture_output=True,
                               text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired as e:
            raise IpmiError(f"timeout: {' '.join(args)}") from e
        if p.returncode != 0:
            raise IpmiError(f"rc={p.returncode}: {' '.join(args)}: {p.stderr.strip()}")
        return p.stdout

    # --- センサ ---------------------------------------------------------
    def sensors(self) -> dict[str, float]:
        """SDR 全体を 1 回で読み、"名前 → 数値" を返す（No Reading は落とす）。"""
        # `ipmitool sdr` の 1 行は "CPU1 Temp | 41 degrees C | ok" 形式（値は 2 列目）
        out, result = self.run("sdr"), {}
        for line in out.splitlines():
            parts = line.split("|")
            if len(parts) < 2:
                continue
            name, raw = parts[0].strip(), parts[1].strip()
            m = re.match(r"^(-?\d+(?:\.\d+)?)", raw)
            if m:
                result[name] = float(m.group(1))
        if not result:
            raise IpmiError("SDR から値が取れませんでした")
        return result

    # --- fan mode / duty ------------------------------------------------
    def get_mode(self) -> int:
        return int(self.run("raw", "0x30", "0x45", "0x00").strip(), 16)

    def set_mode(self, mode: int) -> None:
        self.run("raw", "0x30", "0x45", "0x01", f"0x{mode:02x}")

    def get_duty(self, zone: int) -> int:
        return int(self.run("raw", "0x30", "0x70", "0x66", "0x00", f"0x{zone:02x}").strip(), 16)

    def set_duty(self, zone: int, duty: int) -> None:
        self.run("raw", "0x30", "0x70", "0x66", "0x01", f"0x{zone:02x}", f"0x{duty:02x}")


def group_temps(sensors: dict[str, float]) -> dict[str, float | None]:
    """センサ辞書を cpu / gpu / sys の 3 グループの最大値に畳む。"""
    temps: dict[str, float | None] = {}
    for group, names in SENSOR_GROUPS.items():
        vals = [sensors[n] for n in names if n in sensors]
        temps[group] = max(vals) if vals else None
    gpu = [v for n, v in sensors.items() if GPU_SENSOR_RE.match(n)]
    temps["gpu"] = max(gpu) if gpu else None
    return temps


def duty_for(group: str, temp: float, current_duty: int) -> int:
    """テーブル＋ヒステリシスで duty を決める。上げは即座、下げは 3℃ の余裕を見る。"""
    curve = CURVES[group]
    duty = DUTY_MAX
    for threshold, d in curve:
        if temp <= threshold:
            duty = d
            break
    if duty < current_duty:
        # current_duty に上がった根拠は「その一段下のエントリの閾値を超えたこと」。
        # 下げるのはその閾値を HYSTERESIS_C だけ下回ってから（バタつき防止）。
        boundary = None
        for threshold, d in curve:
            if d < current_duty:
                boundary = threshold
            else:
                break
        if boundary is not None and temp > boundary - HYSTERESIS_C:
            return current_duty
    return duty


def decide(temps: dict[str, float | None], current_duty: int) -> tuple[int, str]:
    """各グループのテーブル結果の最大値を採用する。"""
    duty, why = DUTY_MIN, "min"
    for group, temp in temps.items():
        if temp is None:
            continue
        d = duty_for(group, temp, current_duty)
        if d > duty:
            duty, why = d, f"{group}={temp:.0f}C"
    return max(DUTY_MIN, min(DUTY_MAX, duty)), why


def critical_groups(temps: dict[str, float | None]) -> list[str]:
    return [g for g, t in temps.items() if t is not None and t >= CRITICAL[g]]


class FanController:
    def __init__(self, ipmi: Ipmi, dry_run: bool = False, min_duty: int = DUTY_MIN):
        self.ipmi = ipmi
        self.dry_run = dry_run
        self.min_duty = min_duty
        self.duty = 100          # 起動直後は不明なので安全側（=100%）から始める
        self.fails = 0
        self.last_mode_check = 0.0
        self.applied_at = 0.0
        self.stopping = False

    # --- fail-safe ------------------------------------------------------
    def hand_back_to_bmc(self, reason: str) -> None:
        """Optimal に戻して BMC の自動制御へ委譲する。"""
        log.warning("BMC(Optimal) に制御を返します: %s", reason)
        if self.dry_run:
            return
        for attempt in range(3):
            try:
                self.ipmi.set_mode(MODE_OPTIMAL)
                log.warning("fan mode を Optimal に戻しました")
                return
            except IpmiError as e:
                log.error("Optimal 復帰に失敗 (%d/3): %s", attempt + 1, e)
                time.sleep(2)

    def ensure_full_mode(self) -> bool:
        """Full mode を保証する。設定を変更したら True（duty の再適用が必要）。

        Full へ切り替えると BMC は全 zone の duty を 100% にリセットするため、
        呼び出し側は True のときに必ず duty を書き直すこと。
        """
        now = time.monotonic()
        if now - self.last_mode_check < MODE_CHECK_SEC:
            return False
        self.last_mode_check = now
        mode = self.ipmi.get_mode()
        if mode == MODE_FULL:
            return False
        log.info("fan mode が 0x%02x だったので Full(0x01) に設定します", mode)
        if not self.dry_run:
            self.ipmi.set_mode(MODE_FULL)
            # BMC は Full への切替処理を非同期で行い、その中で全 zone を 100% に
            # 書き戻す。直後に duty を書くと上書きされるため落ち着くまで待つ
            # （2026-08-17 実測: 待たずに書くと zone0 だけ 100% のまま残った）。
            time.sleep(MODE_SETTLE_SEC)
        return True

    def apply(self, duty: int, force: bool = False) -> None:
        if duty == self.duty and not force:
            return
        log.info("duty %d%% → %d%%", self.duty, duty)
        if not self.dry_run:
            for zone in ZONES:
                self.ipmi.set_duty(zone, duty)
        self.duty = duty
        self.applied_at = time.monotonic()

    def verify_duty(self) -> None:
        """BMC が duty を書き戻していないか確認し、ずれていた zone を再設定する。

        Full mode でも BMC 側の事情（mode 再適用、BMC リセット等）で duty が
        100% に戻ることがあるため、毎周期照合して自己修復する。
        """
        if self.dry_run or time.monotonic() - self.applied_at < MODE_SETTLE_SEC:
            return
        for zone in ZONES:
            actual = self.ipmi.get_duty(zone)
            if actual != self.duty:
                log.warning("zone%d の duty が %d%% にずれていたので %d%% を再設定します",
                            zone, actual, self.duty)
                self.ipmi.set_duty(zone, self.duty)

    # --- main loop ------------------------------------------------------
    def tick(self) -> None:
        temps = group_temps(self.ipmi.sensors())
        crit = critical_groups(temps)
        if crit:
            self.apply(DUTY_MAX)
            self.hand_back_to_bmc(f"critical 温度: {crit} / {temps}")
            raise SystemExit(3)
        mode_changed = self.ensure_full_mode()
        duty, why = decide(temps, self.duty)
        duty = max(duty, self.min_duty)
        if duty != self.duty:
            log.info("温度 %s → duty %d%% (決定要因 %s)",
                     {k: v for k, v in temps.items() if v is not None}, duty, why)
        self.apply(duty, force=mode_changed)
        self.verify_duty()

    def loop(self, interval: int) -> None:
        while not self.stopping:
            try:
                self.tick()
                self.fails = 0
            except IpmiError as e:
                self.fails += 1
                log.error("IPMI エラー (%d/%d): %s", self.fails, IPMI_FAIL_LIMIT, e)
                if self.fails >= IPMI_FAIL_LIMIT:
                    self.hand_back_to_bmc("IPMI 連続失敗")
                    raise SystemExit(4)
            time.sleep(interval)


def main() -> int:
    ap = argparse.ArgumentParser(description="Supermicro X10 温度連動ファン制御")
    ap.add_argument("--transport", choices=("open", "lan"), default="open",
                    help="open=in-band(/dev/ipmi0), lan=lanplus（検証用）")
    ap.add_argument("--host"), ap.add_argument("--user")
    ap.add_argument("--password", default=os.environ.get("IPMI_PASSWORD"))
    ap.add_argument("--interval", type=int, default=POLL_SEC)
    ap.add_argument("--min-duty", type=int, default=DUTY_MIN,
                    help=f"下限 duty%%（既定 {DUTY_MIN}）")
    ap.add_argument("--oneshot", action="store_true", help="1 周だけ実行して終了")
    ap.add_argument("--dry-run", action="store_true", help="判定のみ。IPMI に書かない")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s",
                        stream=sys.stdout)

    ipmi = Ipmi(args.transport, args.host, args.user, args.password)
    ctl = FanController(ipmi, dry_run=args.dry_run, min_duty=args.min_duty)

    def on_signal(signum, _frame):
        log.info("シグナル %s を受信、停止します", signal.Signals(signum).name)
        ctl.stopping = True
        ctl.hand_back_to_bmc("サービス停止")
        sys.exit(0)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    try:
        if args.oneshot:
            ctl.tick()
        else:
            log.info("開始: transport=%s interval=%ds min_duty=%d%% dry_run=%s",
                     args.transport, args.interval, args.min_duty, args.dry_run)
            ctl.loop(args.interval)
    except SystemExit:
        raise
    except Exception as e:  # 想定外の例外でも必ず BMC に返す
        log.exception("想定外のエラー: %s", e)
        ctl.hand_back_to_bmc("想定外のエラー")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
