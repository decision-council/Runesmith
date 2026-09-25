# Runesmith Studio: the guide

Runesmith Studio is the app that comes with Runesmith. It is a local web page, served by Runesmith on your own computer, from which you run Runesmith. It is written for everyone: nothing here needs a terminal once it is started.

## Start it

| How | What happens |
|---|---|
| Double-click `Runesmith.cmd` (Windows), `Runesmith.command` (macOS) or run `./runesmith.sh` (Linux) | Opens the folder you used last time, or a fresh *My first project* folder under `~/Runesmith`. |
| Drop a folder onto `Runesmith.cmd` | Opens that folder. |
| `python -m runesmith` inside a folder | Opens that folder. |
| `runesmith up path/to/folder --port 7400 --no-browser` | The same, with options. |

Keep the small window that opens: it is Runesmith working. Close it (or press Ctrl+C) to stop.

**Needs:** Python 3.11 or newer. Nothing else for the Studio. To measure and repair Python code, `pytest` must be installed (`pip install pytest`).

## The first start

Runesmith introduces itself in seven short scenes, about half a minute, and you can skip them:

1. a spark;
2. the forge;
3. **your world**: the folders and files it just found, drawn as a map;
4. **itself**: its fixed kernel and its living organs;
5. **the guard**: tests on throwaway copies, a held-out judge, and you decide;
6. **the evidence**: how a generation it wrote for itself won a sealed test;
7. **any mind**: a model on your computer, a key, a chat window, or none.

Then it asks: **What will you create?** Type a name. A description is optional. Choose what kind of work this is:

- **Build something new:** plans and first files;
- **Improve my code:** finds failing tests and repairs them;
- **Tend my documents:** maps documents and checks links;
- **Just explore:** maps and watches only.

The name and the description become the workspace's name, its first goal and its brief. You can change all of them later.

Replay the sequence any time from **Settings → Behaviour → Introduction**. **Cinema** opens it full screen, looping on demo data, for sharing or recording (`/cinema`; press F for full screen).

## The pages

**Overview.** Where things stand and the one thing to do next:
- a setup checklist;
- what was found;
- what comes next;
- the live log;
- Runesmith's measured capabilities on your work.

**Living map.** One world, four lenses:
- **Environment.** The workspace in the middle and every object around it: Python projects, Node projects, document collections and folders.
  - The border color is the health band. The small segments are the build ladder. A dot shows the last test run.
  - Click an object to see its objectives in bands, its ladder, the facts read from disk, and what is unknown. You can also exclude it, so Runesmith never touches it.
  - Click the center for the whole folder: what it holds, and this computer.
- **Self.** Runesmith's anatomy: the ring of fixed kernel modules around the living organs, the active generation, and the lineage. Click any part.
- **Development.** Tracks of progress:
  - your goals;
  - each plan track with its milestones;
  - every object's ladder, where a glowing ring marks what is next;
  - Runesmith's own generations.
- **Operations.**
  - The work loop (map → find work → repair → judge → propose → you apply), with the live stage highlighted.
  - Which model does which role, with call counts and errors.
  - How much attention goes to self-improvement.
  - The open trial and the schedule.

**Work & proposals.**
- **Fixes:** repairs a held-out judge accepted. Read the diff, then **Apply to my files**, **Reject** (with a reason that becomes a note) or **Undo**.
  - Apply writes only if every file is still exactly as the fix expects, keeps a backup, and preserves your line endings.
- **Drafts:** first files written by the Planner for a milestone, labelled **unverified**. An existing file is never replaced without a second confirmation.
- **Attempts:** every repair attempt with its status, judge verdict, calls and time.
- **Last round:** what the last round found.

**Goals & plan.**
- **Goals:** in your words.
- **Brief:** as long as you like.
- **Blueprint documents:** pick them from the folder, and the Planner reads them.
- **Draft a plan:** milestones on named tracks, first steps, and the questions only you can answer. For each milestone, **Draft first files**.

**Self-improvement.**
- Generations, and the open trial with its counts and looks.
- The **library**. **C7** is the generation that won SR7's sealed test. Adopting it checks and freezes it, then opens a trial against your active generation. It becomes active only if it wins on your work.
- Kaizen campaigns, and capabilities.
- **Make active** is for rolling back, on your own authority. It is recorded as such.

**Thinking power.** Add a model:
- **On this computer:** Ollama, LM Studio and llama.cpp servers that are running are found automatically.
- **With a key:** OpenRouter, Groq, Gemini, Mistral, DeepSeek, OpenAI, Anthropic, Together, or any OpenAI-compatible endpoint. **List models** asks the provider what it serves.
- **A chat window:** no key. When Runesmith needs an answer, the request appears in the **chat relay**: copy it into any chat, paste the reply back.
- **Advanced:** a Milliner router.

