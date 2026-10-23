// Ace Flight Academy — lesson definitions. Each lesson is data + small judge
// functions over REAL sim state (see runner.js). Instructor callsign: KITE (黑鳶).
// Every lesson cites what is real aeronautics, what is this game's simplified
// model, and what is a pure game rule (docs/academy-curriculum.md).
import { holdPhase, gatePhase, placeJet, pointAhead, wrapDeg, KMH } from './runner.js';
import { StraightDrone, TurnDrone, BanditDrone, scriptedLaunch } from './drones.js';
import { PilotAI } from '../ai/pilot.js';
import { sub, len, dot, norm, scale, cross, angleBetween, forwardOf, addScaled, UP, DEG } from '../sim/math.js';
import { gunLead, gunError, missilePk } from '../sim/fire.js';
import { FLARE, GUN } from '../sim/weapons.js';

const fmt = (n) => Math.round(n).toLocaleString('en-US');
const hdg3 = (h) => String(Math.round((h + 360) % 360)).padStart(3, '0');
/** Standard opening: the player alone over the sea, opponent parked (dormant). */
function soloSetup(r, { alt = 3000, kmh = 750, heading = 0, throttle = 0.72 } = {}) {
  r.match.timeLimit = 1e9;
  placeJet(r.me, { pos: { x: 0, y: alt, z: 0 }, speed: kmh / KMH, heading, throttle });
  r.foe.dormant = true;
  placeJet(r.foe, { pos: { x: 0, y: 9000, z: 11500 }, speed: 200 });
}
const turnWord = (err) => (err > 0 ? '右轉' : '左轉');

// =====================================================================
// 01 — 天空與地平線：姿態、速度、高度、W 與 FPM
// =====================================================================
const L01 = {
  id: 'L01', no: 1, title: '天空與地平線', en: 'SKY & HORIZON',
  principle: 'W 是機頭指向，FPM 是你真正前進的方向。平飛＝FPM 貼著地平線。',
  real: '真實航空：機頭姿態（pitch）與航跡角（flight path）之間差一個攻角；儀表飛行以姿態＋性能交叉檢查（FAA 飛行手冊）。',
  model: '本遊戲：W／FPM 的分離來自簡化的航跡跟隨延遲，不是完整攻角模型。',
  hook: '清晨的外海，能見度無限。今天的科目只有一個：學會看天空。',
  goals: ['平飛 5 秒：FPM 對準 0° 線、機翼水平', '爬升 600 m 後改平並穩住', '下降到指定高度並穩住'],
  sHint: 'S：70 秒內完成，爬升與下降的改平合計衝過頭 < 100 m',
  timeLimit: 150,
  timeoutHint: '先讓 FPM 停住，再決定要往哪裡修。',
  setup: (r) => soloSetup(r),
  intro: [
    '這裡是 KITE，你的教官。今天不打仗。',
    '先學會看：W 是機頭。帶翅膀的小圓是 FPM——你真正飛去的地方。',
  ],
  phases: [
    holdPhase({
      id: 'level', need: 5,
      say: (r) => r.pick('放開搖桿，飛控會替你把機翼改平。讓 FPM 貼著 0° 線。',
        '輕推左右把機翼修平，平了就鬆手——搖桿會回中，坡度留在原地，不會自己改平。讓 FPM 貼著 0° 線。'),
      coach(r) {
        if (Math.abs(r.bank) > 15 && r.phaseT > 4) r.cue('bank', r.pick('機翼斜著。放開搖桿，讓飛控改平。', '機翼還斜著。往反方向輕推，平了就放手。'));
        else if (Math.abs(r.gamma) > 4 && r.phaseT > 4) r.cue('fpm', 'FPM 在跑。小修一下，等它停住再判斷。', { cooldown: 12 });
        if ((r.d.held || 0) > 2.5) r.cue('good', '對，就這樣。手放輕。');
      },
      praise: '穩。平飛——世界上最被低估的機動。',
      text: (r) => `平飛：FPM 貼 0° 線、機翼水平　γ ${r.gamma.toFixed(1)}°　坡度 ${Math.round(r.bank)}°`,
      cond: (r) => Math.abs(r.gamma) < 2.5 && Math.abs(r.bank) < 10,
      why: (r, dt) => { if (Math.abs(r.bank) >= 10) r.d.bankOut = (r.d.bankOut || 0) + dt; else r.d.gammaOut = (r.d.gammaOut || 0) + dt; },
      timeout: (r) => ((r.d.bankOut || 0) > (r.d.gammaOut || 0)
        ? `時間到。大部分時間機翼不平：有坡度，升力就不全往上，FPM 會慢慢往下掉。${r.pick('', '先用左右把坡度修回 0°。')}`
        : '時間到。FPM 一直離開 0° 線——小幅修正，然後等 FPM 停下來再判斷。'),
    }),
    {
      id: 'climb',
      enter: (r) => { r.d.target = Math.round((r.alt + 600) / 100) * 100; r.note('climbTarget', r.d.target); },
      say: (r) => `爬升到 ${fmt(r.d.target)} m。快到的時候，讓 FPM 回到 0° 線把它停住。`,
      coach(r) { if (r.d.target - r.alt < 250 && r.d.target - r.alt > 0 && r.gamma > 7) r.cue('flare', '快到了——現在開始放平。'); },
      praise: (r) => ((r.notes.climbOvershoot || 0) < 60 ? '準。高度表都要替你鼓掌。' : `到了，多衝了 ${fmt(r.notes.climbOvershoot)} m。下次早一點放平。`),
      text: (r) => `爬升到 ${fmt(r.d.target)} m（±120）並改平　目前 ${fmt(r.alt)} m　γ ${r.gamma.toFixed(1)}°`,
      progress: (r) => (r.d.held || 0) / 4,
      update(r, dt) {
        const err = r.alt - r.d.target;
        r.d.over = Math.max(r.d.over || 0, err);
        if (Math.abs(err) < 120 && Math.abs(r.gamma) < 3) r.d.held = (r.d.held || 0) + dt;
        if (r.d.over > 250 && !r.d.warned) { r.d.warned = true; r.say(`衝過頭 ${Math.round(r.d.over)} m 了。FPM 放回地平線，再慢慢修回來。`); }
        if ((r.d.held || 0) >= 4) { r.note('climbOvershoot', Math.max(0, r.d.over - 120)); return 'done'; }
        return undefined;
      },
    },
    {
      id: 'descend',
      enter: (r) => { r.d.target = r.notes.climbTarget - 900; },
      say: (r) => `現在下降到 ${fmt(r.d.target)} m。機頭往下，速度會自己長上來——看好速度框。`,
      coach(r) { if (r.kmh > 850) r.cue('speed', '看到速度了嗎？那是你剛剛花掉的高度。'); },
      text: (r) => `下降到 ${fmt(r.d.target)} m（±120）並改平　目前 ${fmt(r.alt)} m　${fmt(r.kmh)} km/h`,
      progress: (r) => (r.d.held || 0) / 4,
      update(r, dt) {
        const err = r.alt - r.d.target;
        r.d.under = Math.max(r.d.under || 0, -err);
        r.d.vmax = Math.max(r.d.vmax || 0, r.kmh);
        if (Math.abs(err) < 120 && Math.abs(r.gamma) < 3) r.d.held = (r.d.held || 0) + dt;
        if ((r.d.held || 0) >= 4) { r.note('descendOvershoot', Math.max(0, r.d.under - 120)); r.note('descendVmax', r.d.vmax); return 'done'; }
        return undefined;
      },
    },
  ],
  grade(r) {
    const over = (r.notes.climbOvershoot || 0) + (r.notes.descendOvershoot || 0);
    return r.t < 70 && over < 100 ? 'S' : r.t < 100 && over < 250 ? 'A' : 'B';
  },
  debrief(r, success) {
    const good = [], improve = [];
    const co = r.notes.climbOvershoot, dov = r.notes.descendOvershoot;
    if (co != null) (co < 60 ? good : improve).push(co < 60 ? '爬升改平很準，沒有衝過目標。' : `爬升衝過目標 ${Math.round(co)} m：在目標前約 γ×20 m 開始放平 FPM。`);
    if (dov != null) (dov < 60 ? good : improve).push(dov < 60 ? '下降改平俐落。' : `下降多掉了 ${Math.round(dov)} m：俯衝時速度上升，改平要更早。`);
    if (r.notes.descendVmax) good.push(`下降時速度從 750 漲到 ${fmt(r.notes.descendVmax)} km/h——高度換成了速度，第五課會用到。`);
    if (!success && !improve.length) improve.push('先讓 FPM 停住，再修。');
    return {
      good, improve,
      stats: [['用時', `${Math.round(r.t)} 秒`], ['最低／最高', `${fmt(r.tel.minAlt)}／${fmt(r.tel.maxAlt)} m`]],
      closing: '看得懂天空了。下一課，讓它轉起來。',
    };
  },
};

