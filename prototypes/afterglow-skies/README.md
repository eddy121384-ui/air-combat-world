# Afterglow Skies — iPhone Safari research playtest

Independent from Ace to Ace and Unreal. The game and shaders originate from the user-provided `AfterglowSkies_AceStrike.html` by Opus 5.5. Mobile controls/ECO/HD, startup error handling and reduced geometry were adapted during this conversation.

Open `/prototypes/afterglow-skies/index.html` via a web server (not `file://`).
The original Opus-bundled Three.js r180 module is included as `vendor/three.module.js`; the smaller Ace to Ace vendor omits required game classes and must not be substituted.

Controls: landscape, left Pitch/Roll stick (latched, CTR resets), MSL, GUN, FLR, AB, BRK, TARGET, PAUSE and ECO/HD.

**Status:** Research prototype. JavaScript syntax checked; mobile WebGL/Safari and FPS not yet confirmed. Previous Netlify copy stalled at LOADING SKY; use the in-app startup error report on this version to investigate. No changes to gameplay physics or original art shaders.

Mobile smoke checklist: load to title; TAKE OFF; turn both axes; fire GUN/MSL; toggle AB; hold BRK; switch target; pause/resume; switch ECO/HD; return to title if defeated. Test on iPhone 13 mini Safari in landscape and review console; try `?safe=1` if WebGL crashes.