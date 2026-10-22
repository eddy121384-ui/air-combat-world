// Ace Flight Academy — lesson definitions. Each lesson is data + small judge
// functions over REAL sim state (see runner.js). Instructor callsign: KITE (黑鳶).
// Every lesson cites what is real aeronautics, what is this game's simplified
// model, and what is a pure game rule (docs/academy-curriculum.md).
import { holdPhase, gatePhase, placeJet, pointAhead, wrapDeg, KMH } from './runner.js';

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
  goals: ['平飛 5 秒：FPM 對準 0° 線、機翼水平', '爬升 600 m 後改平並穩住', '下降到指定高度並穩住'],
  timeLimit: 150,
  timeoutHint: '先讓 FPM 停住，再決定要往哪裡修。',
  setup: (r) => soloSetup(r),
  intro: [
    '這裡是教官 KITE。今天不打仗，先學會「看」。',
    'W 是機頭，帶翅膀的小圓是 FPM——你真正飛去的方向。',
  ],
  phases: [
    holdPhase({
      id: 'level', need: 5,
      say: (r) => r.pick('搖桿放中間，飛控會自動把機翼改平。讓 FPM 貼著 0° 線。', '左右修平機翼，上下讓 FPM 貼著 0° 線。不會有人幫你改平。'),
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
      text: (r) => `爬升到 ${fmt(r.d.target)} m（±120）並改平　目前 ${fmt(r.alt)} m　γ ${r.gamma.toFixed(1)}°`,
      progress: (r) => (r.d.held || 0) / 4,
      update(r, dt) {
        const err = r.alt - r.d.target;
        r.d.over = Math.max(r.d.over || 0, err);
        if (Math.abs(err) < 120 && Math.abs(r.gamma) < 3) r.d.held = (r.d.held || 0) + dt;
        if (r.d.over > 250 && !r.d.warned) { r.d.warned = true; r.say(`衝過頭 ${Math.round(r.d.over)} m 了。接近目標前就要開始把 FPM 放回地平線。`); }
        if ((r.d.held || 0) >= 4) { r.note('climbOvershoot', Math.max(0, r.d.over - 120)); return 'done'; }
        return undefined;
      },
    },
    {
      id: 'descend',
      enter: (r) => { r.d.target = r.notes.climbTarget - 900; },
      say: (r) => `很好。現在下降到 ${fmt(r.d.target)} m——機頭往下，速度會自己長上來，看好速度框。`,
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
  goals: ['右轉到 090° 並改平', '左轉 150° 到 300°', '精準轉到 015°（±4°），14 秒內，高度變化 < 200 m'],
  timeLimit: 150,
  setup: (r) => soloSetup(r),
  intro: [(r) => r.pick(
    'Assisted：搖桿往哪推，飛控就往哪轉——它會替你滾轉再拉桿。看懂它在做什麼。',
    'Expert：左右只會滾轉。機翼斜了還不夠，要拉桿，飛機才會轉。')],
  phases: [
    headingPhase({ id: 'h090', target: 90, limit: 40,
      say: (r) => r.pick('右轉到 090°。看機翼怎麼斜下去——那是飛控在幫你傾斜升力。', '向右滾 60° 左右，然後拉桿。到 090° 前提早改平。') }),
    headingPhase({ id: 'h300', target: 300, limit: 45,
      say: (r) => r.pick('左轉到 300°，一口氣轉 150°。搖桿推越多，轉得越急。', '左轉到 300°。這次坡度大一點、拉多一點：你會看到 G 值上去。') }),
    headingPhase({ id: 'h015', target: 15, tol: 4, need: 3, limit: 14, precise: true,
      say: '最後：14 秒內精準轉到 015°，誤差 4° 以內，高度別亂跑。' }),
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
  goals: ['水平加速到 1000 km/h（高度 ±250 m）', '在時限內減到 650 km/h 以下', '把速度穩在 600–700 km/h 6 秒'],
  timeLimit: 120,
  tune: { arcade: { accelLimit: 24, decelLimit: 13 }, tactical: { accelLimit: 30, decelLimit: 14 } },
  setup: (r) => { soloSetup(r, { kmh: 600, throttle: 0.6 }); r.note('alt0', 3000); },
  intro: ['動力是你的錢包。今天學怎麼花、怎麼省。'],
  phases: [
    {
      id: 'accel',
      say: '油門推到底、點亮 AB，平飛加速到 1000 km/h。不准用俯衝作弊。',
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
      say: '好。現在減到 650 km/h 以下——收油、關 AB、按住 BRK。',
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
      say: '穩住 600 到 700。油門放在哪裡，飛機最後就會停在哪個速度。',
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

export const LESSONS = [L01, L02, L03];
export const lessonById = (id) => LESSONS.find((l) => l.id === id);
export { gatePhase, pointAhead };