// =====================================================================
// 02 — 飛機如何轉彎：滾轉、俯仰、升力方向
// =====================================================================
function headingPhase({ id, target, need = 2.5, tol = 8, say, limit, precise = false }) {
  return {
    id, say,
    coach(r) {
      if (precise) return; // the challenge: no hints
      const err = wrapDeg(target - r.heading), banked = Math.abs(r.bank) > 40, dt = 1 / 60;
      r.d.np = banked && r.g < 1.4 ? (r.d.np || 0) + dt : 0;   // rolled, not pulling (sustained, not the roll-in moment)
      r.d.nr = Math.abs(r.bank) < 15 && r.g > 3 ? (r.d.nr || 0) + dt : 0; // pulling with wings level
      if (r.control === 'expert' && r.d.np > 1.5) r.cue('nopull', '坡度有了，但你沒拉。機頭在往下掉喔。', { cooldown: 10 });
      if (r.d.nr > 1.5) r.cue('noroll', '機翼是平的，拉桿只會爬升。先滾轉。', { cooldown: 10 });
      if (Math.abs(err) < 25 && Math.abs(err) > tol && Math.abs(r.bank) > 30) r.cue('rollout', r.pick('快到了——放開搖桿，讓它改平。', '快到了——反方向滾轉改平。'));
    },
    praise: (r) => { const o = r.notes[`${id}Over`] || 0; return precise ? (o < 4 ? '一刀切進去。漂亮。' : '進了。') : o < 6 ? '準時改平，漂亮。' : `到了，衝過 ${o}°。下次再早一點改平。`; },
    enter: (r) => { r.d.alt0 = r.alt; r.d.start = r.heading; },
    text: (r) => {
      const err = wrapDeg(target - r.heading);
      return `目標航向 ${hdg3(target)}°　目前 ${hdg3(r.heading)}°　${Math.abs(err) < tol ? '改平穩住' : `${turnWord(err)} ${Math.round(Math.abs(err))}°`}`;
    },
    progress: (r) => (r.d.held || 0) / need,
    update(r, dt) {
      const err = wrapDeg(target - r.heading);
      r.d.prevSign ??= Math.sign(err);
      if (Math.sign(err) !== r.d.prevSign && Math.abs(err) < 90) r.d.passed = true;
      if (r.d.passed && Math.abs(err) > (r.d.over || 0)) r.d.over = Math.abs(err);
      r.d.altDev = Math.max(r.d.altDev || 0, Math.abs(r.alt - r.d.alt0));
      if (r.alt < r.d.alt0 - 800) {
        return { fail: r.tel.rollNoPullSec > 1.5
          ? `掉了 ${Math.round(r.d.alt0 - r.alt)} m：大坡度卻沒拉桿，升力撐不住，機頭掉進螺旋俯衝。滾轉之後要拉。`
          : `掉了 ${Math.round(r.d.alt0 - r.alt)} m：坡度越大，越要多拉桿撐住高度（n = 1/cos 坡度）。` };
      }
      if (Math.abs(err) < tol && Math.abs(r.bank) < 12) r.d.held = (r.d.held || 0) + dt; else if (precise) r.d.held = 0;
      if (limit && r.phaseT > limit) {
        const slow = r.tel.rollNoPullSec > 1.5 && r.control === 'expert';
        return { fail: slow
          ? `超過 ${limit} 秒。你有滾轉卻沒拉桿——升力方向斜了，但沒有足夠的升力把航跡拉過去。`
          : (r.d.over || 0) > tol ? `超過 ${limit} 秒。你衝過目標 ${Math.round(r.d.over)}° 又修回來：改平要提早。`
            : `超過 ${limit} 秒。坡度要夠大、拉桿要果斷，轉完立刻改平。` };
      }
      if ((r.d.held || 0) >= need) {
        r.note(`${id}Over`, r.d.passed ? Math.round(r.d.over || 0) : 0);
        r.note(`${id}Alt`, Math.round(r.d.altDev));
        r.note(`${id}T`, r.phaseT);
        return 'done';
      }
      return undefined;
    },
  };
}
const L02 = {
  id: 'L02', no: 2, title: '飛機如何轉彎', en: 'BANK TO TURN',
  principle: '升力垂直於機翼。滾轉把升力斜過去，拉桿才把航跡拉彎；水平轉彎需要 n = 1/cos(坡度) 的負載因子。',
  real: '真實航空：坡度轉彎靠升力水平分量；坡度越大，維持高度所需負載因子越高（60° 坡度約 2G）——FAA 飛行手冊。',
  model: '本遊戲：同樣的升力向量轉彎，Assisted 由飛控代你協調滾轉與拉桿，但用的是同一架飛機、同樣的 G 上限。',
  hook: '同一片海，多了三個航向。轉過去不難——難的是停在對的地方。',
  goals: ['右轉到 090° 並改平', '左轉 150° 到 300°', '精準轉到 015°（±4°），14 秒內，高度變化 < 200 m'],
  sHint: 'S：最多衝過目標 6°、高度偏差 < 150 m、75 秒內',
  timeLimit: 150,
  setup: (r) => soloSetup(r),
  intro: [
    (r) => r.pick('今天學轉彎。Assisted 會替你滾轉，再替你拉桿。', '今天學轉彎。Expert 沒有人幫你。'),
    (r) => r.pick('推住搖桿就一直轉；放開，飛控替你改平。看懂它在做什麼。', '左右只會滾轉。滾到位就鬆手——坡度留著——再往後拉，飛機才會轉。'),
  ],
  phases: [
    headingPhase({ id: 'h090', target: 90, limit: 40,
      say: (r) => r.pick('右轉到 090°。看機翼怎麼斜下去——那是飛控在傾斜升力。', '右滾 60° 左右、鬆手、往後拉。到 090° 前提早改平。') }),
    headingPhase({ id: 'h300', target: 300, limit: 45,
      say: (r) => r.pick('左轉到 300°，一口氣 150°。搖桿推越多，轉得越急。', '左轉到 300°。坡度大一點、拉多一點——看 G 值上去。') }),
    headingPhase({ id: 'h015', target: 15, tol: 4, need: 3, limit: 14, precise: true,
      say: '最後一題：14 秒內轉到 015°，誤差 4° 以內。這次我不提醒了。' }),
  ],
  grade(r) {
    const over = Math.max(r.notes.h090Over || 0, r.notes.h300Over || 0, r.notes.h015Over || 0);
    const alt = Math.max(r.notes.h090Alt || 0, r.notes.h300Alt || 0, r.notes.h015Alt || 0);
    return over < 6 && alt < 150 && r.t < 75 ? 'S' : over < 12 && alt < 300 ? 'A' : 'B';
  },
  debrief(r, success) {
    const good = [], improve = [];
    const over = Math.max(r.notes.h090Over || 0, r.notes.h300Over || 0);
    if (r.notes.h090Over != null) (over < 8 ? good : improve).push(over < 8 ? '改平時機準確，幾乎沒有衝過目標航向。' : `最多衝過目標 ${over}°：坡度 60° 時，大約提前 20° 開始改平。`);
    const alt = Math.max(r.notes.h090Alt || 0, r.notes.h300Alt || 0, r.notes.h015Alt || 0);
    if (r.notes.h090Alt != null) (alt < 200 ? good : improve).push(alt < 200 ? `轉彎中高度只偏了 ${alt} m。` : `轉彎中高度偏了 ${alt} m：坡度越大，越要多拉一點桿來撐住高度。`);
    if (r.control === 'expert' && r.tel.rollNoPullSec > 2) improve.push(`有 ${r.tel.rollNoPullSec.toFixed(1)} 秒在大坡度卻沒拉桿：只滾轉不會轉彎。`);
    if (r.tel.pullNoRollSec > 2) improve.push(`有 ${r.tel.pullNoRollSec.toFixed(1)} 秒機翼水平卻猛拉：那只會爬升，不會轉向。`);
    return { good, improve,
      stats: [['最大 G', `${r.tel.maxG.toFixed(1)} G`], ['精準轉彎', r.notes.h015T ? `${r.notes.h015T.toFixed(1)} 秒` : '—']],
      closing: '升力往哪，飛機就往哪。記住這句話。' };
  },
};

// =====================================================================
// 03 — 動力控制：油門、後燃器、減速板
// =====================================================================
const L03 = {
  id: 'L03', no: 3, title: '動力控制', en: 'THROTTLE, AB & BRAKE',
  principle: '推力大於阻力就加速，小於就減速。AB 增加推力；減速板只增加阻力，不改變推力。',
  real: '真實航空：加速度取決於推力與阻力之差（FAA 飛行手冊的四力平衡）；後燃器以大量燃油換推力。',
  model: '本遊戲：推力、阻力與 AB 由簡化模型計算；不模擬燃油。油門、AB、BRK 三者獨立。',
  hook: '今天的科目叫「錢包管理」：推力、後燃器、減速板。',
  goals: ['水平加速到 1000 km/h（高度 ±250 m）', '在時限內減到 650 km/h 以下', '把速度穩在 600–700 km/h 6 秒'],
  sHint: 'S：45 秒內完成三段',
  timeLimit: 120,
  tune: { arcade: { accelLimit: 24, decelLimit: 13 }, tactical: { accelLimit: 30, decelLimit: 14 } },
  setup: (r) => { soloSetup(r, { kmh: 600, throttle: 0.6 }); r.note('alt0', 3000); },
  intro: ['動力是你的錢包。今天學怎麼花、怎麼省。'],
  phases: [
    {
      id: 'accel',
      say: '油門推到底、點亮 AB，平飛加速到 1000。不准俯衝作弊——我看得到高度表。',
      coach(r) {
        if (r.phaseT > 4 && r.tel.abSec < 0.5) r.cue('ab', 'AB 還沒點。軍用推力只是暖身。');
        if (Math.abs(r.alt - r.notes.alt0) > 150) r.cue('alt', '高度在跑。這課只准用推力。');
      },
      praise: (r) => `${r.notes.accelT.toFixed(1)} 秒破千。後燃器不是萬能鍵——但這次它是。`,
      text: (r) => `平飛加速到 1000 km/h　目前 ${fmt(r.kmh)}　高度 ${fmt(r.alt)}（±250）`,
      progress: (r) => (r.kmh - 600) / 400,
      update(r) {
        if (Math.abs(r.alt - r.notes.alt0) > 250) return { fail: `高度偏離 ${Math.round(r.alt - r.notes.alt0)} m。這一課只用推力加速——拿高度換速度是第五課。` };
        if (r.kmh >= 1000) { r.note('accelT', r.phaseT); return 'done'; }
        if (r.phaseT > r.tune.accelLimit) {
          const ab = r.tel.abSec < 1;
          return { fail: ab ? `${r.tune.accelLimit} 秒只到 ${fmt(r.kmh)} km/h：沒開 AB（點一下 AB 或按住 W）。軍用推力加不上去。`
            : `${r.tune.accelLimit} 秒只到 ${fmt(r.kmh)} km/h：油門推到底了嗎？目前 ${Math.round(r.me.controls.throttle * 100)}%。` };
        }
        return undefined;
      },
    },
    {
      id: 'decel',
      say: '現在減到 650 以下：收油、關 AB、按住 BRK。',
      coach(r) {
        if (r.phaseT > 1.5 && r.me.controls.boost) r.cue('ab', '先關 AB。你在同時踩油門和剎車。');
        else if (r.phaseT > 3 && r.tel.brakeSec - r.d.brake0 < 0.2) r.cue('brk', '只收油太慢了。按住 BRK。');
      },
      praise: (r) => (r.notes.decelBrake > 0.5 ? `${r.notes.decelT.toFixed(1)} 秒。BRK 只加阻力，不碰推力——你用對了。` : '減下來了。BRK 可以讓它快一倍。'),
      text: (r) => `減速到 650 km/h 以下　目前 ${fmt(r.kmh)}　油門 ${Math.round(r.me.controls.throttle * 100)}%${r.me.controls.boost ? '　AB 開著！' : ''}`,
      progress: (r) => (1000 - r.kmh) / 350,
      enter: (r) => { r.d.brake0 = r.tel.brakeSec; },
      update(r) {
        if (r.kmh <= 650) { r.note('decelT', r.phaseT); r.note('decelBrake', r.tel.brakeSec - r.d.brake0); return 'done'; }
        if (r.phaseT > r.tune.decelLimit) {
          const brake = r.tel.brakeSec - r.d.brake0;
          return { fail: r.me.controls.boost ? 'AB 還開著——減速第一步是關掉後燃器。'
            : brake < 1 ? `${r.tune.decelLimit} 秒只減到 ${fmt(r.kmh)} km/h：只收油太慢，按住 BRK 增加阻力。`
              : r.me.controls.throttle > 0.3 ? `油門還在 ${Math.round(r.me.controls.throttle * 100)}%：推力還在推你，收油到底。`
                : `${r.tune.decelLimit} 秒只減到 ${fmt(r.kmh)} km/h：BRK 要按住不放，直到速度下來。` };
        }
        return undefined;
      },
    },
    holdPhase({
      id: 'hold', need: 6,
      say: '穩在 600 到 700。油門放哪，速度最後就停在哪。',
      coach(r) {
        if (r.kmh > 720) r.cue('fast', '太快。油門收一點，別一直用 BRK 硬壓。', { cooldown: 8 });
        else if (r.kmh < 580) r.cue('slow', '太慢。加一點油門，等它自己穩。', { cooldown: 8 });
      },
      text: (r) => `速度穩在 600–700 km/h　目前 ${fmt(r.kmh)}　油門 ${Math.round(r.me.controls.throttle * 100)}%`,
      cond: (r) => r.kmh >= 600 && r.kmh <= 700 && Math.abs(r.alt - r.notes.alt0) < 400,
      why: (r) => { if (r.kmh > 700) r.d.fast = true; else r.d.slow = true; },
    }),
  ],
  grade(r) {
    return r.t < 45 ? 'S' : r.t < 65 ? 'A' : 'B';
  },
  debrief(r) {
    const good = [], improve = [];
    if (r.notes.accelT) good.push(`AB 加速 600→1000 km/h 用了 ${r.notes.accelT.toFixed(1)} 秒。`);
    if (r.notes.decelT) (r.notes.decelBrake > 0.5 ? good : improve).push(r.notes.decelBrake > 0.5
      ? `收油＋BRK，${r.notes.decelT.toFixed(1)} 秒減掉 350 km/h。` : `減速花了 ${r.notes.decelT.toFixed(1)} 秒：BRK 能讓它快一倍。`);
    improve.push(r.tactical ? 'Tactical：AB 是你重建能量的唯一快捷方式，但它不能讓急轉免費。' : 'Arcade：AB 快而寬，收油／BRK 慢而急——第四課會看到差別。');
    return { good, improve,
      stats: [['最高速', `${fmt(r.tel.maxSpeed * KMH)} km/h`], ['AB 使用', `${r.tel.abSec.toFixed(0)} 秒`], ['BRK 使用', `${r.tel.brakeSec.toFixed(1)} 秒`]],
      closing: '油門、AB、BRK——三個開關，三種錢。下一課看 G 力要你付多少。' };
  },
};


