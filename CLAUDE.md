# Raid Table

A free, fan-made web app for playing the Pokémon TCG cooperatively against a Raid Boss, using the Raid Format rules from https://raidformat.com/how-to-play/. Players load their own 60-card decks, play on a drag-and-drop playmat, and team up against a boss Pokémon whose turns are run by the app. Works solo, or online with friends through Firebase.

Live site: GitHub Pages, serving `index.html` from the root of the `main` branch. Merging to `main` publishes.

## The project at a glance

- **Everything is in one file: `index.html`** (about 2,900 lines): markup, CSS and JavaScript, no build step, no framework, no npm dependencies. Open it in a browser and it runs. Keep it that way unless the owner asks to split it.
- External resources: Google Fonts (Chakra Petch, Atkinson Hyperlegible, JetBrains Mono), the Firebase compat SDK from gstatic (loaded only when multiplayer starts), and card data and images from pokemontcg.io with TCGdex as a fallback.
- `tests/` has Playwright browser tests (see Testing). Run them before every change you hand back.
- The owner isn't a professional developer. Explain changes in plain language, say how you tested them, and keep the app working on phones.

## Code map (sections of the script in `index.html`)

Search for the `/* ---------- name ---------- */` comment to find each section.

| Section | What's there |
| - | - |
| top of script | `SAMPLE_DECK`, `SAMPLE_DECKS` (sample decks in Import deck), energy names and colors, `TAB` (per-tab saves in test mode), `claimTab()` |
| storage | `STORE_GAME`, `STORE_CARDS` (`raidtable.cards.v6`), `S` (game state), `CARDS` (card data cache), `emptyState()` |
| deck list parsing | `cleanName()`, `parseDeck()` (PTCGL/Limitless format, headings like `Pokémon: 15` / `Trainer Cards - 30`, set codes like `SVI`, `PR-SV`, `30C`), `entryKey()` |
| card lookup | `lookupCard()` (exact print first, then name + number, then name only, flagged `exact: false`), `lookupTcgdex()`, `resolveEntries()` (looks up 4 at a time and caches in `CARDS`) |
| card helpers | `keyOf()`, `D(uid)` (card data for an id), `isPokemon`, `isBasic`, `isItem`, `isSupporter`, `isStadium`, `slotGet/slotSet` |
| rule checks | "Rule help" (`rulesOn`, saved as `raidtable.rules.v1`, on by default): `ruleProblem(src, dst)` says why a move breaks a general game rule (evolution from the right Pokémon, not on turn 1 or the turn it came into play via the slot's `inTurn`, Basics only in empty spots, Energy/Tools need a Pokémon, one Energy from hand per turn via `S.energyTurn`, one Tool per Pokémon, Items/Supporters don't go on Pokémon, Stadium spot and same-name rule, the team's Supporter limit). `move()` stops such a move with `ruleBlock()` (the reason plus "Do it anyway", which reruns it with `{ force: true }`). `markTargets()` adds `can-go` / `no-go` to your Pokémon spots and the Stadium spot for the picked or dragged card. No card-specific effects: those are what "Do it anyway" is for. Rule help also runs the turn: `turnDraw()` (queued after every `render()`) draws your card once per turn using `S.drewTurn`, turn 1 included, on each player's own screen and without a log line, since the log is shared. The Active Pokémon's Attack buttons call `attackWith()`, which checks `attackProblem()` (boss turn, already attacked via `S.attackTurn`, Asleep/Paralyzed, `costMet()` Energy), adds the base damage to your damage box, then ends your turn: Ready in a room, End turn when playing alone with 1 player, otherwise a reminder to press End turn. After attacking, playing more cards from your hand is stopped. With Rule help off you draw and end turns yourself. |
| actions | `SHARED_FIELDS`, `sharedPart/localPart`, **`act()`**, `undo()`, `move()` → `pull()` + `place()`, `discardStadium()`, `draw()`, `setupMyBoard()`, `newGame()`, `endTurn()` |
| hand sorting | `sortHand()` (evolution lines, then Items, Tools, Stadiums, Supporters, then Energy) |
| rendering / inspector | `render()`, `cardEl()`, `renderSlot()`, `renderInspector()` (the card panel's buttons: Play Item/Supporter/Stadium, attach, damage, conditions) |
| zoom / viewer / drag & drop | `openZoom()`, `setMagnified()`, `openViewer()` / `renderViewer()` (discard, Lost Zone, deck search, boss deck top-N), pointer-event drag and drop |
| import | `openImport()`, `loadDeck()` (in a room only your own board changes) |
| Raid boss | `DEFAULT_BOSS_DECK`, `GENTLE_BOSS_DECK`, `BOSS_DECKS`, `DEFAULT_BOSS`, `BOSS_CHOICES`, `DIFF_GUIDE`, `startBossTurn()`, `bossReveal()`, `enterBossAttack()`, `bossAttack()`, `bossEndTurn()`, `millFor()` |
| boss setup / rendering | `openBossSetup()`, `loadBoss()`, `renderBoss()`, `renderStage()` (the boss turn panel), `healRow()`, `updateEndNumbers()` |
| damage this turn | `queueDamage()`, `renderCalcInputs()` + `calcSignature()`, `calc()` |
| multiplayer | `FIREBASE_CONFIG`, transports (`firebaseTransport`, `localTransport`), `commitShared()`, `undoShared()`, `applyRemoteShared()`, `processInbox()`, `publishSeat()`, `uploadCards()`, `rekey()`, `createRoom/joinRoom/leaveRoom/resumeRoom`, `toggleReady()`, `maybeStartBossTurn()` |
| multiplayer UI | `renderHeaderMP()`, `renderTeam()` (teammates' boards, below your hand), room dialog |
| Raid Camp | secret hub: click the "Raid Table" title 5 times. `HUB_NPCS` (characters, Trainer card lines, 3 lines of dialog each), `openHub()`, `talk()` |
| card back | custom card back setting (`raidtable.back.v1`). The built-in back is an original SVG in the CSS `--default-back` token |

## Game state and the golden rule

`S` is one plain object. Some fields are shared by the whole table in a room (`SHARED_FIELDS`: turn, Supporter count, Stadium, damage entries, log, Ready flags, and everything about the boss); the rest is your own board (deck, hand, discard, prizes, Active, Bench, card ids).

**Every change to `S` must go through `act(label, fn, opts)`.** `act` snapshots `S` for Undo, runs `fn`, adds the log line, saves, redraws, and in a room publishes your board and commits any shared change. Rules that follow from that:

- **Never change `S` before calling `act`.** `act` decides whether to sync by comparing shared fields before and after `fn`. If an input handler sets `S.dmg[i]` or `S.bt.healed` first, `act` sees no change and nothing reaches teammates. (This bug happened twice: damage entry, then boss healing.) In a room, typed values go through a short debounce and then `act(null, () => { ...set it... }, { noUndo: true })`; see `queueDamage()` and `healRow()`.
- `fn` must be safe to run again: in a room a move can be replayed on top of a teammate's newer state. Return `false` from `fn` to cancel (for example `if (S.bt) return false;` when the boss turn already started).
- `fn` must only change `S`. Do toasts, focus and other side effects outside it.
- Each card id (`uid`) is unique across the table. In a room, a player's ids are prefixed with their seat (`k3f9:c12`). Boss cards are `b1`…`b60` plus `boss` (`S.bkeys`). A player's card shown in a shared spot (a Stadium) gets an entry in `S.skeys` so teammates can display it.

## Multiplayer (Firebase Realtime Database)

- Data lives at `rooms/<CODE>/` with string-encoded JSON at `shared`, `seats/<seat>`, `cards/<encoded key>`, `presence/<seat>`. Strings avoid Firebase's array and null quirks.
- `commitShared()` commits optimistically: if `shared.rev` still matches, it writes your version. Otherwise it replays your move on the latest shared state, **starting from a fresh copy of your board each attempt** (reusing the same copy made quick draws give extra cards), and **only applies the replayed board if you haven't moved since** (`localSeq`), so a slow retry can't overwrite a newer move.
- `firebaseTransact()`: Firebase first runs a transaction against the browser's local copy, which is empty (`null`) before data has loaded. Returning "abort" then stops it for good, so an empty first look is passed through and Firebase retries with the real value. Joining a room failed until this was fixed.
- Undo in a room restores your board. It restores the shared part only if nobody has moved since, except the Supporter count, which is always taken back.
- The boss's attack is applied by each player to their own Active Pokémon through `S.bt.hit` and `processInbox()`.
- The boss turn starts automatically when every seat is Ready: the first seat in order starts it, once per turn. Anyone can press "Start the boss turn without waiting".
- **Redraws must never rebuild an input someone is typing in.** The damage boxes are rebuilt only when the players change (`calcSignature()`); the boss panel isn't rebuilt while the healing box has focus.
- Testing without Firebase: `?local=1` makes every tab in one browser a separate player (`localTransport`, BroadcastChannel and localStorage; `claimTab()` gives a tab copied from another tab its own identity).
- Firebase setup: Anonymous sign-in enabled; Realtime Database rules allow read/write on `rooms/$room` when `auth != null`; the API key is restricted to the GitHub Pages domain and the Identity Toolkit + Token Service APIs. The web config in `FIREBASE_CONFIG` is public by design. Because of the key restriction, real-Firebase multiplayer only works on the live site, not from `localhost` or a file.

## Raid Format rules as implemented

Source: https://raidformat.com/how-to-play/ and /difficulty/. Decisions confirmed with the owner:

- Players go first and take turns at the same time. Supporters may be played and attacks made on the first turn. **Pokémon may not evolve on the first turn, or on the turn they come into play.**
- The team may play as many Supporters per turn as there are players (shared counter). Playing a Supporter from hand to discard counts; "Discard (not played)" doesn't.
- Lost Zone cards = (total player damage + 10 if the boss is Poisoned + 20 if Burned − healing) ÷ (10 × players), rounded down, applied at the end of the boss's next turn. Negative healing means damage the boss did to itself. Optional harsher rule: ÷ 10 × (players − 1).
- Boss turn: draws one card per player plus one, resolving each as drawn: Energy attaches, Tools attach (replacing), Stadiums go into play; Supporters and Items are resolved by the players, guided by the difficulty. The boss never holds a hand. Its discard is reshuffled whenever its deck runs out.
- The boss attacks every Active Pokémon at once; costs count as any Energy, paid by discarding. Easy/Medium/Hard pick a random affordable attack; Extremely Hard lets the boss player choose.
- The boss loses Special Conditions at the end of its turn. Weakness and Resistance are ignored.
- In Raid Format, **you** take Prize cards when your Pokémon is Knocked Out, and you're out after your last one. Players win when the boss's deck and discard are all in the Lost Zone.

## Content: how to add more

- **Sample deck:** add `{ name, list }` to `SAMPLE_DECKS` (Limitless/PTCGL format, 60 cards).
- **Boss:** add `{ name, line }` to `BOSS_CHOICES`, where `line` is a deck-list line like `Mewtwo ex 30C 151`. The first entry is the default for new raids. Prefer bosses with two attacks and check abilities: Team Rocket's Mewtwo ex was rejected because its Power Saver ability stops a lone boss from attacking.
- **Boss deck:** add `{ name, list }` to `BOSS_DECKS`: Trainers and Energy only, at most 4 of any card except Basic Energy, 60 cards.
- **Raid Camp character:** add `{ who, card, lines }` to `HUB_NPCS`. Dialog is original writing; never copy lines from the games or anime.
- **Before adding any card, confirm its set code, number and text online.** A lookup by set code and number ignores the name, so a wrong number loads a different card. Newer sets may be missing from pokemontcg.io; the app falls back to TCGdex by name + number and logs any card it couldn't match exactly.
- If you change the shape of cached card data, bump `STORE_CARDS` so browsers refetch.

## Testing

```bash
pip install playwright && python -m playwright install chromium   # once
python tests/run_all.py                                            # about a minute
```

The tests play the real `index.html` in headless Chromium with the internet blocked and stand-in card data built from the app's own decks and bosses. See `tests/README.md`. Add a test when you fix a bug, ideally reproducing it first; `tests/test_firebase_like.py` simulates Firebase's retries and delays, which is where most multiplayer bugs only show up. Also look at the page at phone width (about 390px); nothing may scroll sideways.

## Style and legal

- Visual design: a dark teal felt playmat with amber accents (CSS tokens on `:root`), Chakra Petch for display text. Keep new UI consistent and readable on phones.
- On laptops and desktops (wider than 1180px) the whole table fits the window without scrolling: the body is exactly the window's height, the table and side columns scroll inside themselves only if they must, and card width (`--cw0`) follows the window's height as well as its width. The playmat is two rows: Prizes beside the Active and Bench, then the hand across the whole width under both, with Deck, Discard and a one-line Lost Zone down the right. The Prize cards (2 × 3) take their height from the Active and Bench (`contain: size`) and overlap like a stacked pile, and a Pokémon's HP, attachments and conditions sit over its card so spots never grow. The side column (440px) fits as well: the card panel takes what it needs (a large picture sized by window height, with Attack or Play buttons beside it, and short "Switch with" spot buttons), damage is one compact row, and the game log fills what's left, scrolls inside itself, and gives way entirely when a busy card is picked on a short screen. Windows under 700px tall get a tighter side column (no damage hint or working-out). Anything new on the table or in the card panel has to fit that height budget; `tests/test_layout.py` checks it at 1366×657, 1440×789 and 1920×961, including the tallest card panel (your Active with attacks, Energy and a condition).
- Write UI text plainly and from the player's side ("Send 11 to the Lost Zone", not "Commit mill").
- Fan project disclaimer: not affiliated with The Pokémon Company or Nintendo. Don't reproduce official artwork or logos in the app's own code (the official card back was declined; players may choose their own image). Card images come from the card databases at runtime.
- The README credits raidformat.com and discloses that the app was built with Claude.
