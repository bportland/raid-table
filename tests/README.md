# Raid Table tests

These tests play the real app (`index.html` at the root of the repository) in a hidden Chromium browser, using [Playwright](https://playwright.dev/python/). They click buttons, type into boxes and read the game state the same way a player's browser would, then check the result.

## Setting up (once)

You need Python 3. Then:

```bash
pip install playwright
python -m playwright install chromium
```

The second command downloads a separate copy of Chromium (about 200 MB) for the tests to drive. It doesn't touch your normal browser.

## Running the tests

From the root of the repository:

```bash
python tests/run_all.py
```

It takes about a minute and a half and prints `PASS` or `FAIL` for each test, then `All tests passed.` or how many failed. When a test fails, the lines under `FAIL` show which check failed.

To run just one file, for example while working on multiplayer:

```bash
python tests/test_two_players.py
```

If you have pytest installed, `pytest tests` works too.

## What each test covers

| File | What it checks |
| - | - |
| `test_solo.py` | Solo play. A first visit loads a sample deck and a boss, the damage box works out the Lost Zone count, a full boss turn runs (draws, the attack, healing), Undo takes the end of the boss turn back, negative healing counts as damage the boss did to itself, and nothing scrolls sideways at phone width (390px). |
| `test_two_players.py` | Two players in one room. Joining, seeing each other's Active Pokémon, the shared Supporter counter and Undo, shared damage, Ready starting the boss turn, the attack hitting both players once each, the Lost Zone count, two players changing the table at once, a replaced Stadium going back to its owner, and reloading the page to rejoin with the same board. |
| `test_four_players.py` | Four players in one room. Joining, the four-Supporter limit, shared damage, the boss turn waiting for all four to be Ready, five boss draws, the attack hitting all four Active Pokémon once each, and the Lost Zone count divided by 40. Runs twice: with the normal connection and with Firebase-like timing. |
| `test_card_rules.py` | Rule help. Evolutions only on the Pokémon they evolve from, not on the first turn or the turn it came into play; Basics only in empty spots; Energy and Tools need a Pokémon; one Energy from your hand per turn; one Tool per Pokémon; Items and Supporters don't go on Pokémon; the Stadium spot and same-name rule; the Supporter limit. Also the "Do it anyway" override, the glowing and dimmed spots, the card panel only offering legal moves, the popup at phone width, and turning Rule help off. Also the turn's automatic draw (turn 1 too, once per turn even after Undo), the Attack buttons (Energy cost, adding the damage, ending your turn alone, with teammates at one screen, and in a room by marking you Ready), and no more plays after attacking. The stand-in cards are all Basic with no attacks, so this test turns a few into an evolution, a Tool, a Stadium and an attacker first. |
| `test_firebase_like.py` | Multiplayer bugs that only showed up with real Firebase timing: quick draws while a teammate acts must give exactly one card each, healing the boss did to itself must be shared, and typing damage while a teammate moves must not pull the cursor out of the box. |

## How the tests work

- **No internet.** All network requests are blocked, so results never depend on pokemontcg.io, TCGdex or Firebase being up.
- **Stand-in cards.** Before each test, `helpers.py` reads every card in the app's own sample decks, boss decks and bosses, and puts simple stand-in data for them into the app's card cache. Every boss gets the same two attacks: one that does no damage and one that does 100.
- **Multiplayer without Firebase.** Real Firebase only works on the live site, so multiplayer tests use the app's same-computer mode (`?local=1`), where each browser tab is a separate player. The pages are served from a small local web server that `serve()` starts and stops.
- **Firebase-like timing.** With `serve(firebase_like=True)`, the same-computer connection is swapped for one that behaves like Firebase: updates arrive a little late, and a move that clashes with a teammate's is retried on the newer state. Most multiplayer bugs only show up this way.

## Helpers in `helpers.py`

| Helper | What it does |
| - | - |
| `serve(firebase_like=False)` | Serves a copy of the app on `127.0.0.1` and gives you its address. |
| `offline_context(browser)` | A browser with the internet blocked and the stand-in cards loaded. |
| `two_players(ctx, url)` | Opens two tabs: Ash creates a room and Misty joins it. |
| `room_of(ctx, url, names)` | Same idea for any number of players: the first name creates the room and the rest join. |
| `step_boss_draws(page)` | Presses the boss panel's button until the boss has finished drawing. |
| `give_boss_energy(page)` | Gives the boss enough Energy to attack and picks its 100-damage attack. |
| `watch_errors(page, label, errors)` | Collects any JavaScript errors on the page, so a test can fail on them. |

## Adding a test

- Make a file named `test_something.py` in this folder with functions named `test_...`. `run_all.py` finds them on its own.
- When you fix a bug, add a test that fails without the fix and passes with it.
- Multiplayer changes should also be tested with `serve(firebase_like=True)`.
- **Wait for the result instead of a fixed time.** In multiplayer, syncing can take longer on a busy computer. Use `page.wait_for_function("...", timeout=5000)` to wait until the thing you're checking is true, rather than `wait_for_timeout(600)` followed by an `assert`. Fixed waits make tests fail now and then for no real reason.
- End each test with `assert not errors, errors` so a JavaScript error anywhere fails it.