// =====================================================================
// 04 — G 力的代價：瞬間／持續轉率、轉彎半徑、最佳轉彎速度
// =====================================================================
/** Turn a given number of degrees; records rate, radius, speed and G. */
function turnPhase({ id, deg, say, text, limit, check, armKmh, armedRules, ...extra }) {
  const begin = (r) => { r.d.h = r.heading; r.d.turned = 0; r.d.v0 = r.kmh; r.d.alt0 = r.alt; r.d.gSum = 0; r.d.vSum = 0; r.d.n = 0; r.d.t0 = r.phaseT; };
  return {
    ...extra, // coach / praise / name / checkpoint
    id, say,
    enter: (r) => { r.d.armed = !armKmh; begin(r); },
    text: (r) => (!r.d.armed ? (r.radioBusy ? '聽完教官的指示…' : `速度帶到 ${armKmh}–${armKmh + 60} km/h 開始計時（AB 可用）　目前 ${fmt(r.kmh)}`)
      : text ? text(r) : `滿桿轉 ${deg}°　已轉 ${Math.round(r.d.turned)}°　${fmt(r.kmh)} km/h　${r.g.toFixed(1)}G`),
    progress: (r) => r.d.turned / deg,
    update(r) {
      if (!r.d.armed) {
        // the clock starts only after the instructions, inside a fixed entry-speed window
        if (r.kmh < armKmh || r.kmh > armKmh + 60 || r.radioBusy) {
          if (r.phaseT > 40) return { fail: `40 秒還沒把速度帶到 ${armKmh}–${armKmh + 60} km/h：太慢就開 AB，太快就收油、BRK，先別轉彎。` };
          return undefined;
        }
        r.d.armed = true; begin(r);
        if (armedRules) Object.assign(r.rules, armedRules);
        r.say('計時開始！');
      }
      const elapsed = r.phaseT - r.d.t0;
      const h = r.heading;
      r.d.turned += Math.abs(wrapDeg(h - r.d.h)); r.d.h = h;
      r.d.gSum += r.g; r.d.vSum += r.me.speed; r.d.n += 1;
      if (r.alt < r.d.alt0 - 900) return { fail: `轉彎時掉了 ${Math.round(r.d.alt0 - r.alt)} m：這一課要水平轉彎，機頭別往下栽。` };
      if (limit && elapsed > limit) return { fail: `${limit} 秒只轉了 ${Math.round(r.d.turned)}°：坡度要夠、拉桿要滿。` };
      if (r.d.turned >= deg) {
        const res = { t: elapsed, dps: deg / elapsed, v0: r.d.v0, v1: r.kmh, g: r.d.gSum / r.d.n,
          radius: (r.d.vSum / r.d.n) / ((deg / elapsed) * Math.PI / 180) };
        r.note(id, res);
        const c = check?.(r, res);
        return c || 'done';
      }
      return undefined;
    },
  };
}
const L04 = {
  id: 'L04', no: 4, title: 'G 力的代價', en: 'TURN RATE & G',
  principle: '轉率 ω = g·√(n²−1)/V，半徑 r = V²/(g·√(n²−1))。太快時 G 到頂、轉得寬；最佳轉彎速度（corner）轉得最急；滿 G 會燒掉速度。',
  real: '真實航空：轉率與半徑由速度和負載因子決定；結構 G 上限與低速升力上限交會處是最佳轉彎速度（E-M 理論，Boyd）。',
  model: '本遊戲：可用 G 隨速度變化、誘導阻力隨 G² 增加，皆為簡化模型；HUD 綠色菱形＝目前速度能給出 ≥92% 最佳瞬間轉率。',
  hook: '空戰裡最常見的錯誤，是用錯的速度轉彎。今天你親手量出對的速度。',
  goals: ['高速（約 1050 km/h）滿桿轉 180°，記住轉率', '減速到綠色菱形出現', '在最佳轉彎速度再轉 180°，轉率至少快 15%', '從 750 km/h 起只用 MIL（AB 停用）轉 360°：準時轉完，又要守住結束速度'],
  sHint: (t) => `S：MIL 360° 比時限（${t.sustainT} 秒）快 2 秒以上，且結束速度 > ${t.sustainV + 60} km/h`,
  timeLimit: 170,
  tune: {
    // Calibrated with a level, altitude-held turn from 750 km/h under MIL:
    // full stick ends at ~450 km/h (fails speed); a pilot who spends speed to a
    // floor and then holds it finishes inside the time with margin.
    arcade: { sustainT: 17, sustainV: 580 },
    tactical: { sustainT: 26, sustainV: 560 },
  },
  setup: (r) => soloSetup(r, { kmh: 1050 }),
  intro: ['G 力不是免費的。今天你會親眼看到帳單。'],
  phases: [
    turnPhase({ id: 'fast', deg: 180, limit: 30,
      say: (r) => r.pick('油門推滿、開 AB。搖桿推到底轉 180°。記住轉率和速度。', '油門推滿、開 AB。滾 80° 以上、拉滿，轉 180°。記住數字。'),
      coach(r) { if (r.d.turned > 60 && r.g > r.availG * 0.9) r.cue('cap', `${r.g.toFixed(1)}G，已經到頂了。看轉率：沒有你想的快。`); },
      praise: (r) => {
        const f = r.notes.fast, dv = f.v0 - f.v1;
        return `記下來：${f.dps.toFixed(1)}°/s，半徑 ${fmt(f.radius)} m。${dv > 0 ? `速度掉了 ${fmt(dv)}。` : `AB 全開還多了 ${fmt(-dv)} km/h——太快，G 根本用不完。`}`;
      } }),
    holdPhase({ id: 'band', need: 2,
      say: (r) => { const [lo, hi] = r.bestBandKmh; return `看到了嗎？太快，G 到頂了也轉不快。收油、BRK，降到 ${lo}–${hi} km/h，等綠色菱形亮。`; },
      text: (r) => { const [lo, hi] = r.bestBandKmh; return `減速到最佳轉彎速度 ${lo}–${hi} km/h　目前 ${fmt(r.kmh)}　${r.inBestBand ? '◆ 保持' : ''}`; },
      cond: (r) => r.inBestBand,
      coach(r) { if (r.inBestBand) r.cue('band', '菱形亮了。就是這個速度——記住它。'); },
      timeout: (r) => (r.kmh > r.bestBandKmh[1] ? '還是太快。收油到底、按住 BRK，速度才會掉進菱形區。' : '太慢了。推油門、開 AB，把速度帶回菱形區。') }),
    turnPhase({ id: 'corner', deg: 180, limit: 25,
      say: '現在滿桿，再轉 180°。比比看。',
      praise: (r) => {
        const f = r.notes.fast, c = r.notes.corner;
        return `${c.dps.toFixed(1)}°/s——比剛才快 ${Math.round((c.dps / f.dps - 1) * 100)}%，圈只有 ${Math.round((100 * c.radius) / f.radius)}% 大。慢一點，反而轉得快。`;
      },
      check: (r, res) => {
        const fast = r.notes.fast;
        if (res.dps < fast.dps * 1.15) {
          return { fail: `轉率 ${res.dps.toFixed(1)}°/s，只比高速時快 ${Math.round((res.dps / fast.dps - 1) * 100)}%。轉彎時速度跑到 ${fmt(res.v0)}，離菱形區太遠，或沒有拉滿。` };
        }
        return undefined;
      } }),
    turnPhase({ id: 'sustain', deg: 360, name: 'MIL 360°',
      checkpoint: true, // retry restores the jet exactly as it entered this task
      coach(r) {
        if (!r.d.armed) return;
        if (r.kmh < r.tune.sustainV + 45 && r.g > r.availG * 0.8) r.cue('burn', '速度快見底了——鬆一點桿，守住它。', { urgent: true });
        if (r.d.turned > 180 && r.kmh > r.tune.sustainV + 30) r.cue('half', '一半了，速度還在。照這樣飛。');
      },
      armKmh: 750, armedRules: { ab: false },
      say: (r) => `最後一題：MIL 轉 360°。速度到 750 開始計時，AB 會關。${r.tune.sustainT} 秒內轉完，結束還要 ${r.tune.sustainV} km/h。`,
      text: (r) => `MIL 轉 360°（AB 停用）　${Math.round(r.d.turned)}°　${r.tune.sustainT}s 內　${fmt(r.kmh)} km/h（≥${r.tune.sustainV}）`,
      check: (r, res) => {
        if (res.t > r.tune.sustainT) return { fail: `轉完 360° 用了 ${res.t.toFixed(1)} 秒（要 ${r.tune.sustainT} 秒內）：太保守了，拉多一點，讓 G 留在菱形區給你的轉率。` };
        if (res.v1 < r.tune.sustainV) return { fail: `轉完只剩 ${fmt(res.v1)} km/h（要 ${r.tune.sustainV}）：平均 ${res.g.toFixed(1)}G，速度從 ${fmt(res.v0)} 被燒掉了。滿桿買到的是轉率，付的是速度——掉到 ${r.tune.sustainV + 30} 附近就要鬆桿守住。` };
        return undefined;
      } }),
  ],
  grade(r) {
    const s = r.notes.sustain;
    return s && s.t < r.tune.sustainT - 2 && s.v1 > r.tune.sustainV + 60 ? 'S' : s && s.v1 > r.tune.sustainV + 20 ? 'A' : 'B';
  },
  debrief(r) {
    const f = r.notes.fast, c = r.notes.corner, s = r.notes.sustain;
    const good = [], improve = [];
    if (f && c) good.push(`同樣滿桿：${fmt(f.v0)} km/h 時 ${f.dps.toFixed(1)}°/s、半徑 ${fmt(f.radius)} m；${fmt(c.v0)} km/h 時 ${c.dps.toFixed(1)}°/s、半徑 ${fmt(c.radius)} m。`);
    if (f) improve.push(`高速 180° 讓你從 ${fmt(f.v0)} 掉到 ${fmt(f.v1)} km/h（平均 ${f.g.toFixed(1)}G）——G 越高，帳單越大。`);
    if (s) (s.v1 > r.tune.sustainV + 40 ? good : improve).push(`持續轉彎 360°：${s.t.toFixed(1)} 秒，結束速度 ${fmt(s.v1)} km/h。`);
    improve.push(r.tactical ? 'Tactical：瞬間轉率靠滿桿，持續轉率靠「不掉速」。空戰會比的是第二圈。' : 'Arcade：BRK 讓圈變小，AB 讓速度回來——兩個都按，就是 AC 式急轉。');
    return { good, improve,
      stats: [['高速轉率', f ? `${f.dps.toFixed(1)}°/s` : '—'], ['最佳速轉率', c ? `${c.dps.toFixed(1)}°/s` : '—'], ['最大 G', `${r.tel.maxG.toFixed(1)}`], ['持續 360°', s ? `${s.t.toFixed(1)} s` : '—']],
      closing: '你剛剛付的每一分速度，都是 G 力的帳單。' };
  },
};

