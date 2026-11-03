#!/usr/bin/env python3
"""browser.run_flow: run a YAML step list in a real Chrome profile.

Commands:
  run <flow.yaml> [--profile NAME] [--headless] [--keep-open] [--pause-on-fail]
                  [--out DIR] [--var k=v ...]
  snapshot <url>  [--profile NAME] [--headless] [--out DIR]
  open <url>      [--profile NAME]

Secrets are read with the Infisical CLI at run time. They are never printed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from playwright.sync_api import (
    Error as PWError,
    Locator,
    Page,
    TimeoutError as PWTimeout,
    sync_playwright,
)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PROFILES_DIR = Path(
    os.environ.get("BROWSER_FLOW_PROFILES", Path.home() / ".local/share/browser.run_flow/profiles")
)
ACTIONS = {
    "include", "goto", "click", "fill", "type", "press", "select", "check", "wait_for", "wait_for_code",
    "assert", "extract", "download", "screenshot", "snapshot", "evaluate", "sleep", "log", "shell",
}
STEP_OPTIONS = {"name", "optional", "timeout", "if_visible", "if_hidden", "retry"}
DEFAULT_TIMEOUT = 30.0
DEFAULT_CDP_PORT = 9222


class FlowError(Exception):
    pass


# --------------------------------------------------------------------------- secrets
class Secrets:
    """Resolves ${secret:KEY}, ${var:KEY}, ${env:KEY}. Keeps secret values for redaction."""

    PATTERN = re.compile(r"\$\{(secret|var|env):([A-Za-z0-9_./-]+)\}")

    def __init__(self, cfg: dict | None, variables: dict[str, str]):
        self.cfg = cfg or {}
        self.vars = variables
        self.values: dict[str, str] = {}
        self.secret_values: set[str] = set()

    def _load(self, key: str) -> str:
        if key in self.values:
            return self.values[key]
        provider = self.cfg.get("provider", "infisical")
        if provider != "infisical":
            raise FlowError(f"unknown secrets provider: {provider}")
        cmd = ["infisical", "secrets", "get", key, "--silent", "-o", "json"]
        for flag, k in (("--projectId", "project_id"), ("--env", "env"), ("--path", "path")):
            if k in self.cfg:
                cmd += [flag, str(self.cfg[k])]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=REPO).stdout
        except FileNotFoundError:
            raise FlowError("infisical CLI not found in PATH")
        except subprocess.CalledProcessError as e:
            raise FlowError(f"infisical secrets get {key} failed: {e.stderr.strip()[:300]}")
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            raise FlowError(f"infisical returned non-JSON output for {key}")
        items = data if isinstance(data, list) else [data]
        for item in items:
            if item.get("secretKey") == key:
                value = str(item.get("secretValue", ""))
                if not value or value == "CHANGE_ME":
                    raise FlowError(f"secret {key} is empty or still CHANGE_ME in Infisical")
                self.values[key] = value
                self.secret_values.add(value)
                return value
        raise FlowError(f"secret {key} not found in Infisical")

    def resolve(self, value: Any) -> Any:
        if isinstance(value, str):
            def sub(m: re.Match) -> str:
                kind, key = m.group(1), m.group(2)
                if kind == "secret":
                    return self._load(key)
                if kind == "var":
                    if key not in self.vars:
                        raise FlowError(f"variable {key} is not set (use --var {key}=...)")
                    return str(self.vars[key])
                return os.environ.get(key, "")
            return self.PATTERN.sub(sub, value)
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v) for v in value]
        return value

    def contains_secret(self, text: str) -> bool:
        return any(s in text for s in self.secret_values)

    def redact(self, text: Any) -> Any:
        if isinstance(text, str):
            for s in sorted(self.secret_values, key=len, reverse=True):
                text = text.replace(s, "***")
            return text
        if isinstance(text, dict):
            return {k: self.redact(v) for k, v in text.items()}
        if isinstance(text, list):
            return [self.redact(v) for v in text]
        return text


# --------------------------------------------------------------------------- targets
ROLE_RE = re.compile(r'^role=([a-z]+)(?:\[(.*)\])?$')
ATTR_RE = re.compile(r'(\w+)=(?:"([^"]*)"|/([^/]*)/([a-z]*)|([^\s,\]]+))')


def resolve_target(page: Page, target: Any) -> Locator:
    """Turn a target spec into a Playwright Locator.

    String forms:
      css selector                 -> page.locator
      text=Sign on                 -> get_by_text (substring)
      text="Sign on"               -> get_by_text (exact)
      role=button[name="Sign on"]  -> get_by_role
      role=link[name=/stat/i]      -> get_by_role with regex
      label=Card number            -> get_by_label
      placeholder=Password         -> get_by_placeholder
      testid=login-btn             -> get_by_test_id
      xpath=//button               -> page.locator
    Dict form: {role|text|label|placeholder|testid|css: ..., name: ..., exact: bool,
                nth: int, first: bool, last: bool, frame: <frame css>}
    """
    if isinstance(target, str):
        spec: dict[str, Any] = _parse_string_target(target)
    elif isinstance(target, dict):
        spec = dict(target)
    else:
        raise FlowError(f"bad target: {target!r}")

    root: Any = page
    if "frame" in spec:
        root = page.frame_locator(spec.pop("frame"))

    exact = spec.pop("exact", None)
    nth = spec.pop("nth", None)
    first = spec.pop("first", False)
    last = spec.pop("last", False)

    if "role" in spec:
        name = spec.get("name")
        if isinstance(name, str) and name.startswith("/") and name.count("/") >= 2:
            body, _, flags = name[1:].rpartition("/")
            name = re.compile(body, re.I if "i" in flags else 0)
        kwargs: dict[str, Any] = {}
        if name is not None:
            kwargs["name"] = name
        if exact is not None:
            kwargs["exact"] = exact
        loc = root.get_by_role(spec["role"], **kwargs)
    elif "text" in spec:
        loc = root.get_by_text(spec["text"], exact=bool(exact))
    elif "label" in spec:
        loc = root.get_by_label(spec["label"], exact=bool(exact))
    elif "placeholder" in spec:
        loc = root.get_by_placeholder(spec["placeholder"], exact=bool(exact))
    elif "testid" in spec:
        loc = root.get_by_test_id(spec["testid"])
    elif "css" in spec:
        loc = root.locator(spec["css"])
    elif "xpath" in spec:
        loc = root.locator("xpath=" + spec["xpath"])
    else:
        raise FlowError(f"target has no selector: {target!r}")

    if nth is not None:
        loc = loc.nth(int(nth))
    elif first:
        loc = loc.first
    elif last:
        loc = loc.last
    return loc


def _parse_string_target(s: str) -> dict[str, Any]:
    m = ROLE_RE.match(s)
    if m:
        spec: dict[str, Any] = {"role": m.group(1)}
        for am in ATTR_RE.finditer(m.group(2) or ""):
            k = am.group(1)
            if am.group(2) is not None:
                spec[k] = am.group(2)
                if k == "name":
                    spec.setdefault("exact", True)
            elif am.group(3) is not None:
                spec[k] = f"/{am.group(3)}/{am.group(4)}"
            else:
                v = am.group(5)
                spec[k] = v if k != "nth" else int(v)
        if spec.get("exact") == "true":
            spec["exact"] = True
        return spec
    for prefix in ("text", "label", "placeholder", "testid", "xpath"):
        if s.startswith(prefix + "="):
            v = s[len(prefix) + 1:]
            spec = {prefix: v}
            if len(v) >= 2 and v[0] == v[-1] == '"':
                spec = {prefix: v[1:-1], "exact": True}
            return spec
    return {"css": s}


# --------------------------------------------------------------------------- runner
class Runner:
    def __init__(self, page: Page, secrets: Secrets, out: Path, log):
        self.page = page
        self.secrets = secrets
        self.out = out
        self.log = log
        self.extracted: dict[str, Any] = {}
        self.downloads: list[str] = []
        self.shots = 0

    # ---- helpers
    def _t(self, target: Any) -> Locator:
        return resolve_target(self.page, target)

    def _ms(self, step: dict, default: float = DEFAULT_TIMEOUT) -> float:
        return float(step.get("timeout", default)) * 1000

    def _describe(self, action: str, arg: Any, step: dict) -> str:
        if action in ("fill", "type") and (isinstance(arg, dict) and arg.get("secret") or self._arg_has_secret(arg)):
            tgt = arg.get("target") if isinstance(arg, dict) else arg
            return f"{action} {tgt!r} ***"
        return self.secrets.redact(f"{action} {arg!r}")

    def _arg_has_secret(self, arg: Any) -> bool:
        return self.secrets.contains_secret(json.dumps(arg, ensure_ascii=False, default=str))

    def screenshot(self, name: str) -> str:
        self.shots += 1
        path = self.out / f"{self.shots:02d}-{_slug(name)}.png"
        try:
            self.page.screenshot(path=str(path), full_page=False)
        except PWError as e:
            self.log(f"  screenshot failed: {e.__class__.__name__}")
            return ""
        return str(path)

    def snapshot(self, name: str) -> str:
        path = self.out / f"{_slug(name)}.snapshot.yaml"
        try:
            tree = self.page.locator("body").aria_snapshot()
        except PWError as e:
            tree = f"# aria snapshot failed: {e}"
        header = f"# url: {self.page.url}\n# title: {self.page.title()}\n"
        path.write_text(header + self.secrets.redact(tree))
        return str(path)

    def dump_failure(self, index: int) -> dict[str, str]:
        arts = {}
        arts["screenshot"] = self.screenshot(f"fail-step{index}")
        arts["snapshot"] = self.snapshot(f"fail-step{index}")
        try:
            html = self.out / f"fail-step{index}.html"
            html.write_text(self.secrets.redact(self.page.content()))
            arts["html"] = str(html)
        except PWError:
            pass
        arts["url"] = self.page.url
        return arts

    # ---- step dispatch
    def run_step(self, index: int, step: dict) -> None:
        action, arg = _split_step(step)
        if "if_visible" in step and not self._t(step["if_visible"]).first.is_visible():
            self.log(f"[{index}] skip ({self._describe(action, arg, step)}): if_visible not met")
            return
        if "if_hidden" in step and self._t(step["if_hidden"]).first.is_visible():
            self.log(f"[{index}] skip ({self._describe(action, arg, step)}): if_hidden not met")
            return
        if isinstance(arg, dict) and arg.get("secret") and "value" in arg:
            self.secrets.secret_values.add(str(arg["value"]))
        self.log(f"[{index}] {self._describe(action, arg, step)}")
        attempts = int(step.get("retry", 0)) + 1
        for attempt in range(attempts):
            try:
                getattr(self, "do_" + action)(arg, step)
                return
            except (KeyError, TypeError, ValueError) as e:
                raise FlowError(f"bad step arguments for {action}: {e!r}") from e
            except (PWError, FlowError, AssertionError) as e:
                if attempt + 1 < attempts:
                    self.log(f"  attempt {attempt + 1} failed, retrying: {_short_err(e)}")
                    continue
                raise

    def do_goto(self, arg, step):
        url = arg if isinstance(arg, str) else arg["url"]
        wait = arg.get("wait_until", "load") if isinstance(arg, dict) else "load"
        self.page.goto(url, timeout=self._ms(step, 60), wait_until=wait)

    def do_click(self, arg, step):
        target = arg if not isinstance(arg, dict) else arg["target"]
        self._t(target).click(timeout=self._ms(step))

    def do_fill(self, arg, step):
        if not isinstance(arg, dict):
            raise FlowError("fill needs {target, value}")
        self._t(arg["target"]).fill(str(arg["value"]), timeout=self._ms(step))

    def do_type(self, arg, step):
        if not isinstance(arg, dict):
            raise FlowError("type needs {target, value}")
        loc = self._t(arg["target"])
        loc.click(timeout=self._ms(step))
        loc.press_sequentially(str(arg["value"]), delay=int(arg.get("delay_ms", 60)))

    def do_press(self, arg, step):
        if isinstance(arg, str):
            self.page.keyboard.press(arg)
        else:
            self._t(arg["target"]).press(arg["key"], timeout=self._ms(step))

    def do_select(self, arg, step):
        self._t(arg["target"]).select_option(arg["value"], timeout=self._ms(step))

    def do_check(self, arg, step):
        target = arg if not isinstance(arg, dict) else arg["target"]
        self._t(target).check(timeout=self._ms(step))

    def do_wait_for(self, arg, step):
        if isinstance(arg, (int, float)):
            time.sleep(float(arg))
            return
        if isinstance(arg, str):
            arg = {"target": arg}
        ms = self._ms(step)
        if "url" in arg:
            self.page.wait_for_url(arg["url"], timeout=ms)
        if "target" in arg:
            self._t(arg["target"]).first.wait_for(state=arg.get("state", "visible"), timeout=ms)
        if "text" in arg:
            self.page.get_by_text(arg["text"]).first.wait_for(state=arg.get("state", "visible"), timeout=ms)
        if "load" in arg:
            self.page.wait_for_load_state(arg["load"], timeout=ms)
        if "any" in arg:  # first of several targets to become visible
            deadline = time.time() + ms / 1000
            while time.time() < deadline:
                for t in arg["any"]:
                    if self._t(t).first.is_visible():
                        self.extracted.setdefault("_wait_any", {})[str(step.get("name", "any"))] = t
                        return
                time.sleep(0.5)
            raise FlowError(f"none of {arg['any']} became visible")

    def do_wait_for_code(self, arg, step):
        """Wait for a one-time code from an external source, then fill it.

        source: file  -> poll `path` until it contains `pattern`; the file is deleted after use.
        source: prompt -> read one line from stdin (interactive runs only).
        """
        pattern = re.compile(arg.get("pattern", r"\b\d{4,8}\b"))
        source = arg.get("source", "file")
        timeout = float(step.get("timeout", 180))
        code = None
        if source == "file":
            path = Path(self.secrets.resolve(arg["path"]))
            deadline = time.time() + timeout
            self.log(f"  waiting for code in {path} (timeout {timeout:.0f}s)")
            while time.time() < deadline:
                if path.exists():
                    m = pattern.search(path.read_text())
                    if m:
                        code = m.group(0)
                        path.unlink(missing_ok=True)
                        break
                time.sleep(1)
        elif source == "prompt":
            print("Enter code: ", end="", file=sys.stderr, flush=True)
            line = sys.stdin.readline()
            m = pattern.search(line)
            code = m.group(0) if m else None
        else:
            raise FlowError(f"wait_for_code: unknown source {source}")
        if not code:
            raise FlowError("no code received before timeout")
        self.secrets.secret_values.add(code)
        if "fill" in arg:
            self._t(arg["fill"]).fill(code, timeout=self._ms(step, 30))
        if "submit" in arg:
            sub = arg["submit"]
            if sub == "Enter":
                self.page.keyboard.press("Enter")
            else:
                self._t(sub).click(timeout=self._ms(step, 30))

    def do_assert(self, arg, step):
        if isinstance(arg, str):
            arg = {"target": arg}
        ms = self._ms(step, 10)
        if "url" in arg:
            self.page.wait_for_url(arg["url"], timeout=ms)
        if "target" in arg:
            loc = self._t(arg["target"]).first
            loc.wait_for(state=arg.get("state", "visible"), timeout=ms)
            if "text" in arg:
                actual = loc.inner_text(timeout=ms)
                if arg["text"] not in actual:
                    raise AssertionError(f"expected {arg['text']!r} in {self.secrets.redact(actual)[:200]!r}")
        elif "text" in arg:
            self.page.get_by_text(arg["text"]).first.wait_for(state="visible", timeout=ms)
        if "title" in arg:
            t = self.page.title()
            if arg["title"] not in t:
                raise AssertionError(f"expected title to contain {arg['title']!r}, got {t!r}")

    def do_extract(self, arg, step):
        name = arg["name"]
        attr = arg.get("attr", "text")
        loc = self._t(arg["target"])
        items = loc.all() if arg.get("all") else [loc.first]
        values = []
        for it in items:
            if attr == "text":
                v = it.inner_text(timeout=self._ms(step, 10))
            elif attr == "value":
                v = it.input_value(timeout=self._ms(step, 10))
            else:
                v = it.get_attribute(attr, timeout=self._ms(step, 10))
            v = v.strip() if isinstance(v, str) else v
            if "regex" in arg and isinstance(v, str):
                m = re.search(arg["regex"], v)
                v = m.group(1) if (m and m.groups()) else (m.group(0) if m else None)
            values.append(v)
        self.extracted[name] = values if arg.get("all") else (values[0] if values else None)
        self.log(f"  {name} = {self.secrets.redact(json.dumps(self.extracted[name], ensure_ascii=False))[:300]}")

    def do_download(self, arg, step):
        """download: target | {click, save_as, dir, each, max, skip_existing}

        each: true -> click every element that matches `click` (up to `max`) and name each
        file after the element's text plus `ext` (default .pdf). With skip_existing (default
        true) a file that already exists is not downloaded again.
        """
        if isinstance(arg, str):
            arg = {"click": arg}
        save_dir = Path(self.secrets.resolve(arg.get("dir", str(self.out / "downloads"))))
        save_dir.mkdir(parents=True, exist_ok=True)
        if not arg.get("each"):
            dest = save_dir / (self.secrets.resolve(arg.get("save_as")) or "")
            if arg.get("save_as") and arg.get("skip_existing") and dest.exists():
                self.log(f"  exists, skipped {dest}")
                return
            self._download_one(self._t(arg["click"]), save_dir, self.secrets.resolve(arg.get("save_as")), step)
            return
        loc = self._t(arg["click"])
        loc.first.wait_for(state="visible", timeout=self._ms(step))
        count = min(loc.count(), int(arg.get("max", 100)))
        ext = arg.get("ext", ".pdf")
        skipped = 0
        template = self.secrets.resolve(arg.get("save_as")) or "{label}" + ext
        for i in range(count):
            item = loc.nth(i)
            label = item.inner_text(timeout=self._ms(step, 10)).strip().splitlines()[0]
            name = template.format(label=_slug(label), date=_last_date(label) or _slug(label), index=i + 1)
            if arg.get("skip_existing", True) and (save_dir / name).exists():
                skipped += 1
                continue
            self._download_one(item, save_dir, name, step)
        self.log(f"  {count} matched, {count - skipped} downloaded, {skipped} already present")
        self.extracted.setdefault("_downloads", {})[str(step.get("name", save_dir.name))] = {
            "matched": count, "downloaded": count - skipped, "skipped": skipped}

    def _download_one(self, loc: Locator, save_dir: Path, name: str | None, step: dict) -> None:
        with self.page.expect_download(timeout=self._ms(step, 120)) as dl_info:
            loc.click(timeout=self._ms(step))
        dl = dl_info.value
        dest = save_dir / (name or dl.suggested_filename)
        dl.save_as(str(dest))
        self.downloads.append(str(dest))
        self.log(f"  saved {dest}")

    def do_screenshot(self, arg, step):
        self.log(f"  {self.screenshot(arg if isinstance(arg, str) else arg.get('name', 'shot'))}")

    def do_snapshot(self, arg, step):
        self.log(f"  {self.snapshot(arg if isinstance(arg, str) else arg.get('name', 'page'))}")

    def do_evaluate(self, arg, step):
        js = arg if isinstance(arg, str) else arg["js"]
        result = self.page.evaluate(js)
        if isinstance(arg, dict) and "name" in arg:
            self.extracted[arg["name"]] = result
            self.log(f"  {arg['name']} = {self.secrets.redact(json.dumps(result, default=str))[:300]}")

    def do_sleep(self, arg, step):
        time.sleep(float(arg))

    def do_shell(self, arg, step):
        """shell: run a command in the repository root. Fails on a non-zero exit code."""
        cmd = arg if isinstance(arg, str) else arg["cmd"]
        proc = subprocess.run(cmd, shell=True, cwd=REPO, capture_output=True, text=True,
                              timeout=float(step.get("timeout", 600)))
        for line in (proc.stdout + proc.stderr).strip().splitlines()[-20:]:
            self.log("  | " + self.secrets.redact(line))
        if proc.returncode != 0:
            raise FlowError(f"shell exited {proc.returncode}: {cmd[:120]}")
        if isinstance(arg, dict) and "name" in arg:
            self.extracted[arg["name"]] = proc.stdout.strip()

    def do_log(self, arg, step):
        self.log(f"  {self.secrets.redact(str(arg))}")


# --------------------------------------------------------------------------- utilities
def _split_step(step: dict) -> tuple[str, Any]:
    keys = [k for k in step if k in ACTIONS]
    if len(keys) != 1:
        raise FlowError(f"step must have exactly one action, got {list(step)}")
    unknown = [k for k in step if k not in ACTIONS and k not in STEP_OPTIONS]
    if unknown:
        raise FlowError(f"unknown step options {unknown}; valid: {sorted(STEP_OPTIONS)}")
    arg = step[keys[0]]
    if isinstance(arg, dict):  # options may also live inside the action mapping
        arg = dict(arg)
        for k in STEP_OPTIONS - {"name"}:
            if k in arg:
                step.setdefault(k, arg.pop(k))
    return keys[0], arg


MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
DATE_RE = re.compile(r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s+(\d{4})", re.I)


def _last_date(text: str) -> str | None:
    """Last 'Month D, YYYY' in text as YYYY-MM-DD, e.g. a statement period's end date."""
    found = DATE_RE.findall(text)
    if not found:
        return None
    month, day, year = found[-1]
    return f"{year}-{MONTHS[month.lower()]:02d}-{int(day):02d}"


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")[:60] or "x"


