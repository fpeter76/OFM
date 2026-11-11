# OFM

Click to the [link](https://github.com/fpeter76/OFM/blob/main/script.user.js).

## Python game assistant

The Python assistant is split into three modules:

- `main.py` starts the visible Chromium browser, loads credentials, configures
  logging, and runs the scheduler.
- `login.py` logs in within the browser session and accepts consent prompts.
- `game_actions.py` dispatches the scheduled tasks.
- `task_tactics_school.py` checks the Tactics school countdown and collects the
  card as soon as the enabled “Pick up 1 tactic card” control appears.

1. Install the Python dependencies and Chromium:

   ```sh
   python3 -m venv .venv
   . .venv/bin/activate
   python -m pip install -r requirements.txt
   python -m playwright install chromium
   ```

2. Copy `.env.example` to `.env`, replace the example values with your OFM
   username/email and password, and restrict access to the file:

   ```sh
   cp .env.example .env
   chmod 600 .env
   ```

   `.env` is excluded from Git. Do not commit credentials or share the generated
   `ofm.log`.

3. Run the scheduler:

   ```sh
   . .venv/bin/activate
   ./main.py
   ```

The scheduler logs progress to the terminal and `ofm.log` without recording
credentials. It checks the Tactics school page every 30 seconds, using the
countdown while the card is not ready. If the login screen appears, it logs in
again; after a failed login it waits 10 minutes before retrying. Press Ctrl+C
once in the terminal to stop the scheduler cleanly. Set `LOG_LEVEL=DEBUG` in
`.env` for more diagnostic messages.

Raw button