// =====================================================================
// 05 — 能量交易：高度與速度互換，適度拉桿保存能量（引擎怠速）
// =====================================================================
const L05 = {
  id: 'L05', no: 5, title: '能量交易', en: 'ENERGY TRADE',
  principle: '總能量 E = 高度 + 速度²/2g（能量高度）。俯衝把高度換成速度，躍升把速度換回高度；猛拉桿的誘導阻力隨 G² 增加，是最貴的手續費。',
  real: '真實航空：比能量與比剩餘功率 Ps = V(T−D)/W 是能量機動理論（Boyd、Christie）的核心；推力等於阻力時，能量只在高度與速度之間流動。',
  model: '本課規則（純遊戲化）：油門鎖在「巡航推力」（推力約等於阻力，依物理模式換算）、AB 停用，讓 HUD 面板上的能量高度幾乎只受你的拉桿影響。阻力模型為簡化近似。',
  hook: '油門被教官鎖死了。你只剩兩個帳戶：高度和速度。',
  sHint: 'S：躍升時最大 G < 4.5，且能量高度沒有損失',
  goals: ['俯衝：把高度換成速度，在 2,200 m 以上達到 950 km/h', '躍升：把速度換回高度——爬到「你的能量高度 − 300 m」，同時保有 400 km/h', '看懂 HUD 面板的「能量高度」：平順時幾乎不變，猛拉時往下掉'],
  timeLimit: 120,
  // Cruise throttle: thrust ~ drag at ~900 km/h for each physics profile (game rule).
  tune: { arcade: { cruise: 0.63 }, tactical: { cruise: 0.76 }, all: { budget: 300, keepKmh: 400 } },
  rules: (r) => ({ throttle: r.tune.cruise, ab: false }),
  setup: (r) => { soloSetup(r, { alt: 4500, kmh: 650 }); r.me.pos.z = 7000; r.note('E0', r.energyHeight); },
  intro: ['油門鎖在巡航推力，AB 關了。', '你手上只有高度和速度。看好面板上的「能量高度」。'],
  phases: [
    {
      id: 'dive',
      say: '機頭往下，俯衝到 950 km/h，別低於 2,200 m。',
      coach(r) {
        if (r.kmh > 820) r.cue('same', `看：速度漲了，能量高度還是 ${fmt(r.energyHeight)}——你只是換了貨幣。`);
        if (r.me.controls.brake) r.cue('brk', 'BRK 會把能量直接丟掉。俯衝時別碰。');
      },
      praise: (r) => `能量高度 ${fmt(r.notes.E0)} → ${fmt(r.notes.E1)} m：高度變成速度，幾乎不收手續費。`,
      text: (r) => `俯衝到 950 km/h（高度 ≥ 2,200）　${fmt(r.kmh)} km/h　${fmt(r.alt)} m　能量高度 ${fmt(r.energyHeight)} m`,
      progress: (r) => (r.kmh - 650) / 300,
      update(r) {
        if (r.kmh >= 950 && r.alt >= 2200) { r.note('E1', r.energyHeight); r.note('v1', r.kmh); return 'done'; }
        if (r.alt < 2200) return { fail: `掉到 ${fmt(r.alt)} m 還只有 ${fmt(r.kmh)} km/h：俯衝角太淺、拖太久，或拉了 BRK——高度沒有轉成速度，被阻力吃掉了。俯衝要果斷，30° 左右。` };
        if (r.phaseT > 45) return { fail: '45 秒還沒到 950 km/h：機頭再往下壓一點，高度才會變成速度。' };
        return undefined;
      },
    },
    {
      id: 'zoom',
      enter: (r) => {
        r.d.E = r.energyHeight; r.d.peakG = 0; r.d.brake0 = r.tel.brakeSec;
        const keep = (r.tune.keepKmh / KMH) ** 2 / (2 * 9.81);
        r.d.target = Math.round((r.d.E - keep - r.tune.budget) / 50) * 50;
        r.note('zoomTarget', r.d.target);
      },
      name: '躍升',
      checkpoint: true, // retry restores the jet exactly as it came out of the dive
      say: (r) => `能量高度 ${fmt(r.d.E)} m。平順拉起，你能在保有 ${r.tune.keepKmh} km/h 時爬到 ${fmt(r.d.target)} m。猛拉的話……自己看帳單。`,
      coach(r) {
        if (r.g > 6) r.cue('yank', `${r.g.toFixed(1)}G！能量高度正在掉——這就是手續費。`, { urgent: true });
        else if (r.me.controls.brake) r.cue('brk', '現在按 BRK？那是把存款丟進海裡。');
        else if (r.d.climbed && r.alt > r.d.target - 900 && r.d.E - r.energyHeight < 150) r.cue('smooth', '很順。能量高度幾乎沒動。');
      },
      praise: (r) => (r.notes.zoomLoss > 0 ? `爬到了。能量只少了 ${fmt(r.notes.zoomLoss)} m——手續費付得很省。` : '爬到了，能量一點都沒少。這就是平順。'),
      text: (r) => `躍升到 ${fmt(r.d.target)} m（保有 ≥${r.tune.keepKmh} km/h）　${fmt(r.alt)} m　${fmt(r.kmh)} km/h　能量高度 ${fmt(r.energyHeight)} m`,
      progress: (r) => (r.alt - (r.d.target - 2500)) / 2500,
      update(r) {
        r.d.peakG = Math.max(r.d.peakG, r.g);
        if (r.alt >= r.d.target && r.kmh >= r.tune.keepKmh) { r.note('E2', r.energyHeight); r.note('peakG', r.d.peakG); r.note('zoomLoss', r.d.E - r.energyHeight); return 'done'; }
        if (r.me.vel.y > 20) r.d.climbed = true;
        if (r.phaseT > 30 && !r.d.climbed) return { fail: '30 秒還沒開始躍升：俯衝改出後就要拉起，速度不會等你。' };
        if (r.kmh < r.tune.keepKmh - 20 || (r.d.climbed && r.me.vel.y < 0)) {
          const lost = r.d.E - r.energyHeight, brake = r.tel.brakeSec - r.d.brake0;
          return { fail: brake > 0.5 ? `只爬到 ${fmt(r.tel.maxAlt)} m：拉起時按了 ${brake.toFixed(1)} 秒 BRK，能量高度掉了 ${fmt(lost)} m。`
            : r.d.peakG > 6.5 ? `只爬到 ${fmt(Math.max(r.alt, r.d.apex || 0))} m（目標 ${fmt(r.d.target)}）：你拉到 ${r.d.peakG.toFixed(1)}G，能量高度掉了 ${fmt(lost)} m。用 3–4G 平順地拉，同樣的能量會帶你飛得更高。`
              : `只爬到 ${fmt(Math.max(r.alt, r.d.apex || 0))} m（目標 ${fmt(r.d.target)}）：爬升角太淺，速度被阻力慢慢吃掉。拉到 40° 左右再穩住。` };
        }
        r.d.apex = Math.max(r.d.apex || 0, r.alt);
        return undefined;
      },
    },
  ],
  grade(r) {
    const n = r.notes;
    return n.peakG < 4.5 && n.zoomLoss < 0 ? 'S' : n.peakG < 6 ? 'A' : 'B';
  },
  debrief(r) {
    const n = r.notes, good = [], improve = [];
    if (n.E1 != null) good.push(`俯衝：能量高度 ${fmt(n.E0)} → ${fmt(n.E1)} m，你把 ${fmt(4500 - 2200)} m 左右的高度換成了 ${fmt(n.v1)} km/h。`);
    if (n.E2 != null) (n.peakG < 5 ? good : improve).push(`躍升最大 ${n.peakG.toFixed(1)}G，能量高度${n.zoomLoss > 0 ? `損失 ${fmt(n.zoomLoss)}` : `還多了 ${fmt(-n.zoomLoss)}`} m（巡航推力在低速時略大於阻力）。`);
    improve.push('空戰裡道理一樣：高度是存款，速度是現金，G 是手續費。手續費付在換到東西的時候。');
    return { good, improve,
      stats: [['起點 E', `${fmt(n.E0 || 0)} m`], ['俯衝後 E', n.E1 ? `${fmt(n.E1)} m` : '—'], ['躍升目標', n.zoomTarget ? `${fmt(n.zoomTarget)} m` : '—'], ['拉起 G', n.peakG ? n.peakG.toFixed(1) : '—']],
      closing: '能量守恆不是口號。你剛剛親手驗證了。' };
  },
};