def _short_err(e: Exception) -> str:
    msg = str(e).splitlines()[0] if str(e) else e.__class__.__name__
    return f"{e.__class__.__name__}: {msg[:300]}"


def load_flow(path: Path, _depth: int = 0) -> dict:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise FlowError(f"{path}: YAML error: {e}\nHint: inside {{...}} quote targets that contain [ or ], e.g. target: 'role=button[name=\"OK\"]'")
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise FlowError(f"{path}: flow must be a mapping with a 'steps' list")
    if _depth > 5:
        raise FlowError(f"{path}: include nesting too deep")
    steps: list = []
    for raw in data["steps"]:
        if isinstance(raw, dict) and "include" in raw:
            inc = raw["include"]
            if isinstance(inc, str):
                inc = {"flow": inc}
            sub_path = (path.parent / inc["flow"]).resolve()
            sub = load_flow(sub_path, _depth + 1)
            for key in ("secrets", "profile"):
                if key in sub and key not in data:
                    data[key] = sub[key]
            data["vars"] = {**(sub.get("vars") or {}), **(data.get("vars") or {})}
            sub_steps = sub["steps"]
            if inc.get("vars"):  # fix these variables for the included steps only
                text = yaml.safe_dump(sub_steps, allow_unicode=True)
                for k, v in inc["vars"].items():
                    text = text.replace("${var:%s}" % k, str(v))
                sub_steps = yaml.safe_load(text)
            steps += sub_steps
        else:
            steps.append(raw)
    data["steps"] = steps
    return data