Give each model one or more roles: **Worker**, **Improver**, **Planner**. The first model in a role is preferred, and the rest are fallbacks. **Test** makes one tiny call.

**Notes.** Every comment you made, grouped by what it is about.

**Activity.**
- The live log.
- The **ledger**: every event hash-chained to the one before. **Verify the chain** checks all of it.
- The jobs history.

**Settings.**
- **Name.**
- **How Runesmith may act:**
  - *Observe* maps and watches only.
  - *Propose* also works and brings fixes to you.
- **The rhythm:** scheduled rounds and how often.
- **Mapping:** measuring by running tests on throwaway copies, the most objects to map, and folders never to touch.
- **Notes:** whether models read them.
- **Self-improvement:** on or off, and how much experience it needs first.
- **Theme.**
- **Health checks.**
- **The folder:** switch folders, open it in your file manager, or export a snapshot (keys are left out).
- **About & evidence:** what has been shown and what has not.

## Comment on anything

Press **C** (or the speech-bubble button in the top bar) and click anything. You can also hover over a card and click its bubble. Examples:
- an object, an objective or a rung;
- a fix or a draft;
- a goal or a milestone;
- a model, a capability, a kernel module, or Runesmith itself.

Open notes travel to the model that works on that thing, clearly labelled as the owner's guidance:

| A note on… | is read by |
|---|---|
| an object, its objectives or rungs, or the whole workspace | the **Worker**, whenever it repairs that object |
| Runesmith itself, a generation, a capability, a kernel module or an organ | the **Improver**, in Kaizen campaigns |
| the plan, the brief, a goal, a milestone or a draft | the **Planner** |

Resolve a note when it no longer applies. It is kept, marked resolved, and no longer sent. To keep notes to yourself, turn off **Settings → Give notes to the model**.

## Safety

- **Your files are yours.** Runesmith runs your tests on throwaway copies. It writes to your folder only when you click Apply or Write, and every such write is conflict-checked, backed up and undoable.
- **Keys stay here.** Keys are saved in the folder's `.runesmith/secrets.json`, outside your project files. The home ignores itself for version control. Keys are sent only to the provider they belong to, and never shown again.
- **The Studio is private.** It listens on `127.0.0.1` only.
  - It opens through a link with a one-time key, which becomes a browser cookie.
  - It refuses requests that name another host, to stop DNS rebinding.
  - It refuses changes from other sites: they need a header a cross-site form cannot send.
- **Self-improvement is guarded.**
  - Organs run confined.
  - A candidate generation is tested on work its author never saw.
  - It is switched on only by winning a live trial, or by your explicit choice.
  - Rollback is one click.
- **Everything is recorded** in the hash-chained ledger.

## Limits worth knowing

- **One owner.** The ledger records what happened and when, not which person did it. Several people can use one Studio, but for a team audit with names, each person should run Runesmith on their own copy.
- **What is measured.** Python projects are measured by running their tests. Node projects, websites and documents are mapped statically: files, links, ladders. Nothing contacts the network apart from the models you add.
- **Repairs need a `src/` layout.** The shipped repair organ works on Python projects laid out as `src/<package>`. Other layouts are mapped and planned, but not repaired, for now.
- **Links are never followed.** Symbolic links and Windows junctions inside the folder can lead anywhere: into someone's documents, a whole disk, or round in a circle. Runesmith does not follow them:
  - not when mapping;
  - not when it shows code to a model;
  - not in the throwaway copies that tests run in;
  - never to write a fix.

  A linked folder at the top shows on the map as "a link: not followed". Tests that need linked content will not find it in the throwaway copy.
- **Very large folders.** A folder, or any one object in it, is read up to 20,000 files. Past that, counts and checks stop, and the map says so in its unknowns ("20000+ files" in the middle of the map). Version control, virtual environments, `node_modules` and build output are skipped from the start.

## Keyboard

| Key | Does |
|---|---|
| Ctrl K | command palette: every page and action |
| C | comment mode |
| R | run a round now |
| 1 – 9 | go to a page |
| ? | shortcuts |
| Esc | close |

## Troubleshooting

- **The page says it is locked.** Open the Studio from its launcher, or from the link printed in its window. The link carries the key.
- **"Mapping only: add thinking power".** No model is set up yet. Add one under Thinking power, or keep observing.
- **"The Worker model is not reachable".** A local model server is not running. Start Ollama, LM Studio or llama.cpp, or choose another model.
- **A fix will not apply.** The file changed after the fix was made. Runesmith refuses rather than overwrite your work. Run a round again for a fresh fix.
- **Tests are slow or need set-up.** Turn off **Settings → Measure code by running its tests**, and exclude folders Runesmith should leave alone.
- **Updated Runesmith?** The Studio re-qualifies the active organs under the new kernel automatically: the same bytes, re-checked, and recorded in the ledger.