// =====================================================================
// 06 — 危險飛行狀態：低速升力、失速近似、俯衝與安全拉起
// =====================================================================
const L06 = {
  id: 'L06', no: 6, title: '危險飛行狀態', en: 'STALL & DIVE RECOVERY',
  principle: '升力 ∝ V²：速度一半，可用升力只剩四分之一。低速猛拉只會更慢；失速時先卸載（推桿）、加油門。俯衝越快，拉起需要的高度越多。',
  real: '真實航空：升力方程 L = ½ρV²SC_L（NASA）；負載因子增加時失速速度按 √n 上升（FAA）。真實失速取決於攻角。',
  model: '本遊戲沒有攻角模型：低速時可用 G 降低，速度低於失速門檻時自動配平失效、機頭下垂——這是「失速近似」，不是真實氣動。',
  hook: '教官會親手把你丟進三種會死人的狀況。你的工作：活著出來。',
  sHint: 'S：俯衝改出最低 > 500 m，失速掉高 < 600 m',
  goals: ['低速轉彎：減速到 420 km/h 以下，轉 90°，速度不得低於 300 km/h', '失速改出：機頭過高、速度不足——恢復到 500 km/h 並平飛', '俯衝改出：75° 俯衝、1,150 km/h、1,500 m——安全拉起'],
  timeLimit: 150,
  tune: { all: { diveAlt: 1500, divePitch: -75, diveKmh: 1150, diveFloor: 150, stallLimit: 30 }, arcade: { stallLoss: 900 }, tactical: { stallLoss: 1200 } },
  setup: (r) => soloSetup(r, { alt: 3500, kmh: 650 }),
  crashReason: (r) => (r.phase?.id === 'dive'
    ? (r.tel.pullUpReact != null && r.tel.pullUpReact > 0.6 ? `墜海。PULL UP 亮起後 ${r.tel.pullUpReact.toFixed(1)} 秒才拉滿——在這個速度，半秒就是幾十公尺。` : '墜海。拉起太晚，或沒收油、沒用 BRK：速度越快，拉起半徑越大（r = V²/(g(n−1))）。')
    : '墜海。'),
  intro: ['今天練的是活下來。', '真正的飛行員在模擬機裡把這三件事練到反射。'],
  phases: [
    {
      id: 'slowturn',
      say: '收油、BRK，降到 420 以下，然後轉 90°。別掉到 300——低速拉滿只會更慢。',
      coach(r) {
        if (r.d.armed) r.cue('armed', `420 了。現在可用 G 只剩 ${r.availG.toFixed(1)}——輕輕轉。`);
        if (r.d.armed && r.kmh < 345) r.cue('slow', '速度快沒了！鬆桿、推油門。', { urgent: true });
      },
      praise: (r) => `轉完了，最低 ${fmt(r.notes.slowMinV)} km/h。低速時，耐心比力氣有用。`,
      enter: (r) => { r.d.h = r.heading; r.d.turned = 0; r.d.armed = false; r.d.minV = 9999; },
      text: (r) => (!r.d.armed ? `減速到 420 km/h 以下　目前 ${fmt(r.kmh)}` : `低速轉 90°　已轉 ${Math.round(r.d.turned)}°　${fmt(r.kmh)} km/h（≥300）　可用 ${r.availG.toFixed(1)}G`),
      progress: (r) => (r.d.armed ? r.d.turned / 90 : 0),
      update(r) {
        const h = r.heading;
        if (!r.d.armed) { if (r.kmh < 420) { r.d.armed = true; r.d.h = h; r.note('slowAvailG', r.availG); } r.d.h = h; return undefined; }
        r.d.turned += Math.abs(wrapDeg(h - r.d.h)); r.d.h = h;
        r.d.minV = Math.min(r.d.minV, r.kmh);
        if (r.kmh < 300) return { fail: `速度掉到 ${fmt(r.kmh)} km/h。這個速度只剩 ${r.availG.toFixed(1)}G 可用，滿桿的阻力把速度吃光了——低速要淺坡度、輕拉、推油門。` };
        if (r.d.turned >= 90) { r.note('slowMinV', r.d.minV); return 'done'; }
        if (r.phaseT > 45) return { fail: '太久了：低速轉彎要有耐心，但不能不轉。' };
        return undefined;
      },
    },
    {
      id: 'stall', name: '失速改出', checkpoint: true, // enter() builds the situation
      enter: (r) => {
        placeJet(r.me, { pos: { ...r.me.pos, y: 3600 }, speed: 92, heading: r.heading, pitch: 50 });
        r.d.alt0 = r.alt; r.d.pullSec = 0;
        r.flash('情境：機頭過高、速度不足！', '#ffc04d');
      },
      say: (r) => r.pick('失速！搖桿往前推、油門推滿。速度回來再拉平。', '失速！推桿卸載、機頭朝下、油門推滿。速度回來前別拉。'),
      coach(r) {
        if (r.d.pullSec > 0.8) r.cue('pull', '別拉！機翼現在沒升力可給——推桿！', { urgent: true });
        if (r.kmh > 400) r.cue('back', '速度回來了。現在把 FPM 慢慢帶回地平線。');
      },
      praise: (r) => (r.notes.stallLoss <= 0 ? '漂亮。一公尺都沒少。' : `改出了，掉了 ${fmt(r.notes.stallLoss)} m。`),
      text: (r) => `失速改出：恢復到 500 km/h 並平飛　${fmt(r.kmh)} km/h　γ ${r.gamma.toFixed(0)}°　已掉 ${fmt(Math.max(0, r.d.alt0 - r.alt))} m`,
      progress: (r) => (r.kmh - 330) / 170,
      update(r, dt) {
        if (r.me.speed < 100 && r.me.controls.pitch > 0.3) r.d.pullSec += dt;
        if (r.kmh >= 500 && Math.abs(r.gamma) < 6) { r.note('stallLoss', r.d.alt0 - r.alt); r.note('stallPull', r.d.pullSec); return 'done'; }
        if (r.d.alt0 - r.alt > r.tune.stallLoss || r.phaseT > r.tune.stallLimit) {
          const lost = Math.max(0, r.d.alt0 - r.alt);
          const head = r.phaseT > r.tune.stallLimit ? `${r.tune.stallLimit} 秒還沒改出` : `掉了 ${fmt(lost)} m`;
          return { fail: r.d.pullSec > 1 ? `${head}。失速時你還拉了 ${r.d.pullSec.toFixed(1)} 秒桿——機翼沒有升力可給，拉桿只會讓它反覆失速。先推桿、讓速度回來。`
            : r.phaseT > r.tune.stallLimit ? `${r.tune.stallLimit} 秒還沒改出：機頭要先朝下讓速度長回來，到 500 km/h 再把 FPM 拉回地平線。`
              : `掉了 ${fmt(r.d.alt0 - r.alt)} m 才改出。速度回到 500 km/h 後要立刻把 FPM 拉回地平線。` };
        }
        return undefined;
      },
    },
    {
      id: 'dive', name: '俯衝改出', checkpoint: true,
      enter: (r) => {
        placeJet(r.me, { pos: { ...r.me.pos, y: r.tune.diveAlt }, speed: r.tune.diveKmh / KMH, heading: r.heading, pitch: r.tune.divePitch });
        r.d.minAlt = r.alt; r.tel.pullUpAt = null; r.tel.pullUpReact = null;
        r.flash(`情境：${-r.tune.divePitch}° 俯衝、${fmt(r.tune.diveKmh)} km/h！`, '#ff6a6a');
      },
      say: '俯衝！收油、按住 BRK、拉滿。現在！',
      coach(r) {
        if (r.tel.pullUpAt != null && r.t - r.tel.pullUpAt > 0.4 && r.tel.pullUpReact == null) r.cue('pull', 'PULL UP！拉！', { urgent: true });
      },
      praise: (r) => `最低 ${fmt(r.notes.diveMin)} m。恭喜你還活著——這在飛行員履歷上很重要。`,
      text: (r) => `俯衝改出：拉到平飛　高度 ${fmt(r.alt)} m　γ ${r.gamma.toFixed(0)}°　${fmt(r.kmh)} km/h`,
      progress: (r) => (r.gamma - r.tune.divePitch) / -r.tune.divePitch,
      update(r) {
        r.d.minAlt = Math.min(r.d.minAlt, r.alt);
        if (r.gamma > -1) { r.note('diveMin', r.d.minAlt); r.note('diveReact', r.tel.pullUpReact); return r.d.minAlt >= r.tune.diveFloor ? 'done'
          : { fail: `改出了，但最低只剩 ${fmt(r.d.minAlt)} m（要 ${r.tune.diveFloor} m 以上）。更早拉、收油加 BRK，讓速度別再長。` }; }
        return undefined;
      },
    },
  ],
  grade(r) {
    const n = r.notes;
    return n.diveMin > 500 && n.stallLoss < 600 ? 'S' : n.diveMin > 300 ? 'A' : 'B';
  },
  debrief(r) {
    const n = r.notes, good = [], improve = [];
    if (n.slowAvailG) good.push(`420 km/h 時可用 G 只有 ${n.slowAvailG.toFixed(1)}G——升力隨速度平方下降。`);
    if (n.stallLoss != null) (n.stallPull > 1 ? improve : good).push(n.stallPull > 1 ? `失速時拉了 ${n.stallPull.toFixed(1)} 秒桿，改出掉了 ${fmt(Math.max(0, n.stallLoss))} m。`
      : n.stallLoss <= 0 ? '失速改出果斷：先讓機頭朝下、速度回來，最後高度一點也沒少。' : `失速改出只掉 ${fmt(n.stallLoss)} m。`);
    if (n.diveMin != null) (n.diveMin > 400 ? good : improve).push(`俯衝改出最低高度 ${fmt(n.diveMin)} m。`);
    return { good, improve,
      stats: [['低速最低', n.slowMinV ? `${fmt(n.slowMinV)} km/h` : '—'], ['失速掉高', n.stallLoss != null ? `${fmt(Math.max(0, n.stallLoss))} m` : '—'], ['俯衝最低', n.diveMin != null ? `${fmt(n.diveMin)} m` : '—'], ['最大 G', r.tel.maxG.toFixed(1)]],
      closing: '活著回來，才有下一場空戰。' };
  },
};

// =====================================================================
// shared combat geometry
// =====================================================================
/** Range, my nose-to-target angle (ATA) and how far I am off its tail (AOT), degrees. */
export function geometry(me, tg) {
  const los = sub(tg.pos, me.pos), R = len(los);
  const ata = angleBetween(forwardOf(me.q), los) / DEG;
  const aot = angleBetween(scale(forwardOf(tg.q), -1), sub(me.pos, tg.pos)) / DEG; // 0 = dead six
  const closure = -dot(sub(tg.vel, me.vel), scale(los, 1 / Math.max(R, 1)));     // + = closing
  return { R, ata, aot, closure };
}
/** Lead / pure / lag classification of where my nose points relative to the target's travel. */
export function pursuitType(me, tg) {
  const nose = forwardOf(me.q), los = norm(sub(tg.pos, me.pos));
  if (angleBetween(nose, los) < 6 * DEG) return 'pure';
  const ahead = norm(sub(addScaled(tg.pos, tg.vel, 2), me.pos));
  const behind = norm(sub(addScaled(tg.pos, tg.vel, -2), me.pos));
  return angleBetween(nose, ahead) < angleBetween(nose, behind) ? 'lead' : 'lag';
}
function duoSetup(r, { me, foe, foeCtl, foeDamage = 0 }) {
  r.match.timeLimit = 1e9;
  placeJet(r.me, me);
  placeJet(r.foe, foe);
  r.foe.dormant = false;
  r.foe.damageScale = foeDamage;
  r.foe.flares = 0;
  r.match.setController(r.foe, foeCtl(r));
}
const pct = (a, b) => (b > 0 ? Math.round((100 * a) / b) : 0);

