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


// =====================================================================
// 04 — G 力的代價：瞬間／持續轉率、轉彎半徑、最佳轉彎速度
// =====================================================================
/** Turn a given number of degrees; records rate, radius, speed and G. */
function turnPhase({ id, deg, say, text, limit, check, armKmh, armedRules }) {
  const begin = (r) => { r.d.h = r.heading; r.d.turned = 0; r.d.v0 = r.kmh; r.d.alt0 = r.alt; r.d.gSum = 0; r.d.vSum = 0; r.d.n = 0; r.d.t0 = r.phaseT; };
  return {
    id, say,
    enter: (r) => { r.d.armed = !armKmh; begin(r); },
    text: (r) => (!r.d.armed ? `先加速到 ${armKmh} km/h（AB 可用）　目前 ${fmt(r.kmh)}`
      : text ? text(r) : `滿桿轉 ${deg}°　已轉 ${Math.round(r.d.turned)}°　${fmt(r.kmh)} km/h　${r.g.toFixed(1)}G`),
    progress: (r) => r.d.turned / deg,
    update(r) {
      if (!r.d.armed) {
        if (r.kmh < armKmh) { if (r.phaseT > 40) return { fail: `40 秒還沒加速到 ${armKmh} km/h：油門推滿、開 AB、別轉彎。` }; return undefined; }
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
  goals: ['高速（約 1050 km/h）滿桿轉 180°，記住轉率', '減速到綠色菱形出現', '在最佳轉彎速度再轉 180°，轉率至少快 15%', '從 750 km/h 起只用 MIL（AB 停用）轉 360°：準時轉完，又要守住結束速度'],
  timeLimit: 170,
  tune: {
    // Calibrated with a level, altitude-held turn from 750 km/h under MIL:
    // full stick ends at ~450 km/h (fails speed); a pilot who spends speed to a
    // floor and then holds it finishes inside the time with margin.
    arcade: { sustainT: 17, sustainV: 580 },
    tactical: { sustainT: 26, sustainV: 560 },
  },
  setup: (r) => soloSetup(r, { kmh: 1050 }),
  intro: ['G 力不是免費的。今天你會用自己的眼睛看到它的帳單。'],
  phases: [
    turnPhase({ id: 'fast', deg: 180, limit: 30,
      say: (r) => r.pick('油門推滿、開 AB。搖桿推到底，轉 180°。看轉率和速度。', '油門推滿、開 AB。滾到 80° 以上、拉滿桿，轉 180°。') }),
    holdPhase({ id: 'band', need: 2,
      say: (r) => { const [lo, hi] = r.bestBandKmh; return `看到了嗎？太快，G 到頂了也轉不快。收油、BRK，降到 ${lo}–${hi} km/h，等綠色菱形亮。`; },
      text: (r) => { const [lo, hi] = r.bestBandKmh; return `減速到最佳轉彎速度 ${lo}–${hi} km/h　目前 ${fmt(r.kmh)}　${r.inBestBand ? '◆ 保持' : ''}`; },
      cond: (r) => r.inBestBand,
      timeout: (r) => (r.kmh > r.bestBandKmh[1] ? '還是太快。收油到底、按住 BRK，速度才會掉進菱形區。' : '太慢了。推油門、開 AB，把速度帶回菱形區。') }),
    turnPhase({ id: 'corner', deg: 180, limit: 25,
      say: '就是這個速度。現在滿桿再轉 180°——比比看。',
      check: (r, res) => {
        const fast = r.notes.fast;
        if (res.dps < fast.dps * 1.15) {
          return { fail: `轉率 ${res.dps.toFixed(1)}°/s，只比高速時快 ${Math.round((res.dps / fast.dps - 1) * 100)}%。轉彎時速度跑到 ${fmt(res.v0)}，離菱形區太遠，或沒有拉滿。` };
        }
        return undefined;
      } }),
    turnPhase({ id: 'sustain', deg: 360,
      armKmh: 750, armedRules: { ab: false },
      say: (r) => `最後一題：先加速到 750 km/h。計時一開始 AB 就停用——用 MIL 推力轉 360°，${r.tune.sustainT} 秒內轉完，結束時還要有 ${r.tune.sustainV} km/h。${r.pick('搖桿推越多轉越急，也越燒速度。', '看趨勢條：一路滿桿會把速度燒光。')}`,
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
  goals: ['俯衝：把高度換成速度，在 2,200 m 以上達到 950 km/h', '躍升：把速度換回高度——爬到「你的能量高度 − 300 m」，同時保有 400 km/h', '看懂 HUD 面板的「能量高度」：平順時幾乎不變，猛拉時往下掉'],
  timeLimit: 120,
  // Cruise throttle: thrust ~ drag at ~900 km/h for each physics profile (game rule).
  tune: { arcade: { cruise: 0.63 }, tactical: { cruise: 0.76 }, all: { budget: 300, keepKmh: 400 } },
  rules: (r) => ({ throttle: r.tune.cruise, ab: false }),
  setup: (r) => { soloSetup(r, { alt: 4500, kmh: 650 }); r.me.pos.z = 7000; r.note('E0', r.energyHeight); },
  intro: ['今天油門被我鎖在巡航推力，AB 也關了。你手上只有高度和速度——看好面板上的「能量高度」。'],
  phases: [
    {
      id: 'dive',
      say: '機頭往下，俯衝到 950 km/h，但別低於 2,200 m。注意：能量高度幾乎沒變——你只是把高度換成了速度。',
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
      say: (r) => `你的能量高度 ${fmt(r.d.E)} m。平順地拉起，應該能在保有 ${r.tune.keepKmh} km/h 時爬到 ${fmt(r.d.target)} m。猛拉的話……你自己看帳單。`,
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
  goals: ['低速轉彎：減速到 420 km/h 以下，轉 90°，速度不得低於 300 km/h', '失速改出：機頭過高、速度不足——恢復到 500 km/h 並平飛', '俯衝改出：75° 俯衝、1,150 km/h、1,500 m——安全拉起'],
  timeLimit: 150,
  tune: { all: { diveAlt: 1500, divePitch: -75, diveKmh: 1150, diveFloor: 150, stallLimit: 30 }, arcade: { stallLoss: 900 }, tactical: { stallLoss: 1200 } },
  setup: (r) => soloSetup(r, { alt: 3500, kmh: 650 }),
  crashReason: (r) => (r.phase?.id === 'dive'
    ? (r.tel.pullUpReact != null && r.tel.pullUpReact > 0.6 ? `墜海。PULL UP 亮起後 ${r.tel.pullUpReact.toFixed(1)} 秒才拉滿——在這個速度，半秒就是幾十公尺。` : '墜海。拉起太晚，或沒收油、沒用 BRK：速度越快，拉起半徑越大（r = V²/(g(n−1))）。')
    : '墜海。'),
  intro: ['今天練的是活下來。這三種狀況，真正的飛行員都在模擬機裡練到反射。'],
  phases: [
    {
      id: 'slowturn',
      say: '收油、BRK，降到 420 km/h 以下，然後轉 90°。速度別掉到 300 以下——低速時拉滿，只會更慢。',
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
      id: 'stall',
      enter: (r) => {
        placeJet(r.me, { pos: { ...r.me.pos, y: 3600 }, speed: 92, heading: r.heading, pitch: 50 });
        r.d.alt0 = r.alt; r.d.pullSec = 0;
        r.flash('情境：機頭過高、速度不足！', '#ffc04d');
      },
      say: (r) => r.pick('失速了！搖桿往前推讓機頭下來、推滿油門。速度回來再拉平。', '失速了！先推桿卸載、機頭朝下、推滿油門。速度回來之前別拉。'),
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
      id: 'dive',
      enter: (r) => {
        placeJet(r.me, { pos: { ...r.me.pos, y: r.tune.diveAlt }, speed: r.tune.diveKmh / KMH, heading: r.heading, pitch: r.tune.divePitch });
        r.d.minAlt = r.alt; r.tel.pullUpAt = null; r.tel.pullUpReact = null;
        r.flash(`情境：${-r.tune.divePitch}° 俯衝、${fmt(r.tune.diveKmh)} km/h！`, '#ff6a6a');
      },
      say: '俯衝！收油、按住 BRK、拉滿桿。現在！',
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

export const LESSONS = [L01, L02, L03, L04, L05, L06];
export const lessonById = (id) => LESSONS.find((l) => l.id === id);
export { gatePhase, pointAhead };
