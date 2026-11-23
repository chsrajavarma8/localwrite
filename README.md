# LocalWrite

**A private, Grammarly-style AI writing assistant for Windows that runs entirely on your computer through [Ollama](https://ollama.com).**

Select text in any app (Chrome, Edge, WhatsApp, Telegram, Discord, Word, Notepad, VS Code, Gmail…), press **Ctrl+Alt+G**, review the highlighted improvements in a clean white popup, and click **Accept & Replace**. Your text never leaves your PC and is never saved.

---

## Highlights

- **Works across your desktop.** Global shortcuts capture the selected text from the app you're in and safely put the correction back.
- **Writing modes:** Grammar Correction (default), Spelling Correction, Quick Fix, Natural English, Professional Writing, Casual Writing, Improve Clarity, Shorten Text, Expand Text and Custom Instructions. Every mode keeps your meaning, names, technical terms, numbers, dates, links and formatting.
- **Floating popup.** The popup shows the original and the suggestion with removed and added words highlighted. Buttons: Accept & Replace, Copy, Retry, Mode and Close. It never steals focus, scrolls long text, can be resized from the corner and dragged by its header, and positions itself near your cursor.
- **Safe replacement.** LocalWrite goes back to the original window and checks that the same text is still selected before pasting. If anything changed, it copies the result instead and tells you. Your clipboard is restored afterwards.
- **Private by design:**
  - No correction history and no database.
  - Text is read only when you press a shortcut, and there's no keyboard hook.
  - Requests go only to your Ollama server; system proxies are ignored.
  - Logs never contain your text.
  - Temporary clipboard copies are hidden from Win+V history and cloud sync.
- **Light design.** A minimal white interface with Home, Writing Assistant, Settings and About pages, a light tray menu and a first-run setup guide.

## Requirements

- Windows 10 or 11
- Python 3.11+ (only for running from source)
- [Ollama for Windows](https://ollama.com/download/windows) with at least one model

| Model | Size | Notes |
|---|---|---|
| `qwen2.5:3b` | ~1.9 GB | **Recommended.** Fast and accurate on most PCs |
| `llama3.2:3b` | ~2.0 GB | Lightweight alternative |
| `gemma3:4b` | ~3.3 GB | Good writing quality |
| `qwen2.5:7b` | ~4.7 GB | Best quality; 16 GB RAM or a GPU recommended |

Install one with `ollama pull qwen2.5:3b`. LocalWrite never downloads models unless you click *Download* in the setup guide and confirm.

## Install and launch

1. Install Ollama from https://ollama.com/download/windows and pull a model.
2. Double-click **`install.bat`** (add `/desktop` for a desktop shortcut). It creates a private `.venv`, installs PySide6 and requests, adds a Start Menu shortcut, and checks Ollama.
3. Start **LocalWrite** from the Start Menu, or double-click **`run.bat`**.
4. On first launch the setup guide:
   - checks Python and Ollama;
   - starts Ollama if it isn't running, after you click;
   - lists your models so you can choose one;
   - runs a sample grammar correction.

Command-line options: `--minimized` starts in the tray; `--setup` reopens the setup guide.

## How to use

| Shortcut | Action |
|---|---|
| **Ctrl+Alt+G** | Correct with your default mode (Grammar Correction) |
| **Ctrl+Alt+S** | Spelling Correction |
| **Ctrl+Alt+P** | Professional Writing |
| **Ctrl+Alt+Q** | Quick Fix: obvious mistakes only, no rewriting |
| **Esc** | Close the popup (only while it is open) |

Change any shortcut in **Settings › Keyboard shortcuts**. If another program already owns a combination, LocalWrite tells you on the Home page so you can pick another.

**Inside LocalWrite:** the **Writing Assistant** page lets you type or paste text, pick a mode chip, and copy the result. **Correct clipboard text** in the tray menu handles places where you can't select text, such as terminals.

## Settings

| Section | Options |
|---|---|
| Local AI engine | Server address, Test connection, model selector with refresh and test, temperature, response timeout, keep-alive, context window |
| Writing | Default correction mode, custom instructions |
| Keyboard shortcuts | Enable/disable global shortcuts, record new combinations |
| Correction popup | Position (near cursor, mouse, center, corners), close after replacing |
| Clipboard & replacement | Restore clipboard, verify the selection before replacing, timing options |
| Windows integration | Launch on startup, start in tray, minimize to tray, keep running when closed, notifications |
| Privacy | Real-time spelling assistance (optional, off by default), apps it must never read |

Only `settings.json` and technical logs live in `%APPDATA%\LocalWrite`. Neither contains any of your writing. Correction-history files left by an earlier version are deleted automatically on startup.

### Real-time spelling assistance (optional)

It is off by default. When enabled, it reads the focused *classic Windows edit control*, such as Notepad, after you pause typing. If there are spelling fixes, it shows a small blue badge that you can click to review.

It never reads password fields, read-only fields, sign-in windows or excluded apps. An orange dot on the tray icon shows when it's on. Browsers, chat apps and Office use their own text engines, so use the shortcut there.

## Build a standalone .exe

```bat
build_exe.bat
```

This produces `dist\LocalWrite\LocalWrite.exe` using PyInstaller and `localwrite.spec`. The executable is unsigned, so Windows Smart App Control or SmartScreen may block it until you sign it or allow it. Users still need Ollama installed.

## Troubleshooting

| Problem | Fix |
|---|---|
| Can't reach Ollama | Start Ollama from the Start menu or run `ollama serve`; check the address in Settings; click Retry. |
| Model not installed | `ollama pull <model>` or choose another model. |
| "No text selected" | Highlight text first; increase *Wait for selected text* for slow apps. |
| Copied instead of replaced | The selection changed or the app blocks pasting. Click the target spot and press Ctrl+V. |
| Old clipboard item pasted | Increase *Wait before restoring*. |
| Nothing happens in admin apps | Windows blocks input to elevated apps. Run LocalWrite as administrator, or use Copy. |
| A shortcut doesn't work | Another program owns it. Choose a different one in Settings. |
| Slow corrections | Use a lighter model. The first request after start loads the model. |

## Project structure

```
localwrite/
  main.py                 entry point, single-instance guard
  app_controller.py       orchestration: hotkey → capture → AI → popup → replace (no persistence)
  realtime.py             optional real-time spelling assistant
  paths.py                data/resource paths, legacy-history purge
  config/settings.py      typed, validated settings (JSON)
  core/
    modes.py              writing modes + instructions
    correction_engine.py  prompts, output cleaning, long-text chunking
    ollama_client.py      streaming Ollama client, errors, model download (on request)
    diff.py               word-level diff → highlighted rich text
    cancel.py, logging_setup.py
  win/
    hotkeys.py            RegisterHotKey thread (no keyboard hook)
    clipboard.py          full clipboard snapshot/restore, private copies
    text_capture.py       selected-text capture
    text_replace.py       verified, safe replacement with copy fallback
    keyboard_sim.py, window_info.py, text_fields.py, startup.py, winapi.py
  ui/
    theme.py              the white design system (palette, stylesheet, forced light mode)
    icons.py, widgets.py  drawn icons; cards, toggles, setting rows, tiles, chips
    popup.py              floating correction popup
    home_page.py, assistant_page.py, settings_page.py, about_page.py, main_window.py
    tray.py, setup_wizard.py, invoker.py
tests/                    unit, UI, privacy, desktop and end-to-end tests
```

## Tests

```bat
.venv\Scripts\python -m pytest                        :: unit, UI and privacy tests (offscreen, safe)
set LOCALWRITE_DESKTOP_TESTS=1
set LOCALWRITE_OLLAMA_TESTS=1
.venv\Scripts\python -m pytest tests\test_desktop.py tests\test_e2e_app.py
```

The desktop tests drive real windows, the keyboard and the clipboard, so don't type while they run. Your clipboard is restored afterwards.

## Known limitations

- Replacement uses the app's own Ctrl+C / Ctrl+V. Apps that block either one fall back to Copy.
- Rich formatting inside the corrected selection (bold, links) becomes plain text.
- When nothing is selected, VS Code copies the whole line; LocalWrite detects this. Some other editors that do the same may capture the current line.