def launch(p, profile: str, headless: bool, cdp_port: int = 0):
    user_dir = PROFILES_DIR / profile
    user_dir.mkdir(parents=True, exist_ok=True)
    extra = [f"--remote-debugging-port={cdp_port}"] if cdp_port else []
    return p.chromium.launch_persistent_context(
        str(user_dir),
        channel="chrome",
        headless=headless,
        viewport=None if not headless else {"width": 1366, "height": 900},
        no_viewport=not headless,
        accept_downloads=True,
        ignore_default_args=["--enable-automation"],
        args=["--disable-blink-features=AutomationControlled", "--no-first-run", "--no-default-browser-check", *extra],
        locale="en-CA",
        timezone_id="America/Toronto",
    )


def wait_until_closed(context, log) -> None:
    log("browser stays open. Close the window to finish (or Ctrl-C).")
    closed = {"v": False}
    context.on("close", lambda *_: closed.__setitem__("v", True))
    try:
        while not closed["v"]:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass


# --------------------------------------------------------------------------- commands
def cmd_run(args) -> int:
    flow_path = Path(args.flow).resolve()
    flow = load_flow(flow_path)
    name = flow.get("name", flow_path.stem)
    profile = args.profile or flow.get("profile", "default")
    variables = dict(flow.get("vars") or {})
    for kv in args.var or []:
        k, _, v = kv.partition("=")
        variables[k] = v
    secrets = Secrets(flow.get("secrets"), variables)

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out).resolve() if args.out else REPO / "temp" / "browser.run_flow" / _slug(name) / stamp
    out.mkdir(parents=True, exist_ok=True)
    log_file = (out / "log.txt").open("a")

    def log(msg: str) -> None:
        line = f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}"
        print(line, file=sys.stderr, flush=True)
        log_file.write(line + "\n")
        log_file.flush()

    log(f"flow {name} profile={profile} headless={args.headless} out={out}")
    result: dict[str, Any] = {"ok": False, "flow": name, "profile": profile, "artifacts_dir": str(out),
                              "steps_total": len(flow["steps"]), "steps_run": 0}
    headless = bool(args.headless or flow.get("headless"))
    with sync_playwright() as p:
        cdp_port = args.cdp_port if args.cdp_port is not None else (DEFAULT_CDP_PORT if args.keep_open or args.pause_on_fail else 0)
        if cdp_port:
            log(f"CDP port {cdp_port}: use `run attach --cdp {cdp_port} ...` to drive this browser")
        context = launch(p, profile, headless, cdp_port)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT * 1000)
        runner = Runner(page, secrets, out, log)
        failed = None
        try:
            for i, raw in enumerate(flow["steps"], start=1):
                if i < (args.from_step or 1):
                    continue
                if not isinstance(raw, dict):
                    raise FlowError(f"step {i} is not a mapping: {raw!r}")
                step = secrets.resolve(raw)
                try:
                    runner.run_step(i, step)
                except (PWError, FlowError, AssertionError) as e:
                    if step.get("optional"):
                        log(f"  optional step failed, continuing: {_short_err(e)}")
                    else:
                        raise
                result["steps_run"] = i
            result["ok"] = True
        except (PWError, FlowError, AssertionError, Exception) as e:
            idx = result["steps_run"] + 1
            failed = {"index": idx, "step": secrets.redact(flow["steps"][idx - 1]) if idx <= len(flow["steps"]) else None,
                      "error": secrets.redact(_short_err(e))}
            log(f"FAILED at step {idx}: {failed['error']}")
            try:
                failed["artifacts"] = runner.dump_failure(idx)
            except PWError:
                pass
            result["failed_step"] = failed
        except KeyboardInterrupt:
            result["failed_step"] = {"index": result["steps_run"] + 1, "error": "interrupted"}
        finally:
            result["url"] = secrets.redact(page.url) if not page.is_closed() else None
            result["extracted"] = secrets.redact(runner.extracted)
            result["downloads"] = runner.downloads
            (out / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
            if args.keep_open or (args.pause_on_fail and failed and not headless):
                wait_until_closed(context, log)
            try:
                context.close()
            except PWError:
                pass
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def cmd_snapshot(args) -> int:
    out = Path(args.out).resolve() if args.out else REPO / "temp" / "browser.run_flow" / "snapshot"
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = launch(p, args.profile, args.headless)
        page = context.pages[0] if context.pages else context.new_page()
        if args.url:
            page.goto(args.url, timeout=60_000)
            if args.wait:
                time.sleep(float(args.wait))
        runner = Runner(page, Secrets(None, {}), out, lambda m: print(m, file=sys.stderr))
        snap = runner.snapshot("page")
        shot = runner.screenshot("page")
        print(Path(snap).read_text())
        print(f"# screenshot: {shot}", file=sys.stderr)
        context.close()
    return 0


def cmd_open(args) -> int:
    with sync_playwright() as p:
        context = launch(p, args.profile, False, args.cdp_port)
        page = context.pages[0] if context.pages else context.new_page()
        if args.url:
            page.goto(args.url, timeout=60_000)
        print(f"CDP port {args.cdp_port}: use `run attach --cdp {args.cdp_port} ...`", file=sys.stderr)
        wait_until_closed(context, lambda m: print(m, file=sys.stderr))
        try:
            context.close()
        except PWError:
            pass
    return 0


def cmd_attach(args) -> int:
    """Run steps against a browser that `run --keep-open` or `open` started (CDP)."""
    out = Path(args.out).resolve() if args.out else REPO / "temp" / "browser.run_flow" / "attach"
    out.mkdir(parents=True, exist_ok=True)
    steps: list = []
    flow: dict = {}
    if args.flow:
        flow = load_flow(Path(args.flow))
        steps += flow["steps"]
    for raw in args.step or []:
        try:
            st = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise FlowError(f"--step is not valid YAML: {raw!r}: {e}\nHint: quote targets that contain [ ] inside {{...}}")
        if isinstance(st, list):
            steps += st
        else:
            steps.append(st)
    variables = dict(flow.get("vars") or {})
    for kv in args.var or []:
        k, _, v = kv.partition("=")
        variables[k] = v
    secrets = Secrets(flow.get("secrets"), variables)

    def log(msg: str) -> None:
        print(f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)

    result: dict[str, Any] = {"ok": False, "steps_total": len(steps), "steps_run": 0}
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{args.cdp}")
        except PWError as e:
            raise FlowError(f"cannot attach to CDP port {args.cdp}: {_short_err(e)}. Start the browser with `run ... --keep-open` or `run open`.")
        context = browser.contexts[0]
        pages = [pg for pg in context.pages if not pg.url.startswith(("chrome://", "devtools://"))] or context.pages
        page = pages[-1]
        page.set_default_timeout(DEFAULT_TIMEOUT * 1000)
        runner = Runner(page, secrets, out, log)
        try:
            for i, raw in enumerate(steps, start=1):
                step = secrets.resolve(raw)
                try:
                    runner.run_step(i, step)
                except (PWError, FlowError, AssertionError) as e:
                    if step.get("optional"):
                        log(f"  optional step failed, continuing: {_short_err(e)}")
                    else:
                        raise
                result["steps_run"] = i
            result["ok"] = True
        except (PWError, FlowError, AssertionError) as e:
            idx = result["steps_run"] + 1
            result["failed_step"] = {"index": idx, "step": secrets.redact(steps[idx - 1]), "error": secrets.redact(_short_err(e)),
                                     "artifacts": runner.dump_failure(idx)}
            log(f"FAILED at step {idx}: {result['failed_step']['error']}")
        finally:
            result["url"] = secrets.redact(page.url)
            result["title"] = secrets.redact(page.title())
            result["extracted"] = secrets.redact(runner.extracted)
            result["downloads"] = runner.downloads
            if args.snapshot or not steps:
                result["snapshot"] = runner.snapshot("page")
                print(Path(result["snapshot"]).read_text())
            browser.close()  # detaches only; the browser keeps running
    print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr if (args.snapshot or not steps) else sys.stdout)
    return 0 if result["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="browser.run_flow", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a flow YAML")
    r.add_argument("flow")
    r.add_argument("--profile")
    r.add_argument("--headless", action="store_true")
    r.add_argument("--keep-open", action="store_true", help="keep the browser open after the flow")
    r.add_argument("--pause-on-fail", action="store_true", help="keep the browser open if a step fails")
    r.add_argument("--out", help="artifacts folder (default temp/browser.run_flow/<flow>/<time>)")
    r.add_argument("--var", action="append", metavar="KEY=VALUE")
    r.add_argument("--from-step", type=int, metavar="N", help="skip steps before N")
    r.add_argument("--cdp-port", type=int, help=f"expose a CDP port for `attach` (default {DEFAULT_CDP_PORT} with --keep-open/--pause-on-fail)")
    r.set_defaults(fn=cmd_run)

    a = sub.add_parser("attach", help="run steps in the browser that `run --keep-open` or `open` started")
    a.add_argument("flow", nargs="?", help="flow YAML (steps, secrets, vars)")
    a.add_argument("--step", action="append", metavar="YAML", help="one step as inline YAML, e.g. 'click: role=link[name=\"Statements\"]'. Can repeat.")
    a.add_argument("--cdp", type=int, default=DEFAULT_CDP_PORT)
    a.add_argument("--snapshot", action="store_true", help="print the accessibility tree after the steps")
    a.add_argument("--var", action="append", metavar="KEY=VALUE")
    a.add_argument("--out")
    a.set_defaults(fn=cmd_attach)

    s = sub.add_parser("snapshot", help="print the accessibility tree of a URL")
    s.add_argument("url", nargs="?")
    s.add_argument("--profile", default="default")
    s.add_argument("--headless", action="store_true")
    s.add_argument("--wait", type=float, default=2, help="seconds to wait after load")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_snapshot)

    o = sub.add_parser("open", help="open a headed browser in a profile and wait until it is closed")
    o.add_argument("url", nargs="?")
    o.add_argument("--profile", default="default")
    o.add_argument("--cdp-port", type=int, default=DEFAULT_CDP_PORT)
    o.set_defaults(fn=cmd_open)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except FlowError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