// =====================================================================
// 07 — 空戰追蹤：Lead / Pure / Lag Pursuit
// =====================================================================
const L07 = {
  id: 'L07', no: 7, title: '空戰追蹤', en: 'PURSUIT GEOMETRY',
  principle: 'Lead（機頭在目標前方）縮短距離、機砲要用；Pure（機頭對準）最直覺但在轉彎戰會被甩到外側；Lag（機頭在目標後方）控制接近率、避免衝過頭。',
  real: '依據：公開的基本戰鬥機動（BFM）教學慣例，非 FAA／NASA 規範。真實空戰還涉及轉彎圈、能量與武器包絡。',
  model: '本遊戲：無人機以同一套物理做等速轉彎並定時反轉；追擊型態由「機頭指向目標的未來／過去位置」簡化判定。本課不給武器。',
  hook: '一架 J-16 塗裝的無人機在前方繞圈。今天不准開火，只准跟。',
  sHint: 'S：一次都不衝過頭，70 秒內完成',
  goals: ['在目標尾後控制區（450–1400 m、45° 錐內、機頭大致對著它）累積 12 秒', '衝過頭（Overshoot）超過 3 次就失敗', '最後：把機頭放在機砲提前量上 1.5 秒（900 m 內）'],
  timeLimit: 150,
  setup: (r) => duoSetup(r, {
    me: { pos: { x: 0, y: 3000, z: 4000 }, speed: 900 / KMH, heading: 0 },
    foe: { pos: { x: 0, y: 3000, z: 2200 }, speed: 230, heading: 0 },
    foeCtl: (rr) => new TurnDrone(rr.foe, { speed: 230, rate: 9, reverseEvery: 18 }),
  }),
  intro: ['今天不准開火，只准跟。', '跟得住，下一課才有東西可打。'],
  onEvent: () => {},
  phases: [
    {
      id: 'cone',
      enter: (r) => { r.d.held = 0; r.d.over = 0; r.d.armed = true; r.d.mix = { lead: 0, pure: 0, lag: 0 }; r.d.maxClose = 0; },
      say: (r) => `跟上那架 J-16。它會轉、會反轉。待在它尾後 450 到 1,400 m。${r.pick('', '先滾轉把它放到座艙罩上方，再拉。')}接近太快就收油，機頭放到它後面——那叫 lag。`,
      coach(r) {
        const g = geometry(r.me, r.foe), type = pursuitType(r.me, r.foe), close = g.closure * KMH;
        const drone = r.match.controllers.get(r.foe);
        if (drone?.side != null) { if (r.d.side != null && drone.side !== r.d.side) r.cue('rev', '它反轉了！跟著換邊，別衝出去。', { cooldown: 15 }); r.d.side = drone.side; }
        // prevent the overshoot instead of only punishing it
        if (g.R < 1500 && close > 220 && g.aot < 70) r.cue('closure', `接近率 ${fmt(close)}！太快了——收油，機頭放到它後面。`, { cooldown: 9, urgent: true });
        if (g.R > 1700) { r.d.farT = (r.d.farT || 0) + 1 / 60; if (r.d.farT > 6 && type !== 'lead') r.cue('far', '太遠了。機頭放到它前面（lead），切內圈追上去。', { cooldown: 14 }); } else r.d.farT = 0;
        if (type === 'pure' && g.R > 900 && g.R < 1700 && close < -30) r.cue('pure', '你一直對準它本身——這叫 pure，在轉彎戰會被甩到外側。機頭往前放一點。', { cooldown: 20 });
        if (g.R >= 450 && g.R <= 1400 && g.aot < 45 && g.ata < 35) {
          r.cue('in', '就是這裡。速度跟它一樣，別急。');
          if (type === 'lag' && Math.abs(close) < 60) r.cue('lag', '這就是 lag：距離穩住了。');
        }
      },
      praise: (r) => { const m = r.notes.mix, tot = m.lead + m.pure + m.lag; return `12 秒。Lead ${pct(m.lead, tot)}%、Pure ${pct(m.pure, tot)}%、Lag ${pct(m.lag, tot)}%。${r.notes.over ? '' : '一次都沒衝過頭。'}`; },
      text: (r) => { const g = geometry(r.me, r.foe); return `尾後控制區 ${(r.d.held).toFixed(1)}/12s　${fmt(g.R)} m　偏離機尾 ${Math.round(g.aot)}°　${{ lead: 'LEAD', pure: 'PURE', lag: 'LAG' }[pursuitType(r.me, r.foe)]}　衝過頭 ${r.d.over}/3`; },
      progress: (r) => r.d.held / 12,
      update(r, dt) {
        const g = geometry(r.me, r.foe);
        if (g.R < 3000) r.d.mix[pursuitType(r.me, r.foe)] += dt;
        if (g.R >= 450 && g.R <= 1400 && g.aot < 45 && g.ata < 35) r.d.held += dt;
        if (g.R < 1500) r.d.maxClose = Math.max(r.d.maxClose, g.closure * KMH);
        if (r.d.armed && g.R < 500 && g.aot > 80) {
          r.d.over += 1; r.d.armed = false;
          r.d.lastClose = g.closure * KMH;
          r.say(r.d.over < 3 ? `衝過頭了！接近率 ${fmt(g.closure * KMH)} km/h。下次早點收油、走 lag。` : '');
        }
        if (!r.d.armed && g.R > 800) r.d.armed = true;
        if (r.d.over >= 3) {
          const m = r.d.mix, tot = m.lead + m.pure + m.lag;
          return { fail: `第 3 次衝過頭（最後一次接近率 ${fmt(r.d.lastClose)} km/h）。你 ${pct(m.lead + m.pure, tot)}% 的時間用 lead／pure 直衝——在轉彎戰裡那只會把你送到它前面。近距離改 lag：機頭放在它後方、速度跟它一樣。` };
        }
        if (r.d.held >= 12) { r.note('mix', { ...r.d.mix }); r.note('over', r.d.over); r.note('maxClose', r.d.maxClose); return 'done'; }
        if (r.phaseT > 100) return { fail: `100 秒只在控制區待了 ${r.d.held.toFixed(1)} 秒。${g.R > 1400 ? '你一直離太遠：遠距離用 lead（機頭放在它前方）切內圈追上去。' : '你常常偏到它側面：跟著它的轉彎圈內側飛，別在外側繞。'}` };
        return undefined;
      },
    },
    {
      id: 'lead',
      enter: (r) => { r.d.held = 0; },
      say: '現在靠近到 900 m 內，把機頭放在橘色提前量圈上。子彈打的是它「等一下」在的地方。',
      coach(r) {
        const g = geometry(r.me, r.foe), e = gunError(r.me, gunLead(r.me, r.foe.pos, r.foe.vel).point) / DEG;
        if (g.R < 900 && e < 6) r.cue('close', '快了，再壓一點點。');
        const eTgt = angleBetween(forwardOf(r.me.q), sub(r.foe.pos, r.me.pos)) / DEG;
        if (g.R < 900 && eTgt < 3 && e > 4) r.cue('tgt', '你在對準它五秒前的位置。往前放，對準橘圈。', { cooldown: 10 });
      },
      praise: '看到那個圈了嗎？下一課，就是在那裡扣扳機。',
      text: (r) => { const g = geometry(r.me, r.foe); const e = gunError(r.me, gunLead(r.me, r.foe.pos, r.foe.vel).point) / DEG; return `機頭對準提前量圈 ${r.d.held.toFixed(1)}/1.5s　${fmt(g.R)} m（≤900）　誤差 ${e.toFixed(1)}°（<2.5°）`; },
      progress: (r) => r.d.held / 1.5,
      update(r, dt) {
        const g = geometry(r.me, r.foe);
        const e = gunError(r.me, gunLead(r.me, r.foe.pos, r.foe.vel).point) / DEG;
        if (g.R < 900 && e < 2.5) r.d.held += dt;
        if (r.d.held >= 1.5) { r.note('leadT', r.phaseT); return 'done'; }
        if (r.phaseT > 45) return { fail: g.R > 900 ? '45 秒還沒進到 900 m：先用 lead 拉近，再放慢接近率。' : '機頭一直不在提前量上：轉彎中的目標，要把機頭拉到它前方。' };
        return undefined;
      },
    },
  ],
  grade(r) { const o = r.notes.over || 0; return o === 0 && r.t < 70 ? 'S' : o <= 1 ? 'A' : 'B'; },
  debrief(r) {
    const m = r.notes.mix || { lead: 0, pure: 0, lag: 0 }, tot = m.lead + m.pure + m.lag;
    const good = [], improve = [];
    good.push(`追擊型態：Lead ${pct(m.lead, tot)}%、Pure ${pct(m.pure, tot)}%、Lag ${pct(m.lag, tot)}%。`);
    (r.notes.over ? improve : good).push(r.notes.over ? `衝過頭 ${r.notes.over} 次：近距離時讓機頭落在它後方，接近率才控制得住。` : '沒有衝過頭——接近率控制得很好。');
    if (r.notes.maxClose > 250) improve.push(`最高接近率 ${fmt(r.notes.maxClose)} km/h：1.5 km 內超過 200 km/h 就要開始減速。`);
    return { good, improve,
      stats: [['控制區', '12 秒'], ['衝過頭', `${r.notes.over ?? 0} 次`], ['Lag 比例', `${pct(m.lag, tot)}%`], ['提前量', r.notes.leadT ? `${r.notes.leadT.toFixed(1)} s` : '—']],
      closing: '位置比火力重要。下一課，給你火力。' };
  },
};

// =====================================================================
// 08 — 武器控制：飛彈發射窗口、機砲提前量
// =====================================================================
const L08 = {
  id: 'L08', no: 8, title: '武器控制', en: 'WEAPONS EMPLOYMENT',
  principle: '飛彈要在「鎖定＋射程內＋好角度」時發射；機砲子彈要飛一段時間，必須瞄準目標將要在的位置（提前量）。',
  real: '真實空戰：飛彈有發射包絡（最小／最大射程隨角度與相對速度變化）；機砲需要提前量與穩定追蹤。',
  model: '本遊戲：鎖定需目標在機頭 30° 內 0.85 秒；SHOOT 提示＝遊戲的命中機率估計 Pk > 0.45（尾追近、正對遠、太近會失效）。本課目標無人機不會受損，也不會放熱焰彈。',
  hook: '靶機升空。它不會還手——也不會原諒你浪費彈藥。',
  sHint: 'S：一發飛彈命中，機砲開火時 > 50% 在提前量上',
  goals: ['用飛彈命中一次（最多 4 發）', '機砲命中 12 發（轉彎中的目標，45 秒內）'],
  timeLimit: 150,
  rules: { weapons: true },
  setup: (r) => duoSetup(r, {
    me: { pos: { x: 0, y: 3000, z: 4000 }, speed: 1000 / KMH, heading: 0 },
    foe: { pos: { x: 0, y: 3000, z: 1800 }, speed: 230, heading: 0 },
    foeCtl: (rr) => new StraightDrone(rr.foe, { speed: 230 }),
  }),
  intro: ['今天開火。目標不會還手——', '所以每一發沒中，都是你的問題。'],
  onEvent(r, ev) {
    if (ev.type === 'missileLaunch' && ev.ac === r.me) {
      const g = geometry(r.me, r.foe);
      const aspect = Math.PI - angleBetween(forwardOf(r.foe.q), scale(norm(sub(r.foe.pos, r.me.pos)), -1));
      const pk = r.me.lock.locked ? missilePk({ R: g.R, ata: g.ata * DEG, aspect, mySpeed: r.me.speed, tgSpeed: r.foe.speed, tgG: r.foe.nCur }) : 0;
      (r.notes.shots ||= []).push({ id: ev.missile.id, R: g.R, pk, locked: !!r.me.lock.locked, aot: g.aot });
    }
    if (ev.type === 'missileHit' && ev.missile.owner === r.me) r.note('mslHit', (r.notes.mslHit || 0) + 1);
    if ((ev.type === 'missileMiss' || ev.type === 'missileExpire' || ev.type === 'missileLost') && ev.missile.owner === r.me) {
      const shot = (r.notes.shots || []).find((x) => x.id === ev.missile.id);
      if (shot && !shot.said && ev.missile.result !== 'hit') { shot.said = true; r.say(shotWhy(shot)); }
    }
    if (ev.type === 'gunHit' && ev.owner === r.me) r.d.gunHits = (r.d.gunHits || 0) + 1;
  },
  phases: [
    {
      id: 'missile',
      say: '先用飛彈。把它放進機頭，等方框變紅色菱形（LOCK）、SHOOT 閃，再按 MSL。',
      coach(r) {
        if (r.me.lock.locked) {
          r.cue('lock', 'LOCK。再等 SHOOT。');
          const g = geometry(r.me, r.foe);
          const aspect = Math.PI - angleBetween(forwardOf(r.foe.q), scale(norm(sub(r.foe.pos, r.me.pos)), -1));
          if (missilePk({ R: g.R, ata: g.ata * DEG, aspect, mySpeed: r.me.speed, tgSpeed: r.foe.speed, tgG: r.foe.nCur }) > 0.45) r.cue('shoot', 'SHOOT！就是現在。', { urgent: true });
        }
      },
      praise: (r) => ((r.notes.shots || []).length <= 1 ? '一發命中。飛彈很貴，你很會省。' : `命中。用了 ${(r.notes.shots || []).length} 發——下次一發就夠。`),
      text: (r) => { const g = geometry(r.me, r.foe); return `飛彈命中 1 次（已發射 ${(r.notes.shots || []).length}/4）　${fmt(g.R)} m　${r.me.lock.locked ? 'LOCK' : '未鎖定'}`; },
      progress: (r) => (r.notes.mslHit ? 1 : 0),
      update(r) {
        if (r.notes.mslHit) return 'done';
        const shots = r.notes.shots || [];
        const wasted = shots.filter((x) => !x.locked || x.pk < 0.25);
        if (wasted.length >= 2) {
          return { fail: `教官叫停：兩發白打了——${wasted.map((x) => (x.locked ? `${fmt(x.R)} m、Pk ${x.pk.toFixed(2)}` : '未鎖定')).join('；')}。飛彈很貴：鎖定、靠近、等 SHOOT 再按。` };
        }
        const flying = r.match.missiles.some((m) => m.alive && m.owner === r.me);
        if (shots.length >= 4 && !flying) {
          const bad = shots.filter((x) => x.pk < 0.45);
          return { fail: `4 發都沒中。其中 ${bad.length} 發是在 Pk 偏低時打的${bad.some((x) => !x.locked) ? '（有的根本沒鎖定）' : ''}。等 SHOOT 出現再按：尾追約 0.8–2 km 最穩。` };
        }
        if (r.phaseT > 70) return { fail: '70 秒沒命中。靠近到 2 km 內、在它正後方、鎖定後再發射。' };
        return undefined;
      },
    },
    {
      id: 'guns',
      enter: (r) => {
        placeJet(r.foe, { pos: { x: r.me.pos.x, y: r.me.pos.y, z: r.me.pos.z - 650 }, speed: 220, heading: r.heading });
        r.match.setController(r.foe, new TurnDrone(r.foe, { speed: 220, rate: 7, reverseEvery: 14 }));
        r.d.gunHits = 0; r.d.fired = 0; r.d.atTarget = 0; r.d.goodAim = 0;
        r.flash('目標轉彎中', '#7fe3ff');
      },
      name: '機砲', checkpoint: true, // enter() rebuilds the gun situation
      say: '機砲。它在轉彎——把橘色圈疊在它身上，不是瞄它本身。按住 GUN，短連射。',
      coach(r, dt) {
        // teach the lead WHILE practising, not only in the debrief
        const g = geometry(r.me, r.foe);
        const eLead = gunError(r.me, gunLead(r.me, r.foe.pos, r.foe.vel).point) / DEG;
        const eTgt = angleBetween(forwardOf(r.me.q), sub(r.foe.pos, r.me.pos)) / DEG;
        r.d.tgtAim = r.me.controls.fireGun && eTgt < eLead && eLead > 3 ? (r.d.tgtAim || 0) + dt : 0;
        if (r.d.tgtAim > 0.8) r.cue('tgt', '你在瞄它本身。子彈到的時候它早走了——瞄橘圈。', { cooldown: 7 });
        r.d.farFire = r.me.controls.fireGun && g.R > 1200 ? (r.d.farFire || 0) + dt : 0;
        if (r.d.farFire > 1) r.cue('far', '太遠了，子彈到不了。靠近到 1 km 內。', { cooldown: 8 });
        r.d.ready = !r.me.controls.fireGun && g.R < 900 && eLead < 2 ? (r.d.ready || 0) + dt : 0;
        if (r.d.ready > 0.8) r.cue('fire', '圈在它身上了——開火！', { cooldown: 10 });
        if (r.d.gunHits >= 1) r.cue('first', '命中！就是那個圈。');
        if (r.d.gunHits >= 6) r.cue('half', '一半了。保持提前量，別貪。');
      },
      praise: (r) => `${r.notes.gunHits} 發。開火時 ${r.notes.gunAim}% 在提前量上。`,
      text: (r) => `機砲命中 ${r.d.gunHits}/12（45 秒內）　${fmt(geometry(r.me, r.foe).R)} m`,
      progress: (r) => r.d.gunHits / 12,
      update(r) {
        if (r.me.controls.fireGun) {
          r.d.fired += 1;
          const lead = gunLead(r.me, r.foe.pos, r.foe.vel).point;
          const eLead = gunError(r.me, lead) / DEG, eTgt = angleBetween(forwardOf(r.me.q), sub(r.foe.pos, r.me.pos)) / DEG;
          if (eLead < 2) r.d.goodAim += 1; else if (eTgt < eLead) r.d.atTarget += 1;
        }
        if (r.d.gunHits >= 12) { r.note('gunHits', r.d.gunHits); r.note('gunAim', pct(r.d.goodAim, r.d.fired)); return 'done'; }
        if (r.phaseT > 45) {
          return { fail: r.d.fired < 30 ? `只命中 ${r.d.gunHits} 發：幾乎沒開火。距離 1 km 內、提前量圈疊上目標就按住 GUN。`
            : r.d.atTarget > r.d.goodAim ? `只命中 ${r.d.gunHits} 發：${pct(r.d.atTarget, r.d.fired)}% 的子彈是瞄著它本身打的——它在轉彎，子彈到的時候它已經不在那裡。瞄橘色圈。`
              : `只命中 ${r.d.gunHits} 發：距離太遠或追蹤不穩。拉近到 600 m，讓提前量圈停在它身上再開火。` };
        }
        return undefined;
      },
    },
  ],
  grade(r) { const s = (r.notes.shots || []).length; return s <= 1 && (r.notes.gunAim || 0) > 50 ? 'S' : s <= 2 ? 'A' : 'B'; },
  debrief(r) {
    const shots = r.notes.shots || [], good = [], improve = [];
    if (shots.length) (shots.length === 1 ? good : improve).push(shots.length === 1 ? `一發命中：發射時 ${fmt(shots[0].R)} m、Pk ${shots[0].pk.toFixed(2)}。` : `用了 ${shots.length} 發飛彈。第一發 Pk ${shots[0].pk.toFixed(2)}、${fmt(shots[0].R)} m。`);
    if (r.notes.gunAim != null) (r.notes.gunAim > 40 ? good : improve).push(`機砲開火時，有 ${r.notes.gunAim}% 的時間機頭在提前量上。`);
    return { good, improve,
      stats: [['飛彈', `${r.notes.mslHit ? 1 : 0}/${shots.length}`], ['機砲命中', `${r.notes.gunHits ?? 0}`], ['提前量瞄準', `${r.notes.gunAim ?? 0}%`], ['用時', `${Math.round(r.t)} s`]],
      closing: '武器只是最後一步。前面七課，都是為了讓這一步變簡單。' };
  },
};
function shotWhy(s) {
  if (!s.locked) return '那發沒鎖定。飛彈很貴，拜託先鎖定再發射。';
  if (s.R < 450) return `太近了（${fmt(s.R)} m）：飛彈來不及轉。拉開到 800 m 以上。`;
  if (s.pk < 0.3) return `那發 Pk 只有 ${s.pk.toFixed(2)}，${fmt(s.R)} m。太遠或角度太差——繞到它正後方。`;
  return `Pk ${s.pk.toFixed(2)}，這發是運氣不好。下一發等 SHOOT 穩定再按。`;
}

