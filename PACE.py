#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 PACE — REL Lab Power-Cycle Test Automation Controller
================================================================================
 Hardware   : Up to 8x dual-channel PSUs  (/dev/ttyACM0 .. /dev/ttyACM7)
 Platform   : Raspberry Pi 3 + Thonny IDE
 Library    : tkinter (standard) + pyserial

 SETUP (Run once in Pi terminal):
     pip3 install pyserial --break-system-packages

 RUN:
     Open this file in Thonny and press F5 (Run).

 FEATURES:
   - Voltage/Current are set per scenario step (Power-Up/Power-Down
     "+ Add Step" dialog), applied right before that step switches ON.
     Limited to 60V/20A by default; a per-step override checkbox allows
     entering higher values when needed. The override flag is stored with
     the step (and in JSON) so later edits/runs stay consistent.
   - Synchronous Mode : All PSUs turn ON/OFF together using the PSU1
     row of the settings table (CH1/CH2 Start/On-Dur/V/I from PSU1 are
     applied to every PSU). Only the PSU1 row is editable.
   - Asynchronous Mode : Each PSU operates independently, with its own
     per-channel timing. Each channel has an INDEPENDENT Start(s) [delay
     from cycle start] and On-Dur(s) [how long it stays ON], so CH1 and
     CH2 can overlap fully, partially, be exactly simultaneous, or not
     overlap at all - e.g. CH2 Start >= CH1 Start + CH1 On-Dur turns CH2
     on only after CH1 has already turned off. CH1 and CH2 each have their
     own Cycle OFF(s), so each channel can repeat with its own cadence.
   - Constant Mode : Steady output. Only CHx V / CHx I fields are
     editable; timing fields are disabled. START applies V/I and turns
     outputs ON until STOP/EMERGENCY/time-up.
   - Failsafe/Watchdog: If any PSU connection is lost,
     all outputs are turned OFF. Attempts to reconnect N times.
     If unsuccessful, the cycle is stopped. Every (re)connection - manual,
     auto-detect, or watchdog-triggered - forces that PSU's outputs to a
     known-safe 0V/0A/OFF state before anything else happens, so a session
     never inherits leftover V/I from a previous run or a crash.
   - Total runtime timer (or unlimited + manual stop). When the total
     time expires, all outputs are forced OFF regardless of cycle phase.
   - User-customizable Power-Up / Power-Down scenarios
     (saved/loaded as JSON)
   - Editable Power-Up/Power-Down step table: double-click any cell
     (PSU / Channel / Action / Wait After / Voltage / Current) to edit
     its value inline. Voltage/Current edits respect the same safety
     limits as the Add Step dialog. The Symbol/Step Editor preview
     graph updates live.
   - Power-Down scenarios assume all channels start ON; the preview
     timeline and step defaults reflect that (you only schedule OFF).
   - Each scenario step's "Wait After(s)" is referenced from scenario
     start (t=0), NOT cascaded/cumulative from the previous step.
   - Test Time: dwell between Power-Up completion and Power-Down start
     ("Run Full Cycle" runs Power-Up -> Test -> Power-Down).
   - Cycle programs are built with "+ Add Cycle" (Scenario Editor and
     Cycle Control) - the old "Transfer Cycle Control -> Power-Up" button
     was removed in v20.
   - Engineer / Operator access modes: Engineer can edit and save;
     Operator can load cycle/scenario programs and run them (no password
     is required in this interim version).
   - Live log screen + automatic .txt log file (Desktop)
     + optional .csv export
   - Live MCU Console: raw TX/RX of the MCU protocol, manual command entry
     (PING/RUN:n/LOOP/STOP quick buttons) and opening the MCU port without
     the automatic handshake so PING/READY can be done by hand.
   - Test Time progress bar fills as the test countdown runs.
   - START TEST supports PAUSE TEST: Power-Down runs while timers are
     frozen; START TEST runs Power-Up before resuming the saved time.
     STOP TEST resets the countdown; a new START TEST uses the durations
     currently entered. Test progress is shown in green.
   - Live V/I Graph: Lightweight Tkinter Canvas (no matplotlib)
     for both CH1 and CH2, optimized for Raspberry Pi 3. Live readings
     are requested every 300ms (plus serial query latency).

 ARCHITECTURE (single-file layers for Pi/Thonny deploy):
   1. SCPI Bus          — serial I/O via PSUDriver locks (per-port)
   2. PSU Manager       — PSUDriver registry + health timestamps
   3. Sequence Engine   — absolute-time steps with time.monotonic()
   4. Safety Manager    — IDLE/RUNNING/PAUSED/FAULT/EMERGENCY state machine
   5. Logger & Reports  — TXT + CSV + JSON session + HTML summary
   6. GUI               — presentation only

 RELIABILITY / SAFETY HARDENING:
   - Single global operation lock prevents START (continuous cycle),
     Run Power-Up/Power-Down and Run Full Cycle from running at the
     same time on the same PSUs. Status shown next to Cycle Control.
   - Log file, optional CSV, Watchdog and live V/I reading run for
     ALL modes (continuous cycle, scenario, full cycle).
   - Scenario steps re-validated against 60V/20A limits before every
     run (covers loaded JSON and later table edits).
   - "No PSU connected" confirmation is asked for scenarios/full cycle
     as well as continuous cycle.
   - Full scenario JSON is written into the log at the start of each run
     (audit / traceability).
   - Continuous cycle also stops watchdog/reading and closes log files
     when its duration expires naturally (not only on STOP/EMERGENCY).
   - EMERGENCY OFF also closes log files.
   - Interruptible waits: long sleeps respect STOP / EMERGENCY / PAUSE.
   - emergency_event is checked in all worker loops.
   - Cycle START forces all connected outputs OFF first (no residual ON).
   - STOP, EMERGENCY OFF and PAUSE all force every channel OFF.
   - Failed set_voltage / set_current / set_output commands are logged.

 v4 FIXES / ADDITIONS (this revision, after a full code + rel-lab review):
   - BUG FIX: PAUSE did nothing useful in Sync/Async continuous-cycle mode.
     The top-of-loop check called `_interruptible_sleep(0)`, which returns
     immediately without honoring pause_event (its early-return path for
     seconds<=0 skips the pause-wait entirely). Outputs were forced OFF the
     instant PAUSE was pressed, but the loop then immediately turned them
     back ON on its very next iteration. Fixed with an explicit
     `_wait_while_paused()` call before each iteration's body.
   - BUG FIX: the "Safety: ..." label never actually updated. `_set_safety()`
     pushed a `{"type": "safety", ...}` message to the queue, but
     `_process_queue()` had no handler for that message type. Added one,
     with state-appropriate coloring.
   - Safety state (RUNNING/IDLE) is now also tracked for scenario and full
     cycle runs, not only the continuous cycle — previously the label
     never reflected the two run types that matter most for lab tests.
   - After an EMERGENCY OFF, starting a new operation (START / Run
     Power-Up / Run Power-Down / Run Full Cycle) is now blocked until the
     operator explicitly presses "Reset Emergency" and confirms it is
     safe to resume. Previously START worked immediately with no
     acknowledgement step, which is not acceptable E-stop practice.
   - Session JSON/HTML reports are now written for scenario and full-cycle
     runs too (previously only for the continuous cycle), and include
     elapsed time and which PSUs were connected.
   - SAFETY-CRITICAL LAYOUT FIX: the whole dashboard was one big
     scrollable canvas — including EMERGENCY OFF. If an operator had
     scrolled down to read the log, the emergency button could be
     off-screen. EMERGENCY OFF is now also available as a large, always
     visible red bar pinned above the scrollable area, in addition to the
     original button in the Cycle Control panel.
   - Graph legend no longer lists PSU/Channel series that have no data
     yet (previously always showed all 16 CH1+CH2 entries regardless of
     whether a PSU was connected, cluttering/overflowing the legend).
   - PAUSE now explains itself (via a dialog) when pressed while no
     pauseable continuous cycle is running (e.g. during a scenario run).

 v14 FIXES / ADDITIONS (timing accuracy, after scope-measured delay in
 Power-Up/Power-Down "Wait After" was found larger than requested, and
 growing with PSU count on Raspberry Pi 3):
   - Live V/I reading poll is now one thread PER PSU instead of a single
     thread walking every PSU in sequence. The old shared loop could hold
     a given PSU's lock (the same lock scenario ON/OFF/V/I commands use)
     for a query round-trip right as a scenario step tried to fire on
     that same PSU, and the total time per poll pass - and therefore the
     odds of that overlap - grew with the number of connected PSUs. This
     was the main suspected cause of delay increasing with PSU count.
   - Scenario step waits now busy-wait (spin on time.monotonic()) for the
     final ~2ms before the target time instead of relying on
     time.sleep(), which avoids the OS scheduler's sleep wake-up jitter -
     the main source of small (few-ms) error on short waits like 0.01s on
     a non-realtime kernel. Still fully interruptible by STOP/EMERGENCY.
   - Note: this does not remove every source of delay. The PSU's own
     command-processing/relay-switching time and USB/serial round-trip
     latency are hardware/driver characteristics independent of the host
     platform, so some residual delay (and its variance) is expected even
     after these changes, and may improve further on Pi 5 / a PC purely
     from a faster CPU and (on Pi 3) a less shared internal USB bus.

 v14 ADDITIONS (Output Characteristic presets + Live V/I Monitor table):
   - Live Current/Voltage Monitor table added to the Scenario Editor tab,
     below the Symbol/Step Editor preview: one row per PSU/Channel showing
     Set V/I (from PSUDriver.ch_state), Actual V/I (from the per-PSU
     reading thread), and Output ON/OFF. Updates as "reading"/"conn"
     messages arrive, so it stays live during Sync/Async/Constant cycles
     and Scenario/Full Cycle runs, not just while a scenario is executing.
   - "Output Characteristic" preset selector added: 60V/10A, 60V/3A,
     16V/10A, Custom Limits - mirroring the front-panel Range Selection
     keys. IMPORTANT CAVEAT (confirmed against the PSU's remote
     command reference): front-panel Range Selection has NO SCPI
     equivalent - it is local/manual-only, and there is no command to
     switch it remotely. Selecting a preset here therefore programs the
     instrument's OVP<n>/OCP<n> trip points (which ARE remote-settable) to
     that preset's V/I ceiling instead - the closest legitimate remote
     equivalent, and it does enforce the same limit on the instrument
     itself. It will NOT move the range lamp on the physical front panel.
     Available in two places:
       * Operation Mode panel: one global preset, applied to every
         PSU/channel that Sync/Async/Constant turns ON.
       * Add Step dialog (Power-Up/Power-Down) and the Scenario table's
         new "Output Char." column: one preset per step, applied just
         before that step's V/I/Output-ON commands fire.
     Voltage/Current entry validation (both the Operation Mode panel and
     the step dialog/table) now checks against the selected preset's V/I
     ceiling instead of the global 60V/20A safety limit, unless "Custom
     Limits" is selected (old global-limit behaviour, unchanged).
     Old scenario JSON files without a "characteristic" key still load
     fine - missing values default to "Custom Limits", i.e. today's
     original behaviour.


 v16 CHANGES:
   - Scenario Save/Load now use native file dialogs (asksaveasfilename /
     askopenfilename). The operator picks any folder/file path; the old
     fixed ~/pace_scenarios directory is only the default starting
     folder, not a hard requirement. Cycle program Save/Load already
     used file dialogs; they keep that behaviour (default start folder
     ~/pace_cycle_programs).
   - Dry Run / Simulation Speed UI and logic removed. Scenario and Full
     Cycle runs always drive real hardware (subject to connection checks).
     The previous "simulate only" path was rarely useful on the bench and
     added confusion about whether outputs would actually switch.
   - Watchdog is now OPT-IN and OFF by default. Continuous mid-run USB
     monitoring can interrupt long lab cycles on transient serial glitches;
     cable unplug mid-test is uncommon. Connection is still verified at
     START / Run Scenario / Run Full Cycle via the existing "No PSU
     connected" confirmation and Connect/Auto-Detect flow. When the
     operator enables "Enable mid-run Watchdog" in the Failsafe panel,
     the previous reconnect/failsafe behaviour is restored for that run.
     Live V/I reading is unchanged and independent of the watchdog.

 v18 CHANGES (layout - no more page scrolling):
   - The whole dashboard used to live inside one big Canvas with BOTH a
     vertical and a horizontal scrollbar, because the old two-column layout
     (Operation Mode + Watchdog + Cycle Timeline Preview stacked on the
     left, Scenario Editor + Monitor stacked on the right) was taller and
     sometimes wider than a normal screen. Replaced with a plain
     ttk.Notebook holding two tabs - "Cycle Control" (Operation Mode / PSU
     Settings / Cycle Control / Total Operation Time / Failsafe-Watchdog /
     Cycle Timeline Preview) and "Scenario Editor & Monitor" (Power-Up/
     Power-Down step editor, Symbol/Step Editor preview, Live Current/
     Voltage Monitor). Each tab now gets the FULL window width instead of
     half of it, and only holds about half of what used to be crammed into
     one column, so both tabs fit inside one normal (maximized) screen
     with no outer up/down or left/right scrolling needed.
   - Connection Status stays pinned above the tabs (like EMERGENCY OFF),
     so it - and the always-reachable Connect/Auto-Detect/Detect MCU
     buttons - are visible no matter which tab is selected.
   - Live Graph / Live Log / Live SCPI Console are unchanged: still their
     own separate, independently movable/resizable windows (not part of
     the tabbed dashboard), so they were never part of this scrolling
     issue.
   - Tables/graphs that legitimately benefit from their own internal
     scroll or zoom (the Scenario step table, the Symbol/Step Editor and
     Cycle Timeline Preview canvases, the Live Monitor table, the
     Connection Status PSU strip on very narrow windows) keep their own
     small widget-level scrollbars - only the outer whole-dashboard
     scrolling was removed.

 v19 CHANGES:
   - New Scenario Editor step action: "CYCLE". Lets ONE Power-Up/Power-
     Down step repeatedly turn a single PSU/Channel ON/OFF (its own ON
     time, OFF time and repeat count - 0 = run until STOP/EMERGENCY),
     all inside the normal scenario run. It only ever touches the one
     (PSU, Channel) that step names - every other channel (e.g. the
     ones a preceding ON step already brought up and sequenced) is left
     completely alone, so a CYCLE step can be used to repeatedly power-
     cycle one input for a stress/reset test right after a Power-Up
     sequence has stabilised the rest of the system, with no separate
     Continuous Cycle run and no risk of disturbing those other rails.
     Added motivation: the previous Continuous Cycle (Sync/Async/
     Constant) run always force-turns-OFF every connected PSU/Channel
     the instant it starts, which would also drop any rails a Power-Up
     scenario had just brought up - CYCLE avoids that entirely by
     staying inside the Scenario Editor/engine, which never touches a
     (PSU, Channel) that no step names.
   - The step ends with that channel OFF (whether it completed its full
     repeat count or was interrupted by STOP/EMERGENCY) - add an
     explicit ON step after it if the channel should end up energised.
   - Symbol/Step Editor preview draws the repeating ON/OFF pulses for a
     CYCLE row (an unbounded "until stopped" step previews a handful of
     representative repeats, not literally forever).
 v20 CHANGES (step-based Cycle programs):
   - Cycle Control now has a 4th Operation Mode, "Program (step table)".
     It shows the SAME step table as the Scenario Editor (PSU / Channel /
     Action / Wait After / V / I / ...): Wait After is the time from the
     program start; the program runs once, or repeats every "Repeat every
     (s)" if that is > 0, until Total Operation Time runs out, the Cycle
     Count is reached, Stop Cycle or STOP.
   - The Scenario Editor has a third scenario type, "Cycle". It edits the
     very same list as the Cycle Control table (one source of truth).
     START TEST now runs Power-Up -> Cycle -> Test Time -> Power-Down,
     and a "Run Cycle" button runs it on its own.
   - Program mode NEVER force-switches every PSU off at start or at the
     end: only the (PSU, Channel) pairs named in the steps are touched, so
     rails brought up by Power-Up stay on while the Cycle runs. (STOP /
     EMERGENCY / PAUSE still switch everything off, as before.)
   - CYCLE steps in a Cycle program run on THEIR OWN ON/OFF/Repeat Count
     (Count 0 = until Total Operation Time ends / Stop Cycle / STOP);
     "Repeat every (s)" = 0 runs the program once, > 0 repeats it. Edges
     are scheduled on an absolute timeline (no SCPI-latency drift) and the
     measured average ON/OFF is logged when a CYCLE step finishes.
   - Scenario Monitor: "Stop Cycle" ends only the Cycle program (START TEST
     then continues with Test Time / Power-Down), "STOP TEST" aborts and
     switches everything OFF. A Cycle Duration field (shared with Cycle
     Control's Total Operation Time) and its countdown are shown there.
   - Cycle programs (incl. the step table and period) are saved/loaded
     with "Save Cycle/Test Program" / "Load Program"; Undo/Redo and
     auto-save/recovery cover the Cycle steps too.
================================================================================

 v22 CHANGES (universal MCU protocol + 24 h stability):
   - MCU protocol: replies are now read until the expected answer arrives;
     firmware debug lines ('# ...' or '[12345] ...') are ignored. Fixes
     "Run test sends no pattern" with the Maxwell sketch (DEBUG_LOG 1 printed
     a debug line before READY, which the old one-line read mistook for a
     failed PING) while the MCU Console (which shows all lines) still worked.
   - New optional MCU step field "MCU Profile": SEL:<name> is sent before
     RUN/LOOP so ONE firmware can play several patterns (maxwell / said).
     Old JSON without the field works unchanged. Quick buttons INFO /
     SEL:maxwell / SEL:said added to the MCU Console.
   - EMERGENCY OFF / STOP no longer wait for a running MCU RUN (lock held up
     to 120 s -> GUI froze); RUN also aborts immediately on STOP/EMERGENCY.
   - Anti-freeze: Live Log bounded to LOG_MAX_LINES, LIVE V/I lines logged
     once per LIVE_LOG_INTERVAL_S per channel (graph/CSV still get every
     sample), log file flushed once per batch, SCPI traffic only queued
     while its console is open, and an exception while handling one queue
     message can no longer stop the GUI update loop for good.

 v23 CHANGES (renamed to PACE + mouse/keyboard freeze on the Pi):
   - Program renamed to PACE (window title, log/CSV/report files, data
     folders ~/pace_*). Data folders from older versions are moved to the
     new names automatically on first start.
   - GUI freeze fix: the message queue is processed in time-limited
     batches (QUEUE_BATCH_BUDGET_S) with a real pause between batches, log
     and console lines are written to their widgets once per batch, the
     Live Monitor table / labels are only updated when a value changes,
     the watchdog no longer posts "OK" every 200 ms, graphs are not
     redrawn while hidden, and live V/I samples are dropped (not queued
     forever) if the GUI ever falls behind (QUEUE_MAX_BACKLOG).
   - Live V/I reading interval is now selectable (Live Current/Voltage
     Monitor -> "Reading interval": 300 ms .. 60 s or Off, Engineer mode,
     default 1 s, saved in pace_settings.json) to cut USB traffic. Each
     reading = 4 SCPI queries per connected PSU; the estimated load is
     shown next to the selector. The Live Graph time span widens to
     10 readings for long intervals.
   - "What to read..." (next to the interval): per PSU / channel choose
     Actual V and/or Actual I. Each unticked value saves one SCPI query
     per reading; a PSU with nothing ticked gets no reading traffic.
     Unmonitored values show '-' in the table and are empty in the CSV.

 COMPATIBILITY NOTE:
   Scenario "action" values are "ON"/"OFF"/"CYCLE"/"MCU" (CYCLE added in
   v19 - older JSON files with only ON/OFF/MCU remain fully compatible).
   Mode values are "sync"/"async"/"constant".
   Scenario kind keys are "powerup"/"powerdown". JSON files from older
   English builds remain compatible. Turkish builds that stored
   "AÇIK"/"KAPALI" are NOT compatible — re-create those scenarios or
   edit the JSON action fields to "ON"/"OFF".
   MCU steps require the MCU to run mcu_pattern_listener.py (serial
   text protocol: PING->READY, RUN:<n>->DONE, LOOP, STOP). The controller
   never asks the operator to type those commands; they are fired
   automatically when a scenario step with action=MCU is reached.
================================================================================
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import threading
import queue
import time
import json
import math
import os
import copy
from datetime import datetime
from collections import deque

try:
    import serial  # type: ignore
except Exception:
    serial = None  # App launches; connection attempt will report the error.

try:
    from serial.tools import list_ports as serial_list_ports  # type: ignore
except Exception:
    serial_list_ports = None


# ==============================================================================
# CONSTANTS
# ==============================================================================
MAX_PSUS = 8

# Ports are not hard-coded (Linux /dev/ttyACMx vs Windows COMx; USB hub order
# can also shift). Use "Auto-Detect Ports" (also run once at startup).
DEFAULT_PORTS = [None] * MAX_PSUS

# Strings expected in a genuine supported-PSU *IDN? reply (hardware ID, not shown in the UI).
PSU_IDN_KEYWORDS = ("CPX400", "THURLBY", "AIM-TTI", "AIM TTI", "TTI")

BAUDRATE = 115200
SERIAL_TIMEOUT = 0.3
SCAN_TIMEOUT = 1.0

# --- MCU pattern-trigger link -------------------------------------------
# Separate USB-serial device from the PSUs (runs mcu_pattern_listener.py).
# Tiny text protocol, NOT SCPI:
#   PING      -> READY                  (identify / connection check)
#   RUN:<n>   -> ... -> DONE            (play the RLE pattern n times)
#   LOOP      -> (no DONE)              (play forever until STOP)
#   STOP      -> aborts an active LOOP
# The ns-precision playback itself happens entirely on the MCU's PIO+DMA;
# this app only triggers it and (for non-loop runs) waits for DONE.
MCU_DEFAULT_PORT = None
MCU_BAUDRATE = 115200
MCU_SERIAL_TIMEOUT = 0.3
MCU_SCAN_TIMEOUT = 1.0
# Max wait for DONE on a RUN:<n> (not LOOP). Short RLE patterns finish in
# milliseconds; a high ceiling covers long multi-repeat runs without
# blocking scenario recovery forever if the MCU hangs.
MCU_DONE_TIMEOUT_S = 120.0
MCU_PING_KEYWORD = "READY"
MCU_DONE_KEYWORD = "DONE"
# v22: how long to wait for the actual answer to PING/SEL/INFO. The old code
# read exactly ONE line, so any debug line printed by the firmware before
# its answer (Maxwell sketch with DEBUG_LOG 1) was mistaken for "no reply".
MCU_REPLY_TIMEOUT_S = 1.5


def _is_mcu_noise(line):
    """True for firmware debug/log lines that are not protocol answers:
    '# ...' (the v22 firmware convention) and '[12345] ...' (the old
    Maxwell timestamped debug output), plus the BOOT banner."""
    s = (line or "").lstrip()
    return s.startswith("#") or s.startswith("[") or s == "BOOT"

# Explicit commands the operator can schedule for a MCU scenario step -
# matches the raw text protocol above 1:1 so it's obvious what gets sent
# over USB at that point in the timeline.
MCU_COMMANDS = ("RUN", "LOOP", "PING", "STOP")


def _safe_float(value, default=0.0):
    """float(value), falling back to `default` for None/""/garbage instead
    of raising - scenario step dicts may come from hand-edited JSON."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _mcu_step_cmd(step):
    """Return a MCU scenario step's command: 'RUN'/'LOOP'/'PING'/'STOP'.

    Reads the explicit "mcu_cmd" field used by the command selector in
    ScenarioStepDialog. Falls back to the older "mcu_loop" boolean for
    scenario JSON files saved before that selector existed (no PING/STOP
    option back then - just RUN or LOOP)."""
    cmd = step.get("mcu_cmd")
    if cmd in MCU_COMMANDS:
        return cmd
    return "LOOP" if step.get("mcu_loop") else "RUN"

DESKTOP_DIR = os.path.join(os.path.expanduser("~"), "Desktop")
# v23: data folders were renamed to "pace_*". Folders/files saved by older
# versions (same name, old prefix) are moved over once, on first start.
_LEGACY_DATA_PREFIX = "cpx400dp_"


def _migrate_legacy_data(new_path):
    head, name = os.path.split(new_path)
    old_path = os.path.join(head, _LEGACY_DATA_PREFIX + name[len("pace_"):])
    if os.path.exists(old_path) and not os.path.exists(new_path):
        try:
            os.rename(old_path, new_path)
        except OSError:
            pass


SCENARIO_DIR = os.path.join(os.path.expanduser("~"), "pace_scenarios")
_migrate_legacy_data(SCENARIO_DIR)
os.makedirs(SCENARIO_DIR, exist_ok=True)
PROGRAM_DIR = os.path.join(os.path.expanduser("~"), "pace_cycle_programs")
_migrate_legacy_data(PROGRAM_DIR)
os.makedirs(PROGRAM_DIR, exist_ok=True)
# v21: remembered manual PSU -> COM port assignments (Connection Status).
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), "pace_settings.json")
_migrate_legacy_data(SETTINGS_PATH)

GRAPH_WINDOW_SEC = 60
GRAPH_REFRESH_MS = 500
# One shared sample stream for the monitor, graph and log. Each PSU polls
# independently; actual cadence also includes its serial query latency.
# v23: the interval is chosen by the operator (Live Current/Voltage Monitor
# -> "Reading interval") and saved in SETTINGS_PATH. Every reading costs up
# to 4 SCPI queries per connected PSU (V1O?, I1O?, V2O?, I2O? - only the
# ones selected under "What to read..."), so a longer interval / fewer
# selected values directly reduce USB traffic. "Off" stops live reading.
READING_POLL_OPTIONS = [
    ("300 ms", 300), ("500 ms", 500), ("1 s", 1000), ("2 s", 2000),
    ("5 s", 5000), ("10 s", 10000), ("30 s", 30000), ("60 s", 60000),
    ("Off", 0),
]
READING_POLL_LABELS = {ms: label for label, ms in READING_POLL_OPTIONS}
READING_POLL_DEFAULT_MS = 1000
# v23: order of the per-PSU Live Monitor selection flags in the settings
# file: CH1 V, CH1 I, CH2 V, CH2 I. Each selected flag = 1 SCPI query.
MONITOR_SEL_ORDER = ((1, "v"), (1, "i"), (2, "v"), (2, "i"))

WATCHDOG_INTERVAL_MS = 200
WATCHDOG_TIMEOUT_S = 0.5
RECONNECT_ATTEMPTS = 3
RECONNECT_DELAY_S = 1.0

# v17: how long the always-on reading thread will tolerate a PSU going
# quiet (no successful reply at all - readline() timing out, not an
# actual exception) before it stops trusting psu.connected==True and
# forces a reconnect. Covers the case where the host OS never notices
# the physical disconnect (no OSError from pyserial - the device node
# is still there, it's just not answering), which a purely
# exception-driven check can miss forever. Kept well above one normal
# poll cycle so a single slow reply during a busy scenario step doesn't
# trigger a false reconnect (v23: the reading thread also stretches it to
# at least 3 reading intervals - see _reading_worker_for_psu).
LINK_STALE_TIMEOUT_S = 30.0 + 2 * SERIAL_TIMEOUT + 1.0

SCENARIO_STEP_POLL_S = 0.05
TEST_POLL_S = 0.2
# v14: below this remaining time, _scenario_step_worker busy-waits instead
# of calling time.sleep(). On a non-realtime Linux scheduler (stock Pi/PC
# kernel), a sleeping thread's wake-up latency is not guaranteed and can
# easily add a few ms of jitter on its own - noticeable when the requested
# "Wait After" is itself only ~0.01s. A short spin over time.monotonic()
# for the last couple of ms trades a little extra CPU for much tighter
# timing accuracy right before the step fires. Keep this well below
# SCENARIO_STEP_POLL_S so it only affects the final approach to the
# deadline, not the whole wait.
SCENARIO_STEP_SPIN_S = 0.002
# Slice size for interruptible waits (stop / emergency / pause).
INTERRUPT_SLICE_S = 0.05

# v19: a CYCLE scenario step with cycle_count<=0 ("until stopped") repeats
# forever, so the Symbol/Step Editor preview cannot literally draw every
# pulse - it draws this many representative ON/OFF repeats instead, from
# the step's start offset onward.
CYCLE_PREVIEW_REPS = 6
# v20: hard cap on pulses drawn per CYCLE row in the preview. A transferred
# Cycle Control program (e.g. 0.1s ON/OFF for 1 hour = 18000 pulses x up to
# 16 channels) used to generate hundreds of thousands of canvas points and
# froze the GUI ("not responding"). Beyond this many pulses the preview
# shows the first CYCLE_PREVIEW_MAX_PULSES only (the real run is unaffected).
CYCLE_PREVIEW_MAX_PULSES = 100

LIMIT_VOLTAGE_MAX = 60.0
LIMIT_CURRENT_MAX = 20.0

# v14: "Output Characteristic" presets, mirroring the PSU front-panel
# Range Selection keys (60V/10A, 60V/3A, 16V/10A, Custom Limits - as
# labelled on the unit's panel). IMPORTANT: per the PSU's own
# remote command reference, front-panel Range Selection has NO SCPI
# equivalent - it is a local-only control and changing it remotely is not
# possible ("range changing is only allowed if the output is off" and no
# RANGE command exists in the command list). The closest legitimate
# remote equivalent is programming the OVP<n>/OCP<n> trip points (which
# ARE remotely settable) to the preset's V/I ceiling. Selecting a preset
# here therefore does not move the lamp on the unit itself, but it does
# make the instrument enforce the same V/I ceiling remotely via its
# protection trips, and it is used locally in this app to clamp/validate
# the Voltage/Current fields for that preset. "Custom Limits" keeps the
# previous behaviour (global LIMIT_VOLTAGE_MAX/LIMIT_CURRENT_MAX, with the
# existing per-step/per-mode override checkbox).
OUTPUT_CHARACTERISTICS = [
    ("60V/10A", 60.0, 10.0),
    ("60V/3A", 60.0, 3.0),
    ("16V/10A", 16.0, 10.0),
    ("Custom Limits", None, None),
]
OUTPUT_CHARACTERISTIC_NAMES = [c[0] for c in OUTPUT_CHARACTERISTICS]
OUTPUT_CHARACTERISTIC_MAP = {c[0]: (c[1], c[2]) for c in OUTPUT_CHARACTERISTICS}

# --- Auto-save / Recovery ----------------------------------------------
# The current Power-Up/Power-Down scenario is auto-saved on a timer (and
# on clean exit) to a fixed recovery file, kept separate from the
# user-named files in SCENARIO_DIR so it never clutters the "Load..."
# picker. On next startup, if this file has any steps in it, the operator
# is offered a one-click restore.
AUTOSAVE_INTERVAL_MS = 30_000
RECOVERY_DIR = os.path.join(os.path.expanduser("~"), "pace_recovery")
_migrate_legacy_data(RECOVERY_DIR)
os.makedirs(RECOVERY_DIR, exist_ok=True)
RECOVERY_FILE = os.path.join(RECOVERY_DIR, "last_session.json")

# --- SCPI console ---------------------------------------------------------
SCPI_CONSOLE_MAX_LINES = 500

# v22 anti-freeze limits (24 h unattended runs, Raspberry Pi 3):
# - the Live Log widget used to grow without bound (only the SCPI/MCU
#   consoles were trimmed), eating RAM until the whole Pi stalled;
# - every LIVE V/I sample (every 0.3 s per channel) was also written to the
#   Live Log AND flushed to the SD card. Now the log shows one LIVE line per
#   channel every LIVE_LOG_INTERVAL_S; graph, monitor table and CSV still get
#   every sample.
LOG_MAX_LINES = 2000
LIVE_LOG_INTERVAL_S = 5.0
# v23 anti-freeze (mouse/keyboard stopped responding after a while on the
# Pi): the GUI thread spends at most this long per queue batch, so Tk always
# gets time to handle mouse/keyboard events between batches.
QUEUE_BATCH_BUDGET_S = 0.04
# If the GUI still falls behind, live V/I samples (not log lines) are
# dropped above this backlog instead of growing RAM until the Pi stalls.
QUEUE_MAX_BACKLOG = 3000

PSU_COLORS = {
    1: "#e6194b", 2: "#3cb44b", 3: "#4363d8", 4: "#f58231",
    5: "#911eb4", 6: "#46f0f0", 7: "#f032e6", 8: "#9a6324",
}
# CH2 series use a slightly darker shade of the same PSU colour.
PSU_COLORS_CH2 = {
    1: "#9a1030", 2: "#287830", 3: "#2a4088", 4: "#a85820",
    5: "#601488", 6: "#2a9090", 7: "#a02098", 8: "#6a4420",
}
# Colour used for MCU signal rows in the Symbol/Step Editor timeline preview.
MCU_ROW_COLOR = "#008080"


# ==============================================================================
# SAFETY STATE MACHINE
# ==============================================================================
class SafetyState:
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FAULT = "FAULT"
    EMERGENCY = "EMERGENCY"


# Display color for each safety state (used by the "Safety: ..." label).
SAFETY_COLORS = {
    SafetyState.IDLE: "green",
    SafetyState.RUNNING: "blue",
    SafetyState.PAUSED: "#b8860b",
    SafetyState.FAULT: "red",
    SafetyState.EMERGENCY: "red",
}


# ==============================================================================
# NUMERIC-ONLY ENTRY HELPERS
# Every fillable field in this app (V/I setpoints, ON/OFF/delay seconds,
# hr:min:sec timers, scenario-step cell edits) must only ever accept
# digits and a single decimal point. Comma and any other special
# character are rejected both while typing and while pasting.
# ==============================================================================
def _numeric_key_filter(event):
    """Tk <KeyPress> handler: return "break" to swallow disallowed input."""
    # Let navigation/editing keys through untouched: BackSpace/Delete must
    # always work to correct a typo. Tk reports these with a control-char
    # event.char (e.g. BackSpace = '\x08'), which is truthy and was
    # previously falling through to the "reject" branch below - that bug
    # is why Backspace/Delete looked broken. Check keysym first, and as a
    # second safety net let any non-printable/control character through
    # (Ctrl+<letter> shortcuts also produce control chars here).
    keysym = getattr(event, "keysym", "")
    if keysym in (
        "BackSpace", "Delete", "Left", "Right", "Home", "End", "Tab",
        "Return", "KP_Enter", "Escape", "Up", "Down",
        "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    ):
        return None
    ch = event.char
    if not ch or ord(ch) < 32 or ord(ch) == 127:
        return None
    # Reject comma and any non digit/dot
    if ch == "," or ch == " " or (not ch.isdigit() and ch != "."):
        return "break"
    # Reject a second decimal point
    w = event.widget
    try:
        current = w.get()
        if ch == "." and "." in current:
            return "break"
        # If there is a selection that includes the existing dot, allow replacing it
        if ch == "." and w.selection_present():
            sel = w.selection_get()
            if "." in sel:
                return None
            if "." in current:
                return "break"
    except Exception:
        pass
    return None


def _sanitize_numeric_string(s):
    """Keep only digits and at most one '.' (commas/special chars stripped)."""
    if s is None:
        return ""
    s = str(s).replace(",", ".")  # tolerant paste: comma -> dot, then single-dot rule
    out = []
    seen_dot = False
    for ch in s:
        if ch.isdigit():
            out.append(ch)
        elif ch == "." and not seen_dot:
            out.append(ch)
            seen_dot = True
    return "".join(out)


def _bind_numeric_entry(entry):
    """Attach key filter + paste sanitizer to a ttk/tk Entry."""
    entry.bind("<KeyPress>", _numeric_key_filter)

    def _on_paste(_event):
        try:
            try:
                data = entry.clipboard_get()
            except Exception:
                return "break"
            data = _sanitize_numeric_string(data)
            try:
                if entry.selection_present():
                    entry.delete("sel.first", "sel.last")
            except Exception:
                pass
            entry.insert("insert", data)
        except Exception:
            pass
        return "break"

    entry.bind("<<Paste>>", _on_paste)
    entry.bind("<Control-v>", _on_paste)
    entry.bind("<Control-V>", _on_paste)
    return entry


def _time_key_filter(event):
    """Key filter for a combined 'HH:MM:SS' Entry: digits and ':' only."""
    keysym = getattr(event, "keysym", "")
    if keysym in (
        "BackSpace", "Delete", "Left", "Right", "Home", "End", "Tab",
        "Return", "KP_Enter", "Escape", "Up", "Down",
        "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    ):
        return None
    ch = event.char
    if not ch or ord(ch) < 32 or ord(ch) == 127:
        return None
    if not (ch.isdigit() or ch == ":"):
        return "break"
    return None


def _int_or_zero(value):
    try:
        return max(0, int(str(value).strip() or 0))
    except ValueError:
        return 0


def _normalize_time_entry(entry):
    """Reformat/clamp a combined 'HH:MM:SS' Entry to zero-padded, valid values."""
    bits = (entry.get().strip().split(":") + ["0", "0", "0"])[:3]
    h, m, s = (_int_or_zero(b) for b in bits)
    text = f"{h:02d}:{min(m, 59):02d}:{min(s, 59):02d}"
    old_state = str(entry.cget("state"))
    if old_state == "disabled":
        entry.config(state="normal")
    entry.delete(0, "end")
    entry.insert(0, text)
    if old_state == "disabled":
        entry.config(state="disabled")
    return text


def _bind_time_entry(entry):
    """Attach key filter + on-blur normalization to a combined 'HH:MM:SS' Entry."""
    entry.bind("<KeyPress>", _time_key_filter)
    entry.bind("<FocusOut>", lambda e: _normalize_time_entry(entry))
    return entry


class _TimeEntryPart:
    """Proxy for one H/M/S component of a single combined 'HH:MM:SS' Entry.

    The Total Operation Time field used to be three separate small Entry
    widgets (hour/minute/second). It is now one merged Entry for a cleaner
    UI, but the rest of the code (save/load program, cycle start, state
    toggling) still reads/writes hour/minute/second independently via
    .get()/.insert()/.delete()/.config()/.cget() - this proxy keeps that
    code working unchanged by mapping those calls onto the shared Entry.
    """

    def __init__(self, owner, index):
        self._owner = owner
        self._index = index

    def _parts(self):
        return (self._owner.get().strip().split(":") + ["0", "0", "0"])[:3]

    def _write_parts(self, bits):
        text = ":".join(f"{_int_or_zero(b):02d}" for b in bits)
        old_state = str(self._owner.cget("state"))
        if old_state == "disabled":
            self._owner.config(state="normal")
        self._owner.delete(0, "end")
        self._owner.insert(0, text)
        if old_state == "disabled":
            self._owner.config(state="disabled")

    def get(self):
        # Always return a plain numeric string, even if the user left the
        # combined field mid-edit (e.g. "1::5"), so callers doing int(...)
        # on this never crash.
        return str(_int_or_zero(self._parts()[self._index]))

    def insert(self, _pos, value):
        bits = self._parts()
        bits[self._index] = value
        self._write_parts(bits)

    def delete(self, *_args):
        bits = self._parts()
        bits[self._index] = "0"
        self._write_parts(bits)

    def config(self, **kwargs):
        self._owner.config(**kwargs)

    def cget(self, key):
        return self._owner.cget(key)

    def __getitem__(self, key):
        return self._owner[key]


# ==============================================================================
# PSU DRIVER  (communication with one PSU)
# ==============================================================================
class PSUDriver:
    def __init__(self, index, port):
        self.index = index
        self.port = port
        self.ser = None
        self.lock = threading.Lock()
        self.connected = False
        self.last_ok_time = 0.0
        # Last known commanded state per channel, used to restore the
        # exact V/I/output state after a PAUSE -> RESUME cycle.
        self.ch_state = {1: {"v": 0.0, "i": 0.0, "on": False},
                          2: {"v": 0.0, "i": 0.0, "on": False}}
        # Optional callback(psu_index, "TX"/"RX", text) invoked for every
        # raw SCPI command written / reply read, from whatever thread
        # issued it. Used to drive the Live SCPI Console. Must be cheap
        # and must never raise - callers wrap it defensively anyway.
        self.on_traffic = None

    def connect(self):
        if serial is None or not self.port:
            return False
        try:
            self.ser = serial.Serial(self.port, BAUDRATE, timeout=SERIAL_TIMEOUT)
            time.sleep(0.2)
            idn = self._query("*IDN?")
            self.connected = bool(idn)
            if self.connected:
                self.last_ok_time = time.time()
            return self.connected
        except Exception:
            self.connected = False
            return False

    def disconnect(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass
        self.connected = False

    def reconnect(self):
        """Close a stale handle (if any) and reopen the SAME port, then
        verify with *IDN?. Used by the always-on link-recovery in the
        reading thread (see App._reading_worker_for_psu) so live USB
        comms keep re-establishing themselves even when the operator has
        NOT enabled the mid-run Watchdog checkbox. Deliberately does not
        touch V/I/output state - the caller decides whether/how to
        resync those after a successful reconnect.
        """
        if serial is None or not self.port:
            return False
        try:
            with self.lock:
                if self.ser is not None:
                    try:
                        self.ser.close()
                    except Exception:
                        pass
                    self.ser = None
                self.ser = serial.Serial(self.port, BAUDRATE, timeout=SERIAL_TIMEOUT)
            time.sleep(0.2)
        except Exception:
            self.connected = False
            return False
        idn = self._query("*IDN?")
        self.connected = bool(idn)
        if self.connected:
            self.last_ok_time = time.time()
        return self.connected

    def _write(self, cmd):
        if not self.ser or not self.ser.is_open:
            raise IOError("Port is not open")
        self.ser.write((cmd + "\r\n").encode())
        if self.on_traffic:
            try:
                self.on_traffic(self.index, "TX", cmd)
            except Exception:
                pass

    def _query(self, cmd):
        with self.lock:
            try:
                self.ser.reset_input_buffer()
                self._write(cmd)
                resp = self.ser.readline().decode(errors="ignore").strip()
                if resp:
                    self.last_ok_time = time.time()
                if self.on_traffic:
                    try:
                        self.on_traffic(self.index, "RX", resp if resp else "(no reply)")
                    except Exception:
                        pass
                return resp
            except Exception:
                self.connected = False
                return ""

    def _command(self, cmd):
        with self.lock:
            try:
                self._write(cmd)
                self.last_ok_time = time.time()
                return True
            except Exception:
                self.connected = False
                return False

    def set_voltage(self, ch, value):
        ok = self._command(f"V{ch} {value}")
        if ok:
            self.ch_state[ch]["v"] = value
        return ok

    def set_current(self, ch, value):
        ok = self._command(f"I{ch} {value}")
        if ok:
            self.ch_state[ch]["i"] = value
        return ok

    def set_ovp(self, ch, value):
        """Program the Over-Voltage Protection trip point (SCPI: OVP<n>).
        Remotely settable per the PSU command reference."""
        return self._command(f"OVP{ch} {value}")

    def set_ocp(self, ch, value):
        """Program the Over-Current Protection trip point (SCPI: OCP<n>).
        Remotely settable per the PSU command reference."""
        return self._command(f"OCP{ch} {value}")

    def apply_output_characteristic(self, ch, vmax, imax):
        """Apply an Output Characteristic preset (see OUTPUT_CHARACTERISTICS)
        by programming OVP/OCP to the preset's ceiling - the closest
        remotely-controllable equivalent of the front-panel Range
        Selection keys (which cannot be switched over SCPI)."""
        ok1 = self.set_ovp(ch, vmax)
        ok2 = self.set_ocp(ch, imax)
        return ok1 and ok2

    def set_output(self, ch, state):
        ok = self._command(f"OP{ch} {1 if state else 0}")
        if ok:
            self.ch_state[ch]["on"] = bool(state)
        return ok

    def all_outputs_off(self):
        ok1 = self.set_output(1, False)
        ok2 = self.set_output(2, False)
        return ok1 and ok2

    def read_actual(self, ch):
        try:
            v_resp = self._query(f"V{ch}O?")
            i_resp = self._query(f"I{ch}O?")
            v = float(v_resp.rstrip("V")) if v_resp else None
            i = float(i_resp.rstrip("A")) if i_resp else None
            return v, i
        except Exception:
            return None, None

    def read_selected(self, ch, want_v, want_i):
        """v23: like read_actual() but only sends the queries that are
        actually wanted (Live Monitor selection), to keep USB traffic low.
        Unrequested values are returned as None."""
        v = i = None
        try:
            if want_v:
                v_resp = self._query(f"V{ch}O?")
                v = float(v_resp.rstrip("V")) if v_resp else None
            if want_i:
                i_resp = self._query(f"I{ch}O?")
                i = float(i_resp.rstrip("A")) if i_resp else None
        except Exception:
            pass
        return v, i

    def ping(self):
        idn = self._query("*IDN?")
        return bool(idn)


class MCUTrigger:
    """Serial link to an external microcontroller (Raspberry Pi Pico,
    Arduino, or similar) running the matching mcu_pattern_listener
    firmware for your board.

    Same connect/disconnect/lock shape as PSUDriver, but speaks the tiny
    text protocol above instead of SCPI. The MCU owns all real-time
    timing (e.g. PIO + DMA on a Pico; timers/interrupts on an Arduino);
    this class only fires the trigger and, for a normal (non-loop) run,
    blocks until the MCU confirms it is actually done -- so a scenario
    step that follows an MCU trigger in the timeline is guaranteed to
    start only after the pattern finished.
    """

    def __init__(self, port=None):
        self.port = port
        self.ser = None
        self.lock = threading.Lock()
        self.connected = False
        self.looping = False
        self.profile = ""        # last profile selected with SEL:<name>
        self.info_text = ""      # last INFO reply from the firmware
        # Optional callable returning True when STOP/EMERGENCY was pressed;
        # lets trigger() stop waiting for DONE immediately (set by App).
        self.abort_check = None
        # Optional callback(direction, text) for a future live console,
        # mirroring PSUDriver.on_traffic. Must be cheap and never raise.
        self.on_traffic = None

    def connect(self):
        if serial is None or not self.port:
            return False
        ser = None
        try:
            ser = serial.Serial(self.port, MCU_BAUDRATE,
                                 timeout=MCU_SERIAL_TIMEOUT)
            # FIX: pyserial asserts DTR high by default the instant the
            # port opens. Recent MicroPython USB-CDC builds treat that
            # DTR-low->high transition as "a new terminal attached" and
            # soft-reset the running program back to the raw REPL to
            # hand it a known-clean state - exactly like Thonny does on
            # purpose, except here it happens even though this app never
            # asked for a REPL and just wants to talk to main.py's own
            # command loop. Dropping DTR (and RTS, for the same reason)
            # right after open avoids triggering that reset, so main.py
            # keeps running and answers PING/RUN/LOOP/STOP normally.
            try:
                ser.dtr = False
                ser.rts = False
            except Exception:
                pass
            self.ser = ser
            # Some MCU USB-CDC firmware needs a real moment to settle
            # right after the port opens (and can even reset on open) -
            # 0.3s was too tight for some boards, and a single PING with
            # no retry meant one slow first reply permanently failed the
            # connection. Give it more room to wake up.
            time.sleep(0.6)
            self.ser.reset_input_buffer()
            ok, _msg = self.ping(attempts=3)
            self.connected = ok
            if not ok:
                # BUG FIX: the port was opened successfully but the
                # handshake failed (e.g. slow board, wrong device on this
                # port) - previously self.ser was left assigned and OPEN
                # in this case, leaking the OS handle. Any later
                # connect/Detect MCU attempt on the same port then
                # failed with "Access is denied" because THIS app itself
                # still held it open. Always close on failure.
                self._close_ser()
            return self.connected
        except Exception:
            self.connected = False
            self._close_ser()
            return False

    def _close_ser(self):
        """Close self.ser (if open) and clear the reference. Swallows I/O
        errors - used from every failure/cleanup path so a half-open or
        already-broken handle never lingers and blocks a later attempt to
        reopen the same port ("Access is denied")."""
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass
        self.ser = None

    def adopt_connection(self, port, ser):
        """Adopt an already-open, already PING/READY-verified serial
        connection (from scan_for_mcu_port) instead of closing it and
        reopening a fresh one. Some MCU USB-CDC firmware does not
        reliably survive a close-then-immediate-reopen cycle (needs more
        settle time than is practical during a scan), which used to make
        "Detect MCU" find the port but the very next connect() attempt
        report Not Connected. Reusing the verified connection sidesteps
        that entirely."""
        self.disconnect()
        self.port = port
        self.ser = ser
        self.connected = True
        self.looping = False

    def disconnect(self):
        self._close_ser()
        self.connected = False
        self.looping = False

    def open_raw(self, port):
        """Open `port` WITHOUT the automatic PING/READY handshake, so the
        operator can do the handshake by hand from the MCU Console. The
        link only counts as connected once a manual PING gets READY (see
        send_raw). Returns (ok, message)."""
        if serial is None:
            return False, "pyserial is not installed"
        if not port:
            return False, "no port given"
        self.disconnect()
        try:
            ser = serial.Serial(port, MCU_BAUDRATE, timeout=MCU_SERIAL_TIMEOUT)
            try:
                ser.dtr = False
                ser.rts = False
            except Exception:
                pass
        except Exception as e:
            return False, f"cannot open {port}: {e}"
        self.port = port
        self.ser = ser
        return True, f"{port} opened (no handshake yet - send PING)"

    def send_raw(self, cmd, listen_s=1.0):
        """MCU Console: send one operator-typed line and collect every reply
        line that arrives within `listen_s` seconds (each one is also
        reported as RX via on_traffic). A manual PING answered with READY
        marks the link as connected. Returns (ok, replies, handshake_ok)."""
        if not self.ser or not self.ser.is_open:
            return False, ["MCU port is not open"], False
        if not self.lock.acquire(timeout=0.5):
            return False, ["MCU busy (another MCU command is running)"], False
        try:
            self._write_line(cmd)
            word = cmd.strip().upper()
            if word == "LOOP":
                self.looping = True
            elif word == "STOP":
                self.looping = False
            replies = []
            deadline = time.monotonic() + max(0.1, float(listen_s))
            while time.monotonic() < deadline:
                left = deadline - time.monotonic()
                line = self._read_line(timeout=min(0.2, max(0.05, left)))
                if line:
                    replies.append(line)
            handshake_ok = word == "PING" and MCU_PING_KEYWORD in replies
            if handshake_ok:
                self.connected = True
            return True, replies, handshake_ok
        except Exception as e:
            self.connected = False
            self._close_ser()
            return False, [f"error: {e}"], False
        finally:
            self.lock.release()

    def _write_line(self, cmd):
        if not self.ser or not self.ser.is_open:
            raise IOError("MCU port is not open")
        self.ser.write((cmd + "\n").encode())
        if self.on_traffic:
            try:
                self.on_traffic("TX", cmd)
            except Exception:
                pass

    def _read_line(self, timeout=None):
        if not self.ser or not self.ser.is_open:
            return ""
        old_to = self.ser.timeout
        try:
            if timeout is not None:
                self.ser.timeout = timeout
            line = self.ser.readline().decode(errors="ignore").strip()
        finally:
            try:
                self.ser.timeout = old_to
            except Exception:
                pass
        if line and self.on_traffic:
            try:
                self.on_traffic("RX", line)
            except Exception:
                pass
        return line

    def ping(self, attempts=1):
        """Send PING and check for the READY reply (see protocol above).
        Used both internally by connect() and as its own scheduleable MCU
        step command, so it acquires the lock like trigger()/stop_loop()
        - a scenario step may fire it while another MCU command from a
        previous step is technically still finishing up.

        attempts>1 retries the handshake a few times before giving up -
        useful right after opening the port, since some MCU USB-CDC
        firmware is slow to respond to the very first line it receives.
        Returns (ok: bool, message: str).
        """
        if not self.ser or not self.ser.is_open:
            return False, "MCU not connected"
        with self.lock:
            try:
                self.ser.reset_input_buffer()
                last = ""
                for _ in range(max(1, attempts)):
                    self._write_line("PING")
                    found, last = self._read_until(
                        MCU_PING_KEYWORD, MCU_REPLY_TIMEOUT_S)
                    if found:
                        return True, "READY"
                return False, f"no/unexpected reply ({last or 'timeout'})"
            except Exception as e:
                self.connected = False
                self._close_ser()
                return False, f"error: {e}"

    def _read_until(self, wanted, timeout):
        """Read lines until `wanted` arrives or `timeout` seconds pass.
        Debug/log lines from the firmware (see _is_mcu_noise) are skipped,
        so a firmware that prints '[1234] CMD: PING ...' before 'READY'
        (the Maxwell sketch with DEBUG_LOG 1) still handshakes correctly.
        Caller must hold self.lock. Returns (found, last_meaningful_line)."""
        deadline = time.monotonic() + timeout
        last = ""
        while time.monotonic() < deadline:
            left = max(0.05, deadline - time.monotonic())
            line = self._read_line(timeout=min(0.3, left))
            if not line:
                continue
            if line == wanted:
                return True, line
            if not _is_mcu_noise(line):
                last = line
        return False, last

    def info(self):
        """Ask the firmware to describe itself (INFO -> 'INFO key=val ...').
        Returns (ok, text). Older firmware without INFO answers ERR or
        nothing - that is reported as not ok, never as an error."""
        if not self.ser or not self.ser.is_open:
            return False, "MCU not connected"
        with self.lock:
            try:
                self.ser.reset_input_buffer()
                self._write_line("INFO")
                deadline = time.monotonic() + MCU_REPLY_TIMEOUT_S
                while time.monotonic() < deadline:
                    line = self._read_line(timeout=0.3)
                    if line.startswith("INFO"):
                        self.info_text = line
                        return True, line
                    if line == "ERR":
                        break
                return False, "firmware has no INFO command"
            except Exception as e:
                self.connected = False
                self._close_ser()
                return False, f"error: {e}"

    def select_profile(self, name):
        """Select the pattern profile on a multi-profile firmware
        (SEL:<name> -> OK / ERR). Returns (ok, message)."""
        name = (name or "").strip()
        if not name:
            return True, "no profile requested"
        if not self.ser or not self.ser.is_open:
            return False, "MCU not connected"
        with self.lock:
            try:
                self.ser.reset_input_buffer()
                self._write_line(f"SEL:{name}")
                deadline = time.monotonic() + MCU_REPLY_TIMEOUT_S
                last = ""
                while time.monotonic() < deadline:
                    line = self._read_line(timeout=0.3)
                    if line == "OK":
                        self.profile = name
                        return True, f"profile {name}"
                    if line == "ERR":
                        return False, (f"firmware rejected profile '{name}' "
                                       "(unknown name or a run is active)")
                    if line and not _is_mcu_noise(line):
                        last = line
                return False, (f"no answer to SEL:{name} "
                               f"({last or 'timeout'}) - firmware may not "
                               "support profiles")
            except Exception as e:
                self.connected = False
                self._close_ser()
                return False, f"error: {e}"

    def trigger(self, repeat=1, loop=False, wait_for_done=True,
                timeout=MCU_DONE_TIMEOUT_S):
        """Fire the RLE pattern on the MCU.

        loop=True         -> pattern repeats forever; returns immediately,
                              there is no DONE to wait for by design. Use
                              stop_loop() to end it.
        wait_for_done=True -> (non-loop only) block until the MCU sends
                              DONE, or `timeout` seconds elapse.
        Returns (ok: bool, message: str).

        SAFETY CHECK (pre-flight PING): a bare serial write() succeeding
        only proves the OS handed the bytes to the port - it does NOT
        prove mcu_pattern_listener.py's main() loop is the thing
        reading them. If the MCU is sitting at a raw MicroPython REPL
        instead (e.g. left there after a manual Thonny session, or
        after main.py crashed), "LOOP"/"RUN:n" just get typed at the
        REPL as bare identifiers, throw a NameError there, and nothing
        actually plays - yet the old code still reported "started"
        because the write() itself never raised. To catch this before
        it wastes a scenario run, do one quick PING->READY round trip
        first and fail loudly (instead of lying) if it doesn't answer.
        """
        if not self.ser or not self.ser.is_open:
            return False, "MCU not connected"
        with self.lock:
            try:
                self.ser.reset_input_buffer()

                # Pre-flight handshake - inline (not self.ping()) so we
                # don't try to re-acquire self.lock, which would
                # deadlock (threading.Lock is not reentrant).
                self._write_line("PING")
                found, reply = self._read_until(
                    MCU_PING_KEYWORD, MCU_REPLY_TIMEOUT_S)
                if not found:
                    return False, (
                        "MCU not responding to PING before "
                        f"{'LOOP' if loop else 'RUN'} "
                        f"(got {reply or 'timeout'!r}) - it may be sitting "
                        "at a raw REPL instead of running the firmware, or "
                        "it is still busy with a previous run. "
                        "Reset the MCU (unplug/replug) with no other "
                        "program holding its serial port, then try again.")
                self.ser.reset_input_buffer()

                if loop:
                    self._write_line("LOOP")
                    self.looping = True
                    # Newer firmware answers LOOPING; older ones say nothing.
                    # Either way, do not fail - just consume a quick reply.
                    self._read_line(timeout=0.15)
                    return True, "loop started"

                self._write_line(f"RUN:{max(1, int(repeat))}")
                if not wait_for_done:
                    return True, "fired (not waiting for DONE)"

                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    remaining = max(0.05, deadline - time.monotonic())
                    line = self._read_line(timeout=min(0.3, remaining))
                    if line == MCU_DONE_KEYWORD:
                        return True, "done"
                    if line in ("ERR", "BUSY"):
                        return False, (f"firmware refused RUN ({line}) - "
                                       "another run may still be active")
                    if self.abort_check is not None:
                        try:
                            aborted = bool(self.abort_check())
                        except Exception:
                            aborted = False
                        if aborted:
                            try:
                                self._write_line("STOP")
                            except Exception:
                                pass
                            self.looping = False
                            return False, "aborted by STOP/EMERGENCY"
                    # Any other line (e.g. progress/echo) is ignored here;
                    # keep waiting for the real DONE until the deadline.
                return False, f"timeout waiting for DONE ({timeout:.0f}s)"
            except Exception as e:
                self.connected = False
                self._close_ser()
                return False, f"error: {e}"

    def stop_loop(self):
        """Abort an active LOOP. Safe to call even if not looping / not
        connected -- used as a blanket safety hook from STOP/EMERGENCY."""
        if not self.ser or not self.ser.is_open:
            return False
        # v22 FREEZE FIX: trigger() holds self.lock for the whole time it
        # waits for DONE (up to MCU_DONE_TIMEOUT_S). EMERGENCY OFF calls this
        # from the GUI thread, so waiting for the lock here froze the whole
        # window for up to two minutes. STOP must never wait: try the lock
        # briefly, and if a run still owns it, write STOP anyway (a single
        # short serial write is safe to interleave).
        got = self.lock.acquire(timeout=0.2)
        try:
            self._write_line("STOP")
            self.looping = False
            return True
        except Exception:
            self.connected = False
            self._close_ser()
            return False
        finally:
            if got:
                self.lock.release()


def _probe_port_mcu(port, log=None):
    """Open one serial port and try the MCU's PING/READY handshake (its
    own tiny text protocol, not SCPI, and its own baud rate).

    Returns an already-open serial.Serial on success (caller owns it now -
    either adopt it via MCUTrigger.adopt_connection(), or close it) so
    the real connection doesn't need a separate close+reopen cycle right
    after the scan - some MCU USB-CDC firmware does not reliably survive
    that (needs more settle time than is practical during a quick scan).
    Returns None if this port isn't the pattern-listener MCU (closed
    before returning). Raises on I/O error (port busy / doesn't exist).

    `log`, if given, is called with each attempt's raw reply (or lack of
    one) - this is the key diagnostic for telling apart "wrong/unrelated
    device on this port" (empty reply every time) from "right device but
    protocol mismatch" (some other text/garbage comes back)."""
    ser = serial.Serial(port, MCU_BAUDRATE, timeout=MCU_SCAN_TIMEOUT)
    # FIX: same DTR/RTS-on-open issue as MCUTrigger.connect() - drop
    # both immediately so opening the port during a scan doesn't itself
    # trigger a MicroPython soft-reset back to the raw REPL.
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    try:
        time.sleep(0.5)
        ser.reset_input_buffer()
        # A couple of retries tolerates a slow first reply / stray
        # boot-time output before the real READY line. Debug lines
        # (e.g. '[1234] CMD: PING ...') are skipped, not mistaken for a
        # wrong device - read lines until READY or the attempt times out.
        for attempt in range(3):
            ser.write(b"PING\n")
            reply = ""
            end = time.monotonic() + MCU_SCAN_TIMEOUT
            while time.monotonic() < end:
                line = ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue
                if line == MCU_PING_KEYWORD:
                    return ser
                if not _is_mcu_noise(line):
                    reply = line
            if log:
                log(f"MCU Detect: {port} -> attempt {attempt + 1}/3: "
                    f"{'no reply (timeout)' if not reply else f'got {reply!r}'}")
        ser.close()
        return None
    except Exception:
        try:
            ser.close()
        except Exception:
            pass
        raise


def scan_for_mcu_port(exclude_ports=(), log=None):
    """Scan every serial port not already claimed by a PSU and identify
    the pattern-listener MCU via its PING -> READY handshake.

    Returns (port, ser): ser is the already-open, already-verified
    connection ready to hand straight to MCUTrigger.adopt_connection()
    (see _probe_port_mcu for why). Returns (None, None) if not found."""
    if serial is None or serial_list_ports is None:
        return None, None

    for info in serial_list_ports.comports():
        port = info.device
        if port in exclude_ports:
            continue
        if log:
            log(f"MCU Detect: probing {port}...")
        try:
            ser = _probe_port_mcu(port, log=log)
        except Exception as e:
            if log:
                log(f"MCU Detect: {port} -> could not open/query ({e})")
            continue

        if ser is not None:
            if log:
                log(f"MCU Detect: {port} -> found pattern listener")
            return port, ser
        if log:
            log(f"MCU Detect: {port} -> no READY reply (not the MCU)")

    if log:
        log("MCU Detect: no pattern-listener MCU found on any serial port.")
    return None, None


def _probe_port_idn(port):
    """Open one serial port and try *IDN? with a couple of line-ending/retry
    variants (some PSU firmware/USB-serial combos are picky about
    \\r\\n vs \\n and need the link to warm up before the first reply).
    Returns the raw reply string (possibly empty) or raises on I/O error.
    """
    ser = serial.Serial(port, BAUDRATE, timeout=SCAN_TIMEOUT)
    try:
        time.sleep(0.3)
        ser.reset_input_buffer()
        for terminator in (b"\r\n", b"\n"):
            ser.write(b"*IDN?" + terminator)
            idn = ser.readline().decode(errors="ignore").strip()
            if idn:
                return idn
            time.sleep(0.2)
        return ""
    finally:
        ser.close()


def scan_for_psu_ports(log=None):
    """
    Scan every serial port visible to the OS and identify supported PSU
    units via *IDN?. Works on Windows (COMx) and Linux (/dev/ttyACMx).

    If `log` is given, every probed port is reported with its reply/error.

    Returns a list of (port_name, idn_string) sorted by serial number so
    PSU-slot assignment stays stable across runs.
    """
    found = []
    if serial is None or serial_list_ports is None:
        return found

    ports = list(serial_list_ports.comports())
    if log:
        if ports:
            log(f"Auto-Detect: {len(ports)} serial port(s) visible: " +
                ", ".join(f"{p.device} ({p.description})" for p in ports))
        else:
            log("Auto-Detect: no serial ports visible "
                "(check Device Manager / USB cable / drivers).")

    for info in ports:
        port = info.device
        if log:
            log(f"Auto-Detect: probing {port}...")
        try:
            idn = _probe_port_idn(port)
        except Exception as e:
            if log:
                log(f"Auto-Detect: {port} -> could not open/query ({e})")
            continue

        if not idn:
            if log:
                log(f"Auto-Detect: {port} -> no reply to *IDN? "
                    "(not a supported PSU, or in use elsewhere)")
            continue

        if log:
            log(f"Auto-Detect: {port} -> reply: {idn!r}")
        if any(kw in idn.upper() for kw in PSU_IDN_KEYWORDS):
            found.append((port, idn))

    def sort_key(item):
        parts = item[1].split(",")
        return parts[2].strip() if len(parts) > 2 else item[0]

    found.sort(key=sort_key)
    return found


# ==============================================================================
# GRAPH CANVAS (lightweight, Tkinter Canvas based)
# ==============================================================================
class GraphCanvas(tk.Canvas):
    # v23: time span shown by every graph; widened with long reading
    # intervals so there are always enough points to draw a line.
    window_sec = GRAPH_WINDOW_SEC

    def __init__(self, master, title, unit, **kwargs):
        super().__init__(master, bg="white", highlightthickness=1,
                          highlightbackground="#999999", **kwargs)
        self.title_text = title
        self.unit = unit
        self.series = {}   # key -> deque[(t, value)]
        self.colors = {}
        # key -> display label shown in the legend. Defaults to the key
        # itself, but is kept in sync with the Live Current/Voltage
        # Monitor's PSU/CH label (see App._monitor_label_for /
        # App._sync_graph_labels) so the same PSU/CH is called the same
        # thing everywhere: Monitor table, Live Graph legend, Live Log.
        self.labels = {}
        self.dark = False
        self.axis_color = "#333333"
        self.text_color = "#000000"
        self._after_id = None
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Map>", lambda e: self._draw())
        self._after_id = self.after(GRAPH_REFRESH_MS, self._tick)

    def set_theme(self, dark):
        """Switch the graph's own background/axis/text colors for Dark
        Mode. Per-PSU series colors (PSU_COLORS/PSU_COLORS_CH2) are left
        unchanged since they need to stay distinguishable from each other,
        not from the background."""
        self.dark = dark
        if dark:
            self.configure(bg="#242424", highlightbackground="#555555")
            self.axis_color = "#cccccc"
            self.text_color = "#e0e0e0"
        else:
            self.configure(bg="white", highlightbackground="#999999")
            self.axis_color = "#333333"
            self.text_color = "#000000"
        self._draw()

    def stop(self):
        """Cancel the recurring redraw job before the window is destroyed."""
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def add_series(self, key, color):
        if key not in self.series:
            self.series[key] = deque()
            self.colors[key] = color

    def set_label(self, key, label):
        """Update the legend text shown for `key` (a stable "PSUx-CHy"
        series id). Cheap no-op if unchanged, called on every reading so
        an operator-entered step Name change is picked up promptly."""
        if label and self.labels.get(key) != label:
            self.labels[key] = label

    def push(self, key, t, value):
        if key not in self.series or value is None:
            return
        dq = self.series[key]
        dq.append((t, value))
        cutoff = t - GraphCanvas.window_sec
        while dq and dq[0][0] < cutoff:
            dq.popleft()

    def _tick(self):
        # v23: no redraw while the graph is not on screen (other tab,
        # minimised); <Map> redraws it as soon as it becomes visible again.
        try:
            if self.winfo_viewable():
                self._draw()
        except tk.TclError:
            return
        self._after_id = self.after(GRAPH_REFRESH_MS, self._tick)

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20 or h < 20:
            return
        m_l, m_r, m_t, m_b = 45, 10, 16, 18
        plot_w, plot_h = max(w - m_l - m_r, 10), max(h - m_t - m_b, 10)

        now = time.time()
        t_min, t_max = now - GraphCanvas.window_sec, now

        all_vals = [v for dq in self.series.values() for (_, v) in dq]
        v_max = max(all_vals) * 1.15 if all_vals else 1.0
        v_max = max(v_max, 0.1)

        self.create_line(m_l, m_t, m_l, m_t + plot_h, fill=self.axis_color)
        self.create_line(m_l, m_t + plot_h, m_l + plot_w, m_t + plot_h, fill=self.axis_color)
        self.create_text(m_l - 5, m_t, text=f"{v_max:.2f}{self.unit}", anchor="ne",
                          font=("Arial", 7), fill=self.text_color)
        self.create_text(m_l - 5, m_t + plot_h, text="0", anchor="se",
                          font=("Arial", 7), fill=self.text_color)
        self.create_text(6, 4, text=self.title_text, anchor="nw",
                          font=("Arial", 8, "bold"), fill=self.text_color)

        def to_xy(t, v):
            x = m_l + (t - t_min) / (t_max - t_min) * plot_w
            y = m_t + plot_h - (v / v_max) * plot_h
            return x, y

        lx, ly = m_l + plot_w - 88, m_t + 2
        for key, dq in self.series.items():
            color = self.colors[key]
            if len(dq) >= 2:
                pts = list(dq)
                step = max(1, len(pts) // max(int(plot_w), 1))
                pts = pts[::step]
                coords = []
                for (t, v) in pts:
                    if t < t_min:
                        continue
                    x, y = to_xy(t, v)
                    coords.extend([x, y])
                if len(coords) >= 4:
                    # Dashed line for CH2 so it is easy to tell channels apart.
                    dash = (3, 2) if "-CH2" in key else ()
                    self.create_line(*coords, fill=color, width=1.5, dash=dash)
            # Only list a series in the legend once it actually has data -
            # avoids a cluttered/overflowing legend when most PSUs/channels
            # are not connected or unused (up to 16 possible CH1+CH2 series).
            if dq:
                self.create_line(lx, ly + 4, lx + 12, ly + 4, fill=color, width=2)
                self.create_text(lx + 15, ly, text=self.labels.get(key, key), anchor="nw",
                                  font=("Arial", 7), fill=self.text_color)
                ly += 11


# ==============================================================================
# MINIMAL HOVER TOOLTIP
#   Used to explain WHY a widget is disabled (e.g. a PSU/Channel "On"
#   checkbox in Operation Mode that is locked out because that same
#   PSU/Channel is already driven by the Power-Up/Power-Down scenario -
#   see _refresh_ch_enable_availability). text_fn is called fresh on every
#   hover so the note can change as state changes (e.g. once no longer
#   locked, hovering shows nothing).
# ==============================================================================
class _HoverTooltip:
    def __init__(self, widget, text_fn):
        self.widget = widget
        self.text_fn = text_fn
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _show(self, _event=None):
        text = (self.text_fn() or "").strip()
        if not text:
            return
        self._hide()
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry(f"+{x}+{y}")
            ttk.Label(self.tip, text=text, background="#ffffe0",
                      relief="solid", borderwidth=1, font=("Arial", 8),
                      padding=(4, 2)).pack()
        except tk.TclError:
            self.tip = None

    def _hide(self, _event=None):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


# ==============================================================================
# EDGE DRAGGING (v20) - shared by the Cycle timeline and the Symbol/Step
# Editor timeline. A canvas using it fills self._handle_px with
# (x, y, key, time, row_index) in _draw() and sets self.edit_cb(key,
# delta_seconds, phase) with phase 'begin' / 'move' / 'end'. The time axis
# is frozen while dragging so the edge stays under the pointer even though
# the pattern (and its auto-scaled window) changes on every move.
# ==============================================================================
class _EdgeDragMixin:
    HANDLE_R = 4
    HIT_PX = 8

    def _init_drag_state(self):
        self.edit_cb = None
        self._handle_px = []
        self._geom = None
        self._drag = None

    def _bind_drag(self):
        self.bind("<Motion>", self._on_motion)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Leave>", lambda e: self._on_hover(None))

    # ---- hooks (override as needed) --------------------------------------
    def _drag_window(self):
        return self.window

    def _edge_snap(self, t, drag, event):
        return t

    def _on_hover(self, hit):
        pass

    # ---- hit testing -----------------------------------------------------
    def _hit_handles(self, event):
        """All handles under the pointer, nearest first (several can sit on
        the same spot, e.g. 'end of ON' and 'next rising edge' when OFF=0)."""
        if not self._handle_px or self.edit_cb is None:
            return []
        cx, cy = self.canvasx(event.x), self.canvasy(event.y)
        hits = []
        for h in self._handle_px:
            d = max(abs(cx - h[0]), abs(cy - h[1]) * 0.6)
            if d <= self.HIT_PX:
                hits.append((d, h))
        hits.sort(key=lambda dh: dh[0])
        if not hits:
            return []
        near = hits[0][0] + 1.0
        return [h for d, h in hits if d <= near]

    def _hit_handle(self, event):
        hits = self._hit_handles(event)
        return hits[0] if hits else None

    def _on_motion(self, event):
        if self._drag is not None:
            return
        hit = self._hit_handle(event)
        try:
            self.configure(cursor="sb_h_double_arrow" if hit else "")
        except Exception:
            pass
        self._on_hover(hit)

    def _snap_step(self):
        """~3 px worth of time, rounded up to 1/2/5 x 10^n (never finer than
        1 ms) so dragging lands on tidy values."""
        if not self._geom:
            return 0.001
        _m_l, plot_w, t_total = self._geom
        raw = max(t_total / max(plot_w, 1) * 3.0, 0.001)
        step = 10 ** math.floor(math.log10(raw))
        for mult in (1, 2, 5, 10):
            if step * mult >= raw:
                return max(step * mult, 0.001)
        return max(step * 10, 0.001)

    # ---- press / drag / release -----------------------------------------
    def _on_press(self, event):
        try:
            self.focus_set()
        except Exception:
            pass
        hits = self._hit_handles(event)
        if not hits or not self._geom:
            return
        self._drag = {"cands": hits, "key": None, "t0": 0.0, "row": None,
                      "window": self._drag_window(),
                      "step": self._snap_step(), "last": 0.0,
                      "x0": self.canvasx(event.x)}
        if len(hits) == 1:
            self._begin_drag(hits[0])

    def _begin_drag(self, hit):
        d = self._drag
        d["key"], d["t0"] = hit[2], hit[3]
        d["row"] = hit[4] if len(hit) > 4 else None
        d["cands"] = None
        self.edit_cb(d["key"], 0.0, "begin")
        self._on_hover(hit)
        self._draw()

    def _on_drag(self, event):
        d = self._drag
        if d is None or not self._geom:
            return
        if d["key"] is None:
            # Overlapping handles: decide by the first real movement -
            # left grabs the earlier edge, right the later one.
            dx = self.canvasx(event.x) - d["x0"]
            if abs(dx) < 2:
                return
            cands = d["cands"]
            self._begin_drag(cands[0] if dx < 0 else cands[-1])
        m_l, plot_w, t_total = self._geom
        t = (self.canvasx(event.x) - m_l) / max(plot_w, 1) * t_total
        t = min(max(t, 0.0), d["window"])
        delta = round((t - d["t0"]) / d["step"]) * d["step"]
        t_snapped = self._edge_snap(d["t0"] + delta, d, event)
        delta = round(t_snapped - d["t0"], 6)
        if delta == d["last"]:
            return
        d["last"] = delta
        self.edit_cb(d["key"], delta, "move")

    def _on_release(self, event):
        d = self._drag
        if d is None:
            return
        self._drag = None
        if d["key"] is None:      # click without moving
            return
        self.edit_cb(d["key"], d["last"], "end")
        self._on_hover(None)
        self._draw()


# ==============================================================================
# SCENARIO SYMBOL/STEP PREVIEW (lightweight, Tkinter Canvas based)
#   Each step's "wait" is an ABSOLUTE time from scenario start (t=0).
# ==============================================================================
class ScenarioPreviewCanvas(_EdgeDragMixin, tk.Canvas):
    ROW_H = 20
    VISIBLE_ROWS = 8
    ZOOM_MIN = 1.0
    ZOOM_MAX = 20.0
    ZOOM_STEP = 1.25

    def __init__(self, master, **kwargs):
        super().__init__(master, bg="white", highlightthickness=1,
                          highlightbackground="#999999", **kwargs)
        self.steps = []
        self.kind = "powerup"
        self.rows = []
        self.dark = False
        self.zoom_x = 1.0
        self._init_drag_state()
        self._tl_handles = {}     # (psu, ch) / ("MCU", lbl) -> [(t, key)]
        self._edges = {}          # row index -> [(t, rising)]
        self._init_states = {}    # row index -> bool
        self._real_t_total = 0.1
        self._guide = None        # {"key": ..., "row": ...} while hovering/dragging
        self.grid_color = "#eeeeee"
        self.text_color = "#888888"
        self.baseline_color = "#dddddd"
        self.empty_color = "#999999"
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        self.bind("<Control-Button-4>", lambda e: self._zoom(self.ZOOM_STEP))
        self.bind("<Control-Button-5>", lambda e: self._zoom(1.0 / self.ZOOM_STEP))
        self._bind_drag()

    def _zoom(self, factor):
        new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self.zoom_x * factor))
        if new_zoom != self.zoom_x:
            self.zoom_x = new_zoom
            self._draw()

    def reset_zoom(self):
        self.zoom_x = 1.0
        self._draw()

    def _on_ctrl_wheel(self, event):
        if event.delta > 0:
            self._zoom(self.ZOOM_STEP)
        else:
            self._zoom(1.0 / self.ZOOM_STEP)

    def set_theme(self, dark):
        self.dark = dark
        if dark:
            self.configure(bg="#242424", highlightbackground="#555555")
            self.grid_color = "#3a3a3a"
            self.text_color = "#aaaaaa"
            self.baseline_color = "#444444"
            self.empty_color = "#777777"
        else:
            self.configure(bg="white", highlightbackground="#999999")
            self.grid_color = "#eeeeee"
            self.text_color = "#888888"
            self.baseline_color = "#dddddd"
            self.empty_color = "#999999"
        self._draw()

    def set_steps(self, steps, kind="powerup"):
        self.steps = steps
        self.kind = kind
        # Row order follows the order each (PSU, Channel) combination FIRST
        # appears in the step list (not a fixed PSU/CH sort) - so moving a
        # step up/down with the Scenario Editor's Up/Down buttons visibly
        # reorders this preview's rows to match, instead of always
        # snapping back to a fixed PSU/CH order.
        psu_rows = []
        seen = set()
        for s in steps:
            psu, ch = s.get("psu"), s.get("ch")
            if psu is None or ch is None:
                continue
            rc = (psu, ch)
            if rc not in seen:
                seen.add(rc)
                psu_rows.append(rc)
        # MCU steps have no PSU/Channel of their own; instead they get their
        # own row per distinct manually-entered signal name (see
        # ScenarioStepDialog's "MCU Signals" field), so the operator can see
        # which signal each MCU trigger corresponds to right in this
        # preview. Steps left blank fall back to a single generic "MCU" row.
        mcu_labels = sorted({(s.get("mcu_signals") or "").strip() or "MCU"
                               for s in steps if s.get("action") == "MCU"})
        mcu_rows = [("MCU", lbl) for lbl in mcu_labels]
        self.rows = psu_rows + mcu_rows
        self._draw()
        try:
            if self.winfo_width() < 20:
                self.after_idle(self._draw)
        except Exception:
            pass

    @staticmethod
    def _is_mcu_row(rc):
        return isinstance(rc[0], str)

    def _row_label(self, rc):
        if self._is_mcu_row(rc):
            return rc[1]
        psu, ch = rc
        # A manually-entered "Function Name" (ScenarioStepDialog) overrides
        # the generic "PSUx-CHx" label for every row that shares this
        # PSU/Channel - the first non-empty name found for it wins.
        for s in self.steps:
            if s.get("psu") == psu and s.get("ch") == ch:
                name = (s.get("name") or "").strip()
                if name:
                    return name
        return f"PSU{psu}-CH{ch}"

    def _build_timeline(self):
        # Power-Up starts OFF; Power-Down starts ON (user only schedules OFF).
        initial_state = self.kind == "powerdown"
        row_events = {rc: [] for rc in self.rows if not self._is_mcu_row(rc)}
        mcu_pulses = {rc: [] for rc in self.rows if self._is_mcu_row(rc)}
        self._tl_handles = {rc: [] for rc in self.rows}
        t_total = 0.1
        for s_idx, step in enumerate(self.steps):
            try:
                t = float(step.get("wait", 0.0))
            except (TypeError, ValueError):
                t = 0.0
            t_total = max(t_total, t)

            if step.get("action") == "MCU":
                lbl = (step.get("mcu_signals") or "").strip() or "MCU"
                rc = ("MCU", lbl)
                if rc in mcu_pulses:
                    mcu_pulses[rc].append((t, _mcu_step_cmd(step)))
                    self._tl_handles[rc].append((t, ("wait", s_idx)))
                continue

            rc = (step.get("psu"), step.get("ch"))
            if rc not in row_events:
                continue

            if step.get("action") == "CYCLE":
                # Repeating ON/OFF pulses starting at this step's offset -
                # see CYCLE_PREVIEW_REPS for how an unbounded ("until
                # stopped") step is drawn.
                on_t = max(_safe_float(step.get("cycle_on", 1.0)), 0.0)
                off_t = max(_safe_float(step.get("cycle_off", 1.0)), 0.0)
                raw_count = _safe_float(step.get("cycle_count", 0))
                count = (int(raw_count)
                         if math.isfinite(raw_count) and raw_count > 0 else 0)
                raw_duration = step.get("cycle_duration")
                if raw_duration is not None:
                    cycle_duration = _safe_float(raw_duration)
                    if not math.isfinite(cycle_duration):
                        cycle_duration = 0.0
                    cycle_duration = max(cycle_duration, 0.0)
                    t_end = cycle_duration
                    period = on_t + off_t
                    active_duration = max(t_end - t, 0.0)
                    n_pulses = (
                        min(int(math.ceil(active_duration / period)), 10000)
                        if period > 0 else 0)
                    if count > 0:
                        n_pulses = min(n_pulses, count)
                    truncated = n_pulses > CYCLE_PREVIEW_MAX_PULSES
                    n_pulses = min(n_pulses, CYCLE_PREVIEW_MAX_PULSES)
                    if not truncated:
                        t_total = max(t_total, t_end)
                else:
                    t_end = None
                    truncated = count > CYCLE_PREVIEW_MAX_PULSES
                    n_pulses = (min(count, CYCLE_PREVIEW_MAX_PULSES)
                                if count > 0 else CYCLE_PREVIEW_REPS)
                t_cur = t
                for p_i in range(max(n_pulses, 0)):
                    if t_end is not None and t_cur >= t_end:
                        break
                    row_events[rc].append((t_cur, True))
                    on_end = t_cur + on_t
                    if t_end is not None:
                        on_end = min(on_end, t_end)
                    row_events[rc].append((on_end, False))
                    if p_i == 0:
                        self._tl_handles[rc].append((t_cur, ("wait", s_idx)))
                        self._tl_handles[rc].append(
                            (on_end, ("cycle_on", s_idx)))
                    elif p_i == 1:
                        self._tl_handles[rc].append(
                            (t_cur, ("cycle_off", s_idx)))
                    t_cur = on_end + off_t
                t_total = max(
                    t_total,
                    t_end if (t_end is not None and not truncated) else t_cur)
                continue

            new_state = step.get("action") == "ON"
            row_events[rc].append((t, new_state))
            self._tl_handles[rc].append((t, ("wait", s_idx)))

        timeline = {}
        for rc, evs in row_events.items():
            evs = sorted(evs, key=lambda e: e[0])
            pts = [(0.0, initial_state)]
            state = initial_state
            for (t, new_state) in evs:
                pts.append((t, state))
                pts.append((t, new_state))
                state = new_state
            pts.append((t_total, state))
            timeline[rc] = pts

        # MCU rows have no ON/OFF state of their own - draw each command
        # as a mark at the moment it fires: RUN/PING are a short pulse,
        # LOOP goes high and stays high until STOP (or the timeline ends),
        # STOP drops it back low immediately. Every scheduled command is
        # processed in order (no early exit on LOOP), so a STOP after a
        # LOOP still shows up correctly.
        pulse_w = max(t_total * 0.01, 0.005)
        for rc, pulses in mcu_pulses.items():
            pts = [(0.0, False)]
            state = False
            for (t, cmd) in sorted(pulses, key=lambda e: e[0]):
                pts.append((t, state))
                if cmd == "STOP":
                    pts.append((t, False))
                    state = False
                elif cmd == "LOOP":
                    pts.append((t, True))
                    state = True
                else:  # RUN or PING -> short pulse
                    pts.append((t, True))
                    end_t = min(t + pulse_w, t_total)
                    pts.append((end_t, True))
                    pts.append((end_t, False))
                    state = False
            pts.append((t_total, state))
            timeline[rc] = pts

        return timeline, t_total

    def _drag_window(self):
        # Freeze exactly the axis that is on screen right now (no jump when
        # the drag starts). The editable view always draws 15% headroom
        # after the last event so that edge can be dragged further right.
        if self._geom:
            return self._geom[2]
        return max(self._real_t_total * 1.15, self._real_t_total + 0.1)

    # ---- alignment guide (v20) -------------------------------------------
    def _on_hover(self, hit):
        new = (None if hit is None
               else {"key": hit[2], "row": hit[4] if len(hit) > 4 else None})
        if new != self._guide:
            self._guide = new
            self.delete("guide")
            self._draw_guide()

    def _edge_snap(self, t, drag, event):
        """Snap the dragged edge onto another signal's edge when within a
        few pixels (hold Shift to move freely)."""
        if (getattr(event, "state", 0) & 0x0001) or not self._geom:
            return t
        _m_l, plot_w, t_total = self._geom
        tol = 6.0 * t_total / max(plot_w, 1)
        best, best_d = t, tol
        for ri, edges in self._edges.items():
            if ri == drag.get("row"):
                continue
            for (te, _r) in edges:
                if abs(te - t) <= best_d:
                    best, best_d = te, abs(te - t)
        return best

    def _draw_guide(self):
        g = self._guide
        if not g or not self._geom or not self.edit_cb:
            return
        m_l, plot_w, t_total = self._geom
        t = None
        for (x, y, key, th, ri) in self._handle_px:
            if key == g["key"]:
                t = th
                break
        if t is None:
            return
        row_h = self.ROW_H
        m_t = self._m_t
        n_rows = len(self.rows)
        x_g = m_l + t / t_total * plot_w
        bottom = m_t + row_h * n_rows
        try:
            right = max(int(self.winfo_width()), m_l + plot_w + 10)
        except Exception:
            right = m_l + plot_w + 10
        accent = "#ff8c00"
        good = "#5ddc7a" if self.dark else "#17883a"
        box_bg = "#333333" if self.dark else "#fffbe6"
        fg = "#ffffff" if self.dark else "#000000"
        tol = max(0.5 * t_total / max(plot_w, 1), 1e-6)
        up, dn = "\u2191", "\u2193"

        def label(x, y, text, color, anchor_left, bold=False):
            tid = self.create_text(
                x, y, text=text, anchor="w" if anchor_left else "e",
                font=("Arial", 8, "bold" if bold else "normal"),
                fill=color, tags="guide")
            bb = self.bbox(tid)
            if bb:
                rid = self.create_rectangle(
                    bb[0] - 2, bb[1] - 1, bb[2] + 2, bb[3] + 1,
                    fill=box_bg, outline=color, tags="guide")
                self.tag_lower(rid, tid)

        self.create_line(x_g, m_t - 14, x_g, bottom, fill=accent, width=1,
                         dash=(4, 3), tags="guide")

        # Header: what is being edited + its absolute time.
        what = g["key"][0]
        idx = g["key"][1]
        step = self.steps[idx] if idx < len(self.steps) else {}
        act = step.get("action", "")
        what_txt = {"cycle_on": "ON ends", "cycle_off": "next ON starts"}.get(
            what, {"ON": "ON at", "OFF": "OFF at", "CYCLE": "cycle starts",
                   "MCU": "MCU fires"}.get(act, "edge at"))
        row_lbl = (self._row_label(self.rows[g["row"]])
                   if g.get("row") is not None and g["row"] < len(self.rows)
                   else "")
        head_left = x_g < (right - 260)
        label(x_g + 6 if head_left else x_g - 6, m_t - 8,
              f"{row_lbl}: {what_txt} {t:.3f} s", accent, head_left, True)

        # What every OTHER signal is doing at that exact moment.
        for ri in range(n_rows):
            if ri == g.get("row"):
                continue
            edges = self._edges.get(ri, [])
            state = self._init_states.get(ri, False)
            prev_e = next_e = None
            for (te, rising) in edges:
                if te <= t + tol:
                    prev_e = (te, rising)
                    state = rising
                elif next_e is None:
                    next_e = (te, rising)
            y_mid = m_t + ri * row_h + row_h / 2
            aligned = prev_e is not None and abs(prev_e[0] - t) <= tol
            if not aligned and next_e is not None and abs(next_e[0] - t) <= tol:
                aligned, prev_e = True, next_e
            rc = self.rows[ri]
            color = (MCU_ROW_COLOR if self._is_mcu_row(rc)
                     else PSU_COLORS.get(rc[0], "#333333"))
            r = 4
            if aligned:
                self.create_oval(x_g - r - 2, y_mid - r - 2, x_g + r + 2,
                                 y_mid + r + 2, outline=good, width=2,
                                 tags="guide")
                txt = (f"= {up if prev_e[1] else dn} "
                       f"{prev_e[0]:.3f} s  ALIGNED")
                lcolor = good
            else:
                self.create_oval(x_g - 3, y_mid - 3, x_g + 3, y_mid + 3,
                                 fill=color if state else box_bg,
                                 outline=color, tags="guide")
                parts = ["ON" if state else "OFF"]
                if prev_e is not None:
                    parts.append(
                        f"prev {up if prev_e[1] else dn}"
                        f"{prev_e[0]:.3f} ({t - prev_e[0]:+.3f})")
                if next_e is not None:
                    parts.append(
                        f"next {up if next_e[1] else dn}"
                        f"{next_e[0]:.3f} ({next_e[0] - t:+.3f})")
                txt = "  |  ".join(parts)
                lcolor = fg
            label(x_g + 8 if head_left else x_g - 8, y_mid, txt, lcolor,
                  head_left)

    def _draw(self):
        self.delete("all")
        self._handle_px = []
        self._geom = None
        w = self.winfo_width()
        if w < 20:
            return

        if not self.rows:
            self.configure(scrollregion=(0, 0, w, 1))
            self.create_text(w / 2, 20, anchor="n", fill=self.empty_color,
                              font=("Arial", 9, "italic"),
                              text="No steps yet - add a step to see its ON/OFF timeline here.")
            return

        # Editable (fullscreen) view: extra headroom on top for the guide's
        # header text, wider label column.
        editable = self.edit_cb is not None
        m_l, m_r, m_t, m_b = (110 if editable else 70), 10, (24 if editable else 6), 20
        self._m_t = m_t
        row_h = self.ROW_H
        base_plot_w = max(w - m_l - m_r, 10)
        plot_w = int(base_plot_w * self.zoom_x)
        total_w = m_l + plot_w + m_r
        n_rows = len(self.rows)
        content_h = m_t + row_h * n_rows + m_b
        self.configure(scrollregion=(0, 0, max(total_w, w), content_h))

        timeline, t_total = self._build_timeline()
        self._real_t_total = t_total
        if editable:
            t_total = max(t_total * 1.15, t_total + 0.1)
        if self._drag is not None:
            t_total = max(self._drag["window"], t_total)
        self._geom = (m_l, plot_w, t_total)
        self._edges, self._init_states = {}, {}
        for i, rc in enumerate(self.rows):
            pts = timeline[rc]
            self._init_states[i] = pts[0][1]
            edges = []
            for k in range(1, len(pts)):
                if (pts[k][1] != pts[k - 1][1]
                        and abs(pts[k][0] - pts[k - 1][0]) < 1e-12):
                    edges.append((pts[k][0], pts[k][1]))
            self._edges[i] = edges

        # Adaptive grid: more gridlines when zoomed in, fewer for large windows.
        # Target ~50-100 px spacing; minimum spacing of 30px so labels don't crowd.
        ideal_px_per_line = 80
        ideal_n = max(4, int(plot_w / ideal_px_per_line))
        n_grid = min(ideal_n, 50)

        # Choose a time step that rounds nicely (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5 ...)
        raw_step = t_total / n_grid
        for nice in (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5,
                     1, 2, 5, 10, 20, 50, 100, 200, 500, 1000):
            if t_total / nice <= n_grid + 1:
                grid_step = nice
                break
        else:
            grid_step = raw_step

        # Decimal places for label: show enough to distinguish adjacent ticks
        if grid_step < 0.01:
            lbl_fmt = "{:.3f}s"
        elif grid_step < 0.1:
            lbl_fmt = "{:.2f}s"
        elif grid_step < 1:
            lbl_fmt = "{:.2f}s"
        else:
            lbl_fmt = "{:.1f}s"

        t_g = 0.0
        while t_g <= t_total + grid_step * 0.001:
            x = m_l + (t_g / t_total) * plot_w
            self.create_line(x, m_t - 2, x, m_t + row_h * n_rows, fill=self.grid_color)
            self.create_text(x, m_t + row_h * n_rows + 4, text=lbl_fmt.format(t_g),
                              anchor="n", font=("Arial", 6), fill=self.text_color)
            t_g = round(t_g + grid_step, 6)

        for i, rc in enumerate(self.rows):
            y0 = m_t + i * row_h
            y_low = y0 + row_h - 4
            y_high = y0 + 4
            if self._is_mcu_row(rc):
                color = MCU_ROW_COLOR
                dash = ()
            else:
                psu, ch = rc
                color = PSU_COLORS.get(psu, "#333333")
                dash = () if ch == 1 else (3, 2)
            self.create_line(m_l, y_low, m_l + plot_w, y_low, fill=self.baseline_color)
            self.create_text(4, y0 + row_h / 2, text=self._row_label(rc), anchor="w",
                              font=("Arial", 7), fill=color)

            coords = []
            for (pt, pon) in timeline[rc]:
                x = m_l + (pt / t_total) * plot_w
                y = y_high if pon else y_low
                coords.extend([x, y])
            if len(coords) >= 4:
                if editable:
                    coords.extend([m_l + plot_w, coords[-1]])
                self.create_line(*coords, fill=color, width=2, dash=dash)

            # Draggable edge handles (only when an edit callback is set).
            if self.edit_cb is not None:
                r = self.HANDLE_R
                y_mid = (y_low + y_high) / 2
                for (t_h, key) in self._tl_handles.get(rc, []):
                    if t_h < 0 or t_h > t_total:
                        continue
                    x_h = m_l + (t_h / t_total) * plot_w
                    active = (self._drag is not None
                              and self._drag["key"] == key)
                    self.create_oval(
                        x_h - r, y_mid - r, x_h + r, y_mid + r,
                        fill=("#ffcc00" if active else color),
                        outline=("#ffffff" if self.dark else "#000000"))
                    self._handle_px.append((x_h, y_mid, key, t_h, i))

        # Zoom indicator in top-right corner when zoomed in
        if self.zoom_x > 1.01:
            self.create_text(
                max(total_w, w) - 4, m_t, anchor="ne",
                text=f"🔍 {self.zoom_x:.1f}×  Ctrl+Scroll or ±  to zoom  |  R to reset",
                font=("Arial", 7), fill=self.text_color)

        self._draw_guide()


# ==============================================================================
# CYCLE TIMELINE PREVIEW (lightweight, Tkinter Canvas based)
#   Same visual idea as ScenarioPreviewCanvas above, but for the REPEATING
#   continuous cycle (Synchronous / Asynchronous mode, driven by the "PSU
#   Settings" table under Operation Mode) instead of a one-shot list of
#   absolute Power-Up/Power-Down steps. Each row repeats its own ON/OFF
#   pattern with its own period across a shared time window, so an operator
#   can visually verify the cycle they configured before pressing START.
# ==============================================================================
class CycleTimelineCanvas(_EdgeDragMixin, tk.Canvas):
    """ON/OFF timeline. v20: the first pulse's edges are draggable with the
    mouse (grab a dot on an edge): the app supplies, per row, a list of
    (time, key) "handles" via set_pattern(handles=...) and an edit_cb
    (key, delta_seconds, phase) with phase 'begin' / 'move' / 'end'. The
    canvas freezes its time axis while dragging so the edge stays under
    the pointer even though the pattern (and its auto-scaled window)
    changes with every move."""
    ROW_H = 20
    VISIBLE_ROWS = 8
    N_PERIODS = 2.5  # how many repeats to draw so the repetition is visible
    ZOOM_MIN = 1.0
    ZOOM_MAX = 20.0
    ZOOM_STEP = 1.25

    def __init__(self, master, **kwargs):
        super().__init__(master, bg="white", highlightthickness=1,
                          highlightbackground="#999999", **kwargs)
        # rows: list of (label, color, [(on_start, on_end), ...], dashed, period)
        self.rows = []
        self.window = 0.0
        self.note = ""
        self.dark = False
        self.zoom_x = 1.0
        self.m_l = 130            # left label margin (px)
        self.handles = []         # per row: [(time_s, key), ...]
        self._init_drag_state()
        self.grid_color = "#eeeeee"
        self.text_color = "#888888"
        self.baseline_color = "#dddddd"
        self.empty_color = "#999999"
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        self.bind("<Control-Button-4>", lambda e: self._zoom(self.ZOOM_STEP))
        self.bind("<Control-Button-5>", lambda e: self._zoom(1.0 / self.ZOOM_STEP))
        self._bind_drag()

    def _zoom(self, factor):
        new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self.zoom_x * factor))
        if new_zoom != self.zoom_x:
            self.zoom_x = new_zoom
            self._draw()

    def reset_zoom(self):
        self.zoom_x = 1.0
        self._draw()

    def _on_ctrl_wheel(self, event):
        if event.delta > 0:
            self._zoom(self.ZOOM_STEP)
        else:
            self._zoom(1.0 / self.ZOOM_STEP)

    def set_theme(self, dark):
        self.dark = dark
        if dark:
            self.configure(bg="#242424", highlightbackground="#555555")
            self.grid_color = "#3a3a3a"
            self.text_color = "#aaaaaa"
            self.baseline_color = "#444444"
            self.empty_color = "#777777"
        else:
            self.configure(bg="white", highlightbackground="#999999")
            self.grid_color = "#eeeeee"
            self.text_color = "#888888"
            self.baseline_color = "#dddddd"
            self.empty_color = "#999999"
        self._draw()

    def set_pattern(self, rows, window, note="", handles=None):
        self.rows = rows
        # Keep the time axis fixed while an edge is being dragged.
        self.window = self._drag["window"] if self._drag else window
        self.note = note
        self.handles = handles or []
        self._draw()
        # If the canvas is not yet mapped / sized (common right after opening
        # a fullscreen Toplevel), schedule a redraw once geometry is known.
        try:
            if self.winfo_width() < 20:
                self.after_idle(self._draw)
        except Exception:
            pass

    def _draw(self):
        self.delete("all")
        self._handle_px = []
        self._geom = None
        try:
            w = max(int(self.winfo_width()), 1)
            h = max(int(self.winfo_height()), 1)
        except Exception:
            return
        if w < 20:
            return

        if self.note:
            self.configure(scrollregion=(0, 0, w, max(h, 1)))
            self.create_text(w / 2, max(h // 2, 20), anchor="center",
                              fill=self.empty_color,
                              font=("Arial", 10, "italic"), width=w - 40,
                              justify="center", text=self.note)
            return

        if not self.rows or self.window <= 0:
            self.configure(scrollregion=(0, 0, w, max(h, 1)))
            self.create_text(w / 2, max(h // 2, 20), anchor="center",
                              fill=self.empty_color,
                              font=("Arial", 10, "italic"),
                              text="No ON/OFF pattern to preview yet.")
            return

        m_l, m_r, m_t, m_b = self.m_l, 10, 6, 20
        row_h = self.ROW_H
        base_plot_w = max(w - m_l - m_r, 10)
        plot_w = int(base_plot_w * self.zoom_x)
        total_w = m_l + plot_w + m_r
        n_rows = len(self.rows)
        content_h = m_t + row_h * n_rows + m_b
        # Use at least the widget height so a maximized fullscreen canvas
        # still fills the view (scrollregion drives scrollbar range).
        self.configure(scrollregion=(0, 0, max(total_w, w), max(content_h, h)))

        t_total = self.window
        if t_total <= 0:
            return
        self._geom = (m_l, plot_w, t_total)

        # Adaptive grid: target ~80px per gridline, cap at 50 lines.
        ideal_n = max(4, int(plot_w / 80))
        n_grid = min(ideal_n, 50)
        raw_step = t_total / n_grid
        for nice in (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5,
                     1, 2, 5, 10, 20, 50, 100, 200, 500, 1000):
            if t_total / nice <= n_grid + 1:
                grid_step = nice
                break
        else:
            grid_step = raw_step

        if grid_step < 0.01:
            lbl_fmt = "{:.3f}s"
        elif grid_step < 0.1:
            lbl_fmt = "{:.2f}s"
        elif grid_step < 1:
            lbl_fmt = "{:.2f}s"
        else:
            lbl_fmt = "{:.1f}s"

        t_g = 0.0
        while t_g <= t_total + grid_step * 0.001:
            x = m_l + (t_g / t_total) * plot_w
            self.create_line(x, m_t - 2, x, m_t + row_h * n_rows, fill=self.grid_color)
            self.create_text(x, m_t + row_h * n_rows + 4, text=lbl_fmt.format(t_g),
                              anchor="n", font=("Arial", 6), fill=self.text_color)
            t_g = round(t_g + grid_step, 6)

        for i, (label, color, intervals, dashed, period) in enumerate(self.rows):
            y0 = m_t + i * row_h
            y_low = y0 + row_h - 4
            y_high = y0 + 4
            self.create_line(m_l, y_low, m_l + plot_w, y_low, fill=self.baseline_color)
            self.create_text(4, y0 + row_h / 2, text=label, anchor="w",
                              font=("Arial", 7), fill=color)

            coords = [m_l, y_low]
            t = 0.0
            if period > 0:
                # Cap iterations so a near-zero period can't hang the GUI.
                # v20: also capped so a tiny period next to a long one cannot
                # generate millions of canvas segments and freeze the GUI.
                max_iters = min(int(t_total / period) + 3, 1000)
                iters = 0
                while t < t_total and iters < max_iters:
                    for (on_s, on_e) in intervals:
                        abs_s = t + on_s
                        abs_e = min(t + on_e, t_total)
                        if abs_s >= t_total or abs_e <= abs_s:
                            continue
                        x_s = m_l + (abs_s / t_total) * plot_w
                        x_e = m_l + (abs_e / t_total) * plot_w
                        coords.extend([x_s, y_low, x_s, y_high, x_e, y_high, x_e, y_low])
                    t += period
                    iters += 1
            coords.extend([m_l + plot_w, y_low])
            if len(coords) >= 4:
                self.create_line(*coords, fill=color, width=2,
                                  dash=(3, 2) if dashed else ())

            # Draggable edge handles (first period only).
            if self.edit_cb is not None and i < len(self.handles):
                r = self.HANDLE_R
                y_mid = (y_low + y_high) / 2
                for (t_h, key) in self.handles[i]:
                    if t_h < 0 or t_h > t_total:
                        continue
                    x_h = m_l + (t_h / t_total) * plot_w
                    active = (self._drag is not None
                              and self._drag["key"] == key)
                    self.create_oval(
                        x_h - r, y_mid - r, x_h + r, y_mid + r,
                        fill=("#ffcc00" if active else color),
                        outline=("#000000" if not self.dark else "#ffffff"))
                    self._handle_px.append((x_h, y_mid, key, t_h, i))

        # Zoom indicator in top-right corner when zoomed in
        if self.zoom_x > 1.01:
            self.create_text(
                max(total_w, w) - 4, m_t, anchor="ne",
                text=f"🔍 {self.zoom_x:.1f}×  Ctrl+Scroll or ±  to zoom  |  R to reset",
                font=("Arial", 7), fill=self.text_color)


# ==============================================================================
# SCENARIO MANAGER (Power-Up / Power-Down, JSON)
# ==============================================================================
class ScenarioManager:
    @staticmethod
    def default_powerup():
        return []

    @staticmethod
    def default_powerdown():
        return []

    @staticmethod
    def save(path, steps, run_hours=None):
        """Write steps JSON to an absolute or relative path chosen by the operator.
        Cycle programs (run_hours given) are saved as
        {"steps": [...], "run_hours": h}; 0 hours = unlimited."""
        if not path.endswith(".json"):
            path += ".json"
        payload = steps
        if run_hours is not None:
            payload = {"kind": "pace_cycle_scenario_v1",
                       "run_hours": run_hours, "steps": steps}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return path

    # Old scenario JSON files (saved before the PICO -> MCU rename) used
    # action="PICO" and pico_* step keys. Loading normalizes them so
    # older saved scenarios keep working without the operator having to
    # touch anything.
    _LEGACY_KEY_MAP = {
        "pico_signals": "mcu_signals", "pico_cmd": "mcu_cmd",
        "pico_loop": "mcu_loop", "pico_repeat": "mcu_repeat",
    }

    @classmethod
    def _normalize_step(cls, step):
        if not isinstance(step, dict):
            return step
        if step.get("action") == "PICO":
            step["action"] = "MCU"
        for old_key, new_key in cls._LEGACY_KEY_MAP.items():
            if old_key in step and new_key not in step:
                step[new_key] = step.pop(old_key)
        return step

    @classmethod
    def load(cls, path, with_run_hours=False):
        """Load steps JSON from a path chosen by the operator. With
        with_run_hours=True returns (steps, run_hours_or_None)."""
        with open(path, "r", encoding="utf-8") as f:
            steps = json.load(f)
        run_hours = None
        if isinstance(steps, dict) and isinstance(steps.get("steps"), list):
            run_hours = steps.get("run_hours")
            steps = steps["steps"]
        if isinstance(steps, list):
            steps = [cls._normalize_step(s) for s in steps]
        if with_run_hours:
            return steps, run_hours
        return steps

    @staticmethod
    def list_files():
        if not os.path.isdir(SCENARIO_DIR):
            return []
        return sorted(f for f in os.listdir(SCENARIO_DIR) if f.endswith(".json"))


def _kind_display(kind):
    return {"powerup": "POWER-UP", "powerdown": "POWER-DOWN",
            "cycle": "CYCLE PROGRAM"}.get(kind, "POWER-DOWN")


# ==============================================================================
# DESKTOP-APP SUPPORT (icon / resource lookup; works from source and when frozen)
# ==============================================================================
def _resource_path(rel):
    """Absolute path of a bundled resource (PyInstaller-safe)."""
    import sys
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def _set_windows_app_id():
    """Windows: give the process its own AppUserModelID so the taskbar shows
    the PACE icon instead of the generic Python one. No-op elsewhere."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "REL.PACE.PowerCycleController.1")
    except Exception:
        pass


# ==============================================================================
# MAIN APPLICATION CLASS
# ==============================================================================
class App(tk.Tk):
    def _apply_app_icon(self):
        """Window/taskbar icon on Windows (.ico), Linux/Raspberry Pi and macOS
        (PNG). Silently skipped if the icon files are missing."""
        try:
            import sys
            if sys.platform.startswith("win"):
                self.iconbitmap(_resource_path(os.path.join("assets", "pace.ico")))
            imgs = []
            for n in (256, 128, 64, 32):
                f = _resource_path(os.path.join("assets", f"pace_{n}.png"))
                if os.path.isfile(f):
                    imgs.append(tk.PhotoImage(file=f))
            if imgs:
                self._icon_refs = imgs  # keep references alive
                self.iconphoto(True, *imgs)
        except Exception:
            pass

    def __init__(self):
        super().__init__()
        self.title("PACE - Up to 8x PSU Synchronous/Asynchronous Power Cycle Controller")
        self._apply_app_icon()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        win_w = min(1280, screen_w - 60)
        win_h = min(900, screen_h - 80)
        pos_x = max((screen_w - win_w) // 2, 0)
        pos_y = max((screen_h - win_h) // 2, 0)
        self.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self.minsize(900, 520)

        try:
            self.state("zoomed")
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)
            except tk.TclError:
                pass

        # --- State -------------------------------------------------------
        self.psus = {i: PSUDriver(i, DEFAULT_PORTS[i - 1]) for i in range(1, MAX_PSUS + 1)}
        # MCU pattern-trigger link (separate USB-serial device, not a PSU).
        # Real ns-precision pattern playback happens on the MCU itself
        # (PIO+DMA); this app only triggers it. See MCUTrigger.
        self.mcu = MCUTrigger(MCU_DEFAULT_PORT)
        self.mcu.on_traffic = self._mcu_traffic
        self.mcu.abort_check = lambda: (self.stop_event.is_set()
                                        or self.emergency_event.is_set())
        # v22: flags read by worker threads (see _update_live_panels_visibility)
        self._scpi_visible = False
        self._mcu_visible = False
        self._live_log_last = {}      # (psu, ch) -> time of last LIVE log line
        self._log_file_dirty = False
        self._monitor_row_cache = {}  # monitor iid -> (values, tags) last shown
        for _psu in self.psus.values():
            _psu.on_traffic = self._scpi_traffic
        self.msg_queue = queue.Queue()
        self.run_thread = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.emergency_event = threading.Event()
        self.safety_state = SafetyState.IDLE
        self._pause_began = None  # monotonic timestamp when pause started
        self._pre_pause_state = {}  # per-PSU/channel V/I/on snapshot for RESUME
        self._output_lock = threading.RLock()
        self._pause_context = threading.local()
        self._pause_transition_thread = None
        self._stopping = False
        self.watchdog_thread = None
        self.watchdog_stop = threading.Event()
        self.session_start = None
        self.end_time = None
        self._active_cycle_limit = None

        self.test_end_time = None
        self.test_total_s = 0.0
        self.full_cycle_thread = None
        self.scenario_thread = None

        # Global operation lock: continuous cycle / scenario / full cycle
        # must never run concurrently on the same PSUs.
        self.op_lock = threading.Lock()
        self.op_running = False
        self.current_operation = None
        # monotonic timestamp of when the currently-running operation was
        # acquired; used to compute elapsed time for session reports.
        self._current_run_start = None

        self.log_file_path = None
        self.log_file = None
        self.csv_file = None

        self.async_entries = {}
        self._cycle_enable_before_lock = {}

        self.powerup_steps = ScenarioManager.default_powerup()
        self.powerdown_steps = ScenarioManager.default_powerdown()
        # v20: step-based Cycle program (one period of steps that repeats).
        # Edited from BOTH the Cycle Control tab and the Scenario Editor's
        # "Cycle" type - it is a single shared list.
        self.cycle_steps = []
        self._program_steps_active = []
        self._program_period = 0.0
        # v20: "Stop Cycle" ends only the Cycle phase (see _stop_cycle_phase);
        # _pause_total = total seconds spent paused so far, so absolute
        # ON/OFF schedules can slide past a PAUSE instead of "catching up".
        self.cycle_phase_stop_event = threading.Event()
        self._cycle_phase_active = False
        self._pause_total = 0.0
        self._full_cycle_cfg = None
        self.program_tree = None

        self._cell_editor = None

        # --- Scenario Editor Undo/Redo -----------------------------------
        # Snapshots are (deep-copied powerup_steps, deep-copied powerdown_steps)
        # tuples, pushed BEFORE every mutating action (add/delete/move/inline
        # edit/load). Capped so a long editing session can't grow unbounded.
        self._undo_stack = []
        self._redo_stack = []
        self._undo_stack_max = 50

        # --- Auto-save / Recovery -----------------------------------------
        self._autosave_after_id = None

        # --- Current theme (used e.g. to color plain tk widgets created
        # later, like the Listbox in the Load Scenario dialog) -------------
        self._theme = {"bg": "#f0f0f0", "fg": "#000000", "field_bg": "#ffffff"}

        # --- Fullscreen graph/timeline popups ------------------------------
        # key -> (Toplevel, canvas) while open. Double-clicking a small
        # canvas opens (or, if already open, closes) its fullscreen mirror.
        self._fullscreen = {}

        # --- GUI widget attributes (set during _build_gui) ----------------
        self.scenario_kind = None
        self.mcu_status_label_editor = None
        self.scenario_tree = None
        self.test_h = None
        self.test_m = None
        self.test_s = None
        self.test_label = None
        self.scenario_preview = None
        self.reading_stop = None
        self.reading_threads = []
        # Actual V/I values backing the monitor table. Graph and Live Log
        # consume this same state so all live views report the same sample.
        self.live_readings = {}
        self.reading_interval_ms = READING_POLL_DEFAULT_MS
        # v23: which values the Live Monitor reads: (psu, ch, "v"/"i") -> bool
        self.monitor_sel = {(p, ch, q): True
                            for p in range(1, MAX_PSUS + 1)
                            for ch in (1, 2) for q in ("v", "i")}
        # Per-PSU backoff (seconds) for the always-on link-recovery in
        # _reading_worker_for_psu - grows on repeated failed reconnects
        # so a genuinely unplugged PSU doesn't spam the port with
        # open attempts, and resets to the fast retry as soon as a
        # reconnect (or a normal read) succeeds again.
        self._reconnect_backoff = {}

        # v21: operator-chosen PSU slot -> USB/COM port assignments.
        # {psu_index: {"port": "COM5", "serial": "123456"}}; slots not in
        # here are "auto" (filled by Auto-Detect in serial-number order).
        # _port_idn caches the *IDN? reply seen per port by the last scan.
        self._manual_ports = {}
        self._port_idn = {}
        self._load_port_settings()

        self._build_gui()
        self._apply_theme(False)  # establish a consistent baseline (clam) style
        # Scenario Editor Undo/Redo keyboard shortcuts (global, not just
        # while the tree has focus - matches how Undo/Redo behave in most
        # desktop apps).
        self.bind_all("<Control-z>", lambda e: self._undo())
        self.bind_all("<Control-Z>", lambda e: self._undo())
        self.bind_all("<Control-y>", lambda e: self._redo())
        self.bind_all("<Control-Y>", lambda e: self._redo())
        self.bind_all("<Control-Shift-Z>", lambda e: self._redo())
        self._queue_after_id = self.after(100, self._process_queue)
        self._timer_after_id = self.after(500, self._update_timer_label)
        self._autosave_after_id = self.after(AUTOSAVE_INTERVAL_MS, self._autosave_tick)

        self.after(300, self._auto_detect_ports)
        # Slight extra delay so the main window is visible before any
        # recovery prompt pops up.
        self.after(700, self._check_recovery)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    @staticmethod
    def _allow_operator(widget):
        widget._operator_allowed = True
        return widget

    def _set_access_mode(self, _event=None):
        if self.access_mode_var.get() == "Engineer":
            for widget, state in getattr(
                    self, "_operator_prior_states", {}).items():
                widget.configure(state=state)
            self._operator_prior_states = {}
            self._update_mode_state()
            return
        self._destroy_cell_editor()
        self.show_scpi_var.set(False)
        self.show_mcu_var.set(False)
        self._update_live_panels_visibility()
        self._operator_prior_states = {
            widget: str(widget.cget("state"))
            for widget in self._access_interactive_widgets()
        }
        self._disable_operator_editing()

    def _access_interactive_widgets(self):
        interactive_classes = {
            "TButton", "TEntry", "TCheckbutton", "TRadiobutton",
            "TCombobox", "TSpinbox", "Button", "Entry", "Checkbutton",
            "Radiobutton", "Combobox", "Spinbox",
        }
        widgets = []
        for root in getattr(self, "_access_tabs", ()):
            pending = list(root.winfo_children())
            while pending:
                widget = pending.pop()
                pending.extend(widget.winfo_children())
                if widget.winfo_class() in interactive_classes:
                    widgets.append(widget)
        for name in ("show_scpi_toggle", "scpi_psu_combo",
                     "scpi_cmd_entry", "scpi_send_button",
                     "show_mcu_toggle", "mcu_cmd_entry", "mcu_send_button",
                     "mcu_open_button"):
            widget = getattr(self, name, None)
            if widget is not None:
                widgets.append(widget)
        return widgets

    def _disable_operator_editing(self):
        for widget in self._access_interactive_widgets():
            if not getattr(widget, "_operator_allowed", False):
                widget.configure(state="disabled")

    def _is_engineer_mode(self):
        return self.access_mode_var.get() == "Engineer"

    # --------------------------------------------------------------------
    # Interruptible wait (STOP / EMERGENCY / PAUSE aware)
    # --------------------------------------------------------------------
    def _abort_requested(self):
        return self.stop_event.is_set() or self.emergency_event.is_set()

    def _wait_while_paused(self):
        """Block here while PAUSED, remaining responsive to STOP/EMERGENCY.
        Must be called at the top of every cycle-loop iteration (not just
        relied upon inside `_interruptible_sleep`, whose seconds<=0
        fast-path does NOT check pause_event)."""
        while self.pause_event.is_set() and not self._abort_requested():
            time.sleep(INTERRUPT_SLICE_S)

    def _interruptible_sleep(self, seconds):
        """Sleep up to `seconds`, returning early on STOP/EMERGENCY.
        While PAUSED, the remaining time is held (does not count down).
        Returns True if the full duration completed, False if aborted.
        """
        if seconds <= 0:
            return not self._abort_requested()
        start = (self._pause_began if self._pause_began is not None
                 else time.monotonic())
        end = start + seconds
        base_pause = self._pause_total
        while True:
            if self._abort_requested():
                return False
            self._wait_while_paused()
            if self._abort_requested():
                return False
            remaining = end + (self._pause_total - base_pause) - time.monotonic()
            if remaining <= 0:
                return True
            time.sleep(min(remaining, INTERRUPT_SLICE_S))

    # --------------------------------------------------------------------
    # GUI Setup
    # --------------------------------------------------------------------
    def _build_gui(self):
        # ---------------- Always-visible safety bar -------------------------
        # SAFETY-CRITICAL: this bar sits OUTSIDE the scrollable canvas below,
        # so EMERGENCY OFF is always reachable even if the operator has
        # scrolled the dashboard down to read logs/graphs. The original
        # EMERGENCY OFF button in the Cycle Control panel is kept too, as a
        # second, redundant way to trigger it.
        emergency_bar = ttk.Frame(self)
        emergency_bar.pack(side="top", fill="x")
        emg_btn = tk.Button(
            emergency_bar, text="\u26a0 EMERGENCY OFF \u26a0",
            command=self._emergency_off, bg="#b00020", fg="white",
            activebackground="#7a0016", activeforeground="white",
            font=("Arial", 12, "bold"), relief="raised", bd=3, cursor="hand2")
        emg_btn.pack(fill="x", padx=6, pady=4)

        # ---------------- Top toolbar (theme + editor-wide actions) ---------
        toolbar = ttk.Frame(self)
        toolbar.pack(side="top", fill="x")
        self.access_mode_var = tk.StringVar(value="Engineer")
        ttk.Label(toolbar, text="Access Mode:").pack(side="right", padx=(8, 2))
        self.access_mode_combo = ttk.Combobox(
            toolbar, textvariable=self.access_mode_var,
            values=("Engineer", "Operator"), width=10, state="readonly")
        self.access_mode_combo.pack(side="right", padx=(0, 6), pady=2)
        self.access_mode_combo.bind(
            "<<ComboboxSelected>>", self._set_access_mode)
        ttk.Label(toolbar, text="Password not required yet",
                  font=("Arial", 8, "italic")).pack(side="right", padx=2)
        self.dark_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar, text="\U0001f319 Dark Mode", variable=self.dark_mode_var,
            command=self._toggle_dark_mode).pack(side="right", padx=8, pady=2)
        self.show_graph_var = tk.BooleanVar(value=False)
        self.show_log_var = tk.BooleanVar(value=False)
        self.show_scpi_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar, text="Show Live Graph", variable=self.show_graph_var,
            command=self._update_live_panels_visibility).pack(side="left", padx=6, pady=2)
        ttk.Checkbutton(
            toolbar, text="Show Live Log", variable=self.show_log_var,
            command=self._update_live_panels_visibility).pack(side="left", padx=6, pady=2)
        self.show_scpi_toggle = ttk.Checkbutton(
            toolbar, text="Show Live SCPI", variable=self.show_scpi_var,
            command=self._update_live_panels_visibility)
        self.show_scpi_toggle.pack(side="left", padx=6, pady=2)
        self.show_mcu_var = tk.BooleanVar(value=False)
        self.show_mcu_toggle = ttk.Checkbutton(
            toolbar, text="Show MCU Console", variable=self.show_mcu_var,
            command=self._update_live_panels_visibility)
        self.show_mcu_toggle.pack(side="left", padx=6, pady=2)

        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)

        # ---------------- Connection status --------------------------------
        # Pinned above the tabbed dashboard (like the emergency bar above),
        # so it stays visible no matter which tab is selected.
        conn_frame = ttk.LabelFrame(outer, text="Connection Status")
        conn_frame.pack(fill="x", padx=6, pady=(4, 1))

        conn_btns = ttk.Frame(conn_frame)
        conn_btns.pack(fill="x", pady=(1, 1))
        ttk.Button(conn_btns, text="Connect All / Refresh",
                   command=self._connect_all).pack(side="right", padx=8)
        ttk.Button(conn_btns, text="Auto-Detect Ports",
                   command=self._auto_detect_ports).pack(side="right", padx=8)
        ttk.Button(conn_btns, text="Detect MCU",
                   command=self._detect_mcu).pack(side="right", padx=8)

        conn_body = ttk.Frame(conn_frame)
        conn_body.pack(fill="x", pady=(0, 3))

        # MCU status is pinned here, outside the horizontally-scrollable
        # PSU strip below - previously it was placed as the 9th column
        # *inside* that scrollable strip, so with several PSUs configured
        # it silently scrolled off-screen and was effectively invisible.
        # Pinning it on the right keeps it visible at all times.
        pf = ttk.Frame(conn_body)
        pf.pack(side="right", padx=(10, 6), pady=4)
        ttk.Separator(conn_body, orient="vertical").pack(
            side="right", fill="y", padx=(4, 0), pady=2)
        mcu_port_lbl = ttk.Label(
            pf, text=f"MCU ({self.mcu.port or 'not set'})",
            font=("Arial", 10, "bold"))
        mcu_port_lbl.pack()
        self.mcu_port_label = mcu_port_lbl
        mcu_status_lbl = ttk.Label(pf, text="\u25cb Not Connected", foreground="red")
        mcu_status_lbl.pack()
        self.mcu_status_label = mcu_status_lbl

        conn_scroll_wrap = ttk.Frame(conn_body)
        conn_scroll_wrap.pack(side="left", fill="both", expand=True)
        conn_canvas = tk.Canvas(conn_scroll_wrap, height=54, highlightthickness=0)
        self._conn_canvas = conn_canvas
        conn_hsb = ttk.Scrollbar(conn_scroll_wrap, orient="horizontal",
                                  command=conn_canvas.xview)
        conn_canvas.configure(xscrollcommand=conn_hsb.set)
        conn_canvas.pack(side="top", fill="x")
        conn_hsb.pack(side="top", fill="x")
        conn_inner = ttk.Frame(conn_canvas)
        conn_canvas.create_window((0, 0), window=conn_inner, anchor="nw")
        conn_inner.bind("<Configure>",
                         lambda e: conn_canvas.configure(
                             scrollregion=conn_canvas.bbox("all"),
                             height=conn_inner.winfo_reqheight()))

        self.conn_labels = {}
        self.port_labels = {}
        self.port_combos = {}
        self.port_vars = {}
        for i in range(1, MAX_PSUS + 1):
            f = ttk.Frame(conn_inner)
            f.grid(row=0, column=i - 1, padx=6, pady=2)
            port_lbl = ttk.Label(f, text=f"PSU{i}", font=("Arial", 10, "bold"))
            port_lbl.pack()
            self.port_labels[i] = port_lbl
            pvar = tk.StringVar(value=self._port_display(self.psus[i].port))
            combo = ttk.Combobox(f, textvariable=pvar, width=22,
                                 values=self._port_choice_values(),
                                 state="readonly", postcommand=(
                                     lambda idx=i:
                                     self.port_combos[idx].configure(
                                         values=self._port_choice_values())))
            combo.pack()
            combo.bind("<<ComboboxSelected>>",
                       lambda e, idx=i: self._on_port_selected(idx))
            _HoverTooltip(combo, (lambda idx=i: self._port_tooltip(idx)))
            self.port_vars[i] = pvar
            self.port_combos[i] = combo
            lbl = ttk.Label(f, text="\u25cb Not Connected", foreground="red")
            lbl.pack()
            self.conn_labels[i] = lbl
        self._refresh_port_widgets()

        # ================================================================
        # TABBED DASHBOARD
        #   v18: replaces the old single scrollable canvas (which needed
        #   both vertical AND horizontal page-scrolling to reach every
        #   control) with a plain ttk.Notebook. Each tab now gets the FULL
        #   window width instead of half of it (the old two-column layout),
        #   and only holds about half of what used to be stacked into one
        #   giant column - so every tab's content fits inside one normal
        #   (maximized) screen with no page-level scrollbar in any
        #   direction. Tables/graphs that legitimately benefit from their
        #   own internal scroll/zoom (scenario tree, timeline previews,
        #   monitor table) keep their own widget-level scrollbars - only
        #   the outer whole-dashboard scrolling was removed.
        # ================================================================
        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True, padx=6, pady=(4, 6))
        self._main_notebook = notebook

        # v21: each tab's content sits in its own scrollable page so that on
        # small (laptop) screens everything below the fold can still be
        # reached with the scrollbars / mouse wheel. On a large monitor the
        # page simply stretches to the window and no scrollbar is needed.
        self._page_canvases = []
        page_cycle = ttk.Frame(notebook)
        notebook.add(page_cycle, text="Cycle Control")
        tab_cycle = self._make_scrollable_page(page_cycle)
        page_scenario = ttk.Frame(notebook)
        notebook.add(page_scenario, text="Scenario Monitor")
        tab_scenario = self._make_scrollable_page(page_scenario)
        self._access_tabs = (tab_cycle, tab_scenario)
        self.bind_all("<MouseWheel>", self._on_page_wheel, add="+")
        self.bind_all("<Shift-MouseWheel>",
                      lambda e: self._on_page_wheel(e, horizontal=True), add="+")
        self.bind_all("<Button-4>", self._on_page_wheel, add="+")
        self.bind_all("<Button-5>", self._on_page_wheel, add="+")

        # ---------------- Operation mode -----------------------------------
        mode_frame = ttk.LabelFrame(tab_cycle, text="Operation Mode")
        mode_frame.pack(fill="x", pady=(0, 3))
        self.mode_var = tk.StringVar(value="sync")
        ttk.Radiobutton(
            mode_frame, text="Synchronous (all PSUs together; uses PSU1 row)",
            variable=self.mode_var, value="sync",
            command=self._update_mode_state).grid(
            row=0, column=0, sticky="w", padx=6)
        ttk.Radiobutton(
            mode_frame, text="Asynchronous (each PSU has its own timing)",
            variable=self.mode_var, value="async",
            command=self._update_mode_state).grid(
            row=0, column=1, sticky="w", padx=6)
        ttk.Radiobutton(
            mode_frame, text="Constant (steady V/I output, no ON/OFF cycling)",
            variable=self.mode_var, value="constant",
            command=self._update_mode_state).grid(
            row=0, column=2, sticky="w", padx=6)
        ttk.Radiobutton(
            mode_frame, text="Program (step table, like Scenario Editor)",
            variable=self.mode_var, value="program",
            command=self._update_mode_state).grid(
            row=0, column=3, sticky="w", padx=6)

        limit_text = (
            "Allow Voltage/Current values above the safety limits "
            f"({LIMIT_VOLTAGE_MAX:.0f}V / {LIMIT_CURRENT_MAX:.0f}A)")
        self.limit_override_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(mode_frame, text=limit_text,
                        variable=self.limit_override_var).grid(
            row=1, column=0, columnspan=3, sticky="w", padx=20, pady=(2, 4))

        # v14: Output Characteristic (Range Selection preset) - applied to
        # every PSU/channel this Operation Mode turns on, right before the
        # ON command. Mirrors the front-panel Range keys shown in the PSU
        # photo (60V/10A, 60V/3A, 16V/10A, Custom Limits). See the
        # OUTPUT_CHARACTERISTICS comment near the top of this file for why
        # this programs OVP/OCP rather than actually switching the panel's
        # range lamp (there is no remote command for that).
        ttk.Label(mode_frame, text="Output Characteristic (OVP/OCP preset):").grid(
            row=2, column=0, sticky="w", padx=6, pady=(0, 4))
        self.characteristic_var = tk.StringVar(value="Custom Limits")
        ttk.Combobox(
            mode_frame, textvariable=self.characteristic_var,
            values=OUTPUT_CHARACTERISTIC_NAMES, width=14,
            state="readonly").grid(
            row=2, column=1, sticky="w", pady=(0, 4))
        ttk.Label(
            mode_frame,
            text="Applied to every channel this mode turns ON, via OVP/OCP "
                 "(the panel's range lamp is local-only, not remote-settable).",
            font=("Arial", 8, "italic")).grid(
            row=2, column=2, sticky="w", padx=6, pady=(0, 4))

        # Shared per-PSU settings table (used by Sync / Async / Constant).
        # Sync   : only PSU1 row is editable; its values drive every PSU.
        # Async  : every row fully editable.
        # Constant: only CHx V / CHx I editable; timing fields disabled.
        #
        # Each channel gets its own independent Start(s) [delay from cycle
        # start] and On-Dur(s) [how long it stays ON]. This replaces the
        # older "shared ON/OFF + ON Delay/OFF Delay" model, which always
        # forced CH1 and CH2 to overlap (CH2's ON window was necessarily a
        # sub-interval of CH1's). With independent start/duration per
        # channel, ANY relationship is possible: staggered-but-overlapping
        # (as before), fully simultaneous, or genuinely non-overlapping -
        # e.g. CH2 Start >= CH1 Start + CH1 On-Dur turns CH2 on only after
        # CH1 has already turned off. CH1 and CH2 each have their own
        # Cycle OFF(s), so each repeats independently.
        psu_sub = ttk.LabelFrame(
            mode_frame, text="PSU Settings (Sync uses PSU1 for all units; "
                             "tick a channel's 'On' to include it - CH1/CH2 "
                             "can be enabled independently)")
        psu_sub.grid(row=3, column=0, columnspan=3, sticky="we", padx=20, pady=4)
        # Columns 0/1 = per-channel enable (CH1 On / CH2 On, replacing the
        # old single per-PSU "On" checkbox so a single channel can be used
        # on its own); columns 2..12 = row data; 13/14 = optional operator
        # Name for each channel (used by the Cycle Timeline Preview and the
        # Live Current/Voltage Monitor - see _compute_cycle_preview and
        # _monitor_label_for).
        ttk.Label(psu_sub, text="CH1\nOn").grid(row=0, column=0, padx=2)
        ttk.Label(psu_sub, text="CH2\nOn").grid(row=0, column=1, padx=2)
        ttk.Label(psu_sub, text="PSU").grid(row=0, column=2, padx=2)
        ttk.Label(psu_sub, text="CH1 Start(s)").grid(row=0, column=3)
        ttk.Label(psu_sub, text="CH1 On-Dur(s)").grid(row=0, column=4)
        ttk.Label(psu_sub, text="CH2 Start(s)").grid(row=0, column=5)
        ttk.Label(psu_sub, text="CH2 On-Dur(s)").grid(row=0, column=6)
        ttk.Label(psu_sub, text="CH1 Cycle OFF(s)").grid(row=0, column=7)
        ttk.Label(psu_sub, text="CH2 Cycle OFF(s)").grid(row=0, column=8)
        ttk.Label(psu_sub, text="CH1 V(V)").grid(row=0, column=9)
        ttk.Label(psu_sub, text="CH1 I(A)").grid(row=0, column=10)
        ttk.Label(psu_sub, text="CH2 V(V)").grid(row=0, column=11)
        ttk.Label(psu_sub, text="CH2 I(A)").grid(row=0, column=12)
        ttk.Label(psu_sub, text="CH1 Name").grid(row=0, column=13)
        ttk.Label(psu_sub, text="CH2 Name").grid(row=0, column=14)
        self.async_ch_entries = {}
        self.ch_enable_vars = {}
        self.ch_enable_cbs = {}
        self.opmode_name_entries = {}
        # Reason (str) a given (psu, ch) On checkbox is currently forced
        # off/disabled because that PSU/Channel is already used by a
        # Power-Up/Power-Down scenario step - see
        # _refresh_ch_enable_availability. Empty string/absent = not locked.
        self._ch_lock_reason = {}
        for i in range(1, MAX_PSUS + 1):
            for ch, col in ((1, 0), (2, 1)):
                en_var = tk.BooleanVar(value=True)
                self.ch_enable_vars[(i, ch)] = en_var
                cb = ttk.Checkbutton(
                    psu_sub, variable=en_var,
                    command=self._refresh_cycle_preview)
                cb.grid(row=i, column=col, padx=2)
                self.ch_enable_cbs[(i, ch)] = cb
                _HoverTooltip(
                    cb, (lambda p=i, c=ch: self._ch_lock_reason.get((p, c), "")))
            ttk.Label(psu_sub, text=f"PSU{i}").grid(row=i, column=2, padx=2)
            e_ch1_start = ttk.Entry(psu_sub, width=9)
            e_ch1_start.insert(0, "0.000")
            e_ch1_dur = ttk.Entry(psu_sub, width=9)
            e_ch1_dur.insert(0, "1.000")
            e_ch2_start = ttk.Entry(psu_sub, width=9)
            e_ch2_start.insert(0, "0.000")
            e_ch2_dur = ttk.Entry(psu_sub, width=9)
            e_ch2_dur.insert(0, "1.000")
            e_ch1_cycle_off = ttk.Entry(psu_sub, width=9)
            e_ch1_cycle_off.insert(0, "0.000")
            e_ch2_cycle_off = ttk.Entry(psu_sub, width=9)
            e_ch2_cycle_off.insert(0, "0.000")
            e_ch1_v = ttk.Entry(psu_sub, width=6)
            e_ch1_v.insert(0, "0.00")
            e_ch1_i = ttk.Entry(psu_sub, width=6)
            e_ch1_i.insert(0, "0.00")
            e_ch2_v = ttk.Entry(psu_sub, width=6)
            e_ch2_v.insert(0, "0.00")
            e_ch2_i = ttk.Entry(psu_sub, width=6)
            e_ch2_i.insert(0, "0.00")
            e_ch1_name = ttk.Entry(psu_sub, width=10)
            e_ch2_name = ttk.Entry(psu_sub, width=10)
            e_ch1_start.grid(row=i, column=3, padx=2)
            e_ch1_dur.grid(row=i, column=4, padx=2)
            e_ch2_start.grid(row=i, column=5, padx=2)
            e_ch2_dur.grid(row=i, column=6, padx=2)
            e_ch1_cycle_off.grid(row=i, column=7, padx=2)
            e_ch2_cycle_off.grid(row=i, column=8, padx=2)
            e_ch1_v.grid(row=i, column=9, padx=2)
            e_ch1_i.grid(row=i, column=10, padx=2)
            e_ch2_v.grid(row=i, column=11, padx=2)
            e_ch2_i.grid(row=i, column=12, padx=2)
            e_ch1_name.grid(row=i, column=13, padx=2)
            e_ch2_name.grid(row=i, column=14, padx=2)
            self.async_entries[(i, "ch1_start")] = e_ch1_start
            self.async_entries[(i, "ch1_dur")] = e_ch1_dur
            self.async_entries[(i, "ch2_start")] = e_ch2_start
            self.async_entries[(i, "ch2_dur")] = e_ch2_dur
            self.async_entries[(i, "ch1_cycle_off")] = e_ch1_cycle_off
            self.async_entries[(i, "ch2_cycle_off")] = e_ch2_cycle_off
            self.async_ch_entries[(i, 1, "v")] = e_ch1_v
            self.async_ch_entries[(i, 1, "i")] = e_ch1_i
            self.async_ch_entries[(i, 2, "v")] = e_ch2_v
            self.async_ch_entries[(i, 2, "i")] = e_ch2_i
            self.opmode_name_entries[(i, 1)] = e_ch1_name
            self.opmode_name_entries[(i, 2)] = e_ch2_name
            for _e in (e_ch1_start, e_ch1_dur, e_ch2_start, e_ch2_dur,
                       e_ch1_cycle_off, e_ch2_cycle_off,
                       e_ch1_v, e_ch1_i, e_ch2_v, e_ch2_i):
                _bind_numeric_entry(_e)
                _e.bind("<KeyRelease>", lambda e: self._refresh_cycle_preview(), add="+")
            for _e in (e_ch1_name, e_ch2_name):
                _e.bind(
                    "<KeyRelease>",
                    lambda e: (self._refresh_cycle_preview(),
                               self._refresh_all_monitor_labels()),
                    add="+")

        ttk.Separator(psu_sub, orient="vertical").grid(
            row=0, column=15, rowspan=MAX_PSUS + 1, sticky="ns", padx=10)
        ctrl_panel = ttk.Frame(psu_sub)
        ctrl_panel.grid(row=0, column=16, rowspan=MAX_PSUS + 1, sticky="n",
                         padx=(0, 6), pady=4)
        ttk.Label(ctrl_panel, text="Cycle Control",
                  font=("Arial", 9, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 6))
        self._allow_operator(ttk.Button(
            ctrl_panel, text="\u25b6 START", command=self._start_cycle)).grid(
                row=1, column=0, padx=4, pady=3, sticky="ew")
        self._allow_operator(ttk.Button(
            ctrl_panel, text="\u23f8 PAUSE/RESUME",
            command=self._toggle_pause)).grid(
                row=1, column=1, padx=4, pady=3, sticky="ew")
        self._allow_operator(ttk.Button(
            ctrl_panel, text="\u23f9 STOP", command=self._stop_cycle)).grid(
                row=2, column=0, padx=4, pady=3, sticky="ew")
        self._allow_operator(ttk.Button(
            ctrl_panel, text="\u26a0 EMERGENCY OFF",
            command=self._emergency_off)).grid(
                row=2, column=1, padx=4, pady=3, sticky="ew")
        self.op_status_lbl = ttk.Label(
            ctrl_panel, text="Status: IDLE", foreground="blue",
            font=("Arial", 8, "bold"))
        self.op_status_lbl.grid(row=3, column=0, columnspan=2, pady=(6, 0))
        self.safety_lbl = ttk.Label(
            ctrl_panel, text="Safety: IDLE", foreground="green",
            font=("Arial", 8, "bold"))
        self.safety_lbl.grid(row=4, column=0, columnspan=2, pady=(2, 0))
        # After an EMERGENCY OFF, START/Run Scenario/Run Full Cycle are
        # blocked (see _acquire_operation) until this is pressed and
        # confirmed - mirrors standard E-stop reset practice.
        self._allow_operator(ttk.Button(
            ctrl_panel, text="Reset Emergency",
            command=self._reset_emergency)).grid(
            row=5, column=0, columnspan=2, padx=4, pady=(4, 0), sticky="ew")
        ttk.Button(ctrl_panel, text="Save Cycle/Test Program",
                   command=self._save_cycle_program_dialog).grid(
            row=6, column=0, columnspan=2, padx=4, pady=(8, 0), sticky="ew")
        self._allow_operator(ttk.Button(
            ctrl_panel, text="Load Program",
            command=self._load_cycle_program_dialog)).grid(
            row=7, column=0, columnspan=2, padx=4, pady=(3, 0), sticky="ew")
        # Shows which Sync/Async program file (if any) is currently loaded/
        # saved, so the operator doesn't have to rely on the log to know
        # what is active - see _save_cycle_program_dialog/_load_cycle_program_dialog.
        self.loaded_program_path = None
        self.loaded_cycle_program_data = None
        self.loaded_program_lbl = ttk.Label(
            ctrl_panel, text="Loaded program: (none)",
            font=("Arial", 8, "italic"), wraplength=140, justify="left")
        self.loaded_program_lbl.grid(row=8, column=0, columnspan=2, pady=(6, 0))

        # ---- Total Operation Time ----------------------------------------
        timer_frame = ttk.LabelFrame(mode_frame, text="Total Operation Time")
        timer_frame.grid(row=4, column=0, columnspan=3, sticky="we",
                          padx=20, pady=(8, 4))
        ttk.Label(timer_frame, text="Time (hh:mm:ss):").grid(row=0, column=0, padx=4)
        # Single merged field instead of three separate hour/minute/second
        # boxes. self.dur_h/self.dur_m/self.dur_s stay available as thin
        # proxies (see _TimeEntryPart) so the rest of the code is unchanged.
        self.dur_var = tk.StringVar(value="01:00:00")   # shared with Scenario Monitor
        self.dur_entry = ttk.Entry(timer_frame, width=10, justify="center",
                                   textvariable=self.dur_var)
        self.dur_entry.delete(0, "end")
        self.dur_entry.insert(0, "01:00:00")
        _bind_time_entry(self.dur_entry)
        self.dur_entry.grid(row=0, column=1, columnspan=5, sticky="w", padx=(0, 6))
        self.dur_h = _TimeEntryPart(self.dur_entry, 0)
        self.dur_m = _TimeEntryPart(self.dur_entry, 1)
        self.dur_s = _TimeEntryPart(self.dur_entry, 2)
        self.unlimited_var = tk.BooleanVar(value=False)
        self.unlimited_cb = ttk.Checkbutton(
            timer_frame, text="Unlimited (manual stop)",
            variable=self.unlimited_var,
            command=self._update_stop_control_state)
        self.unlimited_cb.grid(row=0, column=6, padx=10)
        self.timer_label = ttk.Label(
            timer_frame, text="Remaining: --:--:--", font=("Arial", 10, "bold"))
        self.timer_label.grid(row=0, column=7, padx=20)
        self.stop_mode_var = tk.StringVar(value="time")
        self.stop_by_time_rb = ttk.Radiobutton(
            timer_frame, text="Stop by Time", variable=self.stop_mode_var,
            value="time", command=self._update_stop_control_state)
        self.stop_by_time_rb.grid(row=1, column=0, columnspan=2, sticky="w", padx=4, pady=(4, 0))
        self.stop_by_cycles_rb = ttk.Radiobutton(
            timer_frame, text="Stop by Cycle Count (Sync/Async/Program)",
            variable=self.stop_mode_var, value="cycles",
            command=self._update_stop_control_state)
        self.stop_by_cycles_rb.grid(row=1, column=2, columnspan=3, sticky="w", padx=6, pady=(4, 0))
        ttk.Label(timer_frame, text="Cycle Count:").grid(
            row=1, column=5, sticky="e", padx=(8, 2), pady=(4, 0))
        self.cycle_count_entry = ttk.Entry(timer_frame, width=6)
        self.cycle_count_entry.insert(0, "100")
        _bind_numeric_entry(self.cycle_count_entry)
        self.cycle_count_entry.grid(row=1, column=6, sticky="w", pady=(4, 0))

        # ---- v20: Cycle Program (step table) -----------------------------
        # Same editor/steps as the Scenario Editor's "Cycle" type (shared
        # list: self.cycle_steps). Only visible in "Program" mode.
        self.program_frame = ttk.LabelFrame(
            mode_frame,
            text="Cycle Program - one period of steps, repeated "
                 "(same steps as Scenario Editor -> Cycle)")
        self.program_frame.grid(row=5, column=0, columnspan=4, sticky="we",
                                padx=20, pady=(4, 4))
        prog_btns = ttk.Frame(self.program_frame)
        prog_btns.pack(fill="x", pady=(2, 0))
        ttk.Button(prog_btns, text="+ Add Step",
                   command=lambda: self._scenario_add_step("cycle")).pack(
            side="left", padx=2)
        ttk.Button(prog_btns, text="+ Add Cycle",
                   command=lambda: self._scenario_add_step(
                       "cycle", cycle_only=True)).pack(side="left", padx=2)
        ttk.Button(prog_btns, text="Delete",
                   command=lambda: self._scenario_delete_step(
                       self.program_tree)).pack(side="left", padx=2)
        ttk.Button(prog_btns, text="\u2191", width=3,
                   command=lambda: self._scenario_move(
                       -1, self.program_tree)).pack(side="left", padx=2)
        ttk.Button(prog_btns, text="\u2193", width=3,
                   command=lambda: self._scenario_move(
                       1, self.program_tree)).pack(side="left", padx=2)
        ttk.Button(prog_btns, text="\u21b6 Undo",
                   command=self._undo).pack(side="left", padx=(10, 2))
        ttk.Button(prog_btns, text="\u21b7 Redo",
                   command=self._redo).pack(side="left", padx=2)
        ttk.Label(prog_btns, text="Repeat every (s) [0 = run once]:").pack(
            side="left", padx=(16, 2))
        self.program_period_entry = ttk.Entry(prog_btns, width=9)
        self.program_period_entry.insert(0, "0")
        _bind_numeric_entry(self.program_period_entry)
        self.program_period_entry.bind(
            "<KeyRelease>", lambda e: self._refresh_cycle_preview(), add="+")
        self.program_period_entry.pack(side="left")

        prog_tree_wrap = ttk.Frame(self.program_frame)
        prog_tree_wrap.pack(fill="x", pady=2)
        prog_cols = ("psu", "ch", "action", "wait", "voltage", "current",
                     "characteristic", "cycle", "cycle_limit", "repeat", "name")
        self.program_tree = ttk.Treeview(
            prog_tree_wrap, columns=prog_cols, show="headings", height=4)
        prog_headings = {
            "psu": "PSU", "ch": "Channel", "action": "Action",
            "wait": "Wait After(s)", "voltage": "Voltage(V)",
            "current": "Current(A)", "characteristic": "Output Char.",
            "cycle": "Cycle On/Off/Count", "cycle_limit": "Cycle Limit(s)",
            "repeat": "MCU Cmd", "name": "Name / MCU Signals",
        }
        for c, w in zip(prog_cols,
                        (50, 60, 70, 90, 70, 70, 90, 110, 85, 90, 140)):
            self.program_tree.heading(c, text=prog_headings[c])
            self.program_tree.column(c, width=w, anchor="center")
        prog_hsb = ttk.Scrollbar(prog_tree_wrap, orient="horizontal",
                                 command=self.program_tree.xview)
        self.program_tree.configure(xscrollcommand=prog_hsb.set)
        self.program_tree.pack(fill="x")
        prog_hsb.pack(fill="x")
        self.program_tree.bind("<Double-1>", self._on_tree_double_click)
        self.program_tree.bind("<Button-1>", self._destroy_cell_editor, add="+")
        ttk.Label(
            self.program_frame,
            text="Wait After(s) = time from the program start. CYCLE steps "
                 "run on their own ON/OFF/Repeat Count (Count 0 = keep "
                 "cycling until Total Operation Time ends / Stop Cycle / "
                 "STOP). Leave 'Repeat every' at 0 to run the program once; "
                 "set it > 0 to repeat the whole program every N seconds. "
                 "Only the PSU/Channels named here are switched - everything "
                 "else (e.g. rails from Power-Up) stays as is.",
            font=("Arial", 8, "italic"), wraplength=900, justify="left"
        ).pack(anchor="w", padx=4, pady=(0, 2))

        # ---------------- Scenario editor (own tab) -------------------------
        sc_frame = ttk.LabelFrame(
            tab_scenario, text="Power-Up / Power-Down Scenario Editor")
        sc_frame.pack(fill="both", expand=True)
        self._build_scenario_editor(sc_frame)

        # Failsafe / Watchdog (v16: opt-in; OFF by default)
        wd_frame = ttk.LabelFrame(tab_cycle, text="Failsafe / Watchdog")
        wd_frame.pack(fill="x", pady=(0, 3))
        self.watchdog_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            wd_frame,
            text="Enable mid-run Watchdog (OFF by default)",
            variable=self.watchdog_enabled_var
        ).grid(row=0, column=0, padx=6, sticky="w")
        self.wd_status_lbl = ttk.Label(
            wd_frame, text="\u25cf Watchdog idle (disabled)", foreground="#888888")
        self.wd_status_lbl.grid(row=0, column=1, padx=6, sticky="w")
        ttk.Label(
            wd_frame,
            text="When enabled and connection is lost mid-run: All PSU outputs OFF "
                 f"\u2192 try to reconnect ({RECONNECT_ATTEMPTS} times) \u2192 if "
                 "unsuccessful, stop the cycle. Connection is always checked at "
                 "START / Run Scenario before hardware is driven.",
            wraplength=520, justify="left"
        ).grid(row=1, column=0, columnspan=2, padx=6, pady=(2, 4), sticky="w")

        # ---------------- Cycle Timeline Preview (Sync/Async) ----------------
        # Same idea as the Power-Up/Power-Down "Symbol / Step Editor"
        # preview on the right, but for the REPEATING continuous cycle -
        # lets the operator visually verify the Sync/Async ON/OFF pattern
        # built from the "PSU Settings" table above before pressing START.
        cyc_frame = ttk.LabelFrame(
            tab_cycle, text="Cycle Timeline Preview (Synchronous / Asynchronous)")
        cyc_frame.pack(fill="x", pady=(0, 3))
        cyc_top = ttk.Frame(cyc_frame)
        cyc_top.pack(fill="x")
        ttk.Label(
            cyc_top,
            text="Shows the repeating ON/OFF pattern the PSU Settings table "
                 "above would produce (updates automatically; Constant mode "
                 "has no repeating pattern to show).",
            font=("Arial", 8, "italic"), wraplength=520, justify="left"
        ).pack(side="left", anchor="w", padx=4, pady=2)
        ttk.Button(cyc_top, text="\U0001f504 Refresh Preview",
                   command=self._refresh_cycle_preview).pack(side="right", padx=4)
        cyc_wrap = ttk.Frame(cyc_frame)
        cyc_wrap.pack(fill="x", pady=(0, 2))
        self.cycle_preview = CycleTimelineCanvas(
            cyc_wrap,
            height=CycleTimelineCanvas.ROW_H * CycleTimelineCanvas.VISIBLE_ROWS + 26)
        cyc_vsb = ttk.Scrollbar(
            cyc_wrap, orient="vertical", command=self.cycle_preview.yview)
        cyc_hsb = ttk.Scrollbar(
            cyc_wrap, orient="horizontal", command=self.cycle_preview.xview)
        self.cycle_preview.configure(yscrollcommand=cyc_vsb.set,
                                     xscrollcommand=cyc_hsb.set)
        cyc_vsb.pack(side="right", fill="y")
        cyc_hsb.pack(side="bottom", fill="x")
        self.cycle_preview.pack(side="left", fill="x", expand=True)
        self.cycle_preview.bind(
            "<Double-Button-1>",
            lambda e: self._toggle_fullscreen(
                "cycle", self._open_cycle_preview_fullscreen))
        self.cycle_preview.bind("<Key-plus>",
                                lambda e: self.cycle_preview._zoom(CycleTimelineCanvas.ZOOM_STEP))
        self.cycle_preview.bind("<Key-minus>",
                                lambda e: self.cycle_preview._zoom(1.0 / CycleTimelineCanvas.ZOOM_STEP))
        self.cycle_preview.bind("<r>", lambda e: self.cycle_preview.reset_zoom())

        # ---------------- Graphs (own window) -------------------------------
        # Graph/Log/SCPI panels open as separate windows (rather than being
        # embedded inline in the scrollable dashboard) so they can be moved,
        # resized, or put on a second monitor independently, and so toggling
        # them doesn't reshuffle the main dashboard's layout.
        self.graph_win = tk.Toplevel(self)
        self.graph_win.title("Live Graph")
        self.graph_win.geometry("760x420")
        self.graph_win.protocol("WM_DELETE_WINDOW",
                                 lambda: self._close_live_panel("graph"))
        self.graph_win.withdraw()
        self.graph_frame = ttk.LabelFrame(
            self.graph_win, text=self._graph_frame_title())
        self.graph_frame.pack(fill="both", expand=True, padx=6, pady=4)
        self.v_graph = GraphCanvas(self.graph_frame, "Voltage", "V", height=140)
        self.v_graph.pack(fill="x", expand=True, pady=2)
        self.i_graph = GraphCanvas(self.graph_frame, "Current", "A", height=140)
        self.i_graph.pack(fill="x", expand=True, pady=2)
        self.v_graph.bind(
            "<Double-Button-1>",
            lambda e: self._toggle_fullscreen(
                "graph_v", lambda: self._open_graph_fullscreen("v")))
        self.i_graph.bind(
            "<Double-Button-1>",
            lambda e: self._toggle_fullscreen(
                "graph_i", lambda: self._open_graph_fullscreen("i")))
        for i in range(1, MAX_PSUS + 1):
            self.v_graph.add_series(f"PSU{i}-CH1", PSU_COLORS[i])
            self.i_graph.add_series(f"PSU{i}-CH1", PSU_COLORS[i])
            self.v_graph.add_series(f"PSU{i}-CH2", PSU_COLORS_CH2[i])
            self.i_graph.add_series(f"PSU{i}-CH2", PSU_COLORS_CH2[i])

        # ---------------- Log screen (own window) ---------------------------
        self.log_win = tk.Toplevel(self)
        self.log_win.title("Live Log Screen")
        self.log_win.geometry("760x420")
        self.log_win.protocol("WM_DELETE_WINDOW",
                               lambda: self._close_live_panel("log"))
        self.log_win.withdraw()
        self.log_frame = ttk.LabelFrame(self.log_win, text="Live Log Screen")
        self.log_frame.pack(fill="both", expand=True, padx=6, pady=4)
        self.log_text = tk.Text(
            self.log_frame, height=10, state="disabled", bg="#111111", fg="#33ff33",
            font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, side="left")
        scr = ttk.Scrollbar(self.log_frame, command=self.log_text.yview)
        scr.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scr.set)

        self.log_bottom = ttk.Frame(self.log_win)
        self.log_bottom.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Button(self.log_bottom, text="Clear Log", command=self._clear_log).pack(side="left")
        self.csv_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.log_bottom, text="Also save as CSV",
                        variable=self.csv_var).pack(side="left", padx=10)
        self.log_path_lbl = ttk.Label(self.log_bottom, text="Log file: (not started yet)")
        self.log_path_lbl.pack(side="left", padx=10)

        # ---------------- Live SCPI Console (own window) ---------------------
        # Shows every raw SCPI command (TX) and reply (RX) for every PSU,
        # whether triggered automatically (cycle/scenario/watchdog/reading
        # poll) or typed manually below. Kept as its own panel/log, separate
        # from the high-level event log above, since raw bus traffic is
        # much higher volume and mostly a debugging/verification aid.
        self.scpi_win = tk.Toplevel(self)
        self.scpi_win.title("Live SCPI Console")
        self.scpi_win.geometry("760x360")
        self.scpi_win.protocol("WM_DELETE_WINDOW",
                                lambda: self._close_live_panel("scpi"))
        self.scpi_win.withdraw()
        self.scpi_frame = ttk.LabelFrame(
            self.scpi_win, text="Live SCPI Console (raw commands, all PSUs)")
        self.scpi_frame.pack(fill="both", expand=True, padx=6, pady=4)
        self.scpi_text = tk.Text(
            self.scpi_frame, height=7, state="disabled", bg="#0a0a1a", fg="#66ccff",
            font=("Consolas", 9))
        self.scpi_text.pack(fill="both", expand=True, side="top")
        scpi_scr = ttk.Scrollbar(self.scpi_frame, command=self.scpi_text.yview)
        self.scpi_text.config(yscrollcommand=scpi_scr.set)

        scpi_input = ttk.Frame(self.scpi_frame)
        scpi_input.pack(fill="x", pady=(2, 4))
        ttk.Label(scpi_input, text="PSU:").pack(side="left", padx=(4, 2))
        self.scpi_psu_var = tk.StringVar(value="1")
        self.scpi_psu_combo = ttk.Combobox(
            scpi_input, textvariable=self.scpi_psu_var,
            values=[str(i) for i in range(1, MAX_PSUS + 1)],
            width=4, state="readonly")
        self.scpi_psu_combo.pack(side="left")
        self.scpi_cmd_var = tk.StringVar()
        scpi_entry = ttk.Entry(scpi_input, textvariable=self.scpi_cmd_var)
        self.scpi_cmd_entry = scpi_entry
        scpi_entry.pack(side="left", padx=6, fill="x", expand=True)
        scpi_entry.bind("<Return>", lambda e: self._scpi_send_manual())
        self.scpi_send_button = ttk.Button(
            scpi_input, text="Send", command=self._scpi_send_manual)
        self.scpi_send_button.pack(side="left", padx=4)
        ttk.Button(scpi_input, text="Clear Console",
                   command=self._clear_scpi_console).pack(side="left", padx=4)
        ttk.Label(
            self.scpi_frame,
            text="Tip: end a command with '?' to query (e.g. V1?, *IDN?); "
                 "anything else is sent as a write command (e.g. V1 12.00, OP1 1).",
            font=("Arial", 8, "italic")
        ).pack(anchor="w", padx=4, pady=(0, 2))

        # ---------------- Live MCU Console (own window) ----------------------
        # Raw TX/RX of the MCU text protocol (automatic PING/RUN/LOOP/STOP
        # from scenarios as well as manually typed lines). The port can also
        # be opened WITHOUT the automatic handshake so PING/READY can be
        # done by hand.
        self.mcu_win = tk.Toplevel(self)
        self.mcu_win.title("Live MCU Console")
        self.mcu_win.geometry("760x400")
        self.mcu_win.protocol("WM_DELETE_WINDOW",
                               lambda: self._close_live_panel("mcu"))
        self.mcu_win.withdraw()
        self.mcu_frame = ttk.LabelFrame(
            self.mcu_win, text="Live MCU Console (raw text protocol)")
        self.mcu_frame.pack(fill="both", expand=True, padx=6, pady=4)

        mcu_port_row = ttk.Frame(self.mcu_frame)
        mcu_port_row.pack(fill="x", pady=(2, 2))
        ttk.Label(mcu_port_row, text="Port:").pack(side="left", padx=(4, 2))
        self.mcu_console_port_var = tk.StringVar(value=self.mcu.port or "")
        self.mcu_console_port_combo = ttk.Combobox(
            mcu_port_row, textvariable=self.mcu_console_port_var, width=16,
            postcommand=lambda: self.mcu_console_port_combo.configure(
                values=self._mcu_console_port_list()))
        self.mcu_console_port_combo.pack(side="left")
        self.mcu_open_button = ttk.Button(
            mcu_port_row, text="Open (no handshake)",
            command=self._mcu_console_open)
        self.mcu_open_button.pack(side="left", padx=4)
        ttk.Button(mcu_port_row, text="Close Port",
                   command=self._mcu_console_close).pack(side="left", padx=4)
        ttk.Label(mcu_port_row, text="Listen (s):").pack(side="left", padx=(12, 2))
        self.mcu_listen_var = tk.StringVar(value="1.0")
        ttk.Spinbox(mcu_port_row, from_=0.2, to=30.0, increment=0.5,
                    textvariable=self.mcu_listen_var, width=5).pack(side="left")

        mcu_text_wrap = ttk.Frame(self.mcu_frame)
        mcu_text_wrap.pack(fill="both", expand=True, side="top")
        self.mcu_text = tk.Text(
            mcu_text_wrap, height=8, state="disabled", bg="#0a1a0a",
            fg="#ffcc66", font=("Consolas", 9))
        mcu_scr = ttk.Scrollbar(mcu_text_wrap, command=self.mcu_text.yview)
        mcu_scr.pack(side="right", fill="y")
        self.mcu_text.pack(fill="both", expand=True, side="left")
        self.mcu_text.config(yscrollcommand=mcu_scr.set)

        mcu_input = ttk.Frame(self.mcu_frame)
        mcu_input.pack(fill="x", pady=(2, 2))
        self.mcu_cmd_var = tk.StringVar()
        self.mcu_cmd_entry = ttk.Entry(mcu_input, textvariable=self.mcu_cmd_var)
        self.mcu_cmd_entry.pack(side="left", padx=4, fill="x", expand=True)
        self.mcu_cmd_entry.bind("<Return>", lambda e: self._mcu_send_manual())
        self.mcu_send_button = ttk.Button(
            mcu_input, text="Send", command=self._mcu_send_manual)
        self.mcu_send_button.pack(side="left", padx=4)
        ttk.Button(mcu_input, text="Clear Console",
                   command=self._clear_mcu_console).pack(side="left", padx=4)

        mcu_quick = ttk.Frame(self.mcu_frame)
        mcu_quick.pack(fill="x", pady=(0, 2))
        ttk.Label(mcu_quick, text="Quick:").pack(side="left", padx=(4, 2))
        for _q in ("PING", "INFO", "SEL:maxwell", "SEL:said",
                   "RUN:1", "LOOP", "STOP"):
            ttk.Button(mcu_quick, text=_q, width=11 if _q.startswith("SEL") else 7,
                       command=lambda c=_q: self._mcu_send_manual(c)).pack(
                side="left", padx=2)
        ttk.Label(
            self.mcu_frame,
            text="Tip: 'Open (no handshake)' opens the port only; send PING "
                 "yourself - a READY reply marks the MCU as Connected. "
                 "Replies are collected for 'Listen (s)' seconds after each send.",
            font=("Arial", 8, "italic"), wraplength=720, justify="left"
        ).pack(anchor="w", padx=4, pady=(0, 2))

        self._update_mode_state()
        self._update_stop_control_state()
        self._update_live_panels_visibility()

    def _make_scrollable_page(self, page):
        """Put a vertically/horizontally scrollable area inside a notebook
        page and return the inner frame that the tab content is built into.
        The inner frame is stretched to the visible width when the window is
        wide enough, so large monitors look the same as before."""
        canvas = tk.Canvas(page, highlightthickness=0, bd=0,
                           yscrollincrement=20, xscrollincrement=20)
        vsb = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        hsb = ttk.Scrollbar(page, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        page.rowconfigure(0, weight=1)
        page.columnconfigure(0, weight=1)
        inner = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        state = {"last": None}

        def _sync(_event=None):
            req_w, req_h = inner.winfo_reqwidth(), inner.winfo_reqheight()
            cw, ch = canvas.winfo_width(), canvas.winfo_height()
            key = (req_w, req_h, cw, ch)
            if key == state["last"]:
                return
            state["last"] = key
            width = max(req_w, cw)
            canvas.itemconfigure(win_id, width=width)
            canvas.configure(scrollregion=(0, 0, width, max(req_h, ch)))

        def _poll():
            # Content can grow/shrink (e.g. Program table shown/hidden)
            # without a <Configure> on the forced-width inner frame.
            try:
                _sync()
                canvas.after(400, _poll)
            except tk.TclError:
                pass

        inner.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _sync)
        canvas.after(400, _poll)
        canvas._page_inner = inner
        self._page_canvases.append(canvas)
        return inner

    def _on_page_wheel(self, event, horizontal=False):
        """Mouse-wheel scrolling of the visible tab page. Widgets that scroll
        themselves (tables, text boxes, lists, dropdowns) are left alone."""
        widget = event.widget
        if not isinstance(widget, tk.Misc):
            return None
        try:
            if widget.winfo_toplevel() is not self:
                return None
            if widget.winfo_class() in ("Treeview", "Text", "Listbox",
                                        "TCombobox", "Combobox", "TSpinbox"):
                return None
        except (tk.TclError, KeyError):
            return None
        if event.state & 0x0004:  # Ctrl held -> timeline zoom
            return None
        canvas = None
        w = widget
        while w is not None:
            if w in self._page_canvases:
                canvas = w
                break
            w = w.master
        if canvas is None:
            return None
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
        if horizontal:
            if canvas.xview() != (0.0, 1.0):
                canvas.xview_scroll(step * 3, "units")
        elif canvas.yview() != (0.0, 1.0):
            canvas.yview_scroll(step * 3, "units")
        return "break"

    def _update_mode_state(self):
        """Enable/disable PSU-table widgets according to Operation Mode.

        Sync     : only PSU1 row fully editable; PSU2..8 all disabled.
                  Its CH1/CH2 On checkboxes decide whether Sync drives
                  that channel on every connected PSU.
        Async    : every row fully editable; CH1/CH2 On checkboxes active
                  per PSU per channel.
        Constant : every row's CHx V/I editable; timing fields disabled;
                  CH1/CH2 On checkboxes active (only ticked channels get
                  steady output).

        A channel whose (PSU, Channel) is currently used by a Power-Up/
        Power-Down scenario step is always forced disabled here, regardless
        of mode - see _refresh_ch_enable_availability.
        """
        mode = self.mode_var.get()
        locked = getattr(self, "_ch_lock_reason", {})

        for i in range(1, MAX_PSUS + 1):
            if mode == "sync":
                row_active = i == 1
                timing_state = "normal" if row_active else "disabled"
                vi_state = "normal" if row_active else "disabled"
                ch_state = "normal" if row_active else "disabled"
            elif mode == "async":
                timing_state = "normal"
                vi_state = "normal"
                ch_state = "normal"
            elif mode == "program":
                # Program mode takes everything from the step table below.
                timing_state = "disabled"
                vi_state = "disabled"
                ch_state = "disabled"
            else:  # constant
                timing_state = "disabled"
                vi_state = "normal"
                ch_state = "normal"

            for key in ("ch1_start", "ch1_dur", "ch2_start", "ch2_dur",
                        "ch1_cycle_off", "ch2_cycle_off"):
                self.async_entries[(i, key)].config(state=timing_state)
            for ch in (1, 2):
                self.async_ch_entries[(i, ch, "v")].config(state=vi_state)
                self.async_ch_entries[(i, ch, "i")].config(state=vi_state)
                final_state = "disabled" if locked.get((i, ch)) else ch_state
                if hasattr(self, "ch_enable_cbs") and (i, ch) in self.ch_enable_cbs:
                    self.ch_enable_cbs[(i, ch)].config(state=final_state)
                if hasattr(self, "opmode_name_entries") and (i, ch) in self.opmode_name_entries:
                    self.opmode_name_entries[(i, ch)].config(state=final_state)

        if hasattr(self, "program_frame"):
            if mode == "program":
                self.program_frame.grid()
            else:
                self.program_frame.grid_remove()
        if hasattr(self, "stop_mode_var"):
            self._update_stop_control_state()
        if hasattr(self, "cycle_preview"):
            self._refresh_cycle_preview()
        if not self._is_engineer_mode():
            self._disable_operator_editing()

    def _update_stop_control_state(self):
        mode = self.mode_var.get() if hasattr(self, "mode_var") else "sync"
        cycles_supported = mode in ("sync", "async", "program")
        if not cycles_supported and self.stop_mode_var.get() == "cycles":
            self.stop_mode_var.set("time")
        use_cycles = cycles_supported and self.stop_mode_var.get() == "cycles"

        time_state = "disabled" if use_cycles else "normal"
        for e in (self.dur_h, self.dur_m, self.dur_s):
            e.config(state=time_state)
        self.unlimited_cb.config(state=time_state)
        if hasattr(self, "sc_dur_entry"):
            self.sc_dur_entry.config(state=time_state)
            self.sc_unlimited_cb.config(state=time_state)
        self.stop_by_time_rb.config(state="normal")
        self.stop_by_cycles_rb.config(state="normal" if cycles_supported else "disabled")
        self.cycle_count_entry.config(state="normal" if use_cycles else "disabled")

    def _update_live_panels_visibility(self):
        """Show/hide the Live Graph/Log/SCPI windows to match their toolbar
        checkboxes. Each panel lives in its own Toplevel (see _build_gui), so
        "showing" it means opening/raising that window rather than packing
        a frame into the main dashboard."""
        if not hasattr(self, "graph_win"):
            return

        # v22: plain bool flags the worker threads can read safely (Tk
        # variables must only be touched from the GUI thread). Raw SCPI/MCU
        # traffic is only queued while its console window is open.
        self._scpi_visible = bool(self.show_scpi_var.get())
        self._mcu_visible = bool(self.show_mcu_var.get())

        for var, win in (
            (self.show_graph_var, self.graph_win),
            (self.show_log_var, self.log_win),
            (self.show_scpi_var, self.scpi_win),
            (self.show_mcu_var, self.mcu_win),
        ):
            if var.get():
                win.deiconify()
                win.lift()
            else:
                win.withdraw()

    def _close_live_panel(self, which):
        """Handle the user closing a Live Graph/Log/SCPI window (X button):
        untick the matching toolbar checkbox and withdraw the window."""
        var = {
            "graph": self.show_graph_var,
            "log": self.show_log_var,
            "scpi": self.show_scpi_var,
            "mcu": self.show_mcu_var,
        }[which]
        var.set(False)
        self._update_live_panels_visibility()

    # --------------------------------------------------------------------
    # CYCLE TIMELINE PREVIEW (Sync/Async)
    # --------------------------------------------------------------------
    def _compute_cycle_preview(self):
        """Build the (rows, window, note) the CycleTimelineCanvas needs,
        reading straight from the 'PSU Settings' entries/combos - exactly
        what _sync_loop/_async_loop_single will use if START is pressed."""
        mode = self.mode_var.get()
        self._cycle_handles = []

        if mode == "program":
            return self._compute_program_preview()

        if mode == "constant":
            return [], 0.0, (
                "Constant mode holds every connected PSU's outputs steadily "
                "ON at the configured V/I - there is no repeating ON/OFF "
                "timeline to preview.")

        def read_float(entry, default=0.0):
            try:
                return float(entry.get())
            except (ValueError, tk.TclError):
                return default

        def channel_label(psu_idx, ch, default):
            entry = getattr(self, "opmode_name_entries", {}).get((psu_idx, ch))
            name = entry.get().strip() if entry is not None else ""
            return name or default

        def channel_enabled(psu_idx, ch):
            var = getattr(self, "ch_enable_vars", {}).get((psu_idx, ch))
            return var.get() if var is not None else True

        def one_psu_row_data(psu_idx, label_prefix):
            ch1_start = read_float(self.async_entries[(psu_idx, "ch1_start")])
            ch1_dur = read_float(self.async_entries[(psu_idx, "ch1_dur")])
            ch2_start = read_float(self.async_entries[(psu_idx, "ch2_start")])
            ch2_dur = read_float(self.async_entries[(psu_idx, "ch2_dur")])
            ch1_cycle_off = read_float(self.async_entries[(psu_idx, "ch1_cycle_off")])
            ch2_cycle_off = read_float(self.async_entries[(psu_idx, "ch2_cycle_off")])

            # A disabled channel (CH1/CH2 On unticked) never turns on, so it
            # is dropped from the preview entirely, same as a zero duration.
            if not channel_enabled(psu_idx, 1):
                ch1_dur = 0.0
            if not channel_enabled(psu_idx, 2):
                ch2_dur = 0.0

            ch1_end = ch1_start + ch1_dur if ch1_dur > 0 else 0.0
            ch2_end = ch2_start + ch2_dur if ch2_dur > 0 else 0.0
            ch1_period = ch1_end + ch1_cycle_off
            ch2_period = ch2_end + ch2_cycle_off
            if ch1_period <= 0 and ch2_period <= 0:
                return []

            # Each channel is fully independent: CH2 can start before,
            # during, or only after CH1's ON window - including not
            # overlapping at all (e.g. CH2 Start >= CH1 Start + CH1 On-Dur
            # turns CH2 on only once CH1 has already turned off).
            rows = []
            if ch1_dur > 0 and ch1_period > 0:
                label = channel_label(psu_idx, 1, f"{label_prefix} CH1")
                rows.append((label, PSU_COLORS.get(psu_idx, "#333333"),
                             [(ch1_start, ch1_end)], False, ch1_period))
                self._cycle_handles.append([
                    (ch1_start, ("async", psu_idx, 1, "start")),
                    (ch1_end, ("async", psu_idx, 1, "on")),
                    (ch1_period + ch1_start, ("async", psu_idx, 1, "off"))])
            if ch2_dur > 0 and ch2_period > 0:
                label = channel_label(psu_idx, 2, f"{label_prefix} CH2")
                rows.append((label, PSU_COLORS_CH2.get(psu_idx, "#666666"),
                             [(ch2_start, ch2_end)], True, ch2_period))
                self._cycle_handles.append([
                    (ch2_start, ("async", psu_idx, 2, "start")),
                    (ch2_end, ("async", psu_idx, 2, "on")),
                    (ch2_period + ch2_start, ("async", psu_idx, 2, "off"))])
            return rows

        if mode == "sync":
            rows = one_psu_row_data(1, "All PSUs (Sync, PSU1)")
            if not rows:
                return [], 0.0, ("Tick PSU1's CH1/CH2 'On' and set its "
                                  "Start(s)/On-Dur(s) above to preview the "
                                  "Synchronous cycle.")
            max_period = max(r[4] for r in rows)
            return rows, max_period * CycleTimelineCanvas.N_PERIODS, ""

        # Asynchronous: one pair of rows per PSU/channel that is enabled and
        # has a non-zero period, each repeating at its OWN period; the drawn
        # window spans the longest one so every PSU's full pattern is
        # visible at least once.
        all_rows = []
        for p in range(1, MAX_PSUS + 1):
            all_rows.extend(one_psu_row_data(p, f"PSU{p}"))
        if not all_rows:
            return [], 0.0, (
                "Tick at least one PSU's CH1/CH2 'On' checkbox and set its "
                "Start(s) and On-Dur(s) above to preview the Asynchronous cycle.")
        max_period = max(r[4] for r in all_rows)
        return all_rows, max_period * CycleTimelineCanvas.N_PERIODS, ""

    def _refresh_cycle_preview(self):
        rows, window, note = self._compute_cycle_preview()
        handles = getattr(self, "_cycle_handles", [])
        self.cycle_preview.edit_cb = self._cycle_preview_edit
        self.cycle_preview.set_pattern(rows, window, note, handles)
        fs = self._fullscreen.get("cycle")
        if fs:
            fs[1].edit_cb = self._cycle_preview_edit
            fs[1].set_pattern(rows, window, note, handles)

    # ---- mouse editing of the Cycle Timeline Preview (v20) ---------------
    _ASYNC_EDIT_FIELDS = {"start": "start", "on": "dur", "off": "cycle_off"}
    _EDIT_MIN = {"start": 0.0, "on": 0.001, "off": 0.0,
                 "wait": 0.0, "cycle_on": 0.001, "cycle_off": 0.0}

    _SC_EDIT_MIN = {"wait": 0.0, "cycle_on": 0.001, "cycle_off": 0.0}

    def _scenario_preview_edit(self, canvas, key, delta, phase):
        """Mouse retiming from the fullscreen Symbol/Step Editor: key is
        (field, step_index); applies orig + delta to that step."""
        field, idx = key[0], key[1]
        steps = canvas.steps
        if phase == "begin":
            self._sc_orig = None
            self._sc_undone = False
            if self._is_engineer_mode() and idx < len(steps):
                self._sc_orig = _safe_float(steps[idx].get(field, 0.0))
            return
        if getattr(self, "_sc_orig", None) is None or idx >= len(steps):
            return
        if phase == "end":
            self._sc_orig = None
            self._refresh_scenario_tree()
            if steps is self.cycle_steps:
                self._refresh_cycle_preview()
            return
        value = round(max(self._sc_orig + delta,
                          self._SC_EDIT_MIN.get(field, 0.0)), 3)
        if not self._sc_undone:
            self._push_undo()
            self._sc_undone = True
        steps[idx][field] = value
        # Light refresh while dragging (rows + previews only).
        row_vals = self._step_row_values(steps[idx])
        if steps is self._current_steps():
            try:
                self.scenario_tree.item(str(idx), values=row_vals)
            except tk.TclError:
                pass
        if steps is self.cycle_steps and self.program_tree is not None:
            try:
                self.program_tree.item(str(idx), values=row_vals)
            except tk.TclError:
                pass
        if steps is self._current_steps():
            self.scenario_preview.set_steps(steps, self.scenario_kind.get())
        canvas.set_steps(steps, canvas.kind)

    def _cycle_preview_edit(self, key, delta, phase):
        """Called by CycleTimelineCanvas while an edge is dragged. Applies
        orig + delta to the matching Cycle Control entry (Sync/Async) or
        Cycle Program step (Program mode) and redraws live."""
        if phase == "begin":
            self._edit_orig = None
            self._edit_undone = False
            if not self._is_engineer_mode():
                return
            if key[0] == "async":
                _k, psu, ch, field = key
                ent = self.async_entries.get(
                    (psu, f"ch{ch}_{self._ASYNC_EDIT_FIELDS[field]}"))
                if ent is not None:
                    self._edit_orig = _safe_float(ent.get())
            else:
                _k, idx, field = key
                if idx < len(self.cycle_steps):
                    self._edit_orig = _safe_float(
                        self.cycle_steps[idx].get(field, 0.0))
            return
        if phase == "end":
            if getattr(self, "_edit_orig", None) is not None:
                if key[0] != "async":
                    self._refresh_scenario_tree()
                self._refresh_cycle_preview()
            self._edit_orig = None
            return
        if getattr(self, "_edit_orig", None) is None:
            return
        field = key[-1]
        floor = self._EDIT_MIN.get(field, 0.0)
        value = round(max(self._edit_orig + delta, floor), 3)
        if key[0] == "async":
            _k, psu, ch, f = key
            ent = self.async_entries[(psu, f"ch{ch}_{self._ASYNC_EDIT_FIELDS[f]}")]
            prev_state = str(ent.cget("state"))
            ent.configure(state="normal")
            ent.delete(0, "end")
            ent.insert(0, f"{value:.3f}")
            ent.configure(state=prev_state)
        else:
            if not self._edit_undone:
                self._push_undo()
                self._edit_undone = True
            self.cycle_steps[key[1]][field] = value
            if self.program_tree is not None:
                self.program_tree.item(
                    str(key[1]), values=self._step_row_values(
                        self.cycle_steps[key[1]]))
        self._refresh_cycle_preview()

    # --------------------------------------------------------------------
    # FULLSCREEN GRAPH / TIMELINE POPUPS
    #   Double-clicking the Live V/I graphs, the Power-Up/Power-Down
    #   Symbol/Step preview, or the Cycle Timeline preview opens a
    #   maximized copy for a closer look; double-clicking it again (or
    #   pressing Esc, or closing the window) returns to normal. The Live
    #   V/I graphs share their underlying data structures with the popup
    #   so it keeps updating live with no extra plumbing; the two timeline
    #   previews are explicitly re-pushed by _refresh_scenario_tree /
    #   _refresh_cycle_preview whenever the underlying data changes, from
    #   either the small view or the popup's own quick-edit controls.
    # --------------------------------------------------------------------
    def _close_fullscreen(self, key):
        entry = self._fullscreen.pop(key, None)
        if entry:
            win, _canvas = entry
            try:
                win.destroy()
            except Exception:
                pass

    def _toggle_fullscreen(self, key, opener):
        if key in self._fullscreen:
            self._close_fullscreen(key)
        else:
            opener()

    def _maximize_toplevel(self, win):
        try:
            win.state("zoomed")
        except tk.TclError:
            try:
                win.attributes("-zoomed", True)
            except tk.TclError:
                win.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")

    def _open_graph_fullscreen(self, which):
        """which: 'v' (Voltage) or 'i' (Current)."""
        key = f"graph_{which}"
        src = self.v_graph if which == "v" else self.i_graph

        win = tk.Toplevel(self)
        win.title(f"{src.title_text} - Fullscreen (double-click graph or Esc to close)")
        win.configure(bg=self._theme.get("bg", "#f0f0f0"))
        self._maximize_toplevel(win)

        big = GraphCanvas(win, src.title_text, src.unit)
        # Share the SAME series/colors/labels dicts as the small graph (not
        # a copy) - every reading pushed into the small graph's deques, and
        # every label update, is therefore visible here too, with no
        # separate refresh loop needed.
        big.series = src.series
        big.colors = src.colors
        big.labels = src.labels
        big.set_theme(self.dark_mode_var.get())
        big.pack(fill="both", expand=True, padx=8, pady=8)

        def _close(_event=None):
            self._close_fullscreen(key)

        big.bind("<Double-Button-1>", _close)
        win.bind("<Escape>", _close)
        win.protocol("WM_DELETE_WINDOW", _close)

        self._fullscreen[key] = (win, big)

    def _open_scenario_preview_fullscreen(self):
        key = "scenario"
        win = tk.Toplevel(self)
        win.title("Power-Up / Power-Down Timeline - Fullscreen (Esc to close)")
        win.configure(bg=self._theme.get("bg", "#f0f0f0"))
        self._maximize_toplevel(win)

        top = ttk.Frame(win)
        top.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(top, text="Scenario type:").pack(side="left")
        ttk.Radiobutton(top, text="Power-Up", variable=self.scenario_kind,
                        value="powerup", command=self._refresh_scenario_tree
                        ).pack(side="left")
        ttk.Radiobutton(top, text="Power-Down", variable=self.scenario_kind,
                        value="powerdown", command=self._refresh_scenario_tree
                        ).pack(side="left")
        ttk.Radiobutton(top, text="Cycle", variable=self.scenario_kind,
                        value="cycle", command=self._refresh_scenario_tree
                        ).pack(side="left")
        ttk.Button(top, text="+ Add Step", command=self._scenario_add_step
                   ).pack(side="left", padx=(16, 2))
        ttk.Button(top, text="\u21b6 Undo", command=self._undo).pack(side="left", padx=2)
        ttk.Button(top, text="\u21b7 Redo", command=self._redo).pack(side="left", padx=2)
        ttk.Button(top, text="+ Add Cycle",
                   command=lambda: self._scenario_add_step(cycle_only=True)
                   ).pack(side="left", padx=2)
        ttk.Label(top, text="(Esc closes)",
                  font=("Arial", 8, "italic")).pack(side="right", padx=4)

        edit_hint = ttk.Label(
            win, text="Drag the dots on the edges with the mouse to retime a "
                      "step. While you hover/drag, a guide shows what every "
                      "other signal is doing at that moment (state, previous/"
                      "next edge and the time difference); edges snap onto "
                      "other signals' edges ('ALIGNED') - hold Shift to move "
                      "freely.",
            font=("Arial", 8, "italic"), wraplength=1100, justify="left")
        edit_hint.pack(fill="x", padx=10, pady=(0, 2))

        # Zoom controls
        zoom_bar = ttk.Frame(win)
        zoom_bar.pack(fill="x", padx=8, pady=(0, 2))

        canvas_wrap = ttk.Frame(win)
        canvas_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        big = ScenarioPreviewCanvas(canvas_wrap)
        big.ROW_H = 34
        big.edit_cb = lambda k, d, p: self._scenario_preview_edit(big, k, d, p)
        big.set_theme(self.dark_mode_var.get())
        big.set_steps(self._current_steps(), self.scenario_kind.get())

        fs_vsb = ttk.Scrollbar(canvas_wrap, orient="vertical", command=big.yview)
        fs_hsb = ttk.Scrollbar(canvas_wrap, orient="horizontal", command=big.xview)
        big.configure(yscrollcommand=fs_vsb.set, xscrollcommand=fs_hsb.set)
        fs_vsb.pack(side="right", fill="y")
        fs_hsb.pack(side="bottom", fill="x")
        big.pack(fill="both", expand=True)

        ttk.Button(zoom_bar, text="＋ Zoom In",
                   command=lambda: big._zoom(ScenarioPreviewCanvas.ZOOM_STEP)
                   ).pack(side="left", padx=2)
        ttk.Button(zoom_bar, text="－ Zoom Out",
                   command=lambda: big._zoom(1.0 / ScenarioPreviewCanvas.ZOOM_STEP)
                   ).pack(side="left", padx=2)
        ttk.Button(zoom_bar, text="⟲ Reset Zoom",
                   command=big.reset_zoom).pack(side="left", padx=2)
        ttk.Label(zoom_bar, text="  Ctrl+Scroll or +/- keys to zoom, R to reset",
                  font=("Arial", 8, "italic")).pack(side="left", padx=8)

        def _close(_event=None):
            self._close_fullscreen(key)

        ttk.Button(top, text="Close", command=_close).pack(side="right", padx=4)
        big.bind("<Key-plus>", lambda e: big._zoom(ScenarioPreviewCanvas.ZOOM_STEP))
        big.bind("<Key-minus>", lambda e: big._zoom(1.0 / ScenarioPreviewCanvas.ZOOM_STEP))
        big.bind("<r>", lambda e: big.reset_zoom())
        win.bind("<Escape>", _close)
        win.protocol("WM_DELETE_WINDOW", _close)

        self._fullscreen[key] = (win, big)

    def _open_cycle_preview_fullscreen(self):
        key = "cycle"
        win = tk.Toplevel(self)
        win.title("Cycle Timeline Preview - Fullscreen (Esc to close)")
        win.configure(bg=self._theme.get("bg", "#f0f0f0"))
        self._maximize_toplevel(win)

        top = ttk.Frame(win)
        top.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(
            top,
            text=f"Mode: {self.mode_var.get().capitalize()}  -  edit the timing "
                 "fields below; the graph (and the main window's table) update live.",
            font=("Arial", 9, "bold")
        ).pack(side="left")
        ttk.Label(top, text="(double-click the graph, or Esc, to close)",
                  font=("Arial", 8, "italic")).pack(side="right", padx=4)

        # Zoom controls
        zoom_bar = ttk.Frame(win)
        zoom_bar.pack(fill="x", padx=8, pady=(0, 2))

        canvas_wrap = ttk.Frame(win)
        canvas_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        # Canvas first so it claims the expand space; Quick Edit stays at bottom.
        big = CycleTimelineCanvas(canvas_wrap)
        big.edit_cb = self._cycle_preview_edit
        big.set_theme(self.dark_mode_var.get())

        fs_vsb = ttk.Scrollbar(canvas_wrap, orient="vertical", command=big.yview)
        fs_hsb = ttk.Scrollbar(canvas_wrap, orient="horizontal", command=big.xview)
        big.configure(yscrollcommand=fs_vsb.set, xscrollcommand=fs_hsb.set)
        fs_vsb.pack(side="right", fill="y")
        fs_hsb.pack(side="bottom", fill="x")
        big.pack(fill="both", expand=True)

        ttk.Button(zoom_bar, text="＋ Zoom In",
                   command=lambda: big._zoom(CycleTimelineCanvas.ZOOM_STEP)
                   ).pack(side="left", padx=2)
        ttk.Button(zoom_bar, text="－ Zoom Out",
                   command=lambda: big._zoom(1.0 / CycleTimelineCanvas.ZOOM_STEP)
                   ).pack(side="left", padx=2)
        ttk.Button(zoom_bar, text="⟲ Reset Zoom",
                   command=big.reset_zoom).pack(side="left", padx=2)
        ttk.Label(zoom_bar, text="  Ctrl+Scroll or +/- keys to zoom, R to reset",
                  font=("Arial", 8, "italic")).pack(side="left", padx=8)

        # ---- Quick Edit: mirrors the PSU Settings table's per-channel
        # Start(s)/On-Dur(s) columns. Editing here writes straight into the
        # real widgets in the main window (self.async_entries), so the two
        # views can never drift apart - there is exactly one source of
        # truth, this is just another way to edit it while watching the
        # big graph (e.g. to visually confirm CH2 only turns on after CH1
        # has turned off, by setting CH2 Start >= CH1 Start + CH1 On-Dur).
        edit_frame = ttk.LabelFrame(
            win, text="Quick Edit (writes directly into the main PSU Settings table)")
        edit_frame.pack(fill="x", padx=8, pady=(0, 8))
        for c, text in enumerate(
                ("CH1\nOn", "CH2\nOn", "PSU", "CH1 Start(s)", "CH1 On-Dur(s)",
                 "CH2 Start(s)", "CH2 On-Dur(s)",
                 "CH1 Cycle OFF(s)", "CH2 Cycle OFF(s)")):
            ttk.Label(edit_frame, text=text, font=("Arial", 8, "bold")).grid(
                row=0, column=c, padx=4)

        def make_text_writer(main_entry, popup_entry):
            def _on_key(_event=None):
                val = popup_entry.get()
                if main_entry.get() != val:
                    main_entry.delete(0, "end")
                    main_entry.insert(0, val)
                self._refresh_cycle_preview()
            return _on_key

        for i in range(1, MAX_PSUS + 1):
            for ch, col in ((1, 0), (2, 1)):
                ttk.Checkbutton(
                    edit_frame, variable=self.ch_enable_vars[(i, ch)],
                    command=self._refresh_cycle_preview
                ).grid(row=i, column=col, padx=2)
            ttk.Label(edit_frame, text=f"PSU{i}").grid(row=i, column=2, padx=4, pady=1)
            for col, ek in enumerate(
                    ("ch1_start", "ch1_dur", "ch2_start", "ch2_dur",
                     "ch1_cycle_off", "ch2_cycle_off"), start=3):
                e = ttk.Entry(edit_frame, width=7)
                e.insert(0, self.async_entries[(i, ek)].get())
                e.grid(row=i, column=col, padx=2)
                _bind_numeric_entry(e)
                e.bind("<KeyRelease>",
                       make_text_writer(self.async_entries[(i, ek)], e))

        def _close(_event=None):
            self._close_fullscreen(key)

        big.bind("<Double-Button-1>", _close)
        big.bind("<Key-plus>", lambda e: big._zoom(CycleTimelineCanvas.ZOOM_STEP))
        big.bind("<Key-minus>", lambda e: big._zoom(1.0 / CycleTimelineCanvas.ZOOM_STEP))
        big.bind("<r>", lambda e: big.reset_zoom())
        win.bind("<Escape>", _close)
        win.protocol("WM_DELETE_WINDOW", _close)

        self._fullscreen[key] = (win, big)

        # Force geometry to settle (maximize + pack), then push pattern data
        # and redraw. A second deferred redraw covers late size changes on
        # some window managers (esp. Raspberry Pi / LXDE).
        def _populate():
            try:
                win.update_idletasks()
            except Exception:
                pass
            self._refresh_cycle_preview()
            try:
                big._draw()
            except Exception:
                pass

        win.after(0, _populate)
        win.after(80, _populate)

    # --------------------------------------------------------------------
    # DARK MODE
    #   Re-themes every ttk widget application-wide via a single shared
    #   ttk.Style (so it also applies to widgets in Toplevel dialogs created
    #   later, e.g. ScenarioStepDialog), plus the few plain tk widgets that
    #   don't follow ttk styling (root background, the two scrollable
    #   canvases, the graphs, and the scenario timeline preview). The Live
    #   Log and SCPI Console keep their own fixed dark high-contrast
    #   palette regardless of theme, and EMERGENCY OFF keeps its fixed
    #   red/white styling - safety-critical widgets shouldn't change
    #   appearance based on a cosmetic preference.
    # --------------------------------------------------------------------
    def _toggle_dark_mode(self):
        self._apply_theme(self.dark_mode_var.get())

    def _apply_theme(self, dark):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        if dark:
            bg, fg = "#1e1e1e", "#e0e0e0"
            field_bg = "#2b2b2b"
            sel_bg = "#3a3a3a"
            border = "#4a4a4a"
        else:
            bg, fg = "#f0f0f0", "#000000"
            field_bg = "#ffffff"
            sel_bg = "#cfe8ff"
            border = "#999999"

        self._theme = {"bg": bg, "fg": fg, "field_bg": field_bg}

        style.configure(".", background=bg, foreground=fg)
        style.configure("TFrame", background=bg)
        style.configure("TLabelframe", background=bg, foreground=fg, bordercolor=border)
        style.configure("TLabelframe.Label", background=bg, foreground=fg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TButton", background=field_bg, foreground=fg)
        style.map("TButton", background=[("active", sel_bg)])
        style.configure("TCheckbutton", background=bg, foreground=fg)
        style.map("TCheckbutton", background=[("active", bg)])
        style.configure("TRadiobutton", background=bg, foreground=fg)
        style.map("TRadiobutton", background=[("active", bg)])
        style.configure("TEntry", fieldbackground=field_bg, foreground=fg, insertcolor=fg)
        style.configure("TCombobox", fieldbackground=field_bg, foreground=fg)
        style.map("TCombobox",
                  fieldbackground=[("readonly", field_bg)],
                  foreground=[("readonly", fg)])
        style.configure("Treeview", background=field_bg, fieldbackground=field_bg,
                        foreground=fg)
        style.map("Treeview", background=[("selected", sel_bg)])
        style.configure("Treeview.Heading", background=bg, foreground=fg)
        style.configure("TScrollbar", background=field_bg)
        style.configure("TSeparator", background=border)
        style.configure("Test.Horizontal.TProgressbar",
                        background="#28a745", lightcolor="#28a745",
                        darkcolor="#218838", troughcolor=field_bg)
        # v18: the tabbed dashboard's Notebook needs its own theming too,
        # otherwise the tab strip stayed in the light-mode colors in Dark
        # Mode.
        style.configure("TNotebook", background=bg, bordercolor=border)
        style.configure("TNotebook.Tab", background=field_bg, foreground=fg)
        style.map("TNotebook.Tab",
                  background=[("selected", sel_bg)],
                  foreground=[("selected", fg)])

        self.configure(bg=bg)
        for win in (getattr(self, "graph_win", None), getattr(self, "log_win", None),
                    getattr(self, "scpi_win", None)):
            if win is not None:
                try:
                    win.configure(bg=bg)
                except Exception:
                    pass

        for cv in (getattr(self, "_gui_canvas", None), getattr(self, "_conn_canvas", None),
                   *getattr(self, "_page_canvases", ())):
            if cv is not None:
                cv.configure(bg=bg)

        for gc in (getattr(self, "v_graph", None), getattr(self, "i_graph", None)):
            if gc is not None:
                gc.set_theme(dark)

        if hasattr(self, "scenario_preview"):
            self.scenario_preview.set_theme(dark)

        if hasattr(self, "cycle_preview"):
            self.cycle_preview.set_theme(dark)

        for win, canvas in getattr(self, "_fullscreen", {}).values():
            try:
                win.configure(bg=bg)
                canvas.set_theme(dark)
            except Exception:
                pass

    def _build_scenario_editor(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x")
        ttk.Label(top, text="Scenario type:").pack(side="left")
        self.scenario_kind = tk.StringVar(value="powerup")
        self._allow_operator(ttk.Radiobutton(
            top, text="Power-Up", variable=self.scenario_kind,
            value="powerup", command=self._refresh_scenario_tree)).pack(side="left")
        self._allow_operator(ttk.Radiobutton(
            top, text="Power-Down", variable=self.scenario_kind,
            value="powerdown", command=self._refresh_scenario_tree)).pack(side="left")
        self._allow_operator(ttk.Radiobutton(
            top, text="Cycle", variable=self.scenario_kind,
            value="cycle", command=self._refresh_scenario_tree)).pack(side="left")
        self._allow_operator(ttk.Button(
            top, text="Load...", command=self._scenario_load_dialog)).pack(
            side="left", padx=6)
        ttk.Button(top, text="Save...", command=self._scenario_save_dialog).pack(
            side="left", padx=6)
        # Small live mirror of the MCU connection status (see Connection
        # Status panel above) right where MCU steps get added, so the
        # operator doesn't have to scroll up to check before scheduling one.
        self.mcu_status_label_editor = ttk.Label(
            top, text="MCU: \u25cb Not Connected", foreground="red")
        self.mcu_status_label_editor.pack(side="right", padx=6)

        # Which Power-Up/Power-Down scenario file (if any) is currently
        # loaded/saved for each scenario type - shown next to the "Run Full
        # Cycle" button below (see btns2), not here, so the operator sees
        # both at a glance right where they press Run. See
        # _scenario_load_dialog/_scenario_save_dialog and
        # _update_loaded_scenario_label.
        self.loaded_scenario_paths = {"powerup": None, "powerdown": None,
                                      "cycle": None}

        cols = ("psu", "ch", "action", "wait", "voltage", "current",
                "characteristic", "cycle", "cycle_limit", "repeat", "name")
        scenario_tree_wrap = ttk.Frame(parent)
        scenario_tree_wrap.pack(fill="x", pady=2)
        self.scenario_tree = ttk.Treeview(
            scenario_tree_wrap, columns=cols, show="headings", height=5)
        headings = {
            "psu": "PSU", "ch": "Channel", "action": "Action",
            "wait": "Wait After(s)", "voltage": "Voltage(V)",
            "current": "Current(A)", "characteristic": "Output Char.",
            "cycle": "Cycle On/Off/Count",
            "cycle_limit": "Cycle Limit(s)",
            "repeat": "MCU Cmd",
            "name": "Name / MCU Signals",
        }
        for c, w in zip(
                cols, (50, 60, 70, 90, 70, 70, 90, 110, 85, 90, 140)):
            self.scenario_tree.heading(c, text=headings[c])
            self.scenario_tree.column(c, width=w, anchor="center")
        scenario_hsb = ttk.Scrollbar(
            scenario_tree_wrap, orient="horizontal",
            command=self.scenario_tree.xview)
        self.scenario_tree.configure(xscrollcommand=scenario_hsb.set)
        self.scenario_tree.pack(fill="x")
        scenario_hsb.pack(fill="x")

        self.scenario_tree.bind("<Double-1>", self._on_tree_double_click)
        self.scenario_tree.bind("<Button-1>", self._destroy_cell_editor, add="+")

        ttk.Label(
            parent,
            text='Tip: double-click a cell to edit it. "Wait After(s)" is measured '
                 "from t=0 (scenario start), not from the previous step. "
                 "Cycle Limit(s) is relative to t=0; blank means no time limit.",
            font=("Arial", 8, "italic"), justify="left", wraplength=520
        ).pack(anchor="w")

        # v20: Cycle duration + countdown right here in the Scenario Monitor.
        # Same fields as Cycle Control's "Total Operation Time" (shared), so
        # either tab can be used; the countdown starts when Run Cycle / START
        # TEST reaches the Cycle phase.
        cyc_dur_frame = ttk.LabelFrame(
            parent, text="Cycle Duration (Run Cycle / Cycle phase of START TEST)")
        cyc_dur_frame.pack(fill="x", pady=(4, 2))
        ttk.Label(cyc_dur_frame, text="Duration (hh:mm:ss):").grid(
            row=0, column=0, padx=4, pady=2)
        self.sc_dur_entry = ttk.Entry(
            cyc_dur_frame, width=10, justify="center",
            textvariable=self.dur_var)
        _bind_time_entry(self.sc_dur_entry)
        self.sc_dur_entry.grid(row=0, column=1, padx=(0, 6))
        self.sc_unlimited_cb = ttk.Checkbutton(
            cyc_dur_frame, text="Unlimited (manual stop)",
            variable=self.unlimited_var,
            command=self._update_stop_control_state)
        self.sc_unlimited_cb.grid(row=0, column=2, padx=8)
        self.sc_cycle_label = ttk.Label(
            cyc_dur_frame, text="Cycle remaining: --:--:--",
            font=("Arial", 10, "bold"))
        self.sc_cycle_label.grid(row=0, column=3, padx=14)

        test_frame = ttk.LabelFrame(
            parent, text="Test Time (Power-Up \u2192 Power-Down dwell)")
        test_frame.pack(fill="x", pady=(4, 2))
        ttk.Label(test_frame, text="Duration (hr:min:sec):").grid(
            row=0, column=0, padx=4, pady=2)
        self.test_h = ttk.Entry(test_frame, width=4)
        self.test_h.insert(0, "00")
        self.test_m = ttk.Entry(test_frame, width=4)
        self.test_m.insert(0, "05")
        self.test_s = ttk.Entry(test_frame, width=4)
        self.test_s.insert(0, "00")
        for _e in (self.test_h, self.test_m, self.test_s):
            _bind_numeric_entry(_e)
        self.test_h.grid(row=0, column=1)
        ttk.Label(test_frame, text=":").grid(row=0, column=2)
        self.test_m.grid(row=0, column=3)
        ttk.Label(test_frame, text=":").grid(row=0, column=4)
        self.test_s.grid(row=0, column=5)
        self.test_label = ttk.Label(
            test_frame, text="Remaining: --:--:--", font=("Arial", 9, "bold"))
        self.test_label.grid(row=0, column=6, padx=14)
        # Fills from 0 -> 100 % as the Test Time countdown runs (pause-aware,
        # driven from _update_timer_label).
        self.test_progress_var = tk.DoubleVar(value=0.0)
        self.test_progress = ttk.Progressbar(
            test_frame, orient="horizontal", mode="determinate",
            style="Test.Horizontal.TProgressbar",
            maximum=100.0, variable=self.test_progress_var)
        self.test_progress.grid(row=1, column=0, columnspan=7, sticky="ew",
                                padx=4, pady=(2, 4))
        self.test_progress_lbl = ttk.Label(
            test_frame, text="0 %", width=7, anchor="e")
        self.test_progress_lbl.grid(row=1, column=7, padx=(0, 6))
        test_frame.columnconfigure(6, weight=1)

        btns = ttk.Frame(parent)
        btns.pack(fill="x", pady=(2, 0))
        ttk.Button(btns, text="+ Add Step",
                   command=self._scenario_add_step).pack(side="left", padx=2)
        ttk.Button(btns, text="+ Add Cycle",
                   command=lambda: self._scenario_add_step(
                       cycle_only=True)).pack(side="left", padx=2)
        ttk.Button(btns, text="Delete",
                   command=self._scenario_delete_step).pack(side="left", padx=2)
        ttk.Button(btns, text="\u2191", width=3,
                   command=lambda: self._scenario_move(-1)).pack(side="left", padx=2)
        ttk.Button(btns, text="\u2193", width=3,
                   command=lambda: self._scenario_move(1)).pack(side="left", padx=2)
        ttk.Separator(btns, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(btns, text="\u21b6 Undo (Ctrl+Z)",
                   command=self._undo).pack(side="left", padx=2)
        ttk.Button(btns, text="\u21b7 Redo (Ctrl+Y)",
                   command=self._redo).pack(side="left", padx=2)

        btns2 = ttk.Frame(parent)
        btns2.pack(fill="x", pady=(2, 0))
        self._allow_operator(ttk.Button(
            btns2, text="Run Power-Up",
            command=lambda: self._run_scenario("powerup"))).pack(
            side="left", padx=2)
        self._allow_operator(ttk.Button(
            btns2, text="Run Power-Down",
            command=lambda: self._run_scenario("powerdown"))).pack(
            side="left", padx=2)
        self._allow_operator(ttk.Button(
            btns2, text="Run Cycle",
            command=self._run_cycle_program)).pack(side="left", padx=2)
        self._allow_operator(ttk.Button(
            btns2, text="Stop Cycle",
            command=self._stop_cycle_phase)).pack(side="left", padx=2)
        self._allow_operator(ttk.Button(
            btns2, text="START TEST (Power-Up + Cycle + test + Power-Down)",
            command=self._run_full_cycle)).pack(side="left", padx=(8, 2))
        self._allow_operator(ttk.Button(
            btns2, text="STOP TEST",
            command=self._stop_test)).pack(side="left", padx=2)
        self._allow_operator(ttk.Button(
            btns2, text="PAUSE TEST",
            command=self._toggle_pause)).pack(side="left", padx=2)
        btns2b = ttk.Frame(parent)
        btns2b.pack(fill="x", pady=(0, 0))
        # Shows which Power-Up/Power-Down scenario file (if any) is
        # currently loaded/saved, right next to the button that runs them,
        # so the operator can see exactly what will run without having to
        # switch the "Scenario type" radio button above or check the log.
        self.loaded_scenario_lbl = ttk.Label(
            btns2b, text="Power-Up: (none)  |  Power-Down: (none)  |  Cycle: (none)",
            font=("Arial", 8, "italic"))
        self.loaded_scenario_lbl.pack(side="left", padx=4)

        ttk.Label(
            parent,
            text="Symbol / Step Editor (ON/OFF timeline preview) - starts empty; "
                 "a row is added automatically for each PSU/Channel used by a step. "
                 "Double-click the graph for fullscreen.",
            font=("Arial", 9, "bold"), wraplength=520, justify="left"
        ).pack(anchor="w", pady=(4, 0))
        preview_wrap = ttk.Frame(parent)
        preview_wrap.pack(fill="x", pady=2)
        self.scenario_preview = ScenarioPreviewCanvas(
            preview_wrap,
            height=ScenarioPreviewCanvas.ROW_H * ScenarioPreviewCanvas.VISIBLE_ROWS + 26)
        preview_vsb = ttk.Scrollbar(
            preview_wrap, orient="vertical", command=self.scenario_preview.yview)
        preview_hsb = ttk.Scrollbar(
            preview_wrap, orient="horizontal", command=self.scenario_preview.xview)
        self.scenario_preview.configure(yscrollcommand=preview_vsb.set,
                                        xscrollcommand=preview_hsb.set)
        preview_vsb.pack(side="right", fill="y")
        preview_hsb.pack(side="bottom", fill="x")
        self.scenario_preview.pack(side="left", fill="x", expand=True)
        self.scenario_preview.bind(
            "<Double-Button-1>",
            lambda e: self._toggle_fullscreen(
                "scenario", self._open_scenario_preview_fullscreen))
        self.scenario_preview.bind(
            "<Key-plus>",
            lambda e: self.scenario_preview._zoom(ScenarioPreviewCanvas.ZOOM_STEP))
        self.scenario_preview.bind(
            "<Key-minus>",
            lambda e: self.scenario_preview._zoom(1.0 / ScenarioPreviewCanvas.ZOOM_STEP))
        self.scenario_preview.bind("<r>", lambda e: self.scenario_preview.reset_zoom())

        # v14: Live Current/Voltage monitor table - fills the space below
        # the Symbol/Step Editor preview. One row per PSU/Channel (fixed,
        # MAX_PSUS x 2), showing the commanded (Set) and actually measured
        # (Actual, from the per-PSU reading thread - see
        # _reading_worker_for_psu) V/I plus live Output/CV-CC status.
        # Updated from the same "reading"/"conn" messages already flowing
        # through _process_queue, so it stays live during Sync/Async/
        # Constant continuous cycles as well as Scenario/Full Cycle runs.
        monitor_hdr = ttk.Frame(parent)
        monitor_hdr.pack(fill="x", pady=(6, 0))
        ttk.Label(
            monitor_hdr, text="Live Current/Voltage Monitor",
            font=("Arial", 9, "bold")).pack(side="left", anchor="w")
        # Manual refresh: re-derives every row's PSU/CH label from the
        # latest Operation Mode Name / scenario step Name (see
        # _monitor_label_for), for whichever PSUs/channels are currently
        # selected/enabled - useful right after typing a new Name without
        # waiting for the next bulk refresh trigger (add/delete/move/undo/
        # redo/scenario load - see _refresh_all_monitor_labels).
        ttk.Button(
            monitor_hdr, text="\U0001f504 Refresh",
            command=self._refresh_all_monitor_labels).pack(side="left", padx=8)
        ttk.Label(monitor_hdr, text="Reading interval:").pack(
            side="left", padx=(8, 2))
        self.reading_interval_var = tk.StringVar(
            value=READING_POLL_LABELS[self.reading_interval_ms])
        reading_combo = ttk.Combobox(
            monitor_hdr, textvariable=self.reading_interval_var,
            values=[label for label, _ in READING_POLL_OPTIONS],
            width=7, state="readonly")
        reading_combo.pack(side="left")
        reading_combo.bind("<<ComboboxSelected>>",
                           self._on_reading_interval_selected)
        self.reading_load_lbl = ttk.Label(
            monitor_hdr, text=self._reading_load_text(), foreground="#666666")
        self.reading_load_lbl.pack(side="left", padx=6)
        ttk.Button(monitor_hdr, text="What to read...",
                   command=self._open_monitor_selection).pack(
            side="left", padx=(2, 0))
        monitor_wrap = ttk.Frame(parent)
        monitor_wrap.pack(fill="x", pady=2)
        mon_cols = ("psu_ch", "set_v", "set_i", "act_v", "act_i", "output")
        self.monitor_tree = ttk.Treeview(
            monitor_wrap, columns=mon_cols, show="headings",
            height=min(10, MAX_PSUS * 2))
        mon_headings = {
            "psu_ch": "PSU / CH", "set_v": "Set V", "set_i": "Set I",
            "act_v": "Actual V", "act_i": "Actual I", "output": "Output",
        }
        for c, w in zip(mon_cols, (80, 70, 70, 80, 80, 70)):
            self.monitor_tree.heading(c, text=mon_headings[c])
            self.monitor_tree.column(c, width=w, anchor="center")
        mon_vsb = ttk.Scrollbar(
            monitor_wrap, orient="vertical", command=self.monitor_tree.yview)
        self.monitor_tree.configure(yscrollcommand=mon_vsb.set)
        mon_vsb.pack(side="right", fill="y")
        self.monitor_tree.pack(side="left", fill="x", expand=True)
        self.monitor_tree.tag_configure("disconnected", foreground="#999999")
        for p in range(1, MAX_PSUS + 1):
            for ch in (1, 2):
                self.monitor_tree.insert(
                    "", "end", iid=f"mon_{p}_{ch}",
                    values=(self._monitor_label_for(p, ch), "-", "-", "-", "-", "-"),
                    tags=("disconnected",))

        self._refresh_scenario_tree()

    # --------------------------------------------------------------------
    # INLINE CELL EDITING FOR THE SCENARIO TABLE
    # --------------------------------------------------------------------
    def _destroy_cell_editor(self, _event=None):
        if self._cell_editor is not None:
            editor = self._cell_editor
            self._cell_editor = None
            try:
                if editor.winfo_exists():
                    commit_fn = getattr(editor, "_commit", None)
                    if commit_fn and self._is_engineer_mode():
                        commit_fn()
                    editor.destroy()
            except tk.TclError:
                pass

    def _on_tree_double_click(self, event):
        if not self._is_engineer_mode():
            return
        tree = event.widget
        region = tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = tree.identify_row(event.y)
        col_id = tree.identify_column(event.x)
        if not row_id or not col_id:
            return

        self._destroy_cell_editor()

        col_index = int(col_id.replace("#", "")) - 1
        cols = ("psu", "ch", "action", "wait", "voltage", "current",
                "characteristic", "cycle", "cycle_limit", "repeat", "name")
        if col_index < 0 or col_index >= len(cols):
            return
        col_name = cols[col_index]

        idx = int(row_id)
        steps = self._steps_for_tree(tree)
        if idx >= len(steps):
            return
        step = steps[idx]
        is_mcu = step.get("action") == "MCU"
        is_cycle = step.get("action") == "CYCLE"

        # PSU/Channel/Voltage/Current are meaningless for a MCU step,
        # "repeat" is meaningless for a non-MCU step, and "cycle" is
        # meaningless for anything other than a CYCLE step -- editing any
        # of these mismatched combinations in place would silently corrupt
        # the row, so it's blocked here (delete + re-add via the dialog
        # instead). "name" is valid for every action (it maps to "name" or
        # "mcu_signals" as needed).
        if is_mcu and col_name in ("psu", "ch", "voltage", "current",
                                   "characteristic", "cycle", "cycle_limit"):
            return
        if not is_mcu and col_name == "repeat":
            return
        if not is_cycle and col_name in ("cycle", "cycle_limit"):
            return

        bbox = tree.bbox(row_id, col_id)
        if not bbox:
            return
        x, y, w, h = bbox

        if col_name == "repeat":
            cmd = _mcu_step_cmd(step)
            current_value = (f"RUN:{step.get('mcu_repeat', 1)}"
                              if cmd == "RUN" else cmd)
        elif col_name == "cycle":
            raw_count = _safe_float(step.get("cycle_count", 0))
            count = (int(raw_count)
                     if math.isfinite(raw_count) and raw_count >= 0 else 0)
            current_value = (
                f"{_safe_float(step.get('cycle_on', 1.0)):.3f}/"
                f"{_safe_float(step.get('cycle_off', 1.0)):.3f}/"
                f"{count}")
        elif col_name == "cycle_limit":
            current_value = step.get("cycle_duration", "")
        elif col_name == "wait":
            current_value = f"{step.get('wait', 0.0):.3f}"
        elif col_name == "name":
            current_value = step.get("mcu_signals", "") if is_mcu else step.get("name", "")
        elif col_name == "characteristic":
            current_value = step.get("characteristic", "Custom Limits")
        else:
            current_value = step.get(
                col_name, 0.0 if col_name in ("voltage", "current") else "")

        combo_values = {
            "psu": [str(i) for i in range(1, MAX_PSUS + 1)],
            "ch": ["1", "2"],
            "action": ["ON", "OFF", "CYCLE", "MCU"],
            "characteristic": OUTPUT_CHARACTERISTIC_NAMES,
            "repeat": ["PING", "RUN:1", "RUN:2", "RUN:5", "RUN:10", "LOOP", "STOP"],
        }

        def commit():
            raw = var.get()
            try:
                if col_name == "repeat":
                    self._push_undo()
                    raw_up = raw.strip().upper()
                    if raw_up.startswith("RUN"):
                        step["mcu_cmd"] = "RUN"
                        step["mcu_loop"] = False
                        n_part = raw_up.split(":", 1)[1] if ":" in raw_up else "1"
                        try:
                            step["mcu_repeat"] = max(1, int(float(n_part)))
                        except ValueError:
                            step["mcu_repeat"] = 1
                    elif raw_up in ("PING", "LOOP", "STOP"):
                        step["mcu_cmd"] = raw_up
                        step["mcu_loop"] = raw_up == "LOOP"
                    return
                if col_name == "cycle":
                    # "on/off/count" - count 0 means "until STOP/EMERGENCY".
                    parts = raw.split("/")
                    if len(parts) != 3:
                        return
                    try:
                        on_t = max(float(parts[0]), 0.0)
                        off_t = max(float(parts[1]), 0.0)
                        cnt = max(int(float(parts[2])), 0)
                    except ValueError:
                        return
                    self._push_undo()
                    step["cycle_on"] = on_t
                    step["cycle_off"] = off_t
                    step["cycle_count"] = cnt
                    return
                if col_name == "cycle_limit":
                    if not raw.strip():
                        new_limit = None
                    else:
                        try:
                            new_limit = float(raw)
                        except ValueError:
                            messagebox.showerror(
                                "Invalid Cycle Limit",
                                "Enter a positive number or leave the limit blank.")
                            return
                        if not math.isfinite(new_limit) or new_limit <= 0:
                            messagebox.showerror(
                                "Invalid Cycle Limit",
                                "Cycle Limit must be a positive finite number, "
                                "or blank for no time limit.")
                            return
                    self._push_undo()
                    if new_limit is None:
                        step.pop("cycle_duration", None)
                    else:
                        step["cycle_duration"] = new_limit
                    return
                if col_name == "name":
                    self._push_undo()
                    step["mcu_signals" if is_mcu else "name"] = raw.strip()
                    if not is_mcu:
                        # Keep the Live Monitor's PSU/CH label in sync
                        # immediately, without waiting for the next
                        # reading/conn message.
                        self._update_monitor_row(step.get("psu"), ch=step.get("ch"))
                    return
                if col_name in ("psu", "ch"):
                    new_val = int(raw)
                elif col_name in ("wait", "voltage", "current"):
                    new_val = float(raw)
                elif col_name == "action":
                    new_val = raw
                    # Switching a row to/from MCU or CYCLE in place would
                    # leave stale psu/ch/voltage/current/mcu_repeat/
                    # cycle_on/cycle_off/cycle_count fields lying around;
                    # keep it simple and block it here too -- delete +
                    # re-add via the dialog covers this case.
                    if (new_val in ("MCU", "CYCLE")
                            or step.get("action") in ("MCU", "CYCLE")):
                        return
                else:
                    new_val = raw
            except ValueError:
                return

            if col_name in ("voltage", "current") and not step.get(
                    "allow_over_limit", False):
                limit = (LIMIT_VOLTAGE_MAX if col_name == "voltage"
                         else LIMIT_CURRENT_MAX)
                unit = "V" if col_name == "voltage" else "A"
                if new_val > limit:
                    messagebox.showerror(
                        "Error",
                        f"{col_name.capitalize()} value ({new_val}) exceeds the "
                        f"safety limit ({limit:.0f}{unit}).\nThis step does not "
                        "have 'allow over limit' set, so the edit was rejected. "
                        "If intentional, delete the step and re-add it with the "
                        "override checkbox.")
                    return

            self._push_undo()
            step[col_name] = new_val

        def on_commit_and_close(_event=None):
            commit()
            self._destroy_cell_editor()
            self._refresh_scenario_tree()
            tree.selection_set(row_id)

        def on_cancel(_event=None):
            self._cell_editor = None
            editor.destroy()

        var = tk.StringVar(value=str(current_value))

        if col_name in combo_values:
            editor = ttk.Combobox(
                tree, textvariable=var, values=combo_values[col_name],
                state="readonly")
            editor.bind("<<ComboboxSelected>>", on_commit_and_close)
        else:
            editor = ttk.Entry(tree, textvariable=var, justify="center")
            editor.select_range(0, "end")
            if col_name != "name":
                _bind_numeric_entry(editor)

        editor.place(x=x, y=y, width=w, height=h)
        editor.focus_set()
        editor._commit = commit

        editor.bind("<Return>", on_commit_and_close)
        editor.bind("<KP_Enter>", on_commit_and_close)
        editor.bind("<Escape>", on_cancel)

        self._cell_editor = editor

    # --------------------------------------------------------------------
    # SCENARIO EDITOR LOGIC
    # --------------------------------------------------------------------
    def _steps_for_kind(self, kind):
        if kind == "powerup":
            return self.powerup_steps
        if kind == "cycle":
            return self.cycle_steps
        return self.powerdown_steps

    def _current_steps(self):
        return self._steps_for_kind(self.scenario_kind.get())

    def _steps_for_tree(self, tree):
        """Cycle Control's program table always edits the Cycle steps; the
        Scenario Editor's table edits whichever type is selected."""
        if self.program_tree is not None and tree is self.program_tree:
            return self.cycle_steps
        return self._current_steps()

    def _step_row_values(self, step):
        is_mcu = step.get("action") == "MCU"
        if is_mcu:
            cmd = _mcu_step_cmd(step)
            repeat_txt = (f"RUN x{step.get('mcu_repeat', 1)}"
                          if cmd == "RUN" else cmd)
            name_txt = step.get("mcu_signals", "") or "-"
            prof = (step.get("mcu_profile") or "").strip()
            if prof:
                repeat_txt = f"{repeat_txt} [{prof}]"
            return ("-", "-", "MCU", f"{step['wait']:.3f}", "-", "-",
                    "-", "-", "-", repeat_txt, name_txt)
        name_txt = step.get("name", "") or "-"
        if step.get("action") == "CYCLE":
            raw_count = _safe_float(step.get("cycle_count", 0))
            count = (int(raw_count)
                     if math.isfinite(raw_count) and raw_count > 0 else 0)
            cycle_txt = (
                f"{_safe_float(step.get('cycle_on', 1.0)):.2f}/"
                f"{_safe_float(step.get('cycle_off', 1.0)):.2f}/"
                f"{count if count > 0 else '\u221e'}")
        else:
            cycle_txt = "-"
        cycle_limit = step.get("cycle_duration")
        cycle_limit_txt = (
            f"{_safe_float(cycle_limit):.3f}"
            if cycle_limit is not None else "-")
        return (step["psu"], step["ch"], step["action"],
                f"{step['wait']:.3f}",
                step.get("voltage", 0.0), step.get("current", 0.0),
                step.get("characteristic", "Custom Limits"),
                cycle_txt, cycle_limit_txt, "-", name_txt)

    def _refresh_scenario_tree(self):
        self._destroy_cell_editor()
        self.scenario_tree.delete(*self.scenario_tree.get_children())
        for idx, step in enumerate(self._current_steps()):
            self.scenario_tree.insert(
                "", "end", iid=str(idx), values=self._step_row_values(step))
        if self.program_tree is not None:
            self.program_tree.delete(*self.program_tree.get_children())
            for idx, step in enumerate(self.cycle_steps):
                self.program_tree.insert(
                    "", "end", iid=str(idx),
                    values=self._step_row_values(step))
        self.scenario_preview.set_steps(
            self._current_steps(), self.scenario_kind.get())
        fs = self._fullscreen.get("scenario")
        if fs:
            fs[1].set_steps(self._current_steps(), self.scenario_kind.get())
        self._update_loaded_scenario_label()
        # Any (PSU, Channel) now used by a scenario step must not also be
        # driveable from Operation Mode - see _refresh_ch_enable_availability.
        self._refresh_ch_enable_availability()

    def _update_loaded_scenario_label(self):
        if not hasattr(self, "loaded_scenario_lbl"):
            return
        def name_for(kind):
            path = self.loaded_scenario_paths.get(kind)
            return os.path.basename(path) if path else "(none)"
        text = (f"Power-Up: {name_for('powerup')}  |  "
                f"Power-Down: {name_for('powerdown')}  |  "
                f"Cycle: {name_for('cycle')}")
        self.loaded_scenario_lbl.config(text=text)

    def _scenario_used_ch_set(self):
        """Every (PSU, Channel) referenced by a non-MCU step in EITHER the
        Power-Up or Power-Down scenario - see _refresh_ch_enable_availability."""
        used = set()
        for steps in (self.powerup_steps, self.powerdown_steps):
            for step in steps:
                if step.get("action") == "MCU":
                    continue
                psu, ch = step.get("psu"), step.get("ch")
                if psu is not None and ch is not None:
                    used.add((psu, ch))
        return used

    def _refresh_ch_enable_availability(self):
        """Cross-check between Operation Mode and Power-Up/Power-Down:
        a (PSU, Channel) already used by a scenario step must not ALSO be
        driven by Operation Mode (Sync/Async/Constant) at the same time.
        Disables the matching CH On checkbox. Manually-authored scenario
        actions also untick it; imported cycle steps preserve the source
        program's selection so it can be transferred again. Called whenever
        scenario steps change (see _refresh_scenario_tree)."""
        if not hasattr(self, "ch_enable_vars"):
            return
        used = self._scenario_used_ch_set()
        manually_used = {
            (step.get("psu"), step.get("ch"))
            for steps in (self.powerup_steps, self.powerdown_steps)
            for step in steps
            if step.get("action") != "MCU"
            and not step.get("_cycle_control_import")
            and step.get("psu") is not None
            and step.get("ch") is not None
        }
        for p in range(1, MAX_PSUS + 1):
            for ch in (1, 2):
                key = (p, ch)
                locked = (p, ch) in used
                if key in manually_used:
                    if key not in self._cycle_enable_before_lock:
                        self._cycle_enable_before_lock[key] = bool(
                            self.ch_enable_vars[key].get())
                    elif self.ch_enable_vars[key].get():
                        self._cycle_enable_before_lock[key] = True
                    self.ch_enable_vars[key].set(False)
                elif key in self._cycle_enable_before_lock:
                    self.ch_enable_vars[key].set(
                        self._cycle_enable_before_lock.pop(key))
                self._ch_lock_reason[key] = (
                    "Used in Power-Up/Power-Down scenario" if locked else "")
        self._update_mode_state()

    def _scenario_add_step(self, kind=None, cycle_only=False):
        if not self._is_engineer_mode():
            return
        kind = kind or self.scenario_kind.get()
        d = ScenarioStepDialog(self, kind, cycle_only=cycle_only)
        self.wait_window(d)
        if d.result:
            self._push_undo()
            self._steps_for_kind(kind).append(d.result)
            self._refresh_scenario_tree()
            if d.result.get("action") != "MCU":
                self._update_monitor_row(d.result.get("psu"), ch=d.result.get("ch"))

    def _scenario_delete_step(self, tree=None):
        if not self._is_engineer_mode():
            return
        tree = tree or self.scenario_tree
        sel = tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        steps = self._steps_for_tree(tree)
        self._push_undo()
        del steps[idx]
        self._refresh_scenario_tree()
        self._refresh_all_monitor_labels()

    def _scenario_move(self, direction, tree=None):
        if not self._is_engineer_mode():
            return
        tree = tree or self.scenario_tree
        sel = tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        steps = self._steps_for_tree(tree)
        new_idx = idx + direction
        if 0 <= new_idx < len(steps):
            self._push_undo()
            steps[idx], steps[new_idx] = steps[new_idx], steps[idx]
            self._refresh_scenario_tree()
            tree.selection_set(str(new_idx))

    # --------------------------------------------------------------------
    # SCENARIO EDITOR UNDO / REDO
    #   Every mutating action (add/delete/move/inline edit/load) pushes a
    #   deep-copied snapshot of BOTH the Power-Up and Power-Down step lists
    #   onto the undo stack first, and clears the redo stack. Undo/Redo
    #   restore both lists together so the two scenarios never drift out
    #   of sync with each other's history.
    # --------------------------------------------------------------------
    def _snapshot_scenarios(self):
        return (copy.deepcopy(self.powerup_steps),
                copy.deepcopy(self.powerdown_steps),
                copy.deepcopy(self.cycle_steps))

    def _restore_snapshot(self, snap):
        self.powerup_steps, self.powerdown_steps = snap[0], snap[1]
        if len(snap) > 2:
            self.cycle_steps = snap[2]

    def _push_undo(self):
        self._undo_stack.append(self._snapshot_scenarios())
        if len(self._undo_stack) > self._undo_stack_max:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _undo(self):
        if not self._is_engineer_mode():
            return
        if not self._undo_stack:
            self._log("Undo: nothing to undo.")
            return
        self._redo_stack.append(self._snapshot_scenarios())
        self._restore_snapshot(self._undo_stack.pop())
        self._refresh_scenario_tree()
        self._refresh_all_monitor_labels()
        self._log("Scenario edit undone.")

    def _redo(self):
        if not self._is_engineer_mode():
            return
        if not self._redo_stack:
            self._log("Redo: nothing to redo.")
            return
        self._undo_stack.append(self._snapshot_scenarios())
        self._restore_snapshot(self._redo_stack.pop())
        self._refresh_scenario_tree()
        self._refresh_all_monitor_labels()
        self._log("Scenario edit redone.")

    def _current_run_hours(self):
        if self.unlimited_var.get():
            return 0.0
        try:
            return (int(self.dur_h.get()) + int(self.dur_m.get()) / 60.0
                    + int(self.dur_s.get()) / 3600.0)
        except ValueError:
            return 1.0

    def _apply_run_hours(self, hours):
        """Write a run time in hours into the shared Total Operation Time /
        Cycle Duration field (0 = Unlimited)."""
        try:
            hours = max(0.0, float(hours))
        except (TypeError, ValueError):
            return
        if hours <= 0:
            self.unlimited_var.set(True)
        else:
            self.unlimited_var.set(False)
            total = int(round(hours * 3600))
            h, rem = divmod(total, 3600)
            m, s = divmod(rem, 60)
            self._set_entry_text(self.dur_entry, f"{h:02d}:{m:02d}:{s:02d}")
        self._update_stop_control_state()

    def _ask_run_hours(self):
        """Ask how many hours the program should run. Returns the hours
        (0 = unlimited / manual stop) or None if the operator cancelled."""
        current = round(self._current_run_hours(), 3)
        hours = simpledialog.askfloat(
            "Program Run Time",
            "How many hours should this program run?\n"
            "(decimals allowed, e.g. 1.5 = 1 h 30 min; 0 = unlimited / manual stop)",
            parent=self, initialvalue=current, minvalue=0.0)
        if hours is None:
            return None
        self._apply_run_hours(hours)
        return hours

    def _scenario_save_dialog(self):
        if not self._is_engineer_mode():
            return
        kind = self.scenario_kind.get()
        run_hours = None
        if kind == "cycle":
            run_hours = self._ask_run_hours()
            if run_hours is None:
                return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save Scenario",
            initialdir=SCENARIO_DIR,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            path = ScenarioManager.save(path, self._current_steps(),
                                        run_hours=run_hours)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save scenario:\n{e}")
            return
        self.loaded_scenario_paths[kind] = path
        self._update_loaded_scenario_label()
        self._log(f"Scenario saved: {path}"
                  + (f" (run time: {run_hours:g} h)" if run_hours else
                     " (run time: unlimited)" if run_hours == 0 else ""))

    def _scenario_load_dialog(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Load Scenario",
            initialdir=SCENARIO_DIR,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            steps, run_hours = ScenarioManager.load(path, with_run_hours=True)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load scenario:\n{e}")
            return
        if not isinstance(steps, list):
            messagebox.showerror("Error", "Invalid scenario file: expected a JSON list of steps.")
            return
        self._push_undo()
        kind = self.scenario_kind.get()
        if kind == "powerup":
            self.powerup_steps = steps
        elif kind == "cycle":
            self.cycle_steps = steps
            if run_hours is not None:
                self._apply_run_hours(run_hours)
        else:
            self.powerdown_steps = steps
        self.loaded_scenario_paths[kind] = path
        self._refresh_scenario_tree()
        self._refresh_all_monitor_labels()
        self._log(f"Scenario loaded: {path}"
                  + (f" (run time: {float(run_hours):g} h)"
                     if kind == "cycle" and run_hours is not None else ""))

    def _set_entry_text(self, entry, value):
        old_state = str(entry.cget("state"))
        if old_state == "disabled":
            entry.config(state="normal")
        entry.delete(0, "end")
        entry.insert(0, str(value))
        if old_state == "disabled":
            entry.config(state="disabled")

    def _collect_cycle_program_data(self):
        rows = []
        for p in range(1, MAX_PSUS + 1):
            rows.append({
                "psu": p,
                "ch1_enabled": self._cycle_channel_enabled_for_program(p, 1),
                "ch2_enabled": self._cycle_channel_enabled_for_program(p, 2),
                "ch1_name": self.opmode_name_entries[(p, 1)].get(),
                "ch2_name": self.opmode_name_entries[(p, 2)].get(),
                "ch1_start": self.async_entries[(p, "ch1_start")].get(),
                "ch1_dur": self.async_entries[(p, "ch1_dur")].get(),
                "ch2_start": self.async_entries[(p, "ch2_start")].get(),
                "ch2_dur": self.async_entries[(p, "ch2_dur")].get(),
                "ch1_cycle_off": self.async_entries[(p, "ch1_cycle_off")].get(),
                "ch2_cycle_off": self.async_entries[(p, "ch2_cycle_off")].get(),
                "ch1_v": self.async_ch_entries[(p, 1, "v")].get(),
                "ch1_i": self.async_ch_entries[(p, 1, "i")].get(),
                "ch2_v": self.async_ch_entries[(p, 2, "v")].get(),
                "ch2_i": self.async_ch_entries[(p, 2, "i")].get(),
            })
        return {
            "kind": "pace_cycle_program_v1",
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "mode": self.mode_var.get(),
            "stop_mode": self.stop_mode_var.get(),
            "time_h": self.dur_h.get(),
            "time_m": self.dur_m.get(),
            "time_s": self.dur_s.get(),
            "unlimited": bool(self.unlimited_var.get()),
            "run_hours": round(self._current_run_hours(), 4),
            "cycle_count": self.cycle_count_entry.get(),
            "characteristic": self.characteristic_var.get(),
            "limit_override": bool(self.limit_override_var.get()),
            "test_time_h": self.test_h.get(),
            "test_time_m": self.test_m.get(),
            "test_time_s": self.test_s.get(),
            "rows": rows,
            "program_steps": copy.deepcopy(self.cycle_steps),
            "program_period": self.program_period_entry.get(),
        }

    def _cycle_channel_enabled_for_program(self, psu, ch):
        key = (psu, ch)
        if key in self._cycle_enable_before_lock:
            return bool(self._cycle_enable_before_lock[key])
        return bool(self.ch_enable_vars[key].get())

    def _update_loaded_program_label(self):
        path = getattr(self, "loaded_program_path", None)
        text = f"Loaded program: {os.path.basename(path)}" if path else "Loaded program: (none)"
        if hasattr(self, "loaded_program_lbl"):
            self.loaded_program_lbl.config(text=text)

    def _save_cycle_program_dialog(self):
        if not self._is_engineer_mode():
            return
        mode = self.mode_var.get()
        if mode not in ("sync", "async", "program"):
            messagebox.showerror("Error", "Program save is only available in Sync/Async/Program mode.")
            return
        run_hours = self._ask_run_hours()
        if run_hours is None:
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save Cycle/Test Program",
            initialdir=PROGRAM_DIR,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        data = self._collect_cycle_program_data()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save program:\n{e}")
            return
        self.loaded_program_path = path
        self._update_loaded_program_label()
        self._log(f"Cycle program saved: {path} (run time: "
                  + (f"{run_hours:g} h)" if run_hours else "unlimited)"))

    def _load_cycle_program_dialog(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Load Cycle/Test Program",
            initialdir=PROGRAM_DIR,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read program:\n{e}")
            return
        if not isinstance(data, dict):
            messagebox.showerror("Error", "Invalid program file format.")
            return

        mode = data.get("mode", "sync")
        if mode not in ("sync", "async", "program"):
            messagebox.showerror("Error", "Program mode must be 'sync', 'async' or 'program'.")
            return
        stop_mode = data.get("stop_mode", "time")
        if stop_mode not in ("time", "cycles"):
            stop_mode = "time"
        data["mode"] = mode
        data["stop_mode"] = stop_mode
        rows = data.get("rows")
        if mode == "program" and not isinstance(rows, list):
            rows = []
        if not isinstance(rows, list):
            messagebox.showerror("Error", "Invalid program file: missing rows list.")
            return

        self.mode_var.set(mode)
        self.stop_mode_var.set(stop_mode)
        self._set_entry_text(self.dur_h, data.get("time_h", "01"))
        self._set_entry_text(self.dur_m, data.get("time_m", "00"))
        self._set_entry_text(self.dur_s, data.get("time_s", "00"))
        self.unlimited_var.set(bool(data.get("unlimited", False)))
        self._set_entry_text(self.cycle_count_entry, data.get("cycle_count", "100"))
        characteristic = data.get("characteristic", "Custom Limits")
        self.characteristic_var.set(
            characteristic if characteristic in OUTPUT_CHARACTERISTIC_NAMES
            else "Custom Limits")
        self.limit_override_var.set(bool(data.get("limit_override", False)))
        for field, key in (
                (self.test_h, "test_time_h"),
                (self.test_m, "test_time_m"),
                (self.test_s, "test_time_s")):
            if key in data:
                self._set_entry_text(field, data[key])

        if isinstance(data.get("program_steps"), list):
            self.cycle_steps = [
                ScenarioManager._normalize_step(s)
                for s in copy.deepcopy(data["program_steps"])]
            self._set_entry_text(
                self.program_period_entry, data.get("program_period", "0"))
            self._refresh_scenario_tree()

        row_map = {}
        for row in rows:
            if isinstance(row, dict):
                try:
                    row_map[int(row.get("psu", 0))] = row
                except (TypeError, ValueError):
                    continue

        self._cycle_enable_before_lock.clear()
        for p in range(1, MAX_PSUS + 1):
            row = row_map.get(p, {})
            # Backward compatibility: older program files only had a single
            # per-PSU "enabled" flag (no separate CH1/CH2 enable) - fall
            # back to it for both channels when the new fields are absent.
            legacy_enabled = bool(row.get("enabled", True))
            self.ch_enable_vars[(p, 1)].set(bool(row.get("ch1_enabled", legacy_enabled)))
            self.ch_enable_vars[(p, 2)].set(bool(row.get("ch2_enabled", legacy_enabled)))
            self._set_entry_text(self.opmode_name_entries[(p, 1)], row.get("ch1_name", ""))
            self._set_entry_text(self.opmode_name_entries[(p, 2)], row.get("ch2_name", ""))
            self._set_entry_text(self.async_entries[(p, "ch1_start")], row.get("ch1_start", "0.0"))
            self._set_entry_text(self.async_entries[(p, "ch1_dur")], row.get("ch1_dur", "1.0"))
            self._set_entry_text(self.async_entries[(p, "ch2_start")], row.get("ch2_start", "0.0"))
            self._set_entry_text(self.async_entries[(p, "ch2_dur")], row.get("ch2_dur", "1.0"))
            old_cycle_off = row.get("cycle_off", "0.0")
            self._set_entry_text(
                self.async_entries[(p, "ch1_cycle_off")], row.get("ch1_cycle_off", old_cycle_off))
            self._set_entry_text(
                self.async_entries[(p, "ch2_cycle_off")], row.get("ch2_cycle_off", old_cycle_off))
            self._set_entry_text(self.async_ch_entries[(p, 1, "v")], row.get("ch1_v", "0.00"))
            self._set_entry_text(self.async_ch_entries[(p, 1, "i")], row.get("ch1_i", "0.00"))
            self._set_entry_text(self.async_ch_entries[(p, 2, "v")], row.get("ch2_v", "0.00"))
            self._set_entry_text(self.async_ch_entries[(p, 2, "i")], row.get("ch2_i", "0.00"))

        self._refresh_ch_enable_availability()
        self._update_mode_state()
        self._refresh_cycle_preview()
        self._refresh_all_monitor_labels()
        self.loaded_program_path = path
        self.loaded_cycle_program_data = copy.deepcopy(data)
        self._update_loaded_program_label()
        self._log(f"Cycle program loaded: {path}")

    # --------------------------------------------------------------------
    # AUTO-SAVE / RECOVERY
    #   The current Power-Up/Power-Down scenario is written to a fixed
    #   recovery file every 30s (and once more on clean exit), separate
    #   from the operator's named files in SCENARIO_DIR. On the next
    #   startup, if that file has any steps in it, the operator is offered
    #   a one-click restore - covers both an unexpected close (crash, power
    #   loss on the Pi, closed window by mistake) and simply wanting to
    #   pick up the last scenario worked on.
    # --------------------------------------------------------------------
    def _write_autosave(self):
        data = {
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "powerup_steps": self.powerup_steps,
            "powerdown_steps": self.powerdown_steps,
            "cycle_steps": self.cycle_steps,
        }
        with open(RECOVERY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _autosave_tick(self):
        try:
            self._write_autosave()
        except Exception as e:
            self._log(f"Auto-save failed: {e}")
        self._autosave_after_id = self.after(AUTOSAVE_INTERVAL_MS, self._autosave_tick)

    def _check_recovery(self):
        if not os.path.isfile(RECOVERY_FILE):
            return
        try:
            with open(RECOVERY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self._log(f"Recovery: could not read {RECOVERY_FILE} ({e})")
            return

        pu = data.get("powerup_steps") or []
        pd = data.get("powerdown_steps") or []
        cy = data.get("cycle_steps") or []
        if not pu and not pd and not cy:
            return

        saved_at = data.get("saved_at", "unknown time")
        if messagebox.askyesno(
                "Recovery",
                "A previously auto-saved scenario was found "
                f"(saved at {saved_at}):\n"
                f"  Power-Up steps: {len(pu)}\n"
                f"  Power-Down steps: {len(pd)}\n"
                f"  Cycle steps: {len(cy)}\n\n"
                "Restore it into the Scenario Editor?"):
            self._push_undo()
            self.powerup_steps = pu
            self.powerdown_steps = pd
            self.cycle_steps = cy
            self._refresh_scenario_tree()
            self._log(f"Recovery: restored scenario auto-saved at {saved_at}")
        else:
            self._log("Recovery: operator declined to restore the auto-saved scenario.")

    # --------------------------------------------------------------------
    # OPERATION LOCK
    # --------------------------------------------------------------------
    def _acquire_operation(self, name):
        # After an EMERGENCY OFF, no new operation may start until the
        # operator explicitly acknowledges/resets it. This is checked here
        # (not duplicated in every caller) so it uniformly covers START,
        # Run Power-Up, Run Power-Down and Run Full Cycle.
        if self.safety_state == SafetyState.EMERGENCY:
            messagebox.showerror(
                "Blocked",
                "The system is in EMERGENCY state.\n\n"
                "After confirming the setup is safe, press "
                "'Reset Emergency' before starting a new operation.")
            return False

        with self.op_lock:
            if self._stopping or (not self.op_running and any(
                    thread is not None and thread.is_alive()
                    for thread in (self.run_thread, self.scenario_thread,
                                   self.full_cycle_thread,
                                   self._pause_transition_thread))):
                messagebox.showwarning("Stopping", "Wait for STOP to finish.")
                return False
            if self.op_running:
                messagebox.showwarning(
                    "Busy",
                    f"An operation is already running: '{self.current_operation}'.\n"
                    "Press STOP (or EMERGENCY OFF) before starting a new one.")
                return False
            self.op_running = True
            self.current_operation = name
        self._current_run_start = time.monotonic()
        self.pause_event.clear()
        self._pause_began = None
        self._pause_total = 0.0
        self._pre_pause_state = {}
        self.msg_queue.put({"type": "op_status", "text": f"RUNNING ({name})"})
        self._log(f"Operation lock acquired: {name}")
        return True

    def _release_operation(self):
        with self.op_lock:
            if not self.op_running:
                return
            self.op_running = False
            self.current_operation = None
        self.msg_queue.put({"type": "op_status", "text": "IDLE"})

    # --------------------------------------------------------------------
    # SUPPORT SYSTEMS (log / CSV / watchdog / live reading)
    # --------------------------------------------------------------------
    def _start_support_systems(self):
        self._open_log_files()
        # v16: mid-run watchdog is opt-in (see Failsafe panel). Live V/I
        # reading still always starts so the graph/monitor stay useful.
        if getattr(self, "watchdog_enabled_var", None) is not None and self.watchdog_enabled_var.get():
            self._start_watchdog()
            self.msg_queue.put({
                "type": "watchdog", "ok": True,
                "text": "Watchdog active",
            })
            self._log("Watchdog: enabled for this run (mid-run failsafe ON).")
        else:
            self.msg_queue.put({
                "type": "watchdog", "ok": True,
                "text": "Watchdog idle (disabled)",
            })
            self._log("Watchdog: skipped (disabled) - connection checked at start only.")
        self._start_reading_poll()

    def _stop_support_systems(self):
        self._stop_watchdog()
        self._close_log_files()

    def _set_safety(self, state):
        old = getattr(self, "safety_state", None)
        self.safety_state = state
        if old != state:
            self._log(f"SAFETY: {old} \u2192 {state}")
            self.msg_queue.put({"type": "safety", "state": state})

    def _reset_emergency(self):
        """Operator-initiated acknowledgement that clears the EMERGENCY
        latch. Required before any new operation can be started again -
        mirrors standard E-stop reset practice (no silent auto-resume)."""
        if self.safety_state != SafetyState.EMERGENCY:
            messagebox.showinfo("Info", "There is no active EMERGENCY to reset.")
            return
        if not messagebox.askyesno(
                "Confirm Reset",
                "Confirm that the setup has been inspected and it is safe "
                "to clear the EMERGENCY state.\n\nProceed?"):
            return
        self.emergency_event.clear()
        self._set_safety(SafetyState.IDLE)
        self._log("EMERGENCY state acknowledged and reset by operator.")

    def _force_all_outputs_off(self, reason=""):
        for psu in self.psus.values():
            if psu.connected:
                ok = psu.all_outputs_off()
                if not ok:
                    self._log(f"WARNING: failed to turn OFF outputs on PSU{psu.index}"
                              + (f" ({reason})" if reason else ""))
        # A "Loop until stopped" MCU step has no natural end of its own -
        # every path that forces PSU outputs off (PAUSE/STOP/EMERGENCY/
        # cycle-end) must also abort it, or it would keep firing forever.
        # Always send STOP when connected (not only when looping=True): the
        # flag can be stale after a USB glitch, and STOP is harmless if the
        # MCU is idle.
        if self.mcu.connected:
            if not self.mcu.stop_loop():
                self._log("WARNING: failed to stop MCU"
                          + (f" ({reason})" if reason else ""))
            else:
                self.mcu.looping = False

    def _restore_pre_pause_outputs(self):
        """Re-apply the V/I/output state each channel had right before the
        last PAUSE, so RESUME continues the test instead of leaving outputs
        OFF until the next scheduled ON/OFF transition."""
        saved = getattr(self, "_pre_pause_state", None) or {}
        for p, psu in self.psus.items():
            if not psu.connected:
                continue
            ch_saved = saved.get(p)
            if not ch_saved:
                continue
            for ch in (1, 2):
                st = ch_saved.get(ch)
                if not st:
                    continue
                self._safe_set(psu, "set_voltage", ch, st["v"])
                self._safe_set(psu, "set_current", ch, st["i"])
                if st.get("on"):
                    self._safe_set(psu, "set_output", ch, True)
        self._pre_pause_state = {}

    def _safe_set(self, psu, method_name, *args):
        """Call a PSUDriver set_* method and log failures."""
        if self.current_operation == "full cycle":
            transition = getattr(self._pause_context, "transition", False)
            while not self._abort_requested():
                if not transition:
                    self._wait_while_paused()
                with self._output_lock:
                    if self.pause_event.is_set() and not transition:
                        continue
                    if self._abort_requested():
                        return False
                    return self._call_psu_set(psu, method_name, *args)
            return False
        return self._call_psu_set(psu, method_name, *args)

    def _call_psu_set(self, psu, method_name, *args):
        fn = getattr(psu, method_name)
        ok = fn(*args)
        if not ok:
            self._log(f"WARNING: {method_name}{args} failed on PSU{psu.index}")
        return ok

    # v14: Output Characteristic helpers (see OUTPUT_CHARACTERISTICS).
    def _characteristic_limits(self, name):
        """(vmax, imax) for a preset name, or (None, None) for Custom
        Limits / an unrecognised name (falls back to global safety limits
        elsewhere)."""
        return OUTPUT_CHARACTERISTIC_MAP.get(name, (None, None))

    def _selected_characteristic_limits(self):
        """Current global Output Characteristic selection (Operation Mode
        panel), used by the continuous cycle (Sync/Async/Constant)."""
        name = self.characteristic_var.get() if hasattr(
            self, "characteristic_var") else "Custom Limits"
        return self._characteristic_limits(name)

    def _apply_characteristic(self, psu, ch, vmax, imax):
        """Program OVP/OCP for this preset just before that channel turns
        ON. No-op for Custom Limits (vmax/imax None) - global safety
        limits + the existing override checkbox still apply as before."""
        if vmax is None or imax is None:
            return
        self._safe_set(psu, "apply_output_characteristic", ch, vmax, imax)

    # --------------------------------------------------------------------
    # SCENARIO / FULL-CYCLE SAFETY VALIDATION
    # --------------------------------------------------------------------
    def _validate_scenario_steps(self, steps):
        violations = []
        for idx, s in enumerate(steps):
            if s.get("action") == "CYCLE":
                try:
                    on_time = float(s.get("cycle_on", 1.0))
                    off_time = float(s.get("cycle_off", 1.0))
                    raw_count = float(s.get("cycle_count", 0))
                    cycle_duration = s.get("cycle_duration")
                    if cycle_duration is not None:
                        cycle_duration = float(cycle_duration)
                except (TypeError, ValueError):
                    violations.append(f"Step {idx + 1}: invalid CYCLE timing value")
                    continue
                if (not math.isfinite(on_time) or not math.isfinite(off_time)
                        or on_time < 0 or off_time < 0
                        or (on_time == 0 and off_time == 0)):
                    violations.append(f"Step {idx + 1}: invalid CYCLE ON/OFF timing")
                if (not math.isfinite(raw_count)
                        or raw_count < 0 or not raw_count.is_integer()):
                    violations.append(f"Step {idx + 1}: invalid CYCLE count")
                if (cycle_duration is not None
                        and (not math.isfinite(cycle_duration)
                             or cycle_duration <= 0)):
                    violations.append(f"Step {idx + 1}: invalid CYCLE time limit")
            # v19: a CYCLE step's ON phase applies the same voltage/current
            # as a plain ON step, so it's validated the same way.
            if s.get("action") not in ("ON", "CYCLE"):
                continue
            if s.get("allow_over_limit", False):
                continue
            try:
                v = float(s.get("voltage", 0.0))
                i = float(s.get("current", 0.0))
            except (TypeError, ValueError):
                continue
            # v14: validate against this step's Output Characteristic
            # preset (if set to something other than Custom Limits)
            # instead of the global safety limit, since that preset's
            # OVP/OCP is what will actually be enforced on the instrument.
            char_vmax, char_imax = self._characteristic_limits(
                s.get("characteristic", "Custom Limits"))
            vmax = char_vmax if char_vmax is not None else LIMIT_VOLTAGE_MAX
            imax = char_imax if char_imax is not None else LIMIT_CURRENT_MAX
            if v > vmax or i > imax:
                violations.append(
                    f"Step {idx + 1}: PSU{s.get('psu')} CH{s.get('ch')} "
                    f"V={v:.2f} I={i:.2f} (limit {vmax:.0f}V/{imax:.0f}A)")
        return violations

    def _confirm_psu_connected(self):
        if any(p.connected for p in self.psus.values()):
            return True
        return messagebox.askyesno(
            "Warning", "No PSU connected. Do you want to start anyway?")

    # --------------------------------------------------------------------
    # SCENARIO EXECUTION
    # --------------------------------------------------------------------
    def _run_scenario(self, kind):
        steps = (self.powerup_steps if kind == "powerup"
                 else self.powerdown_steps)
        if not steps:
            messagebox.showwarning("Warning", "Scenario is empty.")
            return

        op_name = f"{_kind_display(kind)} scenario"

        if not self._acquire_operation(op_name):
            return

        violations = self._validate_scenario_steps(steps)
        if violations:
            self._release_operation()
            messagebox.showerror(
                "Error",
                "The following scenario steps exceed the safety limit "
                f"({LIMIT_VOLTAGE_MAX:.0f}V / {LIMIT_CURRENT_MAX:.0f}A):\n"
                + "\n".join(violations)
                + "\n\nIf intentional, edit the step with "
                "'allow values above the safety limits'.")
            return

        if not self._confirm_psu_connected():
            self._release_operation()
            return

        self.stop_event.clear()
        self.emergency_event.clear()
        self._start_support_systems()
        self._set_safety(SafetyState.RUNNING)
        self.scenario_thread = threading.Thread(
            target=self._scenario_worker, args=(steps, kind),
            daemon=True)
        self.scenario_thread.start()

    def _scenario_worker(self, steps, kind):
        result = "error"
        try:
            kd = _kind_display(kind)
            self._log(f"--- {kd} scenario started ---")
            try:
                self._log(f"Scenario steps: {json.dumps(steps, ensure_ascii=False)}")
            except Exception:
                pass
            self._execute_scenario_steps(steps, kind)
            if self._abort_requested():
                self._log(f"--- {kd} scenario interrupted (STOP/EMERGENCY) ---")
                result = "stopped"
            else:
                self._log(f"--- {kd} scenario completed ---")
                result = "completed"
        finally:
            self._write_session_reports(
                result,
                extra={"operation": f"{kind} scenario"})
            if self.safety_state not in (SafetyState.EMERGENCY, SafetyState.FAULT):
                self._set_safety(SafetyState.IDLE)
            self._stop_support_systems()
            self._release_operation()

    def _execute_scenario_steps(self, steps, kind, pause_aware=True):
        if not steps:
            return
        start_t = (self._pause_began
                   if pause_aware and self._pause_began is not None
                   else time.monotonic())
        base_pause = self._pause_total
        threads = []
        for step in steps:
            th = threading.Thread(
                target=self._scenario_step_worker,
                args=(step, kind, start_t, None, base_pause, pause_aware),
                daemon=True)
            threads.append(th)
            th.start()
        for th in threads:
            th.join()

    def _scenario_step_worker(self, step, kind, start_t, stop_check=None,
                              base_pause=None, pause_aware=True):
        self._pause_context.transition = not pause_aware
        if base_pause is None:
            base_pause = self._pause_total
        try:
            offset = float(step.get("wait", 0.0))
        except (TypeError, ValueError):
            offset = 0.0
        target_time = start_t + offset

        def stopped():
            return self._abort_requested() or bool(stop_check and stop_check())

        while True:
            if stopped():
                return
            if pause_aware:
                self._wait_while_paused()
                if stopped():
                    return
            deadline = target_time + (self._pause_total - base_pause
                                      if pause_aware else 0.0)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if remaining <= SCENARIO_STEP_SPIN_S:
                # Final approach: busy-wait instead of time.sleep(). This
                # burns a bit of CPU for the last ~2ms, but avoids the
                # OS scheduler's sleep wake-up jitter, which is the
                # dominant source of small (few-ms) timing error on a
                # non-RT kernel - most noticeable for short "Wait After"
                # values like 0.01s. Still checks for STOP/EMERGENCY on
                # every spin so it stays interruptible.
                while True:
                    if stopped():
                        return
                    if pause_aware and self.pause_event.is_set():
                        break
                    if time.monotonic() >= deadline:
                        break
                if pause_aware and self.pause_event.is_set():
                    continue
                break
            time.sleep(min(remaining - SCENARIO_STEP_SPIN_S,
                            SCENARIO_STEP_POLL_S))

        if stopped():
            return

        self._fire_step(step, _kind_display(kind), offset,
                        start_t + (self._pause_total - base_pause
                                   if pause_aware else 0.0),
                        stop_check)

    def _fire_step(self, step, kd, offset, start_t, stop_check=None):
        """Execute one scenario/program step right now (after its wait)."""
        if step.get("action") == "MCU":
            if not getattr(self._pause_context, "transition", False):
                self._wait_while_paused()
                if self._abort_requested():
                    return
            self._execute_mcu_step(step, kd, offset)
            return

        if step.get("action") == "CYCLE":
            self._execute_cycle_step(step, kd, offset, start_t, stop_check)
            return

        state = step["action"] == "ON"

        psu = self.psus.get(step["psu"])
        if psu and psu.connected:
            ch = step["ch"]
            if state:
                v = float(step.get("voltage", 0.0))
                i = float(step.get("current", 0.0))
                char_vmax, char_imax = self._characteristic_limits(
                    step.get("characteristic", "Custom Limits"))
                self._apply_characteristic(psu, ch, char_vmax, char_imax)
                self._safe_set(psu, "set_voltage", ch, v)
                self._safe_set(psu, "set_current", ch, i)
            self._safe_set(psu, "set_output", ch, state)
            self._log(
                f"{kd}: PSU{step['psu']} CH{step['ch']} "
                f"{'ON' if state else 'OFF'} (t={offset:.2f}s)")
        else:
            self._log(
                f"{kd}: PSU{step['psu']} not connected, step skipped "
                f"(t={offset:.2f}s)")

    def _cycle_sleep_until(self, target, base_pause, stop_check=None):
        """Sleep until monotonic time `target` (pushed back by whatever time
        was spent PAUSED since `base_pause`). Absolute targets mean command
        latency can never accumulate into the ON/OFF times. Returns False if
        STOP/EMERGENCY (or stop_check) ended the wait."""
        while True:
            if self._abort_requested() or (stop_check and stop_check()):
                return False
            if not getattr(self._pause_context, "transition", False):
                self._wait_while_paused()
            if self._abort_requested() or (stop_check and stop_check()):
                return False
            remaining = (target + (self._pause_total - base_pause)
                         - time.monotonic())
            if remaining <= 0:
                return True
            time.sleep(max(min(remaining - SCENARIO_STEP_SPIN_S,
                               INTERRUPT_SLICE_S), 0.0))

    def _execute_cycle_step(self, step, kd, offset, scenario_start_t,
                            stop_check=None):
        """Fire a CYCLE step - repeatedly turn ONE (PSU, Channel) ON for
        its ON time then OFF for its OFF time (repeat count, 0 = until
        STOP/EMERGENCY/stop_check), optionally bounded by a start-relative
        time limit (cycle_duration), entirely within this step's own thread.

        v20: every edge is scheduled against an ABSOLUTE timeline
        (start + n*(ON+OFF) [+ ON]) instead of sleeping ON/OFF after each
        command, so SCPI latency no longer stretches the times, and the
        measured average ON/OFF is logged when the step finishes.

        Only ever touches the (psu, ch) this step names. Always ends with
        the channel OFF - add an explicit ON step after it if the channel
        should end up energised."""
        psu = self.psus.get(step.get("psu"))
        ch = step.get("ch")
        label = (step.get("name") or "").strip() or f"PSU{step.get('psu')} CH{ch}"

        if not (psu and psu.connected):
            self._log(
                f"{kd}: {label} not connected, CYCLE step skipped "
                f"(t={offset:.2f}s)")
            return

        v = float(step.get("voltage", 0.0))
        i = float(step.get("current", 0.0))
        on_t = max(_safe_float(step.get("cycle_on", 1.0)), 0.0)
        off_t = max(_safe_float(step.get("cycle_off", 1.0)), 0.0)
        count = max(int(_safe_float(step.get("cycle_count", 0)) or 0), 0)
        cycle_duration = step.get("cycle_duration")
        deadline = (scenario_start_t + float(cycle_duration)
                    if cycle_duration is not None else None)
        char_vmax, char_imax = self._characteristic_limits(
            step.get("characteristic", "Custom Limits"))

        setup_pause = self._pause_total
        self._apply_characteristic(psu, ch, char_vmax, char_imax)
        self._safe_set(psu, "set_voltage", ch, v)
        self._safe_set(psu, "set_current", ch, i)

        count_txt = f"x{count}" if count > 0 else "until STOP/EMERGENCY"
        if cycle_duration is not None:
            count_txt += f", max {float(cycle_duration):.3f}s"
        self._log(
            f"{kd}: {label} CYCLE started (ON {on_t:.3f}s / OFF {off_t:.3f}s, "
            f"{count_txt}) (t={offset:.2f}s)")

        base_pause = self._pause_total
        if deadline is not None:
            deadline += base_pause - setup_pause
        period_len = on_t + off_t
        t0 = time.monotonic()
        n = 0
        is_on = False
        t_on = t_prev_off = None
        on_meas, off_meas = [], []

        def deadline_now():
            if deadline is None:
                return None
            return deadline + (self._pause_total - base_pause)

        try:
            while count <= 0 or n < count:
                on_at = t0 + n * period_len
                if not is_on:
                    if not self._cycle_sleep_until(on_at, base_pause, stop_check):
                        break
                dl = deadline_now()
                if dl is not None and time.monotonic() >= dl:
                    break
                if not is_on:
                    self._safe_set(psu, "set_output", ch, True)
                    is_on = True
                    t_on = time.monotonic()
                    if t_prev_off is not None:
                        off_meas.append(t_on - t_prev_off)
                off_at = on_at + on_t
                if dl is not None:
                    off_at = min(off_at, dl - (self._pause_total - base_pause))
                if not self._cycle_sleep_until(off_at, base_pause, stop_check):
                    break
                n += 1
                is_last = count > 0 and n >= count
                dl = deadline_now()
                hit_deadline = dl is not None and time.monotonic() >= dl - 1e-3
                if off_t <= 0 and not is_last and not hit_deadline:
                    continue          # OFF time 0: stay ON, no glitch
                self._safe_set(psu, "set_output", ch, False)
                is_on = False
                t_off = time.monotonic()
                on_meas.append(t_off - t_on)
                t_prev_off = t_off
                if is_last or hit_deadline:
                    break
        finally:
            # Guarantee OFF on every exit path.
            self._safe_set(psu, "set_output", ch, False)
            meas = ""
            if on_meas:
                meas = f", measured avg ON {sum(on_meas) / len(on_meas):.3f}s"
                if off_meas:
                    meas += f" / OFF {sum(off_meas) / len(off_meas):.3f}s"
            self._log(
                f"{kd}: {label} CYCLE finished after {n} cycle(s){meas} "
                f"(t={offset:.2f}s)")

    def _execute_mcu_step(self, step, kd, offset):
        """Fire a MCU step (see MCUTrigger). Runs on its own worker
        thread (from _scenario_step_worker), same as a PSU ON/OFF step.

        Dispatches on the explicit command chosen in ScenarioStepDialog
        ("MCU Command": RUN/LOOP/PING/STOP) - each maps 1:1 to a raw
        line sent over the MCU's USB-serial link (see MCUTrigger)."""
        cmd = _mcu_step_cmd(step)
        repeat = max(1, int(step.get("mcu_repeat", 1)))
        # The manually-entered "MCU Signals" text (see ScenarioStepDialog)
        # is purely a label for logs/preview - the MCU itself has no idea
        # of it, it always just plays the one RLE pattern already loaded
        # onto it via RUN:<n>/LOOP/PING/STOP.
        label = (step.get("mcu_signals") or "").strip() or "MCU"
        mode_txt = {"RUN": f"RUN x{repeat}", "LOOP": "LOOP until stopped",
                    "PING": "PING", "STOP": "STOP"}[cmd]

        if not self.mcu.connected:
            self._log(
                f"{kd}: {label} not connected, step skipped (t={offset:.2f}s)")
            return

        if cmd == "PING":
            ok, msg = self.mcu.ping()
            self._log(f"{kd}: {label} PING -> {msg} (t={offset:.2f}s)")
            return

        # v22: multi-profile firmware - select the pattern profile
        # (e.g. "maxwell" / "said") before the pattern is fired. Skipped
        # when the step has no profile (single-pattern firmware, as before).
        profile = (step.get("mcu_profile") or "").strip()
        if profile and cmd in ("RUN", "LOOP"):
            ok, msg = self.mcu.select_profile(profile)
            self._log(f"{kd}: {label} SEL:{profile} -> "
                      f"{'OK' if ok else 'FAILED: ' + msg} (t={offset:.2f}s)")
            if not ok:
                return

        if cmd == "STOP":
            ok = self.mcu.stop_loop()
            self._log(
                f"{kd}: {label} STOP -> "
                f"{'sent' if ok else 'FAILED'} (t={offset:.2f}s)")
            return

        if cmd == "LOOP":
            ok, msg = self.mcu.trigger(loop=True)
            self._log(
                f"{kd}: {label} LOOP "
                f"{'started' if ok else 'FAILED: ' + msg} (t={offset:.2f}s)")
            return

        ok, msg = self.mcu.trigger(repeat=repeat, loop=False, wait_for_done=True)
        self._log(
            f"{kd}: {label} {mode_txt} -> "
            f"{'done' if ok else 'FAILED: ' + msg} (t={offset:.2f}s)")

    # --------------------------------------------------------------------
    # CYCLE PROGRAM (v20): one period of steps, repeated
    #   Shared by Cycle Control ("Program" mode) and the Scenario Editor's
    #   "Cycle" type / START TEST. Single-threaded timeline per period so
    #   PAUSE/STOP/EMERGENCY behave exactly like the other cycle modes.
    #   Only (PSU, Channel) pairs named in the steps are ever switched.
    # --------------------------------------------------------------------
    def _explicit_period(self):
        try:
            return max(float(self.program_period_entry.get().strip() or 0), 0.0)
        except (ValueError, tk.TclError):
            return 0.0

    def _program_period_value(self, steps):
        """Period in seconds, or 0 = run the program ONCE (no repetition).
        v20: the period is only ever what the operator typed - it is no
        longer derived from the steps' Wait values (that cut CYCLE steps
        short, so their ON/OFF times were not honoured)."""
        return self._explicit_period()

    def _validate_program(self, steps):
        """Return (violations, period) for a Cycle program."""
        if not steps:
            return ["Cycle program is empty."], 0.0
        violations = []
        period = self._program_period_value(steps)
        max_wait = max(max(_safe_float(s.get("wait", 0.0)), 0.0) for s in steps)
        if period > 0 and period < max_wait:
            violations.append(
                f"Period ({period:g}s) is shorter than the last step's "
                f"Wait ({max_wait:g}s).")
        violations += self._validate_scenario_steps(steps)
        return violations, period

    def _prepare_program_run(self):
        steps = copy.deepcopy(self.cycle_steps)
        violations, period = self._validate_program(steps)
        if violations:
            messagebox.showerror("Cycle Program", "\n".join(violations))
            return False
        self._program_steps_active = steps
        self._program_period = period
        return True

    def _read_program_stop_settings(self):
        """(cycle_limit|None, duration_s|None, error|None) from the Total
        Operation Time / Cycle Count controls. Both None = until STOP."""
        if self.stop_mode_var.get() == "cycles":
            try:
                n = int(self.cycle_count_entry.get())
            except ValueError:
                n = 0
            if n <= 0:
                return None, None, "Cycle Count must be a positive integer."
            return n, None, None
        if self.unlimited_var.get():
            return None, None, None
        try:
            h = int(self.dur_h.get())
            m = int(self.dur_m.get())
            s = int(self.dur_s.get())
        except ValueError:
            h, m, s = 1, 0, 0
        total = h * 3600 + m * 60 + s
        if total <= 0:
            return None, None, "Total Operation Time must be greater than 0."
        return None, float(total), None

    def _program_stop_due(self, phase_end):
        now = (self._pause_began if self._pause_began is not None
               else time.monotonic())
        if phase_end is not None:
            phase_end += self._pause_total - self._cycle_phase_pause_base
        return (self._abort_requested() or self._time_up()
                or self.cycle_phase_stop_event.is_set()
                or (phase_end is not None and now >= phase_end))

    def _run_program_pass(self, steps, cap, kd, phase_end):
        """Run every step once at its Wait After offset (each in its own
        thread, exactly like a Power-Up scenario). CYCLE steps run on their
        own ON/OFF/count until they finish or the run is stopped; with a
        period (`cap`) they are cut at the period end. Returns True if the
        pass ran to completion (not stopped)."""
        def stop_check():
            return self._program_stop_due(phase_end)

        pass_steps = []
        for s in steps:
            if s.get("action") == "CYCLE" and cap:
                s = dict(s)
                cd = s.get("cycle_duration")
                s["cycle_duration"] = (min(_safe_float(cd), cap)
                                       if cd is not None else cap)
            pass_steps.append(s)
        start_t = (self._pause_began if self._pause_began is not None
                   else time.monotonic())
        base_pause = self._pause_total
        threads = []
        for s in pass_steps:
            th = threading.Thread(
                target=self._scenario_step_worker,
                args=(s, "cycle", start_t, stop_check, base_pause), daemon=True)
            threads.append(th)
            th.start()
        for th in threads:
            th.join()
        return not stop_check()

    def _run_program_cycles(self, steps, period, kd, limit, duration):
        """Run the program: period <= 0 -> once (or `limit` times back to
        back); period > 0 -> repeated every `period` seconds. Ends on
        limit / duration / Total Operation Time / Stop Cycle / STOP.
        Returns the number of completed passes."""
        self._cycle_phase_active = True
        self.cycle_phase_stop_event.clear()
        self._cycle_phase_pause_base = self._pause_total
        start = (self._pause_began if self._pause_began is not None
                 else time.monotonic())
        phase_end = (start + duration
                     if duration is not None else None)

        def stop_check():
            return self._program_stop_due(phase_end)

        base_pause = self._pause_total
        first = start
        n = 0
        try:
            while not stop_check():
                self._wait_while_paused()
                if stop_check():
                    break
                if limit is not None and n >= limit:
                    break
                if period > 0 and n > 0:
                    if not self._cycle_sleep_until(
                            first + n * period, base_pause, stop_check):
                        break
                if not self._run_program_pass(
                        steps, period if period > 0 else None, kd, phase_end):
                    break
                n += 1
                if period <= 0 and limit is None:
                    break          # single pass finished
        finally:
            self._cycle_phase_active = False
        return n

    def _program_loop(self):
        steps = self._program_steps_active
        period = self._program_period
        mode_txt = (f"repeated every {period:.3f}s" if period > 0
                    else "run once (CYCLE steps run on their own ON/OFF)")
        self._log(
            f"Program: {len(steps)} step(s), {mode_txt} - only the "
            "PSU/Channels named in the steps are switched.")
        try:
            self._log(f"Program steps: {json.dumps(steps, ensure_ascii=False)}")
        except Exception:
            pass
        n = self._run_program_cycles(
            steps, period, "CYCLE PROGRAM", self._active_cycle_limit, None)
        self._log(f"Program: ended (completed passes: {n}).")

    def _program_channels_off(self, steps):
        """Switch OFF only the PSU/Channels a Cycle program names."""
        seen = set()
        for s in steps:
            if s.get("action") == "MCU":
                continue
            key = (s.get("psu"), s.get("ch"))
            if None in key or key in seen:
                continue
            seen.add(key)
            psu = self.psus.get(key[0])
            if psu and psu.connected:
                self._safe_set(psu, "set_output", key[1], False)

    def _stop_cycle_phase(self):
        """'Stop Cycle' (Scenario Monitor): end ONLY the running Cycle
        program. Its channels are switched OFF; every other channel is left
        as is. Inside START TEST the run then continues with Test Time and
        Power-Down; use 'STOP TEST' to abort everything."""
        if not self._cycle_phase_active:
            messagebox.showinfo("Stop Cycle", "No Cycle program is running.")
            return
        self.cycle_phase_stop_event.set()
        self._log("Stop Cycle requested - ending the Cycle program.")

    def _stop_test(self):
        """'STOP TEST' (Scenario Monitor): abort the running test/scenario
        and switch every output OFF (same as the STOP button)."""
        if not self.op_running:
            if not self._stopping:
                self._stop_cycle()
            return
        self._stop_cycle()

    def _run_cycle_program(self):
        """'Run Cycle' button (Scenario Editor): run the Cycle program on
        its own, using Cycle Control's stop settings."""
        if self.mode_var.get() != "program":
            self.mode_var.set("program")
            self._update_mode_state()
        self._start_cycle()

    def _compute_program_preview(self):
        """(rows, window, note) for CycleTimelineCanvas from the Cycle steps.
        Period 0 -> the program is drawn once (as it will run); a Period > 0
        is drawn repeating."""
        indexed = [(i, s) for i, s in enumerate(self.cycle_steps)
                   if s.get("action") in ("ON", "OFF", "CYCLE")]
        steps = [s for _i, s in indexed]
        if not steps:
            return [], 0.0, ("Add ON/OFF/CYCLE steps to the Cycle Program "
                              "table to preview it.")
        explicit = self._explicit_period()

        def cyc(s):
            on_t = max(_safe_float(s.get("cycle_on", 1.0)), 0.0)
            off_t = max(_safe_float(s.get("cycle_off", 1.0)), 0.0)
            raw = _safe_float(s.get("cycle_count", 0))
            count = int(raw) if math.isfinite(raw) and raw > 0 else 0
            return on_t, off_t, count

        span = 0.0
        for s in steps:
            t = max(_safe_float(s.get("wait", 0.0)), 0.0)
            if s.get("action") == "CYCLE":
                on_t, off_t, count = cyc(s)
                npulse = (min(count, CYCLE_PREVIEW_MAX_PULSES) if count > 0
                          else CYCLE_PREVIEW_REPS)
                t += npulse * (on_t + off_t)
            span = max(span, t)
        horizon = explicit if explicit > 0 else span
        if horizon <= 0:
            return [], 0.0, ("Give a step a Wait > 0 (or add a CYCLE step) "
                              "to preview the Cycle Program.")
        window = (horizon * CycleTimelineCanvas.N_PERIODS if explicit > 0
                  else horizon * 1.05)
        row_period = horizon if explicit > 0 else window

        per_rc = {}
        for i, s in indexed:
            per_rc.setdefault((s.get("psu"), s.get("ch")), []).append((i, s))
        rows = []
        for (psu, ch), ilst in per_rc.items():
            lst = [s for _i, s in ilst]
            events = []
            row_handles = []
            for si, s in ilst:
                t = max(_safe_float(s.get("wait", 0.0)), 0.0)
                if s.get("action") == "CYCLE":
                    on_t, off_t, count = cyc(s)
                    row_handles.append((t, ("prog", si, "wait")))
                    row_handles.append((t + on_t, ("prog", si, "cycle_on")))
                    if count != 1:
                        row_handles.append(
                            (t + on_t + off_t, ("prog", si, "cycle_off")))
                    k, t_cur = 0, t
                    while (t_cur < horizon and (count == 0 or k < count)
                           and k < CYCLE_PREVIEW_MAX_PULSES):
                        events.append((t_cur, True))
                        on_end = min(t_cur + on_t, horizon)
                        events.append((on_end, False))
                        t_cur = on_end + off_t
                        k += 1
                        if on_t + off_t <= 0:
                            break
                else:
                    events.append((t, s.get("action") == "ON"))
                    row_handles.append((t, ("prog", si, "wait")))
            events.sort(key=lambda e: e[0])
            intervals, start = [], None
            for t, state in events:
                if state and start is None:
                    start = t
                elif not state and start is not None:
                    intervals.append((start, t))
                    start = None
            if start is not None:
                intervals.append((start, horizon))
            name = next((str(s.get("name")).strip() for s in lst
                         if str(s.get("name") or "").strip()), "")
            label = name or f"PSU{psu} CH{ch}"
            color = (PSU_COLORS if ch == 1 else PSU_COLORS_CH2).get(
                psu, "#333333")
            rows.append((label, color, intervals, ch == 2, row_period))
            self._cycle_handles.append(row_handles)
        return rows, window, ""

    # --------------------------------------------------------------------
    # FULL CYCLE: Power-Up -> Test Time -> Power-Down
    # --------------------------------------------------------------------
    def _run_full_cycle(self):
        if self.op_running and self.pause_event.is_set():
            self._resume_paused_operation()
            return
        if (not self.powerup_steps and not self.powerdown_steps
                and not self.cycle_steps):
            messagebox.showwarning(
                "Warning", "Power-Up/Cycle/Power-Down scenario is empty.")
            return

        op_name = "full cycle"

        if not self._acquire_operation(op_name):
            return

        violations = (self._validate_scenario_steps(self.powerup_steps)
                      + self._validate_scenario_steps(self.cycle_steps)
                      + self._validate_scenario_steps(self.powerdown_steps))
        if violations:
            self._release_operation()
            messagebox.showerror(
                "Error",
                "The following scenario steps exceed the safety limit "
                f"({LIMIT_VOLTAGE_MAX:.0f}V / {LIMIT_CURRENT_MAX:.0f}A):\n"
                + "\n".join(violations)
                + "\n\nIf intentional, edit the step with "
                "'allow values above the safety limits'.")
            return

        if not self._confirm_psu_connected():
            self._release_operation()
            return

        self._full_cycle_cfg = None
        if self.cycle_steps:
            prog_violations, period = self._validate_program(self.cycle_steps)
            if prog_violations:
                self._release_operation()
                messagebox.showerror(
                    "Cycle Program", "\n".join(prog_violations))
                return
            limit, duration, err = self._read_program_stop_settings()
            if err:
                self._release_operation()
                messagebox.showerror("Cycle Program", err)
                return
            infinite = period > 0 or any(
                st.get("action") == "CYCLE"
                and _safe_float(st.get("cycle_count", 0)) <= 0
                and st.get("cycle_duration") is None
                for st in self.cycle_steps)
            if limit is None and duration is None and infinite:
                if not messagebox.askyesno(
                        "Unbounded Cycle",
                        "The Cycle phase is set to 'Unlimited' and runs until "
                        "STOP/EMERGENCY - Test Time and Power-Down will not "
                        "be reached. Continue?"):
                    self._release_operation()
                    return
            self._full_cycle_cfg = (period, limit, duration)

        self.stop_event.clear()
        self.emergency_event.clear()
        self._start_support_systems()
        self._set_safety(SafetyState.RUNNING)
        self.full_cycle_thread = threading.Thread(
            target=self._full_cycle_worker, daemon=True)
        self.full_cycle_thread.start()

    def _full_cycle_worker(self):
        result = "error"
        try:
            self._log("===== FULL CYCLE STARTED (Power-Up -> test -> Power-Down) =====")
            try:
                self._log(
                    f"Power-Up steps: "
                    f"{json.dumps(self.powerup_steps, ensure_ascii=False)}")
                self._log(
                    f"Power-Down steps: "
                    f"{json.dumps(self.powerdown_steps, ensure_ascii=False)}")
            except Exception:
                pass

            self._log("--- POWER-UP scenario started ---")
            self._execute_scenario_steps(self.powerup_steps, "powerup")
            self._wait_while_paused()
            if self._abort_requested():
                self._log("--- POWER-UP interrupted, full cycle stopped ---")
                result = "stopped"
                return
            self._log("--- POWER-UP scenario completed ---")

            cfg = self._full_cycle_cfg
            if self.cycle_steps and cfg:
                period, limit, duration = cfg
                self._log("--- CYCLE PROGRAM started ---")
                try:
                    self._log(
                        f"Cycle steps: "
                        f"{json.dumps(self.cycle_steps, ensure_ascii=False)}")
                except Exception:
                    pass
                # Countdown for the Cycle phase (shown in Scenario Monitor
                # and Cycle Control): Total Operation Time / Duration.
                self.session_start = (
                    self._pause_began if self._pause_began is not None
                    else time.monotonic())
                self.end_time = (self.session_start + duration
                                 if duration is not None else None)
                try:
                    n = self._run_program_cycles(
                        copy.deepcopy(self.cycle_steps), period,
                        "CYCLE PROGRAM", limit, duration)
                finally:
                    self.end_time = None
                    self.session_start = None
                self._program_channels_off(self.cycle_steps)
                self._wait_while_paused()
                if self.cycle_phase_stop_event.is_set() \
                        and not self._abort_requested():
                    self._log("--- CYCLE PROGRAM ended by Stop Cycle, "
                              "continuing with the test ---")
                if self._abort_requested():
                    self._log("--- CYCLE PROGRAM interrupted, full cycle stopped ---")
                    result = "stopped"
                    return
                self._log(f"--- CYCLE PROGRAM completed ({n} period(s)) ---")

            try:
                h = int(self.test_h.get())
                m = int(self.test_m.get())
                s = int(self.test_s.get())
            except ValueError:
                h, m, s = 0, 0, 0
                self._log("Test time fields invalid, assumed 00:00:00")
            test_seconds = max(0, h * 3600 + m * 60 + s)

            self._log(f"--- TEST TIME started: {h:02d}:{m:02d}:{s:02d} ---")
            self.test_total_s = float(test_seconds)
            test_start = (self._pause_began if self._pause_began is not None
                          else time.monotonic())
            self.test_end_time = test_start + test_seconds
            if not self._interruptible_sleep(test_seconds):
                self._log("--- TEST TIME interrupted, full cycle stopped ---")
                self.test_end_time = None
                result = "stopped"
                return
            self.test_end_time = None
            self._log("--- TEST TIME completed ---")

            self._log("--- POWER-DOWN scenario started ---")
            self._execute_scenario_steps(self.powerdown_steps, "powerdown")
            self._wait_while_paused()
            if self._abort_requested():
                self._log("--- POWER-DOWN interrupted, full cycle stopped ---")
                result = "stopped"
                return
            self._log("--- POWER-DOWN scenario completed ---")
            self._log("===== FULL CYCLE COMPLETED =====")
            result = "completed"
        finally:
            self._write_session_reports(result, extra={"operation": "full cycle"})
            if self.safety_state not in (SafetyState.EMERGENCY, SafetyState.FAULT):
                self._set_safety(SafetyState.IDLE)
            self._stop_support_systems()
            self._release_operation()

    # --------------------------------------------------------------------
    # CONNECTION
    # --------------------------------------------------------------------
    def _zero_psu_on_connect(self, psu):
        """Safety default: whenever a PSU (re)connects - manually, via
        Auto-Detect, or after the Watchdog reconnects it - force both
        channels to 0V/0A and outputs OFF. This guarantees a session never
        starts (or resumes) at whatever V/I happened to be left over from
        a previous run, a crash, or someone else's bench session."""
        for ch in (1, 2):
            self._safe_set(psu, "set_voltage", ch, 0.0)
            self._safe_set(psu, "set_current", ch, 0.0)
            self._safe_set(psu, "set_output", ch, False)
        self._log(f"PSU{psu.index}: zeroed to 0V/0A and OFF on connect (safety default).")

    def _connect_all(self):
        threading.Thread(target=self._connect_all_worker, daemon=True).start()

    def _connect_all_worker(self):
        for i, psu in self.psus.items():
            ok = psu.connect()
            self.msg_queue.put({"type": "conn", "psu": i, "ok": ok})
            self._log(
                f"PSU{i} ({psu.port}): "
                f"{'CONNECTED' if ok else 'NOT CONNECTED'}")
            if ok:
                self._zero_psu_on_connect(psu)
        self._connect_mcu_worker()
        if any(psu.connected for psu in self.psus.values()):
            self._start_reading_poll()

    def _connect_mcu_worker(self):
        if self.mcu.connected:
            # Already connected (e.g. just adopted straight from a
            # successful Detect MCU / Auto-Detect scan in the same
            # click) - nothing to do, just confirm the status. Calling
            # self.mcu.connect() again here would try to open the same
            # port a second time while the adopted one is still open,
            # which fails and would wrongly report Not Connected.
            self.msg_queue.put({"type": "mcu_conn", "ok": True})
            return
        if not self.mcu.port:
            self.msg_queue.put({"type": "mcu_conn", "ok": False})
            return
        ok = self.mcu.connect()
        self.msg_queue.put({"type": "mcu_conn", "ok": ok})
        self._log(
            f"MCU ({self.mcu.port}): {'CONNECTED' if ok else 'NOT CONNECTED'}")

    def _detect_mcu(self):
        threading.Thread(target=self._detect_mcu_worker, daemon=True).start()

    def _detect_mcu_worker(self):
        self._log("MCU Detect: scanning serial ports for pattern listener...")
        if serial is None:
            self._log("MCU Detect: pyserial is not installed, cannot scan.")
            return
        if serial_list_ports is None:
            self._log(
                "MCU Detect: serial.tools.list_ports unavailable, cannot scan.")
            return

        if self.mcu.connected:
            self.mcu.disconnect()

        # Don't probe ports already claimed by a connected/known PSU.
        exclude = {p.port for p in self.psus.values() if p.port}
        port, ser = scan_for_mcu_port(exclude_ports=exclude, log=self._log)
        self.msg_queue.put({"type": "mcu_port", "port": port})
        if port:
            # Adopt the connection the scan already verified (PING ->
            # READY) instead of closing it and reopening from scratch -
            # see MCUTrigger.adopt_connection for why.
            self.mcu.adopt_connection(port, ser)
            self.msg_queue.put({"type": "mcu_conn", "ok": True})
            self._log(f"MCU ({port}): CONNECTED")
        else:
            self.mcu.port = None
            self.msg_queue.put({"type": "mcu_conn", "ok": False})

    # --------------------------------------------------------------------
    # MANUAL PSU <-> USB/COM PORT ASSIGNMENT (v21)
    # --------------------------------------------------------------------
    @staticmethod
    def _idn_serial(idn):
        parts = (idn or "").split(",")
        return parts[2].strip() if len(parts) > 2 else ""

    def _load_port_settings(self):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            saved_ms = data.get("reading_interval_ms")
            if saved_ms in READING_POLL_LABELS:
                self.reading_interval_ms = saved_ms
                GraphCanvas.window_sec = self._graph_window_for(saved_ms)
            saved_sel = data.get("monitor_selection")
            if isinstance(saved_sel, dict):
                for key, flags in saved_sel.items():
                    try:
                        p = int(key)
                    except (TypeError, ValueError):
                        continue
                    if (1 <= p <= MAX_PSUS and isinstance(flags, list)
                            and len(flags) == 4):
                        for (ch, q), flag in zip(MONITOR_SEL_ORDER, flags):
                            self.monitor_sel[(p, ch, q)] = bool(flag)
        manual = data.get("manual_psu_ports", {}) if isinstance(data, dict) else {}
        for key, entry in manual.items():
            try:
                idx = int(key)
            except (TypeError, ValueError):
                continue
            if not (1 <= idx <= MAX_PSUS) or not isinstance(entry, dict):
                continue
            port = entry.get("port")
            if not port:
                continue
            self._manual_ports[idx] = {
                "port": str(port), "serial": str(entry.get("serial") or "")}
            self.psus[idx].port = str(port)

    def _save_port_settings(self):
        data = {}
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        data["manual_psu_ports"] = {
            str(idx): entry for idx, entry in sorted(self._manual_ports.items())}
        data["reading_interval_ms"] = self.reading_interval_ms
        data["monitor_selection"] = {
            str(p): [self.monitor_sel[(p, ch, q)] for ch, q in MONITOR_SEL_ORDER]
            for p in range(1, MAX_PSUS + 1)}
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            self._log(f"Port assignment: could not save settings ({e})")

    # --------------------------------------------------------------------
    # v23: operator-selectable Live V/I reading interval
    # --------------------------------------------------------------------
    @staticmethod
    def _graph_window_for(interval_ms):
        return max(GRAPH_WINDOW_SEC, 10 * interval_ms / 1000.0)

    def _graph_frame_title(self):
        win = GraphCanvas.window_sec
        span = f"{win / 60:.0f} min" if win >= 120 else f"{win:.0f}s"
        return (f"Live Graph (last {span}, lightweight Canvas drawing) "
                "- double-click a graph for fullscreen")

    def _monitored_count(self, psu_index):
        return sum(1 for ch, q in MONITOR_SEL_ORDER
                   if self.monitor_sel[(psu_index, ch, q)])

    def _reading_load_text(self):
        ms = self.reading_interval_ms
        if ms <= 0:
            return "Live reading OFF - no USB queries"
        connected = [i for i, p in self.psus.items() if p.connected]
        per_reading = sum(self._monitored_count(i) for i in connected)
        total_sel = sum(self._monitored_count(i)
                        for i in range(1, MAX_PSUS + 1))
        return (f"\u2248 {per_reading * 1000.0 / ms:.1f} queries/s for "
                f"{len(connected)} connected PSU(s)  "
                f"[{total_sel}/{MAX_PSUS * 4} values selected]")

    def _refresh_reading_load_label(self):
        if hasattr(self, "reading_load_lbl"):
            self._set_label(self.reading_load_lbl, self._reading_load_text())

    def _open_monitor_selection(self):
        """v23: choose per PSU / channel whether Actual V and/or Actual I
        are read. Every unticked box removes one SCPI query per reading;
        a PSU with nothing ticked gets no reading traffic at all."""
        win = getattr(self, "_monitor_sel_win", None)
        if win is not None and win.winfo_exists():
            win.deiconify()
            win.lift()
            return
        win = tk.Toplevel(self)
        self._monitor_sel_win = win
        win.title("Live Monitor - what to read")
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=8)
        frm.pack(fill="both", expand=True)
        ttk.Label(
            frm, text="Each ticked box = 1 USB query per reading. "
                      "Unticked values are shown as '-'.",
            foreground="#666666").grid(row=0, column=0, columnspan=8,
                                       sticky="w", pady=(0, 6))
        for col, text in enumerate(
                ("PSU", "CH1 V", "CH1 I", "CH2 V", "CH2 I", "", "", "")):
            if text:
                ttk.Label(frm, text=text, font=("Arial", 9, "bold")).grid(
                    row=1, column=col, padx=6)
        vars_ = {}

        def changed():
            for key, var in vars_.items():
                self.monitor_sel[key] = bool(var.get())
            self._on_monitor_selection_changed()

        def set_row(p, flags):
            for (ch, q), flag in zip(MONITOR_SEL_ORDER, flags):
                vars_[(p, ch, q)].set(flag)
            changed()

        def set_all(pred):
            for (p, ch, q), var in vars_.items():
                var.set(pred(ch, q))
            changed()

        for p in range(1, MAX_PSUS + 1):
            row = p + 1
            ttk.Label(frm, text=f"PSU{p}").grid(row=row, column=0, sticky="w")
            for col, (ch, q) in enumerate(MONITOR_SEL_ORDER, start=1):
                var = tk.BooleanVar(value=self.monitor_sel[(p, ch, q)])
                vars_[(p, ch, q)] = var
                ttk.Checkbutton(frm, variable=var, command=changed).grid(
                    row=row, column=col)
            ttk.Button(frm, text="All", width=4,
                       command=lambda p=p: set_row(p, (1, 1, 1, 1))).grid(
                row=row, column=6, padx=(10, 2))
            ttk.Button(frm, text="None", width=5,
                       command=lambda p=p: set_row(p, (0, 0, 0, 0))).grid(
                row=row, column=7, padx=2)
        bottom = ttk.Frame(frm)
        bottom.grid(row=MAX_PSUS + 2, column=0, columnspan=8, pady=(8, 0),
                    sticky="w")
        for text, pred in (("All", lambda ch, q: True),
                           ("None", lambda ch, q: False),
                           ("V only", lambda ch, q: q == "v"),
                           ("I only", lambda ch, q: q == "i"),
                           ("CH1 only", lambda ch, q: ch == 1),
                           ("CH2 only", lambda ch, q: ch == 2)):
            ttk.Button(bottom, text=text,
                       command=lambda pred=pred: set_all(pred)).pack(
                side="left", padx=2)
        ttk.Button(bottom, text="Close", command=win.destroy).pack(
            side="left", padx=(12, 2))

    def _on_monitor_selection_changed(self):
        # Drop now-unmonitored cached values so the table shows '-' for
        # them instead of an old, frozen number.
        for (p, ch), (v, i) in list(self.live_readings.items()):
            v = v if self.monitor_sel[(p, ch, "v")] else None
            i = i if self.monitor_sel[(p, ch, "i")] else None
            self.live_readings[(p, ch)] = (v, i)
        for p in range(1, MAX_PSUS + 1):
            self._update_monitor_row(p)
        self._refresh_reading_load_label()
        self._save_port_settings()

    def _on_reading_interval_selected(self, _event=None):
        label = self.reading_interval_var.get()
        ms = next((m for lbl, m in READING_POLL_OPTIONS if lbl == label),
                  READING_POLL_DEFAULT_MS)
        if ms == self.reading_interval_ms:
            return
        self.reading_interval_ms = ms
        GraphCanvas.window_sec = self._graph_window_for(ms)
        if hasattr(self, "graph_frame"):
            self.graph_frame.config(text=self._graph_frame_title())
        self.reading_load_lbl.config(text=self._reading_load_text())
        self._save_port_settings()
        self._log(f"Live V/I reading interval set to {label}.")

    def _port_display(self, port):
        if not port:
            return "auto"
        serial_no = self._idn_serial(self._port_idn.get(port))
        return f"{port}  SN {serial_no}" if serial_no else port

    @staticmethod
    def _parse_port_choice(text):
        text = (text or "").strip()
        if not text or text == "auto":
            return None
        return text.split()[0]

    def _port_choice_values(self):
        ports = set()
        if serial_list_ports is not None:
            try:
                ports.update(p.device for p in serial_list_ports.comports())
            except Exception:
                pass
        ports.update(p.port for p in self.psus.values() if p.port)
        ports.update(self._port_idn)

        def key(p):
            digits = "".join(c for c in p if c.isdigit())
            return (p.rstrip("0123456789"), int(digits) if digits else 0, p)

        return ["auto"] + [self._port_display(p) for p in sorted(ports, key=key)]

    def _port_tooltip(self, idx):
        psu = self.psus[idx]
        mode = "manual (kept by Auto-Detect)" if idx in self._manual_ports \
            else "auto (filled by Auto-Detect, sorted by serial number)"
        idn = self._port_idn.get(psu.port, "") if psu.port else ""
        lines = [f"PSU{idx}: {psu.port or 'no port'} - {mode}"]
        if idn:
            lines.append(f"*IDN?: {idn}")
        lines.append("Pick a COM port to assign it manually, or 'auto'.")
        return "\n".join(lines)

    def _refresh_port_widgets(self):
        for idx in range(1, MAX_PSUS + 1):
            if idx in getattr(self, "port_vars", {}):
                self.port_vars[idx].set(self._port_display(self.psus[idx].port))
                manual = idx in self._manual_ports
                self.port_labels[idx].config(
                    text=f"PSU{idx} ({'manual' if manual else 'auto'})")

    def _on_port_selected(self, idx):
        new_port = self._parse_port_choice(self.port_vars[idx].get())
        old_port = self.psus[idx].port
        if self.op_running:
            messagebox.showwarning(
                "Port assignment",
                "Stop the running cycle/scenario before changing PSU ports.")
            self._refresh_port_widgets()
            return
        if new_port and new_port == self.mcu.port:
            messagebox.showerror(
                "Port assignment",
                f"{new_port} is used by the MCU. Choose another port.")
            self._refresh_port_widgets()
            return
        if new_port == old_port and (new_port is None) == (idx not in self._manual_ports):
            return
        if new_port and new_port == old_port:
            # Just pin the current auto-assigned unit to this slot.
            self._manual_ports[idx] = {
                "port": new_port,
                "serial": self._idn_serial(self._port_idn.get(new_port))}
            self._log(f"Port assignment: PSU{idx} -> {new_port} (manual)")
            self._save_port_settings()
            self._refresh_port_widgets()
            return

        changed = {idx}
        # Port already used by another slot -> swap the two slots.
        for j, other in self.psus.items():
            if j != idx and new_port and other.port == new_port:
                other.disconnect()
                other.port = old_port
                if j in self._manual_ports:
                    if old_port:
                        self._manual_ports[j] = {
                            "port": old_port,
                            "serial": self._idn_serial(self._port_idn.get(old_port))}
                    else:
                        del self._manual_ports[j]
                changed.add(j)
                self._log(f"Port assignment: PSU{j} -> {old_port or 'none'} "
                          f"(swapped with PSU{idx})")

        psu = self.psus[idx]
        psu.disconnect()
        psu.port = new_port
        if new_port:
            self._manual_ports[idx] = {
                "port": new_port,
                "serial": self._idn_serial(self._port_idn.get(new_port))}
            self._log(f"Port assignment: PSU{idx} -> {new_port} (manual)")
        else:
            self._manual_ports.pop(idx, None)
            self._log(f"Port assignment: PSU{idx} -> auto "
                      "(will be filled by the next Auto-Detect)")
        self._save_port_settings()
        self._refresh_port_widgets()
        for j in changed:
            self.msg_queue.put({"type": "conn", "psu": j, "ok": False})
        threading.Thread(target=self._connect_slots_worker,
                         args=(sorted(changed),), daemon=True).start()

    def _connect_slots_worker(self, indices):
        for i in indices:
            psu = self.psus[i]
            if not psu.port:
                continue
            ok = psu.connect()
            if ok:
                idn = psu._query("*IDN?") or ""
                if idn:
                    self._port_idn[psu.port] = idn
                    if i in self._manual_ports:
                        self._manual_ports[i]["serial"] = self._idn_serial(idn)
            self.msg_queue.put({"type": "conn", "psu": i, "ok": ok})
            self.msg_queue.put({"type": "port", "psu": i, "port": psu.port})
            self._log(f"PSU{i} ({psu.port}): "
                      f"{'CONNECTED' if ok else 'NOT CONNECTED'}")
            if ok:
                self._zero_psu_on_connect(psu)
        if any(i in self._manual_ports for i in indices):
            self._save_port_settings()
        if any(p.connected for p in self.psus.values()):
            self._start_reading_poll()

    def _assign_found_psus(self, found):
        """Fill PSU slots from an Auto-Detect result. Manually assigned
        slots keep their unit (followed by serial number if its COM port
        changed); remaining units fill the 'auto' slots in serial order."""
        for port, idn in found:
            self._port_idn[port] = idn
        by_serial = {self._idn_serial(idn): port for port, idn in found
                     if self._idn_serial(idn)}
        taken = set()
        for idx, entry in sorted(self._manual_ports.items()):
            port = entry.get("port")
            sn = entry.get("serial")
            if sn and sn in by_serial and by_serial[sn] != port:
                self._log(f"Auto-Detect: PSU{idx} (SN {sn}) moved "
                          f"{port} -> {by_serial[sn]}")
                port = by_serial[sn]
                entry["port"] = port
            if port in taken:
                self._log(f"Auto-Detect: PSU{idx} manual port {port} is "
                          "already used by another slot - set to auto.")
                del self._manual_ports[idx]
                continue
            self.psus[idx].port = port
            taken.add(port)
            if port not in dict(found):
                self._log(f"Auto-Detect: PSU{idx} -> {port} (manual) - "
                          "no PSU reply on this port right now.")
            else:
                if not entry.get("serial"):
                    entry["serial"] = self._idn_serial(self._port_idn[port])
                self._log(f"Auto-Detect: PSU{idx} -> {port} (manual) "
                          f"({self._port_idn[port]})")

        remaining = [(p, idn) for p, idn in found if p not in taken]
        auto_slots = [i for i in range(1, MAX_PSUS + 1)
                      if i not in self._manual_ports]
        if len(remaining) > len(auto_slots):
            self._log(
                f"Auto-Detect: {len(remaining)} unassigned units found, only "
                f"{len(auto_slots)} free slot(s) - extra units are ignored.")
        for slot in auto_slots:
            if remaining:
                port, idn = remaining.pop(0)
                self.psus[slot].port = port
                self._log(f"Auto-Detect: PSU{slot} -> {port} ({idn})")
            else:
                self.psus[slot].port = None
                self._log(f"Auto-Detect: PSU{slot} -> no unit found")
        self._save_port_settings()
        for i in range(1, MAX_PSUS + 1):
            self.msg_queue.put(
                {"type": "port", "psu": i, "port": self.psus[i].port})

    def _auto_detect_ports(self):
        threading.Thread(
            target=self._auto_detect_ports_worker, daemon=True).start()

    def _auto_detect_ports_worker(self):
        self._log("Auto-Detect: scanning serial ports for PSU units...")
        if serial is None:
            self._log("Auto-Detect: pyserial is not installed, cannot scan.")
            return
        if serial_list_ports is None:
            self._log(
                "Auto-Detect: serial.tools.list_ports unavailable, cannot scan.")
            return

        for psu in self.psus.values():
            if psu.connected:
                psu.disconnect()

        found = scan_for_psu_ports(log=self._log)
        if not found:
            self._log("Auto-Detect: no PSU units found on any serial port.")
        self._assign_found_psus(found)

        # Also scan for the pattern-listener MCU on any remaining port so
        # one "Auto-Detect" click wires both PSU(s) and MCU for scenario
        # runs that include MCU steps.
        if self.mcu.connected:
            self.mcu.disconnect()
        exclude = {p.port for p in self.psus.values() if p.port}
        mcu_port, mcu_ser = scan_for_mcu_port(exclude_ports=exclude, log=self._log)
        self.msg_queue.put({"type": "mcu_port", "port": mcu_port})
        if mcu_port:
            self.mcu.adopt_connection(mcu_port, mcu_ser)
        else:
            self.mcu.port = None
            self._log("Auto-Detect: no pattern-listener MCU found "
                      "(MCU scenario steps will be skipped until Detect MCU).")

        self._connect_all_worker()

    # --------------------------------------------------------------------
    # LOG / FILE MANAGEMENT
    # --------------------------------------------------------------------
    def _open_log_files(self):
        os.makedirs(DESKTOP_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file_path = os.path.join(DESKTOP_DIR, f"PACE_log_{ts}.txt")
        self.log_file = open(self.log_file_path, "a", encoding="utf-8")
        self.log_path_lbl.config(text=f"Log file: {self.log_file_path}")
        if self.csv_var.get():
            csv_path = os.path.join(DESKTOP_DIR, f"PACE_data_{ts}.csv")
            self.csv_file = open(csv_path, "a", encoding="utf-8", newline="")
            self.csv_file.write("timestamp,psu,ch,voltage,current\n")

    def _write_session_reports(self, result="ok", extra=None):
        """Write JSON + HTML session summary next to the TXT log.
        Called for the continuous cycle AND for scenario/full-cycle runs
        (previously only the continuous cycle produced a report, leaving
        the two run types that matter most for lab qualification tests
        with no audit trail)."""
        if not getattr(self, "log_file_path", None):
            return
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        base = os.path.join(DESKTOP_DIR, "pace_reports")
        os.makedirs(base, exist_ok=True)

        elapsed_s = None
        if getattr(self, "_current_run_start", None) is not None:
            elapsed_s = round(time.monotonic() - self._current_run_start, 1)

        connected_psus = [i for i, p in self.psus.items() if p.connected]

        meta = {
            "result": result,
            "operation": self.current_operation or "",
            "mode": self.mode_var.get() if hasattr(self, "mode_var") else "",
            "elapsed_seconds": elapsed_s,
            "connected_psus": connected_psus,
            "ended": datetime.now().isoformat(timespec="seconds"),
            "log_txt": self.log_file_path,
        }
        if extra:
            meta.update(extra)

        json_path = os.path.join(base, f"PACE_session_{ts}.json")
        html_path = os.path.join(base, f"PACE_report_{ts}.html")
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            self._log(f"JSON report failed: {e}")
        try:
            html = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'/>"
                f"<title>PACE Report {ts}</title></head><body>"
                f"<h1>PACE Session Report</h1>"
                f"<p><b>Operation:</b> {meta['operation']}</p>"
                f"<p><b>Result:</b> {result}</p>"
                f"<p><b>Mode:</b> {meta['mode']}</p>"
                f"<p><b>Elapsed:</b> "
                f"{elapsed_s if elapsed_s is not None else '-'} s</p>"
                f"<p><b>Connected PSUs:</b> {connected_psus}</p>"
                f"<p><b>Log:</b> {self.log_file_path}</p>"
                f"<p><b>Ended:</b> {meta['ended']}</p>"
                "</body></html>"
            )
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            self._log(f"Reports written: {json_path} | {html_path}")
        except Exception as e:
            self._log(f"HTML report failed: {e}")

    def _close_log_files(self):
        if self.log_file:
            try:
                self.log_file.close()
            except Exception:
                pass
            self.log_file = None
        if self.csv_file:
            try:
                self.csv_file.close()
            except Exception:
                pass
            self.csv_file = None

    def _log(self, text):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"{ts}  {text}"
        self.msg_queue.put({"type": "log", "text": line})

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    # --------------------------------------------------------------------
    # LIVE SCPI CONSOLE
    # --------------------------------------------------------------------
    def _scpi_traffic(self, psu_index, direction, text):
        """PSUDriver.on_traffic callback - fires from whatever thread issued
        the command (main thread, cycle worker, scenario worker, watchdog,
        reading poll, or the manual-send thread below). Never touches Tk
        widgets directly; routes through the message queue like every
        other cross-thread update in this app.

        v22: nothing is queued while the SCPI console window is closed.
        The reading poll alone produces ~8 lines/s per connected PSU, which
        used to pile up in the queue (and in the Text widget) for hours
        even though nobody was looking at it."""
        if not self._scpi_visible:
            return
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        arrow = "->" if direction == "TX" else "<-"
        self.msg_queue.put({
            "type": "scpi",
            "text": f"{ts}  PSU{psu_index} {arrow} {text}",
        })

    def _scpi_send_manual(self):
        """Send an operator-typed raw SCPI command to the selected PSU.
        Runs the actual serial I/O on a background thread so a slow/stuck
        port can't freeze the GUI; the console updates via on_traffic."""
        if not self._is_engineer_mode():
            return
        try:
            p = int(self.scpi_psu_var.get())
        except ValueError:
            return
        cmd = self.scpi_cmd_var.get().strip()
        if not cmd:
            return
        psu = self.psus.get(p)
        if not psu or not psu.connected:
            messagebox.showwarning("Warning", f"PSU{p} is not connected.")
            return

        def worker():
            if cmd.endswith("?"):
                psu._query(cmd)
            else:
                psu._command(cmd)
        threading.Thread(target=worker, daemon=True).start()
        self.scpi_cmd_var.set("")

    def _clear_scpi_console(self):
        self.scpi_text.config(state="normal")
        self.scpi_text.delete("1.0", "end")
        self.scpi_text.config(state="disabled")

    # --------------------------------------------------------------------
    # LIVE MCU CONSOLE
    # --------------------------------------------------------------------
    def _mcu_traffic(self, direction, text):
        """MCUTrigger.on_traffic callback (any thread) - queued like SCPI."""
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        arrow = "->" if direction == "TX" else "<-"
        self.msg_queue.put({"type": "mcu_console",
                            "text": f"{ts}  MCU {arrow} {text}"})

    def _mcu_console_note(self, text):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.msg_queue.put({"type": "mcu_console", "text": f"{ts}  ** {text}"})

    def _mcu_console_port_list(self):
        if serial_list_ports is None:
            return []
        try:
            return sorted(p.device for p in serial_list_ports.comports())
        except Exception:
            return []

    def _mcu_console_open(self):
        if not self._is_engineer_mode():
            return
        port = self.mcu_console_port_var.get().strip()
        if not port:
            messagebox.showwarning("Warning", "Select or type the MCU port first.")
            return
        claimed = {p.port for p in self.psus.values() if p.connected and p.port}
        if port in claimed:
            messagebox.showwarning("Warning", f"{port} is in use by a PSU.")
            return

        def worker():
            ok, msg = self.mcu.open_raw(port)
            self._mcu_console_note(msg)
            self.msg_queue.put({"type": "mcu_port", "port": port if ok else None})
            self.msg_queue.put({"type": "mcu_conn", "ok": False})
        threading.Thread(target=worker, daemon=True).start()

    def _mcu_console_close(self):
        def worker():
            self.mcu.disconnect()
            self._mcu_console_note("MCU port closed")
            self.msg_queue.put({"type": "mcu_conn", "ok": False})
        threading.Thread(target=worker, daemon=True).start()

    def _mcu_send_manual(self, cmd=None):
        """Send a raw line to the MCU (typed or from a Quick button). Serial
        I/O runs on a background thread; replies show up via on_traffic."""
        if not self._is_engineer_mode():
            return
        if cmd is None:
            cmd = self.mcu_cmd_var.get().strip()
            self.mcu_cmd_var.set("")
        if not cmd:
            return
        try:
            listen_s = min(max(float(self.mcu_listen_var.get()), 0.1), 30.0)
        except ValueError:
            listen_s = 1.0

        def worker():
            ok, replies, handshake_ok = self.mcu.send_raw(cmd, listen_s)
            if not ok:
                self._mcu_console_note(f"'{cmd}' failed: {'; '.join(replies)}")
                if not self.mcu.connected:
                    self.msg_queue.put({"type": "mcu_conn", "ok": False})
                return
            if not replies:
                self._mcu_console_note(f"no reply within {listen_s:g}s")
            if handshake_ok:
                self._mcu_console_note("Handshake OK (READY) - MCU connected")
                self.msg_queue.put({"type": "mcu_conn", "ok": True})
                self._log(f"MCU ({self.mcu.port}): CONNECTED (manual handshake)")
        threading.Thread(target=worker, daemon=True).start()

    def _clear_mcu_console(self):
        self.mcu_text.config(state="normal")
        self.mcu_text.delete("1.0", "end")
        self.mcu_text.config(state="disabled")

    # --------------------------------------------------------------------
    # QUEUE PROCESSING (GUI thread)
    # --------------------------------------------------------------------
    def _opmode_active_name_for(self, psu_index, ch):
        """Operator-entered Operation Mode Name for this PSU/Channel (see
        the "CH1 Name"/"CH2 Name" fields next to the CH On checkboxes in
        the PSU Settings table), but ONLY if that channel is currently
        active in Operation Mode - i.e. its On checkbox is ticked, and (in
        Sync mode) it belongs to PSU1, whose row drives every PSU. Returns
        None if not active or no name was entered, so the caller can fall
        back to the Power-Up/Power-Down step name / default label."""
        if not hasattr(self, "ch_enable_vars") or not hasattr(self, "opmode_name_entries"):
            return None
        mode = self.mode_var.get() if hasattr(self, "mode_var") else "async"
        name_psu = 1 if mode == "sync" else psu_index
        var = self.ch_enable_vars.get((name_psu, ch))
        if var is None or not var.get():
            return None
        entry = self.opmode_name_entries.get((name_psu, ch))
        name = entry.get().strip() if entry is not None else ""
        return name or None

    def _monitor_label_for(self, psu_index, ch):
        """PSU/CH label shown in the Live Current/Voltage Monitor table.

        Prefers the Operation Mode "Name" field for that PSU/Channel if it
        is currently active there (see _opmode_active_name_for). Otherwise
        prefers the first non-empty operator-entered "Name" from a
        matching PSU/CH step (that column is shared with the MCU
        Signals field - see Scenario Editor -> "Name / MCU Signals"),
        checking Power-Up steps first, then Power-Down. Falls back to
        the plain "PSUx CHy" label when no step has a name for that
        PSU/CH, or when nothing is defined yet."""
        opmode_name = self._opmode_active_name_for(psu_index, ch)
        if opmode_name:
            return opmode_name
        for steps in (getattr(self, "powerup_steps", None),
                      getattr(self, "powerdown_steps", None),
                      getattr(self, "cycle_steps", None)):
            if not steps:
                continue
            for step in steps:
                if step.get("action") == "MCU":
                    continue
                if step.get("psu") == psu_index and step.get("ch") == ch:
                    name = (step.get("name") or "").strip()
                    if name:
                        return name
        return f"PSU{psu_index} CH{ch}"

    def _sync_graph_label(self, psu_index, ch):
        """Push the Live Current/Voltage Monitor's PSU/CH label (operator
        Name if set, else "PSUx CHy" - see _monitor_label_for) into the
        Live Graph legend and the fullscreen mirror (shared dict), so the
        Monitor table, the Live Graph and the Live Log all call the same
        PSU/Channel by the same name."""
        if not hasattr(self, "v_graph"):
            return
        label = self._monitor_label_for(psu_index, ch)
        key = f"PSU{psu_index}-CH{ch}"
        self.v_graph.set_label(key, label)
        self.i_graph.set_label(key, label)
        return label

    def _refresh_all_monitor_labels(self):
        """Re-derive every Live Monitor row's PSU/CH label (see
        _monitor_label_for). Cheap - called after bulk step changes
        (delete, undo/redo, scenario load) where a single-row update
        isn't enough."""
        for p in range(1, MAX_PSUS + 1):
            for ch in (1, 2):
                self._sync_graph_label(p, ch)
        if not hasattr(self, "monitor_tree"):
            return
        for p in range(1, MAX_PSUS + 1):
            for ch in (1, 2):
                self._update_monitor_row(p, ch=ch)

    def _update_monitor_row(self, psu_index, ch=None, act_v=None, act_i=None,
                             connected=None):
        """Update the Live Current/Voltage Monitor table (Scenario Editor
        tab) for one PSU/Channel row. Called from _process_queue on every
        'reading' message (actual V/I) and 'conn' message (connect state).
        Set V/I is read directly from the PSUDriver's own ch_state, which
        set_voltage/set_current already update on every successful write.

        When act_v/act_i are provided they are the fresh values from the
        current reading; they are stored in live_readings AND used directly
        for the table so the monitor always shows the latest sample, never
        the previous one."""
        if not hasattr(self, "monitor_tree"):
            return
        psu = self.psus.get(psu_index)
        channels = (ch,) if ch is not None else (1, 2)
        for c in channels:
            iid = f"mon_{psu_index}_{c}"
            if not self.monitor_tree.exists(iid):
                continue
            label = self._monitor_label_for(psu_index, c)
            is_connected = psu.connected if (psu and connected is None) else bool(connected)
            if not is_connected:
                self.live_readings.pop((psu_index, c), None)
                self._set_monitor_item(
                    iid, (label, "-", "-", "-", "-", "-"), ("disconnected",))
                continue
            st = psu.ch_state[c] if psu else {"v": 0.0, "i": 0.0, "on": False}
            set_v, set_i, out = st.get("v", 0.0), st.get("i", 0.0), st.get("on", False)
            # Use the fresh values passed in directly (not a cached lookup).
            # Also persist them so other callers (e.g. _refresh_all_monitor_labels)
            # can still display the last known reading.
            if (act_v is not None or act_i is not None) and c == ch:
                self.live_readings[(psu_index, c)] = (act_v, act_i)
            cached = self.live_readings.get((psu_index, c), (None, None))
            # v23: '-' when that value is not selected for monitoring
            # (or no sample yet).
            av = (f"{cached[0]:.3f}" if cached[0] is not None
                  and self.monitor_sel[(psu_index, c, "v")] else "-")
            ai = (f"{cached[1]:.3f}" if cached[1] is not None
                  and self.monitor_sel[(psu_index, c, "i")] else "-")
            self._set_monitor_item(
                iid,
                (label, f"{set_v:.2f}", f"{set_i:.2f}",
                 av, ai, "ON" if out else "OFF"),
                ())

    def _set_monitor_item(self, iid, values, tags):
        """v23: only touch the Treeview when a row really changes (it was
        rewritten for every sample of every channel)."""
        cache = self._monitor_row_cache
        if cache.get(iid) == (values, tags):
            return
        cache[iid] = (values, tags)
        self.monitor_tree.item(iid, values=values, tags=tags)

    def _append_text_lines(self, widget, lines, max_lines):
        """Append many lines to a read-only Text widget in ONE insert/trim/
        scroll (v23: was one insert + index + see() per line, which kept
        the GUI thread busy enough to stop reacting to the mouse)."""
        if not lines:
            return
        widget.config(state="normal")
        widget.insert("end", "\n".join(lines) + "\n")
        try:
            n_lines = int(widget.index("end-1c").split(".", maxsplit=1)[0])
            if n_lines > max_lines:
                widget.delete("1.0", f"{n_lines - max_lines}.0")
        except Exception:
            pass
        widget.see("end")
        widget.config(state="disabled")

    def _process_queue(self):
        # v23: time-budgeted, batched processing. Log/console lines are
        # collected and written to their Text widgets once per batch, and
        # the Live Monitor table is updated once per PSU/channel per batch
        # (latest sample) instead of once per sample. The graph and CSV
        # still receive every sample.
        log_lines, scpi_lines, mcu_lines = [], [], []
        latest_readings = {}
        deadline = time.monotonic() + QUEUE_BATCH_BUDGET_S
        try:
            while time.monotonic() < deadline:
                msg = self.msg_queue.get_nowait()
                mtype = msg.get("type")
                if mtype == "log":
                    log_lines.append(msg["text"])
                    if self.log_file:
                        # flushed once per batch (below), not per line
                        self.log_file.write(msg["text"] + "\n")
                        self._log_file_dirty = True
                elif mtype == "conn":
                    lbl = self.conn_labels[msg["psu"]]
                    if msg["ok"]:
                        lbl.config(text="\u25cf Connected", foreground="green")
                    else:
                        lbl.config(text="\u25cb Not Connected", foreground="red")
                    for c in (1, 2):
                        latest_readings.pop((msg["psu"], c), None)
                    self._update_monitor_row(msg["psu"], connected=msg["ok"])
                    if hasattr(self, "reading_load_lbl"):
                        self._set_label(self.reading_load_lbl,
                                        self._reading_load_text())
                elif mtype == "port":
                    self._refresh_port_widgets()
                elif mtype == "mcu_conn":
                    if msg["ok"]:
                        self.mcu_status_label.config(
                            text="\u25cf Connected", foreground="green")
                        self.mcu_status_label_editor.config(
                            text="MCU: \u25cf Connected", foreground="green")
                    else:
                        self.mcu_status_label.config(
                            text="\u25cb Not Connected", foreground="red")
                        self.mcu_status_label_editor.config(
                            text="MCU: \u25cb Not Connected", foreground="red")
                elif mtype == "mcu_port":
                    self.mcu_port_label.config(
                        text=f"MCU ({msg['port'] or 'not set'})")
                    if msg["port"] and hasattr(self, "mcu_console_port_var"):
                        self.mcu_console_port_var.set(msg["port"])
                elif mtype == "reading":
                    p, ch, v, i, t = (
                        msg["psu"], msg["ch"], msg["v"], msg["i"], msg["t"])
                    key = f"PSU{p}-CH{ch}"
                    self.v_graph.push(key, t, v)
                    self.i_graph.push(key, t, i)
                    if self.csv_file:
                        # v23: unmonitored values are left empty in the CSV
                        self.csv_file.write(
                            f"{t},{p},{ch},{'' if v is None else v},"
                            f"{'' if i is None else i}\n")
                    latest_readings[(p, ch)] = (v, i, t)
                elif mtype == "watchdog":
                    if msg["ok"]:
                        label = msg.get("text") or "All PSUs OK"
                        if "disabled" in label.lower() or "idle" in label.lower():
                            self._set_label(self.wd_status_lbl,
                                            f"\u25cf {label}", "#888888")
                        else:
                            self._set_label(self.wd_status_lbl,
                                            f"\u25cf {label}", "green")
                    else:
                        self._set_label(self.wd_status_lbl,
                                        f"\u26a0 {msg['text']}", "red")
                elif mtype == "op_status":
                    self._set_label(self.op_status_lbl, f"Status: {msg['text']}")
                elif mtype == "safety":
                    state = msg["state"]
                    color = SAFETY_COLORS.get(state, "black")
                    self.safety_lbl.config(text=f"Safety: {state}", foreground=color)
                elif mtype == "scpi":
                    scpi_lines.append(msg["text"])
                elif mtype == "mcu_console":
                    mcu_lines.append(msg["text"])
        except queue.Empty:
            pass
        except Exception as exc:
            # v22: one bad message must never kill the GUI update loop.
            try:
                print(f"_process_queue error: {exc!r}", flush=True)
            except Exception:
                pass

        try:
            for (p, ch), (v, i, t) in latest_readings.items():
                # Same PSU/CH label as the Monitor row (operator Name if
                # set, else "PSUx CHy") in the Live Graph legend and the
                # Live Log line.
                label = self._sync_graph_label(p, ch)
                self._update_monitor_row(p, ch=ch, act_v=v, act_i=i)
                # v22: one LIVE log line per channel every LIVE_LOG_INTERVAL_S.
                last = self._live_log_last.get((p, ch), 0.0)
                if t - last >= LIVE_LOG_INTERVAL_S:
                    self._live_log_last[(p, ch)] = t
                    parts = []
                    if v is not None:
                        parts.append(f"V={v:.3f} V")
                    if i is not None:
                        parts.append(f"I={i:.3f} A")
                    self._log(f"LIVE {label}: Actual {', '.join(parts)}")
            self._append_text_lines(self.log_text, log_lines, LOG_MAX_LINES)
            if hasattr(self, "scpi_text"):
                self._append_text_lines(self.scpi_text, scpi_lines,
                                        SCPI_CONSOLE_MAX_LINES)
            if hasattr(self, "mcu_text"):
                self._append_text_lines(self.mcu_text, mcu_lines,
                                        SCPI_CONSOLE_MAX_LINES)
        except Exception as exc:
            try:
                print(f"_process_queue display error: {exc!r}", flush=True)
            except Exception:
                pass
        # v22: flush the .txt log once per batch instead of once per line.
        if self._log_file_dirty and self.log_file:
            try:
                self.log_file.flush()
            except Exception:
                pass
            self._log_file_dirty = False
        # v23: always leave Tk a real pause for mouse/keyboard/redraw, even
        # with a backlog (was 10 ms).
        delay = 100 if self.msg_queue.empty() else 30
        self._queue_after_id = self.after(delay, self._process_queue)

    @staticmethod
    def _set_label(widget, text, foreground=None):
        """config() a label only when its text/colour actually changes.
        Avoids needless geometry recalculation of the large scrollable
        page on every timer/watchdog tick (v23 anti-freeze)."""
        try:
            if (widget.cget("text") == text
                    and (foreground is None
                         or str(widget.cget("foreground")) == foreground)):
                return
        except tk.TclError:
            pass
        if foreground is None:
            widget.config(text=text)
        else:
            widget.config(text=text, foreground=foreground)

    # --------------------------------------------------------------------
    # TIMER LABEL UPDATE (GUI thread)
    # --------------------------------------------------------------------
    def _update_timer_label(self):
        # While paused, freeze the displayed countdown/elapsed at the
        # moment PAUSE was pressed (deadlines themselves are extended on
        # RESUME in _toggle_pause, so this is purely a display freeze).
        now = self._pause_began if self._pause_began is not None else time.monotonic()
        if self.stop_event.is_set():
            self._set_label(self.timer_label, "Remaining: 00:00:00")
            cyc_txt = "Cycle remaining: 00:00:00"
        elif self.end_time and not self.unlimited_var.get():
            remaining = max(0, self.end_time - now)
            hh = int(remaining // 3600)
            mm = int((remaining % 3600) // 60)
            ss = int(remaining % 60)
            txt = f"{hh:02d}:{mm:02d}:{ss:02d}"
            self._set_label(self.timer_label, f"Remaining: {txt}")
            cyc_txt = f"Cycle remaining: {txt}"
        elif self.session_start and self.unlimited_var.get():
            elapsed = now - self.session_start
            hh = int(elapsed // 3600)
            mm = int((elapsed % 3600) // 60)
            ss = int(elapsed % 60)
            txt = f"{hh:02d}:{mm:02d}:{ss:02d}"
            self._set_label(self.timer_label, f"Elapsed: {txt} (unlimited)")
            cyc_txt = f"Cycle elapsed: {txt} (unlimited)"
        else:
            self._set_label(self.timer_label, "Remaining: --:--:--")
            cyc_txt = ("Cycle: stop by cycle count"
                       if self.stop_mode_var.get() == "cycles"
                       else "Cycle remaining: --:--:--")
        if hasattr(self, "sc_cycle_label"):
            self._set_label(self.sc_cycle_label, cyc_txt)

        if self.test_end_time and not self.stop_event.is_set():
            remaining = max(0, self.test_end_time - now)
            hh = int(remaining // 3600)
            mm = int((remaining % 3600) // 60)
            ss = int(remaining % 60)
            self._set_label(
                self.test_label,
                f"Test remaining: {hh:02d}:{mm:02d}:{ss:02d}")
            total = self.test_total_s
            pct = 100.0 if total <= 0 else round(min(
                100.0, max(0.0, (total - remaining) / total * 100.0)), 1)
            if self.test_progress_var.get() != pct:
                self.test_progress_var.set(pct)
            self._set_label(self.test_progress_lbl, f"{pct:.0f} %")
        else:
            self._set_label(
                self.test_label,
                "Test remaining: 00:00:00" if self.stop_event.is_set()
                else "Test remaining: --:--:--")
            if self.test_progress_var.get() != 0.0:
                self.test_progress_var.set(0.0)
            self._set_label(self.test_progress_lbl, "0 %")

        self._timer_after_id = self.after(500, self._update_timer_label)

    # --------------------------------------------------------------------
    # START / PAUSE / STOP / EMERGENCY CYCLE
    # --------------------------------------------------------------------
    def _start_cycle(self):
        if self.op_running and self.pause_event.is_set():
            self._resume_paused_operation()
            return
        if (not self._is_engineer_mode()
                and self.loaded_cycle_program_data is None):
            messagebox.showwarning(
                "Load Program", "Load a Cycle Control program before starting.")
            return
        if not self._acquire_operation("continuous cycle"):
            return

        mode = self.mode_var.get()
        locked = getattr(self, "_ch_lock_reason", {})
        if mode == "program":
            conflicts = []
        elif mode == "sync":
            conflicts = [
                (psu, ch)
                for psu in range(1, MAX_PSUS + 1)
                for ch in (1, 2)
                if self.ch_enable_vars[(1, ch)].get() and locked.get((psu, ch))
            ]
        else:
            conflicts = [
                (psu, ch)
                for psu in range(1, MAX_PSUS + 1)
                for ch in (1, 2)
                if self.ch_enable_vars[(psu, ch)].get()
                and locked.get((psu, ch))
            ]
        if conflicts:
            self._release_operation()
            messagebox.showerror(
                "Channel In Use",
                "Cycle Control cannot start while enabled channels are also "
                "used by a Power-Up/Power-Down scenario.")
            return

        if not self._confirm_psu_connected():
            self._release_operation()
            return
        if mode == "program":
            if not self._prepare_program_run():
                self._release_operation()
                return
        elif not self._validate_channel_limits():
            self._release_operation()
            return

        self.stop_event.clear()
        self.pause_event.clear()
        self.emergency_event.clear()
        self._pause_began = None
        self._pre_pause_state = {}

        # No residual ON from a previous session. Program mode is the
        # exception: it only touches the channels named in its steps, so
        # rails brought up by a Power-Up scenario stay on.
        if mode != "program":
            self._force_all_outputs_off(reason="pre-start")
        self._set_safety(SafetyState.RUNNING)

        self.session_start = time.monotonic()
        self._active_cycle_limit = None
        use_cycle_limit = (mode in ("sync", "async", "program")
                           and self.stop_mode_var.get() == "cycles")
        if use_cycle_limit:
            try:
                cycle_limit = int(self.cycle_count_entry.get())
            except ValueError:
                cycle_limit = 0
            if cycle_limit <= 0:
                messagebox.showerror("Error", "Cycle Count must be a positive integer.")
                self._set_safety(SafetyState.IDLE)
                self._release_operation()
                return
            self._active_cycle_limit = cycle_limit
            self.end_time = None
        else:
            self._active_cycle_limit = None
            try:
                h = int(self.dur_h.get())
                m = int(self.dur_m.get())
                s = int(self.dur_s.get())
            except ValueError:
                h, m, s = 1, 0, 0
            if self.unlimited_var.get():
                self.end_time = None
            else:
                self.end_time = self.session_start + h * 3600 + m * 60 + s

        self._start_support_systems()
        if self._active_cycle_limit is None:
            self._log(f"===== CYCLE STARTED (mode={mode}, stop=time) =====")
        else:
            self._log(
                f"===== CYCLE STARTED (mode={mode}, stop=cycles, count={self._active_cycle_limit}) =====")

        self.run_thread = threading.Thread(
            target=self._cycle_worker, args=(mode,), daemon=True)
        self.run_thread.start()

    def _validate_channel_limits(self):
        if self.limit_override_var.get():
            return True

        # v14: if an Output Characteristic preset (other than Custom
        # Limits) is selected, validate against ITS V/I ceiling instead of
        # the global safety limit - that preset is what will actually be
        # enforced on the instrument via OVP/OCP.
        char_vmax, char_imax = self._selected_characteristic_limits()
        vmax = char_vmax if char_vmax is not None else LIMIT_VOLTAGE_MAX
        imax = char_imax if char_imax is not None else LIMIT_CURRENT_MAX

        violations = []
        mode = self.mode_var.get()
        # Sync: only PSU1 V/I matter (they are applied to every unit).
        # Async/Constant: every PSU is considered, but a per-channel check
        # below skips any (PSU, Channel) whose CH On checkbox is unticked.
        psu_range = (1,) if mode == "sync" else range(1, MAX_PSUS + 1)
        for p in psu_range:
            for ch in (1, 2):
                if hasattr(self, "ch_enable_vars") and not self.ch_enable_vars[(p, ch)].get():
                    continue
                try:
                    v = float(self.async_ch_entries[(p, ch, "v")].get())
                    i = float(self.async_ch_entries[(p, ch, "i")].get())
                except ValueError:
                    continue
                if v > vmax or i > imax:
                    label = f"CH{ch}" if mode == "sync" else f"PSU{p} CH{ch}"
                    violations.append(f"{label}: V={v} I={i}")

        if violations:
            messagebox.showerror(
                "Error",
                "The following Voltage/Current values exceed the safety limit "
                f"({vmax:.0f}V / {imax:.0f}A):\n"
                + "\n".join(violations)
                + '\n\nCheck "Allow Voltage/Current values above the safety '
                'limits" if this is intentional.')
            return False
        return True

    def _toggle_pause(self):
        if self._abort_requested() or self._stopping:
            return
        if self.op_running and self.current_operation == "full cycle":
            if self.pause_event.is_set():
                self._resume_paused_operation()
            else:
                self._pause_began = time.monotonic()
                self.pause_event.set()
                self._set_safety(SafetyState.PAUSED)
                self._log("Test PAUSING - timers frozen, running Power-Down")
                self._pause_transition_thread = threading.Thread(
                    target=self._test_pause_transition, args=(False,),
                    daemon=True)
                self._pause_transition_thread.start()
            return
        if not self.run_thread or not self.run_thread.is_alive():
            if self.op_running and self.current_operation != "continuous cycle":
                messagebox.showinfo(
                    "Info",
                    "Use START TEST for a pausable test. Standalone "
                    "Power-Up/Power-Down scenarios can only be stopped.")
            return
        if self.pause_event.is_set():
            self._resume_paused_operation()
        else:
            self._pre_pause_state = {
                p: {ch: dict(psu.ch_state[ch]) for ch in (1, 2)}
                for p, psu in self.psus.items() if psu.connected
            }
            self._pause_began = time.monotonic()
            self.pause_event.set()
            self._force_all_outputs_off(reason="pause")
            self._set_safety(SafetyState.PAUSED)
            self._log("Cycle PAUSED - all channels OFF, timers frozen")

    def _resume_paused_operation(self):
        if self._abort_requested() or self._stopping:
            return
        if not self.op_running or not self.pause_event.is_set():
            return
        if self.current_operation == "full cycle":
            if (self._pause_transition_thread is not None
                    and self._pause_transition_thread.is_alive()):
                messagebox.showinfo(
                    "Please wait", "Power-Up/Power-Down is still running.")
                return
            self._log("Test RESUMING - running Power-Up, timers still frozen")
            self._pause_transition_thread = threading.Thread(
                target=self._test_pause_transition, args=(True,), daemon=True)
            self._pause_transition_thread.start()
        else:
            self._restore_pre_pause_outputs()
            self._resume_timers()
            self._log("Cycle RESUMED")

    def _resume_timers(self):
        if self._pause_began is not None:
            paused_for = time.monotonic() - self._pause_began
            self._pause_total += paused_for
            if self.end_time is not None:
                self.end_time += paused_for
            if self.test_end_time is not None:
                self.test_end_time += paused_for
            if self.session_start is not None:
                self.session_start += paused_for
            self._pause_began = None
            self._log(f"Timers resumed (paused for {paused_for:.2f}s)")
        self.pause_event.clear()
        self._set_safety(SafetyState.RUNNING)

    def _test_pause_transition(self, resume):
        self._pause_context.transition = True
        kind = "powerup" if resume else "powerdown"
        steps = copy.deepcopy(self.powerup_steps if resume
                              else self.powerdown_steps)
        try:
            violations = self._validate_scenario_steps(steps)
            if violations:
                raise ValueError("; ".join(violations))
            # Let any in-flight normal PSU command finish. Further normal
            # commands are held by _safe_set until Power-Up has completed.
            with self._output_lock:
                if self._abort_requested():
                    return
            self._execute_scenario_steps(steps, kind, pause_aware=False)
            with self._output_lock:
                if self._abort_requested():
                    return
                if resume:
                    self._resume_timers()
                    self._log("Test RESUMED")
                else:
                    self._force_all_outputs_off(reason="test pause")
                    self._log("Test PAUSED - Power-Down completed, timers frozen")
        except Exception as exc:
            self._log(f"ERROR: {kind} pause transition failed: {exc}")
            self.stop_event.set()
            self.pause_event.clear()
            self._pause_began = None
            self.end_time = self.test_end_time = self.session_start = None
            self._force_all_outputs_off(reason="pause transition failure")
            self._set_safety(SafetyState.FAULT)
        finally:
            self._pause_context.transition = False

    def _stop_cycle(self):
        if self._stopping:
            return
        self._stopping = True
        self.stop_event.set()
        self.pause_event.clear()
        self._pause_began = None
        self._pre_pause_state = {}
        # Freeze/clear the Remaining timer so it no longer counts down after STOP.
        self.end_time = None
        self.session_start = None
        self._log("Cycle STOPPING...")
        self._stop_watchdog()
        self.test_end_time = None
        self.test_total_s = 0.0

        def worker():
            try:
                with self._output_lock:
                    self._force_all_outputs_off(reason="stop")
                for thread in (self.run_thread, self.scenario_thread,
                               self.full_cycle_thread,
                               self._pause_transition_thread):
                    if thread is not None and thread.is_alive():
                        thread.join()
                with self._output_lock:
                    self._force_all_outputs_off(reason="stop complete")
                self._log("All outputs turned off. Cycle stopped.")
                self._close_log_files()
                self._release_operation()
            finally:
                self._stopping = False
        threading.Thread(target=worker, daemon=True).start()

    def _emergency_off(self):
        self.emergency_event.set()
        self.stop_event.set()
        self.pause_event.clear()
        self._pause_began = None
        self._pre_pause_state = {}
        # Freeze/clear the Remaining timer so it no longer counts down after E-stop.
        self.end_time = None
        self.session_start = None
        self.test_end_time = None
        with self._output_lock:
            self._force_all_outputs_off(reason="emergency")
        self._set_safety(SafetyState.EMERGENCY)
        self._log("!!! EMERGENCY SHUTDOWN triggered - all PSU outputs OFF !!!")
        self._stop_watchdog()
        self._close_log_files()
        self._release_operation()

    # --------------------------------------------------------------------
    # CYCLE WORKER (SYNC / ASYNC / CONSTANT)
    # --------------------------------------------------------------------
    def _time_up(self):
        if self.end_time is None:
            return False
        # While paused, the deadline is frozen (extended on resume).
        now = self._pause_began if self._pause_began is not None else time.monotonic()
        return now >= self.end_time

    def _cycle_worker(self, mode):
        try:
            if mode == "sync":
                self._sync_loop()
            elif mode == "program":
                self._program_loop()
            elif mode == "constant":
                self._constant_loop()
            else:
                threads = []
                for p in range(1, MAX_PSUS + 1):
                    if hasattr(self, "ch_enable_vars") and not (
                            self.ch_enable_vars[(p, 1)].get()
                            or self.ch_enable_vars[(p, 2)].get()):
                        self._log(f"Async: PSU{p} skipped (CH1/CH2 On checkboxes both unchecked)")
                        continue
                    t = threading.Thread(
                        target=self._async_loop_single, args=(p,), daemon=True)
                    threads.append(t)
                    t.start()
                for t in threads:
                    t.join()

            # Guarantee all outputs OFF when total time expires or cycle ends
            # (program mode: only the channels its steps name).
            if mode == "program":
                self._program_channels_off(self._program_steps_active)
            else:
                self._force_all_outputs_off(reason="cycle-end")

            if self._abort_requested():
                self._log("===== CYCLE STOPPED - ALL OUTPUTS OFF =====")
            elif mode == "program":
                self._log(
                    "===== CYCLE PROGRAM FINISHED - PROGRAM CHANNELS OFF =====")
            else:
                self._log(
                    "===== CYCLE COMPLETED (TIME UP) - ALL OUTPUTS OFF =====")
        finally:
            # Stop the Remaining / Elapsed display when the cycle ends
            # (time-up, STOP, or EMERGENCY) so it does not keep ticking.
            self.end_time = None
            self.session_start = None
            self._active_cycle_limit = None
            self._write_session_reports(
                "stopped" if self._abort_requested() else "completed")
            if self.safety_state not in (SafetyState.EMERGENCY, SafetyState.FAULT):
                self._set_safety(SafetyState.IDLE)
            self._stop_support_systems()
            self._release_operation()

    def _run_one_cycle_period(self, ch1_start, ch1_dur, ch2_start, ch2_dur,
                               cycle_off, apply_fn):
        """Run one full period of fully independent CH1/CH2 ON/OFF events,
        applied strictly in time order. Each channel's ON window
        [start, start+dur) is entirely independent of the other's, so any
        relationship is possible - overlapping (as in the old coupled
        model), exactly simultaneous, or non-overlapping (e.g. CH2 only
        turns on once CH1 has already turned off).

        apply_fn(ch, state) must perform the actual hardware action (and
        its own logging) for turning that channel ON or OFF.

        Honors PAUSE/STOP/EMERGENCY between every event via
        _interruptible_sleep. Returns False if aborted mid-cycle (the
        caller should stop looping), True if the full period completed.
        """
        events = []
        if ch1_dur > 0:
            events.append((ch1_start, 1, True))
            events.append((ch1_start + ch1_dur, 1, False))
        if ch2_dur > 0:
            events.append((ch2_start, 2, True))
            events.append((ch2_start + ch2_dur, 2, False))
        events.sort(key=lambda e: e[0])

        if not events:
            # Nothing to switch this period (both durations are 0) - idle
            # briefly instead of busy-looping, then let the caller re-check
            # abort/time-up on the next pass.
            return self._interruptible_sleep(max(cycle_off, 0.2))

        elapsed = 0.0
        for (t_evt, ch, state) in events:
            gap = t_evt - elapsed
            if gap > 0:
                if not self._interruptible_sleep(gap):
                    return False
            apply_fn(ch, state)
            elapsed = t_evt

        return self._interruptible_sleep(cycle_off)

    def _run_independent_channel_cycles(self, ch1_start, ch1_dur, ch1_cycle_off,
                                        ch2_start, ch2_dur, ch2_cycle_off, apply_fn,
                                        cycle_limit=None):
        """Run CH1/CH2 as independent repeating schedules.

        If cycle_limit is provided, each active channel runs exactly that
        many ON windows; otherwise it runs until time-up/STOP/EMERGENCY.
        """
        cfg = {}
        if ch1_dur > 0:
            cfg[1] = {
                "start": max(ch1_start, 0.0),
                "dur": max(ch1_dur, 0.0),
                "off": max(ch1_cycle_off, 0.0),
            }
        if ch2_dur > 0:
            cfg[2] = {
                "start": max(ch2_start, 0.0),
                "dur": max(ch2_dur, 0.0),
                "off": max(ch2_cycle_off, 0.0),
            }
        if not cfg:
            return self._interruptible_sleep(0.2)

        cycles_done = {ch: 0 for ch in cfg}
        next_on = {ch: val["start"] for ch, val in cfg.items()}
        next_off = {ch: None for ch in cfg}
        elapsed = 0.0

        while not self._abort_requested() and not self._time_up():
            self._wait_while_paused()
            if self._abort_requested() or self._time_up():
                break

            if cycle_limit is not None and all(cycles_done[ch] >= cycle_limit for ch in cfg):
                return True

            events = []
            for ch in cfg:
                if cycle_limit is not None and cycles_done[ch] >= cycle_limit:
                    continue
                if next_on[ch] is not None:
                    events.append((next_on[ch], ch, True))
                if next_off[ch] is not None:
                    events.append((next_off[ch], ch, False))

            if not events:
                if cycle_limit is not None:
                    return True
                return self._interruptible_sleep(0.2)

            t_evt = min(ev[0] for ev in events)
            gap = t_evt - elapsed
            if gap > 0:
                if not self._interruptible_sleep(gap):
                    return False
            elapsed = t_evt

            same_time = [ev for ev in events if abs(ev[0] - t_evt) < 1e-9]
            same_time.sort(key=lambda ev: (0 if not ev[2] else 1, ev[1]))
            for _, ch, state in same_time:
                if cycle_limit is not None and (not state) and cycles_done[ch] >= cycle_limit:
                    continue
                apply_fn(ch, state)
                if state:
                    next_on[ch] = None
                    next_off[ch] = t_evt + cfg[ch]["dur"]
                else:
                    next_off[ch] = None
                    cycles_done[ch] += 1
                    if cycle_limit is None or cycles_done[ch] < cycle_limit:
                        next_on[ch] = t_evt + cfg[ch]["off"]
                    else:
                        next_on[ch] = None

        return not self._abort_requested()

    def _sync_loop(self):
        """Synchronous cycle: PSU1 table row drives every connected PSU."""
        try:
            ch1_start = float(self.async_entries[(1, "ch1_start")].get())
            ch1_dur = float(self.async_entries[(1, "ch1_dur")].get())
            ch2_start = float(self.async_entries[(1, "ch2_start")].get())
            ch2_dur = float(self.async_entries[(1, "ch2_dur")].get())
            ch1_cycle_off = float(self.async_entries[(1, "ch1_cycle_off")].get())
            ch2_cycle_off = float(self.async_entries[(1, "ch2_cycle_off")].get())
        except ValueError:
            ch1_start = ch1_dur = ch2_start = ch2_dur = ch1_cycle_off = ch2_cycle_off = 0.0

        # PSU1's CH1/CH2 On checkboxes decide whether Sync drives that
        # channel at all (on every connected PSU) - a disabled channel is
        # treated exactly like a zero duration (never cycled).
        if not self.ch_enable_vars[(1, 1)].get():
            ch1_dur = 0.0
        if not self.ch_enable_vars[(1, 2)].get():
            ch2_dur = 0.0

        try:
            ch_vi = {
                1: (float(self.async_ch_entries[(1, 1, "v")].get()),
                    float(self.async_ch_entries[(1, 1, "i")].get())),
                2: (float(self.async_ch_entries[(1, 2, "v")].get()),
                    float(self.async_ch_entries[(1, 2, "i")].get())),
            }
        except ValueError:
            ch_vi = {1: (0.0, 0.0), 2: (0.0, 0.0)}

        self._log(
            f"Sync: using PSU1 settings for all units "
            f"(CH1 Start={ch1_start}s Dur={ch1_dur}s | "
            f"CH2 Start={ch2_start}s Dur={ch2_dur}s | "
            f"CH1 OFF={ch1_cycle_off}s CH2 OFF={ch2_cycle_off}s)")

        def apply_fn(ch, state):
            v, i = ch_vi[ch]
            char_vmax, char_imax = self._selected_characteristic_limits()
            for p in self.psus.values():
                if p.connected:
                    if state:
                        self._apply_characteristic(p, ch, char_vmax, char_imax)
                        self._safe_set(p, "set_voltage", ch, v)
                        self._safe_set(p, "set_current", ch, i)
                    self._safe_set(p, "set_output", ch, state)
            self._log(f"Sync: All PSU CH{ch} {'ON' if state else 'OFF'}"
                      + (f" (V={v} I={i})" if state else ""))

        self._run_independent_channel_cycles(
            ch1_start, ch1_dur, ch1_cycle_off,
            ch2_start, ch2_dur, ch2_cycle_off,
            apply_fn, cycle_limit=self._active_cycle_limit)

    def _constant_loop(self):
        """Constant mode: apply each PSU's CHx V/I and hold outputs ON."""
        ch_vi = {}
        for p in range(1, MAX_PSUS + 1):
            try:
                ch_vi[p] = {
                    1: (float(self.async_ch_entries[(p, 1, "v")].get()),
                        float(self.async_ch_entries[(p, 1, "i")].get())),
                    2: (float(self.async_ch_entries[(p, 2, "v")].get()),
                        float(self.async_ch_entries[(p, 2, "i")].get())),
                }
            except ValueError:
                ch_vi[p] = {1: (0.0, 0.0), 2: (0.0, 0.0)}

        def apply_on():
            applied = []
            char_vmax, char_imax = self._selected_characteristic_limits()
            for p, psu in self.psus.items():
                if not psu.connected:
                    continue
                chs_on = []
                for ch in (1, 2):
                    if not self.ch_enable_vars[(p, ch)].get():
                        continue
                    v, i = ch_vi[p][ch]
                    self._apply_characteristic(psu, ch, char_vmax, char_imax)
                    self._safe_set(psu, "set_voltage", ch, v)
                    self._safe_set(psu, "set_current", ch, i)
                    self._safe_set(psu, "set_output", ch, True)
                    chs_on.append(ch)
                if chs_on:
                    applied.append(
                        f"PSU{p}(CH{'+'.join(str(c) for c in chs_on)})")
            self._log(
                "Constant: channels ON with configured V/I on "
                + (", ".join(applied) if applied else "(none enabled)"))

        apply_on()

        while not self._abort_requested() and not self._time_up():
            # If pause was entered, outputs are already forced OFF by
            # _toggle_pause; wait until resume, then re-assert ON.
            if self.pause_event.is_set():
                self._wait_while_paused()
                if self._abort_requested() or self._time_up():
                    break
                apply_on()
            if not self._interruptible_sleep(0.2):
                break

    def _async_loop_single(self, psu_index):
        try:
            ch1_start = float(self.async_entries[(psu_index, "ch1_start")].get())
            ch1_dur = float(self.async_entries[(psu_index, "ch1_dur")].get())
            ch2_start = float(self.async_entries[(psu_index, "ch2_start")].get())
            ch2_dur = float(self.async_entries[(psu_index, "ch2_dur")].get())
            ch1_cycle_off = float(self.async_entries[(psu_index, "ch1_cycle_off")].get())
            ch2_cycle_off = float(self.async_entries[(psu_index, "ch2_cycle_off")].get())
        except ValueError:
            ch1_start = ch1_dur = ch2_start = ch2_dur = ch1_cycle_off = ch2_cycle_off = 0.0

        # A channel whose On checkbox is unticked never cycles for this PSU,
        # even if it has non-zero timing configured - treat it as if its
        # duration were 0 (see _run_independent_channel_cycles).
        if not self.ch_enable_vars[(psu_index, 1)].get():
            ch1_dur = 0.0
        if not self.ch_enable_vars[(psu_index, 2)].get():
            ch2_dur = 0.0

        try:
            ch_vi = {
                1: (float(self.async_ch_entries[(psu_index, 1, "v")].get()),
                    float(self.async_ch_entries[(psu_index, 1, "i")].get())),
                2: (float(self.async_ch_entries[(psu_index, 2, "v")].get()),
                    float(self.async_ch_entries[(psu_index, 2, "i")].get())),
            }
        except ValueError:
            ch_vi = {1: (0.0, 0.0), 2: (0.0, 0.0)}

        psu = self.psus[psu_index]

        def apply_fn(ch, state):
            v, i = ch_vi[ch]
            if psu.connected:
                if state:
                    self._safe_set(psu, "set_voltage", ch, v)
                    self._safe_set(psu, "set_current", ch, i)
                self._safe_set(psu, "set_output", ch, state)
            self._log(f"Async: PSU{psu_index} CH{ch} {'ON' if state else 'OFF'}"
                      + (f" (V={v} I={i})" if state else ""))

        self._run_independent_channel_cycles(
            ch1_start, ch1_dur, ch1_cycle_off,
            ch2_start, ch2_dur, ch2_cycle_off,
            apply_fn, cycle_limit=self._active_cycle_limit)

    # --------------------------------------------------------------------
    # READING POLL (live graph + CSV) — both CH1 and CH2
    # --------------------------------------------------------------------
    def _start_reading_poll(self):
        # v14: one reading thread PER PSU instead of a single thread that
        # walks every PSU in sequence. With the old shared loop, a full
        # poll pass did up to MAX_PSUS x 2ch x 2 queries (V?/I?) back to
        # back, each a blocking serial round-trip that holds that PSU's
        # PSUDriver.lock. A scenario step's set_voltage/set_current/
        # set_output for a given PSU shares that SAME lock, so if the
        # reading loop happened to be mid-query on that PSU right when a
        # step tried to fire, the step's SCPI write had to wait - and the
        # more PSUs connected, the longer each poll pass took and the more
        # likely that overlap became. That's the main reason the observed
        # power-up/down delay grew with PSU count. Splitting into
        # independent per-PSU threads means PSU A's read never delays PSU
        # B's read or PSU B's ON/OFF command; each PSU's own lock is only
        # ever contended by that PSU's own reading thread vs its own
        # scenario/cycle commands, not by every other PSU's traffic too.
        if any(thread.is_alive() for thread in self.reading_threads):
            return
        self.reading_stop = threading.Event()
        self.reading_threads = []
        for p in range(1, MAX_PSUS + 1):
            th = threading.Thread(
                target=self._reading_worker_for_psu, args=(p,), daemon=True)
            self.reading_threads.append(th)
            th.start()

    def _reading_worker_for_psu(self, psu_index):
        """Live V/I polling for a single PSU. See _start_reading_poll for
        why this runs one-thread-per-PSU rather than one shared loop.

        ALWAYS-ON link recovery: this used to just skip a PSU forever
        once psu.connected went False, relying entirely on the opt-in
        mid-run Watchdog (OFF by default) to ever try reopening the
        port. In practice that meant a USB hiccup silently and
        permanently dropped that PSU out of the live monitor/log unless
        the operator had ticked "Enable mid-run Watchdog" - which also
        forces outputs OFF and can abort the running cycle, so most
        people leave it off. This loop now attempts its own lightweight
        reconnect (PSUDriver.reconnect(): close the stale handle, reopen
        the same port, re-verify with *IDN?) independent of that
        checkbox, with exponential backoff (1s -> 10s cap) so a truly
        unplugged unit doesn't get hammered. It does NOT touch outputs
        or abort anything - it only tries to keep the USB link itself
        alive. The Watchdog checkbox still controls the separate,
        stricter safety behaviour (force outputs off / stop the cycle
        on loss).

        SILENT-DEATH DETECTION: a real cable pull / port disappearing
        makes pyserial raise (OSError etc.), which PSUDriver._query
        already turns into connected=False. But if the OS never
        notices the physical loss - the /dev/ttyACMx node is still
        there, it just stops answering - ser.readline() only times
        out; no exception is raised, so connected would stay True
        forever and this loop would keep "successfully" polling a dead
        port with nothing to show for it. PSUDriver.last_ok_time is
        only bumped on an actual reply, so if it hasn't moved in
        LINK_STALE_TIMEOUT_S even though connected==True, we treat the
        link as lost ourselves and fall into the same reconnect path
        as an explicit exception would have."""
        # Note: reading intentionally keeps running through EMERGENCY too -
        # read_actual() only issues passive V?/I? queries, it never touches
        # outputs, so there is no safety reason to blind the Live Monitor/
        # Graph/Log right when the operator most wants to see what the
        # outputs are actually doing. Only reading_stop (app close) ends it.
        while not self.reading_stop.is_set():
            cycle_start = time.monotonic()
            interval_ms = self.reading_interval_ms
            psu = self.psus.get(psu_index)
            if psu is not None and psu.connected and interval_ms > 0:
                got_reply = False
                queried = False
                for ch in (1, 2):
                    # v23: only the values selected under "What to read..."
                    want_v = self.monitor_sel[(psu_index, ch, "v")]
                    want_i = self.monitor_sel[(psu_index, ch, "i")]
                    if not (want_v or want_i):
                        continue
                    queried = True
                    v, i = psu.read_selected(ch, want_v, want_i)
                    complete = ((v is not None or not want_v)
                                and (i is not None or not want_i))
                    if complete:
                        got_reply = True
                        if self.msg_queue.qsize() > QUEUE_MAX_BACKLOG:
                            # v23: GUI is behind - drop this sample
                            # rather than let the queue eat the Pi's RAM.
                            continue
                        self.msg_queue.put({
                            "type": "reading", "psu": psu_index, "ch": ch,
                            "v": v, "i": i, "t": time.time(),
                        })
                    elif v is not None or i is not None:
                        # A partial response confirms that the link is alive,
                        # but must not overwrite the last complete V/I sample.
                        got_reply = True
                        self._log(
                            f"PSU{psu_index} CH{ch}: incomplete live reading "
                            f"(V={v!r}, I={i!r}); retaining the last complete value.")
                stale_limit = max(LINK_STALE_TIMEOUT_S,
                                  3 * interval_ms / 1000.0 + 2 * SERIAL_TIMEOUT)
                if got_reply:
                    self._reconnect_backoff[psu_index] = 1.0
                elif queried and time.time() - psu.last_ok_time > stale_limit:
                    self.msg_queue.put({
                        "type": "log",
                        "text": (f"PSU{psu_index}: no reply for over "
                                 f"{stale_limit:.0f}s (port still open "
                                 "but silent - host never saw a disconnect). "
                                 "Closing and reopening the port now."),
                    })
                    psu.connected = False
                    self.msg_queue.put({"type": "conn", "psu": psu_index, "ok": False})
                    # Don't wait for next loop tick - refresh the port
                    # (close handle, reopen same port, re-verify with
                    # *IDN?) right now, so a silent-death link comes
                    # back with as little delay as possible and the
                    # PSU picks up right where it left off (ch_state /
                    # last commanded V-I-output is untouched by
                    # reconnect(), so nothing needs to be re-sent).
                    self._attempt_reconnect(psu, psu_index)
            elif psu is not None and not psu.connected and psu.port:
                # Link is down but this PSU has a known port - try to
                # bring the USB connection back on its own.
                if not self._attempt_reconnect(psu, psu_index):
                    backoff = self._reconnect_backoff.get(psu_index, 1.0)
                    time.sleep(backoff)
                    self._reconnect_backoff[psu_index] = min(backoff * 2, 10.0)
            self._wait_next_reading(cycle_start)

    def _wait_next_reading(self, cycle_start):
        """Wait until the operator-selected reading interval has elapsed
        since cycle_start (v23). Re-checks the interval in short slices so
        a new choice in the dropdown takes effect at once; while reading is
        "Off" it only wakes every second (no USB traffic) so link recovery
        for disconnected PSUs keeps working."""
        while not self.reading_stop.is_set():
            ms = self.reading_interval_ms
            period = ms / 1000.0 if ms > 0 else 1.0
            remaining = period - (time.monotonic() - cycle_start)
            if remaining <= 0:
                return
            self.reading_stop.wait(min(remaining, 0.25))

    def _attempt_reconnect(self, psu, psu_index):
        """Close+reopen psu's port and re-verify with *IDN? (see
        PSUDriver.reconnect). Pushes the resulting conn/log messages and
        resets the backoff on success. Returns True/False like
        PSUDriver.reconnect() so callers can decide whether to back off."""
        if psu.reconnect():
            self._reconnect_backoff[psu_index] = 1.0
            self.msg_queue.put({"type": "conn", "psu": psu_index, "ok": True})
            self.msg_queue.put({
                "type": "log",
                "text": f"PSU{psu_index}: USB link auto-recovered on {psu.port}.",
            })
            return True
        return False

    # --------------------------------------------------------------------
    # WATCHDOG (FAILSAFE)
    # --------------------------------------------------------------------
    def _start_watchdog(self):
        self.watchdog_stop.clear()
        self.watchdog_thread = threading.Thread(
            target=self._watchdog_worker, daemon=True)
        self.watchdog_thread.start()

    def _stop_watchdog(self):
        # BUG FIX: this used to also set self.reading_stop, which
        # permanently killed the always-on Live V/I reading threads every
        # time a cycle/scenario stopped or completed (or STOP/EMERGENCY was
        # pressed) - since _stop_watchdog() is called from those paths too,
        # not only when the optional mid-run Watchdog itself is torn down.
        # That's why Set V/I and Actual V/I in the Live Current/Voltage
        # Monitor (and the Live Graph/Log fed from the same readings) froze
        # after the first cycle ended. Reading now has its own lifecycle,
        # stopped only on app close (see _on_close).
        self.watchdog_stop.set()

    def _watchdog_worker(self):
        # v23: the "OK" status is only sent once (it is unchanged until a
        # failure), not every WATCHDOG_INTERVAL_MS.
        wd_ok_sent = False
        while (not self.watchdog_stop.is_set()
               and not self.stop_event.is_set()
               and not self.emergency_event.is_set()):
            time.sleep(WATCHDOG_INTERVAL_MS / 1000.0)
            failed = []
            for p, psu in self.psus.items():
                if not psu.connected:
                    continue
                if time.time() - psu.last_ok_time > WATCHDOG_TIMEOUT_S:
                    if not psu.ping():
                        failed.append(p)

            if failed:
                self.msg_queue.put({
                    "type": "watchdog", "ok": False,
                    "text": f"PSU{failed} connection lost - failsafe triggered",
                })
                self._log(
                    f"!!! WATCHDOG: PSU{failed} connection lost. "
                    "Turning all outputs OFF.")
                self._force_all_outputs_off(reason="watchdog")

                reconnected = self._try_reconnect(failed)
                if reconnected:
                    self._log(
                        "WATCHDOG: Reconnection successful, cycle can continue "
                        "(use START to resume).")
                    self.msg_queue.put({"type": "watchdog", "ok": True})
                else:
                    self._log("WATCHDOG: Reconnection failed. Cycle stopping.")
                    self._set_safety(SafetyState.FAULT)
                self.stop_event.set()
                break
            if not wd_ok_sent:
                self.msg_queue.put({"type": "watchdog", "ok": True})
                wd_ok_sent = True

    def _try_reconnect(self, failed_list):
        for attempt in range(1, RECONNECT_ATTEMPTS + 1):
            self._log(
                f"WATCHDOG: Reconnection attempt "
                f"{attempt}/{RECONNECT_ATTEMPTS}")
            time.sleep(RECONNECT_DELAY_S)
            still_failed = []
            for p in failed_list:
                psu = self.psus[p]
                psu.disconnect()
                if psu.connect():
                    self.msg_queue.put({"type": "conn", "psu": p, "ok": True})
                    self._zero_psu_on_connect(psu)
                else:
                    still_failed.append(p)
                    self.msg_queue.put({"type": "conn", "psu": p, "ok": False})
            if not still_failed:
                return True
            failed_list = still_failed
        return False

    # --------------------------------------------------------------------
    def _on_close(self):
        self.stop_event.set()
        self.emergency_event.set()
        self.watchdog_stop.set()
        if self.reading_stop is not None:
            self.reading_stop.set()
        for p in self.psus.values():
            if p.connected:
                try:
                    p.all_outputs_off()
                except Exception:
                    pass
                p.disconnect()
        self._close_log_files()

        # Capture the very latest scenario state (not just up to 30s old)
        # so Recovery Mode has the freshest possible snapshot next launch.
        try:
            self._write_autosave()
        except Exception:
            pass

        for after_id in (getattr(self, "_queue_after_id", None),
                         getattr(self, "_timer_after_id", None),
                         getattr(self, "_autosave_after_id", None)):
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
        for graph in (getattr(self, "v_graph", None),
                      getattr(self, "i_graph", None)):
            if graph is not None:
                graph.stop()

        self.destroy()


# ==============================================================================
# SCENARIO STEP DIALOG
# ==============================================================================
class ScenarioStepDialog(tk.Toplevel):
    def __init__(self, master, kind="powerup", cycle_only=False):
        super().__init__(master)
        self.title("Add Cycle" if cycle_only else "Add Step")
        self.result = None
        self.cycle_only = cycle_only

        self.psu_lbl = ttk.Label(self, text="PSU:")
        self.psu_lbl.grid(row=0, column=0, padx=6, pady=4, sticky="w")
        self.psu_var = tk.StringVar(value="1")
        self.psu_combo = ttk.Combobox(
            self, textvariable=self.psu_var,
            values=[str(i) for i in range(1, MAX_PSUS + 1)],
            width=5, state="readonly")
        self.psu_combo.grid(row=0, column=1, sticky="w")

        self.ch_lbl = ttk.Label(self, text="Channel:")
        self.ch_lbl.grid(row=1, column=0, padx=6, pady=4, sticky="w")
        self.ch_var = tk.StringVar(value="1")
        self.ch_combo = ttk.Combobox(
            self, textvariable=self.ch_var, values=["1", "2"],
            width=5, state="readonly")
        self.ch_combo.grid(row=1, column=1, sticky="w")

        ttk.Label(self, text="Action:").grid(
            row=2, column=0, padx=6, pady=4, sticky="w")
        self.action_var = tk.StringVar(
            value="CYCLE" if cycle_only
            else ("OFF" if kind == "powerdown" else "ON"))
        self.action_combo = ttk.Combobox(
            self, textvariable=self.action_var,
            values=["CYCLE"] if cycle_only else ["ON", "OFF", "CYCLE", "MCU"],
            width=6, state="readonly")
        self.action_combo.grid(row=2, column=1, sticky="w")
        self.action_combo.bind(
            "<<ComboboxSelected>>", lambda e: self._update_field_state())

        ttk.Label(self, text="Wait After (s) [t=0 reference]:").grid(
            row=3, column=0, padx=6, pady=4, sticky="w")
        self.wait_var = tk.StringVar(value="0.000" if cycle_only else "0.010")
        e_wait = ttk.Entry(self, textvariable=self.wait_var, width=10)
        e_wait.grid(row=3, column=1, sticky="w")
        _bind_numeric_entry(e_wait)
        ttk.Label(self, text="e.g. 0.010 = 10 ms, 0.001 = 1 ms",
                  font=("Arial", 7, "italic"), foreground="#777777").grid(
            row=3, column=2, padx=(4, 6), sticky="w")

        self.v_lbl = ttk.Label(
            self, text=f"Voltage (V) [max {LIMIT_VOLTAGE_MAX:.0f}V]:")
        self.v_lbl.grid(row=4, column=0, padx=6, pady=4, sticky="w")
        self.voltage_var = tk.StringVar(value="0.00")
        self.e_v = ttk.Entry(self, textvariable=self.voltage_var, width=8)
        self.e_v.grid(row=4, column=1, sticky="w")
        _bind_numeric_entry(self.e_v)

        self.i_lbl = ttk.Label(
            self, text=f"Current (A) [max {LIMIT_CURRENT_MAX:.0f}A]:")
        self.i_lbl.grid(row=5, column=0, padx=6, pady=4, sticky="w")
        self.current_var = tk.StringVar(value="0.00")
        self.e_i = ttk.Entry(self, textvariable=self.current_var, width=8)
        self.e_i.grid(row=5, column=1, sticky="w")
        _bind_numeric_entry(self.e_i)

        self.allow_over_limit_var = tk.BooleanVar(value=False)
        self.allow_over_limit_chk = ttk.Checkbutton(
            self,
            text="Allow values above the safety limits (60V / 20A)",
            variable=self.allow_over_limit_var,
        )
        self.allow_over_limit_chk.grid(
            row=7, column=0, columnspan=2, padx=6, pady=(2, 4), sticky="w")

        # v14: Output Characteristic preset for this step's ON action - see
        # OUTPUT_CHARACTERISTICS near the top of the file. Applied (via
        # OVP/OCP) right before this step's V/I/Output-ON commands fire;
        # also used instead of the global safety limit to validate the
        # Voltage/Current fields above, unless "Custom Limits" is chosen.
        self.characteristic_lbl = ttk.Label(
            self, text="Output Characteristic:")
        self.characteristic_lbl.grid(row=6, column=0, padx=6, pady=4, sticky="w")
        self.characteristic_var = tk.StringVar(value="Custom Limits")
        self.characteristic_combo = ttk.Combobox(
            self, textvariable=self.characteristic_var,
            values=OUTPUT_CHARACTERISTIC_NAMES, width=12, state="readonly")
        self.characteristic_combo.grid(row=6, column=1, sticky="w")

        # --- MCU-only fields (hidden unless Action == MCU) -------------
        # A MCU step sends one explicit command over the MCU's USB link
        # (see MCUTrigger / MCU_COMMANDS): RUN fires the RLE pattern n
        # times, LOOP repeats it forever until STOP, PING just checks the
        # link is alive, STOP aborts an active LOOP. None of these go
        # through any PSU.
        self.mcu_cmd_lbl = ttk.Label(self, text="MCU Command:")
        self.mcu_cmd_var = tk.StringVar(value="RUN")
        self.mcu_cmd_combo = ttk.Combobox(
            self, textvariable=self.mcu_cmd_var, values=list(MCU_COMMANDS),
            width=8, state="readonly")
        self.mcu_cmd_combo.bind(
            "<<ComboboxSelected>>", lambda e: self._update_field_state())

        self.mcu_repeat_lbl = ttk.Label(self, text="Repeat count:")
        self.mcu_repeat_var = tk.StringVar(value="1")
        self.mcu_repeat_entry = ttk.Entry(
            self, textvariable=self.mcu_repeat_var, width=8)
        _bind_numeric_entry(self.mcu_repeat_entry)

        self.mcu_hint_lbl = ttk.Label(
            self,
            text="RUN fires the RLE pattern n times and waits for DONE. "
                 "LOOP repeats it forever until a STOP step (or STOP/"
                 "EMERGENCY). PING just checks the MCU link is alive "
                 "(READY). STOP aborts an active LOOP.",
            font=("Arial", 8, "italic"), wraplength=260, justify="left")

        # --- Function Name (non-MCU steps only) -------------------------
        # Optional manual label for this PSU/Channel row, shown in the
        # Symbol/Step Editor timeline preview instead of the generic
        # "PSUx-CHx" text. Left blank -> falls back to "PSUx CHx" as before.
        self.name_lbl = ttk.Label(self, text="Function Name (optional):")
        self.name_var = tk.StringVar(value="")
        self.name_entry = ttk.Entry(self, textvariable=self.name_var, width=22)
        self.name_hint_lbl = ttk.Label(
            self,
            text='Shown in the Symbol/Step Editor instead of "PSUx CHx". '
                 "Leave blank to keep the default.",
            font=("Arial", 8, "italic"), wraplength=260, justify="left")

        # --- MCU Signals (MCU steps only) -------------------------------
        # Optional manual note of which signal(s)/GPIO(s) this MCU step
        # takes/drives, shown as this row's label in the Symbol/Step Editor
        # timeline preview instead of the generic "MCU" text.
        self.mcu_signals_lbl = ttk.Label(self, text="MCU Signals (optional):")
        self.mcu_signals_var = tk.StringVar(value="")
        self.mcu_signals_entry = ttk.Entry(
            self, textvariable=self.mcu_signals_var, width=22)
        self.mcu_signals_hint_lbl = ttk.Label(
            self,
            text="Which signal(s)/GPIO(s) this step fires or reads, e.g. "
                 '"GPIO2 TRIG_A". Shown in the Symbol/Step Editor. Leave '
                 'blank for a generic "MCU" row.',
            font=("Arial", 8, "italic"), wraplength=260, justify="left")

        # --- MCU Profile (MCU steps only, v22) ---------------------------
        # Which pattern profile the (multi-profile) firmware should play,
        # sent as SEL:<name> right before RUN/LOOP. Blank = leave the
        # firmware's current profile alone (single-pattern firmware).
        self.mcu_profile_lbl = ttk.Label(self, text="MCU Profile (optional):")
        self.mcu_profile_var = tk.StringVar(value="")
        self.mcu_profile_combo = ttk.Combobox(
            self, textvariable=self.mcu_profile_var, width=20,
            values=["", "maxwell", "said"])
        self.mcu_profile_hint_lbl = ttk.Label(
            self,
            text="Pattern profile on the Arduino (SEL:<name> is sent before "
                 "RUN/LOOP). Leave blank for firmware without profiles.",
            font=("Arial", 8, "italic"), wraplength=260, justify="left")

        # --- CYCLE-only fields (hidden unless Action == CYCLE) ----------
        # v19: a CYCLE step repeatedly turns ONLY this (PSU, Channel) ON
        # then OFF - its own ON time, OFF time and repeat count - without
        # touching any other channel. Voltage/Current/Output Characteristic
        # above are applied once, before the first ON.
        self.cycle_on_lbl = ttk.Label(self, text="Cycle ON Time (s):")
        self.cycle_on_var = tk.StringVar(value="1.0")
        self.cycle_on_entry = ttk.Entry(
            self, textvariable=self.cycle_on_var, width=10)
        _bind_numeric_entry(self.cycle_on_entry)

        self.cycle_off_lbl = ttk.Label(self, text="Cycle OFF Time (s):")
        self.cycle_off_var = tk.StringVar(value="1.0")
        self.cycle_off_entry = ttk.Entry(
            self, textvariable=self.cycle_off_var, width=10)
        _bind_numeric_entry(self.cycle_off_entry)

        self.cycle_count_lbl = ttk.Label(self, text="Repeat Count (0=until stopped):")
        self.cycle_count_var = tk.StringVar(value="10")
        self.cycle_count_entry = ttk.Entry(
            self, textvariable=self.cycle_count_var, width=10)
        _bind_numeric_entry(self.cycle_count_entry)

        self.cycle_limit_lbl = ttk.Label(
            self, text="Cycle Limit (s) [blank = none]:")
        self.cycle_limit_var = tk.StringVar(value="")
        self.cycle_limit_entry = ttk.Entry(
            self, textvariable=self.cycle_limit_var, width=10)
        _bind_numeric_entry(self.cycle_limit_entry)

        # Live preview of the cycle being defined. Drag the dots on the
        # edges: 1st dot = start (Wait After), 2nd = end of ON (ON time),
        # 3rd = next rising edge (OFF time).
        self.cycle_graph = CycleTimelineCanvas(self, height=84)
        self.cycle_graph.m_l = 60
        self.cycle_graph.ROW_H = 52
        self.cycle_graph.edit_cb = self._graph_edit
        self.cycle_graph_hint = ttk.Label(
            self, text="Drag the dots on the graph with the mouse to change "
                       "Wait After / ON time / OFF time (the fields update).",
            font=("Arial", 8, "italic"), wraplength=360, justify="left")
        self._graph_orig = None
        for _v in (self.wait_var, self.cycle_on_var, self.cycle_off_var):
            _v.trace_add("write", lambda *a: self._refresh_cycle_graph())

        self.cycle_hint_lbl = ttk.Label(
            self,
            text="Repeatedly switches ONLY this PSU/Channel ON for the ON "
                 "time, then OFF for the OFF time. Count=0 repeats until "
                 "STOP/EMERGENCY. Every other channel (e.g. ones already "
                 "brought up by an earlier step) is left untouched. The "
                 "channel always ends OFF when this step finishes.",
            font=("Arial", 8, "italic"), wraplength=260, justify="left")

        btns = ttk.Frame(self)
        btns.grid(row=19, column=0, columnspan=2, pady=8)
        ttk.Button(btns, text="Add", command=self._ok).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(
            side="left", padx=4)

        self._update_field_state()

    def _update_field_state(self):
        is_mcu = self.action_var.get() == "MCU"
        psu_state = "disabled" if is_mcu else "readonly"
        entry_state = "disabled" if is_mcu else "normal"

        self.psu_combo.configure(state=psu_state)
        self.ch_combo.configure(state=psu_state)
        self.e_v.configure(state=entry_state)
        self.e_i.configure(state=entry_state)
        self.allow_over_limit_chk.configure(
            state="disabled" if is_mcu else "normal")
        self.characteristic_combo.configure(
            state="disabled" if is_mcu else "readonly")

        if is_mcu:
            self.mcu_cmd_lbl.grid(row=4, column=0, padx=6, pady=4, sticky="w")
            self.mcu_cmd_combo.grid(row=4, column=1, sticky="w")
            if self.mcu_cmd_var.get() == "RUN":
                self.mcu_repeat_lbl.grid(row=5, column=0, padx=6, pady=4, sticky="w")
                self.mcu_repeat_entry.grid(row=5, column=1, sticky="w")
            else:
                self.mcu_repeat_lbl.grid_forget()
                self.mcu_repeat_entry.grid_forget()
            self.mcu_hint_lbl.grid(
                row=8, column=0, columnspan=2, padx=6, pady=(2, 4), sticky="w")

            self.name_lbl.grid_forget()
            self.name_entry.grid_forget()
            self.name_hint_lbl.grid_forget()
            self.mcu_signals_lbl.grid(row=9, column=0, padx=6, pady=4, sticky="w")
            self.mcu_signals_entry.grid(row=9, column=1, sticky="w")
            self.mcu_signals_hint_lbl.grid(
                row=10, column=0, columnspan=2, padx=6, pady=(0, 4), sticky="w")
            self.mcu_profile_lbl.grid(row=11, column=0, padx=6, pady=4, sticky="w")
            self.mcu_profile_combo.grid(row=11, column=1, sticky="w")
        else:
            self.mcu_profile_lbl.grid_forget()
            self.mcu_profile_combo.grid_forget()
            self.mcu_cmd_lbl.grid_forget()
            self.mcu_cmd_combo.grid_forget()
            self.mcu_repeat_lbl.grid_forget()
            self.mcu_repeat_entry.grid_forget()
            self.mcu_hint_lbl.grid_forget()

            self.mcu_signals_lbl.grid_forget()
            self.mcu_signals_entry.grid_forget()
            self.mcu_signals_hint_lbl.grid_forget()
            self.name_lbl.grid(row=9, column=0, padx=6, pady=4, sticky="w")
            self.name_entry.grid(row=9, column=1, sticky="w")
            self.name_hint_lbl.grid(
                row=10, column=0, columnspan=2, padx=6, pady=(0, 4), sticky="w")

        is_cycle = self.action_var.get() == "CYCLE"
        if is_cycle:
            self.cycle_on_lbl.grid(row=12, column=0, padx=6, pady=4, sticky="w")
            self.cycle_on_entry.grid(row=12, column=1, sticky="w")
            self.cycle_off_lbl.grid(row=13, column=0, padx=6, pady=4, sticky="w")
            self.cycle_off_entry.grid(row=13, column=1, sticky="w")
            self.cycle_count_lbl.grid(row=14, column=0, padx=6, pady=4, sticky="w")
            self.cycle_count_entry.grid(row=14, column=1, sticky="w")
            self.cycle_limit_lbl.grid(
                row=15, column=0, padx=6, pady=4, sticky="w")
            self.cycle_limit_entry.grid(row=15, column=1, sticky="w")
            self.cycle_graph.grid(
                row=16, column=0, columnspan=3, padx=6, pady=(4, 0),
                sticky="we")
            self.cycle_graph_hint.grid(
                row=17, column=0, columnspan=3, padx=6, pady=(0, 4),
                sticky="w")
            self.cycle_hint_lbl.grid(
                row=18, column=0, columnspan=2, padx=6, pady=(0, 4), sticky="w")
            self._refresh_cycle_graph()
        else:
            self.cycle_limit_lbl.grid_forget()
            self.cycle_limit_entry.grid_forget()
            self.cycle_graph.grid_forget()
            self.cycle_graph_hint.grid_forget()
            self.cycle_on_lbl.grid_forget()
            self.cycle_on_entry.grid_forget()
            self.cycle_off_lbl.grid_forget()
            self.cycle_off_entry.grid_forget()
            self.cycle_count_lbl.grid_forget()
            self.cycle_count_entry.grid_forget()
            self.cycle_hint_lbl.grid_forget()

    # ---- live cycle graph + mouse editing ---------------------------------
    def _graph_values(self):
        def f(var, default):
            try:
                return max(float(var.get()), 0.0)
            except (ValueError, tk.TclError):
                return default
        return (f(self.wait_var, 0.0), f(self.cycle_on_var, 1.0),
                f(self.cycle_off_var, 1.0))

    def _refresh_cycle_graph(self):
        if self.action_var.get() != "CYCLE":
            return
        start, on_t, off_t = self._graph_values()
        period = on_t + off_t
        if on_t <= 0 or period <= 0:
            self.cycle_graph.set_pattern(
                [], 0.0, "Enter an ON time > 0 to preview the cycle.")
            return
        row = ("PSU CH", "#e6194b", [(start, start + on_t)], False, period)
        handles = [[(start, "wait"), (start + on_t, "cycle_on"),
                    (start + period, "cycle_off")]]
        self.cycle_graph.set_pattern(
            [row], start + period * 2.5, "", handles)

    _GRAPH_VARS = {"wait": "wait_var", "cycle_on": "cycle_on_var",
                   "cycle_off": "cycle_off_var"}
    _GRAPH_MIN = {"wait": 0.0, "cycle_on": 0.001, "cycle_off": 0.0}

    def _graph_edit(self, key, delta, phase):
        var = getattr(self, self._GRAPH_VARS[key])
        if phase == "begin":
            try:
                self._graph_orig = float(var.get())
            except (ValueError, tk.TclError):
                self._graph_orig = self._graph_values()[
                    ("wait", "cycle_on", "cycle_off").index(key)]
            return
        if phase != "move" or self._graph_orig is None:
            return
        value = round(max(self._graph_orig + delta, self._GRAPH_MIN[key]), 3)
        var.set(f"{value:.3f}")

    def _ok(self):
        try:
            wait = float(self.wait_var.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid numeric value.")
            return

        if self.action_var.get() == "MCU":
            cmd = self.mcu_cmd_var.get()
            repeat = 1
            if cmd == "RUN":
                try:
                    repeat = max(1, int(float(self.mcu_repeat_var.get())))
                except ValueError:
                    messagebox.showerror("Error", "Invalid repeat count.")
                    return
            self.result = {
                "psu": None,
                "ch": None,
                "action": "MCU",
                "wait": wait,
                "voltage": 0.0,
                "current": 0.0,
                "allow_over_limit": False,
                "mcu_cmd": cmd,
                "mcu_repeat": repeat,
                "mcu_loop": cmd == "LOOP",
                "mcu_signals": self.mcu_signals_var.get().strip(),
                "mcu_profile": self.mcu_profile_var.get().strip(),
            }
            self.destroy()
            return

        if self.action_var.get() == "CYCLE":
            try:
                voltage = float(self.voltage_var.get())
                current = float(self.current_var.get())
                cycle_on = float(self.cycle_on_var.get())
                cycle_off = float(self.cycle_off_var.get())
                cycle_count = max(0, int(float(self.cycle_count_var.get())))
                limit_txt = self.cycle_limit_var.get().strip()
                cycle_limit = float(limit_txt) if limit_txt else None
            except ValueError:
                messagebox.showerror("Error", "Invalid numeric value.")
                return
            if cycle_limit is not None and cycle_limit <= 0:
                messagebox.showerror("Error", "Cycle Limit must be > 0 (or blank).")
                return
            if cycle_on < 0 or cycle_off < 0:
                messagebox.showerror(
                    "Error", "Cycle ON/OFF Time must not be negative.")
                return
            if cycle_on <= 0 and cycle_off <= 0:
                messagebox.showerror(
                    "Error", "Cycle ON Time and OFF Time cannot both be 0.")
                return

            char_vmax, char_imax = OUTPUT_CHARACTERISTIC_MAP.get(
                self.characteristic_var.get(), (None, None))
            vmax = char_vmax if char_vmax is not None else LIMIT_VOLTAGE_MAX
            imax = char_imax if char_imax is not None else LIMIT_CURRENT_MAX
            allow_over_limit = self.allow_over_limit_var.get()
            if not allow_over_limit:
                if voltage > vmax or current > imax:
                    messagebox.showerror(
                        "Error",
                        f"Voltage/Current exceeds the safety limit "
                        f"({vmax:.0f}V / {imax:.0f}A).\n"
                        'Check "Allow values above the safety limits" if '
                        "this is intentional.")
                    return

            self.result = {
                "psu": int(self.psu_var.get()),
                "ch": int(self.ch_var.get()),
                "action": "CYCLE",
                "wait": wait,
                "voltage": voltage,
                "current": current,
                "allow_over_limit": allow_over_limit,
                "characteristic": self.characteristic_var.get(),
                "name": self.name_var.get().strip(),
                "cycle_on": cycle_on,
                "cycle_off": cycle_off,
                "cycle_count": cycle_count,
            }
            if cycle_limit is not None:
                self.result["cycle_duration"] = cycle_limit
            self.destroy()
            return

        try:
            voltage = float(self.voltage_var.get())
            current = float(self.current_var.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid numeric value.")
            return

        # v14: validate against the selected Output Characteristic preset
        # (if any) instead of the global safety limit, since that preset's
        # OVP/OCP is what will actually be enforced on the instrument.
        char_vmax, char_imax = OUTPUT_CHARACTERISTIC_MAP.get(
            self.characteristic_var.get(), (None, None))
        vmax = char_vmax if char_vmax is not None else LIMIT_VOLTAGE_MAX
        imax = char_imax if char_imax is not None else LIMIT_CURRENT_MAX

        allow_over_limit = self.allow_over_limit_var.get()
        if not allow_over_limit:
            if voltage > vmax or current > imax:
                messagebox.showerror(
                    "Error",
                    f"Voltage/Current exceeds the safety limit "
                    f"({vmax:.0f}V / {imax:.0f}A).\n"
                    'Check "Allow values above the safety limits" if this is '
                    "intentional.")
                return

        self.result = {
            "psu": int(self.psu_var.get()),
            "ch": int(self.ch_var.get()),
            "action": self.action_var.get(),
            "wait": wait,
            "voltage": voltage,
            "current": current,
            "allow_over_limit": allow_over_limit,
            "characteristic": self.characteristic_var.get(),
            "name": self.name_var.get().strip(),
        }
        self.destroy()


# ==============================================================================
if __name__ == "__main__":
    _set_windows_app_id()
    app = App()
    app.mainloop()