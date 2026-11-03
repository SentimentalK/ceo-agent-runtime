# browser.run_flow

Runs a list of browser steps from a YAML file in a real Google Chrome profile. Use it to sign on to a web site, click, fill forms, download files, and extract text. Site recipes live in `flows/<site>/<task>.yaml` at the repository root.

## Setup

```bash
capabilities/browser.run_flow/setup
```

Needs `uv`, `google-chrome`, and the `infisical` CLI (logged in) in `PATH`.

## Run

```bash
capabilities/browser.run_flow/run run flows/<site>/<task>.yaml [options]
capabilities/browser.run_flow/run snapshot <URL> [--profile NAME] [--headless]
capabilities/browser.run_flow/run open <URL> --profile NAME
capabilities/browser.run_flow/run attach [flow.yaml] [--step '<yaml>' ...] [--snapshot] [--cdp 9222]
```

- `run`: runs the flow. Prints a JSON result to stdout. Writes a log and artifacts to `temp/browser.run_flow/<flow>/<time>/`.
- `snapshot`: opens the URL and prints the accessibility tree of the page. Use it to find targets before you write a flow.
- `open`: opens a headed browser in a profile and waits until you close the window. Use it for a one-time manual sign-on.
- `attach`: runs steps in a browser that `run --keep-open`, `run --pause-on-fail`, or `open` started. The browser stays open after `attach` ends. Use it to explore a signed-on site one step at a time. Without steps, or with `--snapshot`, it prints the accessibility tree of the current page.

## Explore a signed-on site

1. Sign on with the window kept open: `run run flows/<site>/login.yaml --keep-open`. This exposes CDP port 9222.
2. Look at the page: `run attach --snapshot`.
3. Run one step: `run attach --step 'click: role=link[name="Statements"]' --snapshot`.
4. Repeat until the task works. Then put the steps into `flows/<site>/<task>.yaml`.
5. Run the new flow with `run attach flows/<site>/<task>.yaml` in the same browser. It does not sign on again.

## Options for `run`

- `--profile NAME`: Chrome profile. Default: the `profile` key in the flow, then `default`. Profiles persist cookies and sessions in `~/.local/share/browser.run_flow/profiles/`.
- `--headless`: no window. Do not use it for bank sites. They detect headless browsers.
- `--keep-open`: keep the browser open after the last step until the window is closed.
- `--pause-on-fail`: keep the browser open after a failed step. The user can then finish the step by hand.
- `--var KEY=VALUE`: set `${var:KEY}`. Can repeat.
- `--from-step N`: skip steps before N.
- `--cdp-port N`: port for `attach`. Default: 9222 when `--keep-open` or `--pause-on-fail` is set, else none.
- `--out DIR`: artifacts folder.

## Flow file

```yaml
name: cibc.login
profile: cibc
headless: false
secrets: {provider: infisical, project_id: <id>, env: prod, path: /automation/cibc}
vars: {month: "2026-10"}
steps:
  - goto: https://example.com/signon
  - fill: {target: role=textbox[name="Card number"], value: "${secret:CIBC_CARD_NUMBER}", secret: true}
  - click: role=button[name="Continue"]
  - wait_for: {target: role=heading[name=/my accounts/i], timeout: 300}
  - extract: {name: balance, target: ".balance", regex: "([0-9,.]+)"}
  - download: {click: "text=Download PDF", save_as: "${var:month}.pdf"}
```

### Values

- `${secret:KEY}`: read from Infisical with the `secrets` block. The value is never printed. It is replaced with `***` in logs, results, snapshots, and HTML dumps.
- `${var:KEY}`: from `vars` or `--var`.
- `${env:KEY}`: from the environment.
- `secret: true` on `fill` or `type`: hide the value in the log and redact it everywhere.

### Targets

| Form | Meaning |
|---|---|
| `#id`, `.class`, `div > a` | CSS selector |
| `role=button[name="Sign on"]` | Element by ARIA role and exact name |
| `role=link[name=/statement/i]` | Role with regex name |
| `text=Sign on` / `text="Sign on"` | Element by text (substring / exact) |
| `label=Card number` | Form control by label |
| `placeholder=Password` | Input by placeholder |
| `testid=login-btn` | `data-testid` |
| `xpath=//button` | XPath |
| `{role: button, name: Continue, nth: 1, frame: "iframe#login"}` | Dict form with `exact`, `nth`, `first`, `last`, `frame` |