// =====================================================================
// 09 — 防守與反擊：飛彈警告、熱焰彈、Overshoot
// =====================================================================
const L09 = {
  id: 'L09', no: 9, title: '防守與反擊', en: 'DEFENSE & REVERSAL',
  principle: '飛彈有轉彎極限和反應延遲：在它最後一刻（約 0.5 km）往側面急轉，並在 2.6 km 內放熱焰彈。太早轉，它還來得及修正。被咬尾時，急轉＋減速逼對方衝過頭，再反咬。',
  real: '真實空戰：飛彈防禦依賴機動（beam、break）與誘餌；被追擊時以減速、剪刀等機動迫使攻擊者 overshoot（公開 BFM 教學慣例）。',
  model: '本遊戲規則：飛彈有 0.4 秒自動駕駛延遲與 G 上限；熱焰彈只在 2.6 km 內、每枚飛彈一次 40–55% 機率被誘騙；熱焰彈 2 組，25 秒回充。實測：熱焰彈＋剩 0.5 km 急轉 0/18 被命中，太早（1.6 km）急轉 7/18，不防守 12/18。飛彈段 AB 停用（遊戲規則）；本課機體不會損毀。反咬段的 J-16 是腳本化攻擊機（純遊戲規則）：G 上限約可用 G 的 45%、在機砲距離配速，所以直線飛永遠甩不掉它；急轉＋減速才會逼它衝過頭，之後它做穩定轉彎讓你練反咬。',
  hook: '今天角色互換：教官會向你發射三枚訓練彈。',
  sHint: 'S：3 枚飛彈全躲掉，且 40 秒內反咬成功',
  goals: ['教官連發 3 枚飛彈：最多被命中 1 枚（第 1 枚我喊時機，第 2 枚只喊熱焰彈，第 3 枚靠你自己）', '熱焰彈只有 2 組——第 3 枚只能靠急轉', '被 J-16 咬尾：逼它衝過頭，反咬到它尾後 3 秒'],
  timeLimit: 170,
  rules: { weapons: false, playerDamage: 0 },
  setup: (r) => {
    duoSetup(r, {
      me: { pos: { x: 0, y: 3200, z: 9000 }, speed: 800 / KMH, heading: 0 },
      foe: { pos: { x: 0, y: 3200, z: 11500 }, speed: 260, heading: 0 },
      foeCtl: (rr) => new StraightDrone(rr.foe, { speed: 260 }),
    });
    r.me.damageScale = 0;
  },
  intro: ['今天換你被打。', '慌是正常的。慌了還照程序做，才叫飛行員。'],
  onEvent(r, ev) {
    if (ev.type === 'missileHit' && ev.target === r.me) { r.d.hits = (r.d.hits || 0) + 1; r.say(missileWhy(r, ev.missile, true)); }
    if ((ev.type === 'missileMiss' || ev.type === 'missileExpire') && ev.missile.target === r.me && !ev.missile.reported) {
      ev.missile.reported = true; r.d.misses = (r.d.misses || 0) + 1;
      r.say(ev.missile.decoy ? '騙走了。熱焰彈是你的好朋友。' : `躲掉了！最後關頭你拉到 ${(ev.missile.defG || 0).toFixed(1)}G。`);
    }
    if (ev.type === 'flares' && ev.ac === r.me) {
      for (const m of r.match.missiles) if (m.alive && m.target === r.me) m.flareAt ??= len(sub(m.pos, r.me.pos));
    }
  },
  phases: [
    {
      id: 'missiles',
      rules: { ab: false },
      enter: (r) => { r.d.hits = 0; r.d.misses = 0; r.d.launched = 0; r.d.next = 3; },
      say: (r) => `飛彈從後方來，AB 故障，跑不掉。約 2 km 放熱焰彈（${r.pick('FLR', 'FLR／Q')}）。剩 0.5 km，往側面${r.pick('推滿', '滾轉拉滿')}。第一枚我幫你喊時機。`,
      coach(r) {
        // explain -> practise -> challenge: missile 1 fully called, 2 flare only, 3 silent
        const m = r.match.missiles.find((x) => x.alive && x.target === r.me);
        if (!m) return;
        const d = len(sub(m.pos, r.me.pos)), n = r.d.launched;
        if (n <= 2 && d < 2300) r.cue(`flr${n}`, n === 1 ? 'FLARE！' : 'FLARE——接下來自己算。', { urgent: true });
        if (n === 1 && d < 700) r.cue('brk1', 'BREAK！往側面拉滿！', { urgent: true });
        if (d > 1400 && r.g > 5) r.cue(`early${n}`, '太早了！它還轉得過來——先撐住，等它靠近。', { urgent: true });
      },
      text: (r) => {
        const m = r.match.missiles.find((x) => x.alive && x.target === r.me);
        const d = m ? len(sub(m.pos, r.me.pos)) : 0;
        return `飛彈防禦 ${r.d.launched}/3　被命中 ${r.d.hits}（最多 1）　熱焰彈 ${r.me.flares}${m ? `　來襲 ${(d / 1000).toFixed(1)} km${r.d.launched === 1 && d < 700 ? '　▶ BREAK' : ''}` : ''}`;
      },
      progress: (r) => (r.d.hits + r.d.misses) / 3,
      update(r) {
        for (const m of r.match.missiles) {
          if (!m.alive || m.target !== r.me) continue;
          const d = len(sub(m.pos, r.me.pos));
          if (d < 1500) m.defG = Math.max(m.defG || 0, r.g);
          if (d < 2600 && r.g > 5 && m.breakAt == null) m.breakAt = d;
        }
        const active = r.match.missiles.some((m) => m.alive && m.target === r.me);
        // the first launch waits until KITE has finished the defence briefing
        if (r.d.launched < 3 && r.phaseT > r.d.next && !active && (r.d.launched > 0 || !r.radioBusy)) {
          // 150 deg off the nose, 1.9 km, AB unavailable: running away is not a defence,
          // and (measured, docs/academy-curriculum.md) flares + a last-second break are.
          const side = r.d.launched % 2 ? -1 : 1, bearing = (r.heading + side * 150) * DEG;
          const dist = 1900;
          const lp = { x: r.me.pos.x + Math.sin(bearing) * dist, y: r.me.pos.y + 150, z: r.me.pos.z - Math.cos(bearing) * dist };
          const toMe = Math.atan2(r.me.pos.x - lp.x, -(r.me.pos.z - lp.z)) / DEG;
          placeJet(r.foe, { pos: lp, speed: 280, heading: toMe });
          r.match.setController(r.foe, new StraightDrone(r.foe, { speed: 260 }));
          scriptedLaunch(r.match, r.foe, r.me);
          r.d.launched += 1; r.d.next = r.phaseT + 11;
          r.flash(`MISSILE ${r.d.launched}/3`, '#ff6a6a');
          if (r.d.launched === 3) r.say('第三枚。熱焰彈沒了，只剩你和時機。');
        }
        if (r.d.hits >= 2) return { fail: `被命中 ${r.d.hits} 枚。${r.d.why || ''}` };
        if (r.d.launched >= 3 && !active && r.d.hits + r.d.misses >= 3) { r.note('mslHits', r.d.hits); return 'done'; }
        return undefined;
      },
    },
    {
      id: 'reverse', name: '反咬', checkpoint: true, // enter() rebuilds the bandit-on-six situation
      enter: (r) => {
        // Always the same situation, in the middle of the training area (room to fight,
        // and a retry / checkpoint retry is the identical scenario).
        const h = 0;
        placeJet(r.me, { pos: { x: 0, y: 3200, z: 0 }, speed: 700 / KMH, heading: 0 });
        placeJet(r.foe, { pos: { x: r.me.pos.x - Math.sin(h) * 900, y: 3250, z: r.me.pos.z + Math.cos(h) * 900 }, speed: 260, heading: r.heading });
        r.foe.missiles = 0; r.foe.gunRounds = 600;
        r.match.setController(r.foe, new BanditDrone(r.foe, r.me, { speed: 260 }));
        r.me.damageScale = 0; r.d.held = 0; r.d.overshoots = 0; r.d.armed = true; r.d.brakeUsed = 0;
        r.flash('BANDIT ON YOUR SIX!', '#ff6a6a');
      },
      say: (r) => `BANDIT 六點鐘，900 m！${r.pick('搖桿往它那邊推到底', '朝它的方向滾轉、拉滿')}。必要時收油、BRK——逼它衝過頭，再反咬。`,
      coach(r) {
        const g = geometry(r.me, r.foe);
        const straight = Math.abs(r.bank) < 20 && g.R < 1300 && g.aot > 120;
        r.d.straight = straight ? (r.d.straight || 0) + 1 / 60 : 0;
        if (straight) r.d.straightSum = (r.d.straightSum || 0) + 1 / 60;
        if (r.d.straight > 4) r.cue('straight', '直線飛就是靶子。朝它轉！', { cooldown: 12 });
      },
      praise: (r) => `反咬成功。它衝過頭 ${r.notes.overshoots} 次——是你讓它衝的。`,
      text: (r) => { const g = geometry(r.me, r.foe); return `反咬：它的尾後 ${r.d.held.toFixed(1)}/3s　${fmt(g.R)} m　我機頭偏差 ${Math.round(g.ata)}°　偏離它機尾 ${Math.round(g.aot)}°`; },
      progress: (r) => r.d.held / 3,
      update(r, dt) {
        const g = geometry(r.me, r.foe), rev = geometry(r.foe, r.me);
        if (r.me.controls.brake) r.d.brakeUsed += dt;
        if (r.d.armed && rev.R < 450 && rev.aot > 90) { r.d.overshoots += 1; r.d.armed = false; r.say('它衝過頭了！現在反咬！'); }
        if (!r.d.armed && rev.R > 900) r.d.armed = true;
        if (g.R < 1500 && g.ata < 30 && g.aot < 60) r.d.held += dt;
        if (r.d.held >= 3) { r.note('revT', r.phaseT); r.note('overshoots', r.d.overshoots); r.note('revBrake', r.d.brakeUsed); return 'done'; }
        if ((r.d.straightSum || 0) > 15 && !r.d.overshoots) {
          return { fail: `你有 ${Math.round(r.d.straightSum)} 秒在直線飛，它就在你後面開火。直線飛就是靶子——朝它急轉、收油、BRK，逼它衝過頭。` };
        }
        if (r.phaseT > 75) {
          return { fail: r.d.overshoots === 0 ? `75 秒還沒甩掉它，它一次都沒衝過頭。${r.d.brakeUsed < 1 ? '你沒用 BRK：' : ''}朝它急轉、適時減速，讓它的速度把它送到你前面。`
            : `它衝過頭 ${r.d.overshoots} 次，你卻沒能咬住它的尾巴：衝過頭的瞬間就要反轉、追 lead。` };
        }
        return undefined;
      },
    },
  ],
  grade(r) { return r.notes.mslHits === 0 && r.notes.revT < 40 ? 'S' : r.notes.mslHits === 0 || r.notes.revT < 40 ? 'A' : 'B'; },
  debrief(r) {
    const good = [], improve = [];
    (r.notes.mslHits ? improve : good).push(r.notes.mslHits ? `3 枚飛彈被命中 ${r.notes.mslHits} 枚。` : '3 枚飛彈全部躲掉。');
    if (r.notes.revT != null) good.push(`反咬用了 ${Math.round(r.notes.revT)} 秒，逼它衝過頭 ${r.notes.overshoots} 次${r.notes.revBrake > 0.5 ? `，BRK ${r.notes.revBrake.toFixed(1)} 秒` : ''}。`);
    improve.push('真實戰場不會有教官暫停：先看 MISSILE、再看距離、最後拉桿——順序要變成反射。');
    return { good, improve,
      stats: [['飛彈命中', `${r.notes.mslHits ?? 0}/3`], ['熱焰彈', `${r.me.stats.flaresUsed}`], ['Overshoot', `${r.notes.overshoots ?? 0}`], ['反咬', r.notes.revT ? `${Math.round(r.notes.revT)} s` : '—']],
      closing: '活下來，然後反咬。這就是戰鬥機飛行員。' };
  },
};
function missileWhy(r, m, hit) {
  const parts = [];
  if (m.flareAt == null) parts.push('沒放熱焰彈');
  else if (m.flareAt > FLARE.decoyRange) parts.push(`熱焰彈在 ${(m.flareAt / 1000).toFixed(1)} km 就放了（2.6 km 外無效）`);
  if (m.breakAt != null && m.breakAt > 1200) parts.push(`你在 ${(m.breakAt / 1000).toFixed(1)} km 就開始急轉，太早了，它修正得過來`);
  else if ((m.defG || 0) < 5) parts.push(`最後 1.5 km 只拉了 ${(m.defG || 0).toFixed(1)}G`);
  const why = parts.length ? `命中！${parts.join('、')}。` : '命中！這枚運氣好——時機都對，下一枚照做。';
  r.d.why = parts.length ? `${parts.join('、')}。2 km 放熱焰彈，剩 0.5 km 往側面拉滿。` : '';
  return why;
}

