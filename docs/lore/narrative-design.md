# Skyfront: Homeland — Narrative Design Principles v0.1

Status: Working direction / review required
Updated: 2026-10-12 (Asia/Taipei)

## 1. Narrative North Star — CONFIRMED

**The player does not need to remember who their silent avatar was. They should remember a few people they loved hearing on the radio.**

Skyfront is **not** a small Ace Combat campaign with a full-scale geopolitical plot attached. It is an arcade air-combat game with a persistent sense of place, recurring personalities, strong small moments and optional deeper stories.

Gameplay and recognizable geography must carry the first impression; exposition can remain deep in the background.

## 2. Roles that carry emotional continuity — CONFIRMED design aim

### AWACS / controller

A recurring controller can be the consistent relationship between flights that use different protagonists and take place in different regions. Their language, professional habits, emotional restraint and occasional surprises define personality.

**Military grounding:** AWACS means *Airborne Warning and Control System*. A single aircraft need not physically travel between every continent: control may be assigned to different aircraft or regional centers, and any recurring individual requires a coherent deployment/communications rationale.

No specific name, callsign, gender, personality or backstory is approved yet.

### Wingmen

The player must experience their personalities **through help, mistakes, rescue and disagreement during play**, not only biography entries. At least a few are recurring enough to become recognizable. The Taiwan prologue mentor is one potential emotional anchor, but their loss alone does not create an enduring cast.

### Enemy aces

A recurring antagonist should be recognizable by tactics, speech and interactions, not only by a health bar or machine stats. The enemy may be ideologically committed without being a caricature. Whether the player may take that pilot's perspective in optional faction content is OPEN.

## 3. Radio as gameplay storytelling — WORKING mechanics

- **Priority 1: safety and actionable tactical information** (missile cues, incoming threats, mission shifts, target changes).
- **Priority 2: mission stakes and state changes.**
- **Priority 3: character interaction and humor**, ideally triggered in brief breathing spaces.
- Reactions should reference **actual player behavior** (rescue, missed shots, clean kill, low health, excellent evasion, mission outcome) rather than playing an identical script every sortie.
- Give each character a small vocabulary and behavioral identity. Avoid everyone becoming a sarcastic one-liner machine.
- Use simple **offline deterministic event/state scripting** in early versions; no live generative model, remote speech service or persistent server required.
- Interrupt, suppress or queue lines so critical tactical cues are not masked by banter.
- Prove emotional usefulness with a small set of strong lines before investing in large-scale voiceover production.

## 4. Viewpoint and game mode model

### Quick Battle / Free Flight — CONFIRMED product direction, detailed rules OPEN

- Choose map, aircraft and available encounter style; replay without requiring a single canonical campaign itinerary.
- A player may engage in both defensive and offensive scenarios. There is no need to claim every quick battle is a canonical historical event.
- Cross-national aircraft and hypothetical faction pairings may be allowed for arcade freedom.

### Optional War Stories / Campaign DLC — WORKING business and narrative hypothesis

- Use short connected missions to deepen favorite voices, local stakes and exceptional boss fights.
- Could tell different countries' and even different factions' perspectives without forcing the original ROC pilot to travel from Taipei to Tokyo to London to New York.
- Share world geometry, aircraft and combat AI with the free game; pay for authored encounters and strong characterization, **not mere text/cutscenes**.
- **No DLC, prices, storefront, number of free cities or expansion sequence is yet final.**
- The Taiwan First Contact tutorial is a strong **free** onboarding candidate; charging for the continuation is only a concept to test.

## 5. World and mission consistency

- Multiple cities can provide distinct independent sorties; city liberation, defense or attack requires a local objective but not necessarily full occupation of an entire metropolis.
- Allow several perspectives on related global events, but tag which chapters are canon, noncanon or alternative-history before publishing.
- Use short mission context (one sentence if enough) rather than mandatory timeline lectures.
- Real-world geography is the visual/emotional differentiator. Missions should actually exploit coastlines, mountains, dense buildings, islands or naval traffic, not merely reskin the same dogfight.
- A real country is not the default villain. The Commune's global conflict supports shared threats and shifting partnerships.

## 6. Product boundaries and exploratory content plan

**CONFIRMED:** mobile-first arcade combat; short encounters; solo/offline-first; original geography; keep narrative subordinate to repeatable combat.

**WORKING examples:** free Northern Taiwan plus Shanghai **or** Tokyo; some lower-cost coastal/ocean, canyon, snowy mountain or Southwestern Islands / Sakishima-inspired battlefields; optional premium story missions. These are proposals, not approved launch scope.

**OPEN:** exact launch cities and number, aircraft count, in-app purchase model, story campaign length, voice budget, content download sizes and whether opposing factions become fully playable.

## 7. Practical validation

1. Test flight feel and enemy AI in a short northern Taiwan combat scenario.
2. Add a small recognizable AWACS/wingman voice set, with performance-reactive lines.
3. Test whether players recall and anticipate those voices after repeated sorties.
4. Prototype only a few connected story missions before financing full narrative DLC production.
5. If a scene can be removed without changing gameplay, character attachment or memorable payoff, reconsider producing it.

Reference: [Music Direction](../game-design/music-direction.md) describes a complementary **place → institution → person** emotional framework. This narrative work should support, not overwrite, that established musical identity.