Inside a `{...}` mapping, put quotes around a target that contains `[`: `{target: 'role=button[name="Continue"]', timeout: 5}`. Prefer `role=` and `label=` targets. CSS class names on bank sites change often. Get names from `snapshot`.

### Actions

One action per step. Options `optional`, `timeout` (seconds), `retry`, `if_visible`, `if_hidden` go next to the action or inside its mapping.

| Action | Argument |
|---|---|
| `goto` | URL, or `{url, wait_until}` |
| `click` | target |
| `fill` | `{target, value, secret}` sets the value at once |
| `type` | `{target, value, delay_ms, secret}` types key by key |
| `press` | key name, or `{target, key}` |
| `select` | `{target, value}` |
| `check` | target |
| `wait_for` | target, seconds, or `{target, url, text, load, any: [targets], state, timeout}` |
| `wait_for_code` | `{source: file, path, pattern, fill, submit}` waits for a one-time code in a file, fills it, submits. The file is deleted after use. |
| `assert` | target, or `{target, text, url, title}` |
| `extract` | `{name, target, attr: text\|value\|href\|..., all, regex}` saves into `extracted` |
| `download` | target, or `{click, save_as, dir, skip_existing}`. With `each: true` it clicks every match (up to `max`) and names each file from `save_as` with `{label}`, `{date}` (last "Month D, YYYY" in the element text as YYYY-MM-DD), `{index}`. Existing files are skipped. `allow_none: true` makes zero matches a success. |
| `screenshot` | name |
| `snapshot` | name. Writes `<name>.snapshot.yaml` with the accessibility tree. |
| `evaluate` | JS string, or `{js, name}` |
| `sleep` | seconds |
| `log` | text |
| `shell` | command string, or `{cmd, name}`. Runs in the repository root. Fails on a non-zero exit. |
| `include` | `path.yaml` or `{flow: path.yaml, vars: {k: v}}`. Inserts the steps of another flow (path relative to this file). `vars` fix `${var:k}` for the included steps only. The first included `secrets` and `profile` apply when the flow has none. |

## Compose flows

A task flow calls other flows with `include`. Example `flows/cibc/all_estatements.yaml`:

```yaml
steps:
  - shell: rclone copy "onedrive:Folder" output/cibc
  - include: login.yaml
  - include: {flow: download_estatements.yaml, vars: {card: CIBC MasterCard}}
  - include: {flow: download_estatements.yaml, vars: {card: CIBC VISA}}
  - shell: rclone copy output/cibc "onedrive:Folder"
```

## Output

- stdout: JSON with `ok`, `steps_run`, `failed_step`, `extracted`, `downloads`, `artifacts_dir`.
- On failure the artifacts folder has `fail-step<N>.png`, `fail-step<N>.snapshot.yaml`, and `fail-step<N>.html`. Read the snapshot to find the correct target. Then fix the flow.
- Exit code 0 on success, 1 on a failed step, 2 on a bad flow file.

## Rules

1. Run bank flows with a window (no `--headless`). The window opens on the user's screen.
2. Do not print, log, or ask for secret values. Use `${secret:KEY}` and `secret: true`.
3. Before you write a new flow, run `snapshot` on the page. Build targets from the tree.
4. When a step fails, read `fail-step<N>.snapshot.yaml` in the artifacts folder. Fix the target. Run again with `--from-step N` if the browser state allows it.
5. If a flow needs a one-time code and no code source is set up, run with `--keep-open` and ask the user to type the code in the browser window.
6. Delete the `temp/browser.run_flow/` artifacts when the task is complete.
7. Do not use `wait_for: {load: networkidle}` on bank sites. They poll the server and never go idle. Wait for a heading or a button instead.
8. Do not click "Accept" or "No thanks" on an offer page. Go to the next URL with `goto` instead.

## Tests

```bash
capabilities/browser.run_flow/tests/run_tests.sh
```