// =====================================================================
// 10 — ACE QUALIFICATION：完整 1v1 畢業考核
// =====================================================================
const L10 = {
  id: 'L10', no: 10, title: 'ACE QUALIFICATION', en: 'FINAL CHECKRIDE', final: true,
  seed: 52036, // fixed opening so a retry is the same checkride (see docs/academy-curriculum.md)
  principle: '完整 1v1：對手是 VETERAN AI，規則與自由對戰相同。用前九課的一切——能量、位置、武器、防守。',
  real: '整合課程：真實的戰鬥機考核同樣看「決策」而不只是結果。',
  model: '本遊戲：VETERAN AI 與你使用同一套物理與武器。評等依勝負、剩餘耐久、時間、命中率與能量管理計算（純遊戲化）。',
  hook: '畢業考核。對手：VETERAN J-16。規則：跟真的一樣。',
  sHint: 'S：剩餘耐久 ≥ 70 且 150 秒內擊落；A：剩餘耐久 ≥ 40',
  goals: ['擊落 VETERAN J-16（或時間到時耐久較高）', '通過後授予 ACE RATING 與 TAC NAME'],
  timeLimit: null,
  rules: { weapons: true },
  setup: (r) => {
    r.foe.dormant = false;
    r.foeAI = new PilotAI(r.foe, { skill: 'veteran', seed: r.match.seed + 7 });
    r.match.setController(r.foe, r.foeAI);
  },
  intro: ['這是畢業考。對手是 VETERAN。', '我不會再提示你——除非你快死了。', "祝好運。FIGHT'S ON！"],
  crashReason: () => '墜海。高度也是武器——別在海面上跟它纏鬥。',
  phases: [
    {
      id: 'fight',
      say: '',
      text: (r) => { const g = geometry(r.me, r.foe); return `擊落 J-16　我 HP ${Math.round(r.me.hp)}　敵 HP ${Math.round(r.foe.hp)}　${fmt(g.R)} m`; },
      progress: (r) => 1 - r.foe.hp / r.foe.type.hp,
      update(r) {
        const res = r.match.result;
        if (r.me.hp <= 50 && r.me.alive) r.cue('hp', '你中彈了。拉開、拿回能量，別硬拚。');
        if (r.match.missiles.some((m) => m.alive && m.target === r.me)) r.cue('msl', 'MISSILE。你知道該怎麼做。');
        if (r.alt < 500 && r.me.vel.y < -30) r.cue('low', '高度！別在海面上跟它纏。', { cooldown: 25, urgent: true });
        if (r.foe.hp < r.foe.type.hp) r.cue('hit', '命中！別停，壓上去。');
        if (!res) return undefined;
        if (res.winner === r.me) { r.note('reason', res.reason); return 'done'; }
        if (res.winner === r.foe) return { fail: res.reason === 'timeDecision' ? `時間到：耐久 ${Math.round(r.me.hp)} 對 ${Math.round(r.foe.hp)}，判負。` : res.reason === 'crash' ? r.lesson.crashReason(r) : res.reason === 'outOfBounds' ? '脫離戰區判負。' : '你被擊落了。' };
        return { fail: '平手。王牌不接受平手。' };
      },
    },
  ],
  grade(r) {
    const hp = r.me.hp, t = r.t;
    return hp >= 70 && t <= 150 ? 'S' : hp >= 40 ? 'A' : 'B';
  },
  debrief(r, success) {
    const st = r.me.stats, good = [], improve = [];
    const band = pct(r.tel.bandSec, r.tel.flightSec);
    (band > 35 ? good : improve).push(`有 ${band}% 的時間速度在最佳轉彎區（綠色菱形）。`);
    if (st.missilesFired) (st.missileHits / st.missilesFired >= 0.3 ? good : improve).push(`飛彈 ${st.missileHits}/${st.missilesFired}。${st.missileHits / st.missilesFired < 0.3 ? '等 SHOOT 再打。' : ''}`);
    if (st.roundHits) good.push(`機砲命中 ${st.roundHits} 發。`);
    const taken = 100 - Math.max(0, r.me.hp);
    if (taken > 0) improve.push(`受到 ${Math.round(taken)} 點傷害${r.foe.stats.missileHits ? `（被飛彈命中 ${r.foe.stats.missileHits} 次）` : ''}。`);
    if (r.tel.gHighSec > 25) improve.push(`超過 7G 的時間累積 ${Math.round(r.tel.gHighSec)} 秒：能量燒太多。`);
    const tac = success ? tacName(r, band) : null;
    return { good, improve,
      stats: [['剩餘耐久', `${Math.round(Math.max(0, r.me.hp))}`], ['時間', `${Math.round(r.t)} s`], ['飛彈', `${st.missileHits}/${st.missilesFired}`], ['最佳轉彎區', `${band}%`]],
      extra: tac,
      closing: success
        ? ['擊落確認。', `KITE 呼叫 ${tac.name}。這是你的 TAC NAME——${tac.why}`, '歡迎加入王牌名單。回場吧，咖啡我請。']
        : '再來一次。王牌也是從被擊落學起的。' };
  },
};

/**
 * Graduation callsign from how the checkride was actually flown (pure game flavour).
 * First matching rule wins; each reason quotes the real number behind it.
 */
export function tacName(r, band) {
  const st = r.me.stats, taken = 100 - Math.max(0, r.me.hp);
  if (taken <= 0) return { name: 'GHOST', why: '整場一發都沒被打中。' };
  if (st.roundHits > 0 && st.missileHits === 0) return { name: 'SABER', why: `你用機砲把它拆了，${st.roundHits} 發。` };
  if (st.missilesFired > 0 && st.missileHits / st.missilesFired >= 0.5) return { name: 'LANCE', why: `飛彈 ${st.missileHits}/${st.missilesFired}，一點都不浪費。` };
  if (r.t < 100) return { name: 'FALCON', why: `${Math.round(r.t)} 秒結束戰鬥。` };
  if (band >= 35) return { name: 'CORNER', why: `${band}% 的時間你都在最佳轉彎速度。` };
  if (r.me.hp < 40) return { name: 'PHOENIX', why: `剩 ${Math.round(r.me.hp)} 點耐久還贏，你命很硬。` };
  return { name: 'TALON', why: '咬住了，就沒放手。' };
}

export const LESSONS = [L01, L02, L03, L04, L05, L06, L07, L08, L09, L10];
export const lessonById = (id) => LESSONS.find((l) => l.id === id);
export { gatePhase, pointAhead };
