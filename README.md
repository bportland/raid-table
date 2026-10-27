# Raid Table tests

Browser tests that play the real app (`index.html`) in headless Chromium. The internet is blocked during tests and stand-in card data is generated from the app's own sample decks, boss decks and bosses, so the tests don't depend on pokemontcg.io or TCGdex being up.

## Setup (once)

```bash
pip install playwright
python -m playwright install chromium
```

## Run

From the repository root:

```bash
python tests/run_all.py
```

It prints PASS or FAIL for each test and takes about a minute.

## What's covered

- `test_solo.py`: a first visit loads a deck and boss; damage math; a full boss turn (draws, attack, healing, damage the boss does to itself); Undo; no sideways scrolling on a phone.
- `test_two_players.py`: two players in one room using same-computer mode (`?local=1`): joining, seeing each other's boards, the shared Supporter counter and Undo, shared damage entry, Ready starting the boss turn, the boss's attack hitting both players once, a Stadium returning to its owner, two players acting at the same moment, rejoining after a reload.
- `test_firebase_like.py`: the same multiplayer code with a stand-in connection that behaves like real Firebase (stale local copies, retries, delays). These cover bugs that only appeared with Firebase: extra cards when drawing quickly while a teammate acts, healing that wasn't shared, and the cursor jumping out of the damage box.

Firebase itself is never contacted. To check the real thing, play a round on two devices on the live site.
