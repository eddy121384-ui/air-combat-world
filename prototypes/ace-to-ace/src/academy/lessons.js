// Ace Flight Academy — lesson definitions. Each lesson is data + small judge
// functions over REAL sim state (see runner.js). Instructor callsign: KITE (黑鳶).
// Every lesson cites what is real aeronautics, what is this game's simplified
// model, and what is a pure game rule (docs/academy-curriculum.md).
import { holdPhase, gatePhase, placeJet, pointAhead, wrapDeg, KMH } from './runner.js';
import { StraightDrone, TurnDrone, scriptedLaunch } from './drones.js';
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
  goals: ['平飛 5 秒：FPM 對準 0° 線、機翼水平', '爬升 600 m 後改平並穩住', '下降到指定高度並穩住'],
  timeLimit: 150,
  timeoutHint: '先讓 FPM 停住，再決定要往哪裡修。',
  setup: (r) => soloSetup(r),
  intro: [
    'KITE 呼叫學員：先飛穩，再飛帥。今天把一條爬升與下降航線交給你。',
  ],
  phases: [
    holdPhase({
      id: 'level', need: 5, strict: true,
      say: (r) => r.pick('放手，搖桿回中，飛控替你改平機翼。小幅修正，讓 FPM 貼 0° 線。', '放手只讓搖桿回中，機翼不會自己改平。反向修平坡度，再看 FPM。'),
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
        if (Math.abs(err) < 120 && Math.abs(r.gamma) < 3) r.d.held = (r.d.held || 0) + dt; else r.d.held = 0;
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
        if (Math.abs(err) < 120 && Math.abs(r.gamma) < 3) r.d.held = (r.d.held || 0) + dt; else r.d.held = 0;
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
      if (precise && r.d.altDev > 200) return { fail: `高度偏離 ${Math.round(r.d.altDev)} m（上限 200）：坡度與拉桿要一起協調，別用掉高換航向。` };
      if (limit && r.phaseT > limit) {
        const slow = r.tel.rollNoPullSec > 1.5 && r.control === 'expert';
        return { fail: slow
          ? `超過 ${limit} 秒。你有滾轉卻沒拉桿——升力方向斜了，但升力不足以維持轉彎高度。`
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
  principle: '升力垂直於機翼。滾轉傾斜升力、產生轉向分量；要維持高度還得增加升力。協調水平轉彎需要 n = 1/cos(坡度) 的負載因子。',
  real: '真實航空：坡度轉彎靠升力水平分量；坡度越大，維持高度所需負載因子越高（60° 坡度約 2G）——FAA 飛行手冊。',
  model: '本遊戲：同樣的升力向量轉彎，Assisted 由飛控代你協調滾轉與拉桿，但用的是同一架飛機、同樣的 G 上限。',
  goals: ['右轉到 090° 並改平', '左轉 150° 到 300°', '精準轉到 015°（±4°），14 秒內，高度變化 < 200 m'],
  timeLimit: 150,
  setup: (r) => soloSetup(r),
  intro: [(r) => r.pick(
    '領隊要三個新航向。Assisted 替你協調轉彎；到航向前放手，飛控會改平。',
    '領隊要三個新航向。Expert 先滾轉、再拉桿；放手不會改平，改平要反向滾轉。')],
  phases: [
    headingPhase({ id: 'h090', target: 90, limit: 40,
      say: (r) => r.pick('右轉 090°。接近目標就放手，讓飛控改平。', '右滾約 60°，橫向回中後拉桿轉彎。接近 090° 時反向滾轉改平。') }),
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
    if (r.control === 'expert' && r.tel.rollNoPullSec > 2) improve.push(`有 ${r.tel.rollNoPullSec.toFixed(1)} 秒在大坡度卻沒拉桿：只滾轉不會自動維持轉彎高度。`);
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
      id: 'hold', need: 6, strict: true,
      say: '連續穩住 600 到 700。先小幅調油門，再看速度趨勢；別追著數字來回推。',
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
      ? `收油＋BRK，${r.notes.decelT.toFixed(1)} 秒減掉 350 km/h。` : `減速花了 ${r.notes.decelT.toFixed(1)} 秒：BRK 能增加阻力、加快減速。`);
    improve.push(r.tactical ? 'Tactical：MIL 也能加速，AB 能更快重建能量；兩者都不能讓急轉免費。' : 'Arcade：AB 快而寬，收油／BRK 慢而急——第四課會看到差別。');
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
      say: (r) => { const [lo, hi] = r.bestBandKmh; return `高速基準 ${r.notes.fast.dps.toFixed(1)} 度每秒。收油、BRK 到 ${lo}–${hi}。下一次用同樣滿桿比較。`; },
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
        r.flash(`轉率 +${Math.round((res.dps/fast.dps-1)*100)}%`, '#7dffb0');
        r.coachOnce('corner-gain', `同樣滿桿，轉率多了 ${Math.round((res.dps/fast.dps-1)*100)}%。速度對了，G 才買得到好位置。`);
        return undefined;
      } }),
    turnPhase({ id: 'sustain', deg: 360,
      armKmh: 750, armedRules: { ab: false },
      say: (r) => `先回到 750，計時後 AB 停用。MIL 轉一圈，${r.tune.sustainT} 秒內，保留 ${r.tune.sustainV}。第二圈還想飛，就別把速度全花光。`,
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
  goals: ['俯衝：把高度換成速度，在 2,200 m 以上達到 950 km/h', '躍升：保留 400 km/h 的動能及 300 m 損耗預算，其餘換成目標高度', '比較高度＋動能高度＝能量高度；推力與阻力仍會改變總額'],
  timeLimit: 120,
  // Cruise throttle: thrust ~ drag at ~900 km/h for each physics profile (game rule).
  tune: { arcade: { cruise: 0.63 }, tactical: { cruise: 0.76 }, all: { budget: 300, keepKmh: 400 } },
  rules: (r) => ({ throttle: r.tune.cruise, ab: false }),
  setup: (r) => { soloSetup(r, { alt: 4500, kmh: 650 }); r.me.pos.z = 7000; r.note('E0', r.energyHeight); },
  intro: ['這趟試飛只准用巡航推力，AB 停用。把高度換成速度，再換回來；我收的是數據，不是你的高度。'],
  phases: [
    {
      id: 'dive',
      say: '機頭往下，俯衝到 950 km/h，但別低於 2,200 m。注意：能量高度幾乎沒變——你只是把高度換成了速度。',
      text: (r) => `俯衝到 950 km/h（高度 ≥ 2,200）　${fmt(r.kmh)} km/h　${fmt(r.alt)} m　能量高度 ${fmt(r.energyHeight)} m`,
      progress: (r) => (r.kmh - 650) / 300,
      update(r) {
        if (r.kmh >= 950 && r.alt >= 2200) { r.note('E1', r.energyHeight); r.note('v1', r.kmh); r.note('diveAlt', r.alt); return 'done'; }
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
      say: (r) => `平順拉起，別猛拉。目標 ${fmt(r.d.target)} m，保留 ${r.tune.keepKmh} km/h。看兩種餘額互換，別把總額花在阻力上。`,
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
    if (n.E1 != null) good.push(`俯衝：高度實際減少 ${fmt(4500 - n.diveAlt)} m，速度到 ${fmt(n.v1)} km/h；能量高度 ${fmt(n.E0)} → ${fmt(n.E1)} m。`);
    if (n.E2 != null) (n.peakG < 5 ? good : improve).push(`躍升最大 ${n.peakG.toFixed(1)}G，能量高度${n.zoomLoss > 0 ? `損失 ${fmt(n.zoomLoss)}` : `還多了 ${fmt(-n.zoomLoss)}`} m（巡航推力在低速時略大於阻力）。`);
    improve.push('空戰裡道理一樣：高度是存款，速度是現金，G 是手續費。手續費付在換到東西的時候。');
    return { good, improve,
      stats: [['起點 E', `${fmt(n.E0 || 0)} m`], ['俯衝後 E', n.E1 ? `${fmt(n.E1)} m` : '—'], ['躍升目標', n.zoomTarget ? `${fmt(n.zoomTarget)} m` : '—'], ['拉起 G', n.peakG ? n.peakG.toFixed(1) : '—']],
      closing: '高度與速度可以互換；引擎在存錢，阻力在收費。現在你看得懂這本帳了。' };
  },
};

// =====================================================================
// 06 — 危險飛行狀態：低速升力、失速近似、俯衝與安全拉起
// =====================================================================
const L06 = {
  id: 'L06', no: 6, title: '危險飛行狀態', en: 'STALL & DIVE RECOVERY',
  principle: '密度、升力係數等條件相同時，升力 ∝ V²。低速猛拉增加阻力；本遊戲失速近似先卸載（推桿）、加油門。俯衝越快，拉起需要的高度越多。',
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
          return { fail: r.d.pullSec > 1 ? `${head}。失速時你還拉了 ${r.d.pullSec.toFixed(1)} 秒桿——可用升力不足以繼續抬頭，持續拉桿又增加阻力。先推桿、讓速度回來。`
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
  goals: ['在目標尾後控制區（450–1400 m、45° 錐內、機頭大致對著它）累積 12 秒', '第三次衝過頭（Overshoot）即叫停，最多容許兩次', '最後：把機頭放在機砲提前量上 1.5 秒（900 m 內）'],
  timeLimit: 150,
  setup: (r) => duoSetup(r, {
    me: { pos: { x: 0, y: 3000, z: 4000 }, speed: 900 / KMH, heading: 0 },
    foe: { pos: { x: 0, y: 3000, z: 2200 }, speed: 230, heading: 0 },
    foeCtl: (rr) => new TurnDrone(rr.foe, { speed: 230, rate: 9, reverseEvery: 18 }),
  }),
  intro: ['今天不准開火。只准跟。追得住，下一課才有東西可打。'],
  onEvent: () => {},
  phases: [
    {
      id: 'cone',
      enter: (r) => { r.d.held = 0; r.d.over = 0; r.d.armed = true; r.d.mix = { lead: 0, pure: 0, lag: 0 }; r.d.maxClose = 0; },
      say: (r) => `跟到尾後 450–1,400 m。青色 LEAD 收距、白色 PURE 指目標、金色 LAG 控接近。${r.pick('放手會改平，追蹤時要持續修正。', '滾轉後拉桿；放手不會替你改平。')}`,
      markers: (r) => {
        const ahead=addScaled(r.foe.pos,r.foe.vel,2), behind=addScaled(r.foe.pos,r.foe.vel,-2);
        const los=sub(r.foe.pos,r.me.pos);
        // On a straight tail chase the three points share one sightline. Drawing
        // three stacked rings teaches nothing; reveal the comparison as it turns.
        if(Math.max(angleBetween(sub(ahead,r.me.pos),los),angleBetween(sub(behind,r.me.pos),los))<3*DEG)return [];
        return [
          {pos:ahead,label:'LEAD 前方',kind:'reference',labelOffsetY:-18,color:'#7fe3ff'},
          {pos:r.foe.pos,label:'PURE 目標',kind:'reference',labelOffsetY:0,color:'#f4fbff'},
          {pos:behind,label:'LAG 後方',kind:'reference',labelOffsetY:18,color:'#ffc04d'},
        ];
      },
      text: (r) => { const g = geometry(r.me, r.foe); return `尾後控制區 ${(r.d.held).toFixed(1)}/12s　${fmt(g.R)} m　偏離機尾 ${Math.round(g.aot)}°　${{ lead: 'LEAD', pure: 'PURE', lag: 'LAG' }[pursuitType(r.me, r.foe)]}　衝過頭 ${r.d.over}/3`; },
      progress: (r) => r.d.held / 12,
      update(r, dt) {
        const g = geometry(r.me, r.foe);
        if (g.R < 3000) r.d.mix[pursuitType(r.me, r.foe)] += dt;
        if (g.R >= 450 && g.R <= 1400 && g.aot < 45 && g.ata < 35) r.d.held += dt;
        if (g.R < 1500) r.d.maxClose = Math.max(r.d.maxClose, g.closure * KMH);
        if (r.d.armed && g.R < 500 && g.aot > 80) {
          r.d.over += 1; r.d.armed = false;
          r.d.lastClose = r.d.maxClose;
          r.say(r.d.over < 3 ? `衝過頭了！先前最高接近率 ${fmt(r.d.maxClose)} km/h。收油、BRK，改追 LAG。` : '', { urgent: true });
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
      say: '很好。現在靠近到 900 m 內，把機頭放在橘色提前量圈上——機砲打的是它「將要」在的位置。',
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
    const m = r.notes.mix || r.d.mix || { lead: 0, pure: 0, lag: 0 }, tot = m.lead + m.pure + m.lag;
    const over=r.notes.over ?? (r.phase?.id==='cone'?r.d.over:0), held=r.notes.mix?12:(r.phase?.id==='cone'?r.d.held:0);
    const good = [], improve = [];
    good.push(`追擊型態：Lead ${pct(m.lead, tot)}%、Pure ${pct(m.pure, tot)}%、Lag ${pct(m.lag, tot)}%。`);
    if(over)improve.push(`衝過頭 ${over} 次：近距離改 LAG，提早控制接近率。`);
    else if(held>=12)good.push('控制區滿 12 秒且沒有衝過頭，接近率控制得很好。');
    else improve.push(`控制區僅 ${Number(held||0).toFixed(1)} 秒；先取得穩定尾後位置。`);
    if (r.notes.maxClose > 250) improve.push(`最高接近率 ${fmt(r.notes.maxClose)} km/h：1.5 km 內超過 200 km/h 就要開始減速。`);
    return { good, improve,
      stats: [['控制區', `${Number(held||0).toFixed(1)} 秒`], ['衝過頭', `${over??0} 次`], ['Lag 比例', `${pct(m.lag, tot)}%`], ['提前量', r.notes.leadT ? `${r.notes.leadT.toFixed(1)} s` : '—']],
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
  goals: ['用飛彈命中一次（最多 4 發）', '機砲命中 12 發（轉彎中的目標，45 秒內）'],
  timeLimit: 150,
  rules: { weapons: true },
  setup: (r) => duoSetup(r, {
    me: { pos: { x: 0, y: 3000, z: 4000 }, speed: 1000 / KMH, heading: 0 },
    foe: { pos: { x: 0, y: 3000, z: 1800 }, speed: 230, heading: 0 },
    foeCtl: (rr) => new StraightDrone(rr.foe, { speed: 230 }),
  }),
  intro: ['武器測試開始。目標不還手，你可以專心把準備做對；飛彈不是拿來代替轉彎的。'],
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
      say: '先用飛彈。把它放進機頭，等方框變成紅色菱形（LOCK），再等 SHOOT 閃——那時候按 MSL。',
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
      say: '機頭 W 對準橘色提前量圈，再短按 GUN。別把圈追到目標身上：圈是子彈要去的位置。',
      text: (r) => `機砲命中 ${r.d.gunHits}/12（45 秒內）　${fmt(geometry(r.me, r.foe).R)} m`,
      progress: (r) => r.d.gunHits / 12,
      update(r, dt) {
        if (r.me.controls.fireGun) {
          r.d.fired += 1;
          const lead = gunLead(r.me, r.foe.pos, r.foe.vel).point;
          const eLead = gunError(r.me, lead) / DEG, eTgt = angleBetween(forwardOf(r.me.q), sub(r.foe.pos, r.me.pos)) / DEG;
          if (eLead < 2) r.d.goodAim += 1; else if (eTgt < eLead) r.d.atTarget += 1;
          if (eTgt < eLead && eLead > 2) r.d.bodyAimSec = (r.d.bodyAimSec || 0)+dt;
        }
        if (r.d.bodyAimSec > 0.6) r.coachOnce('aim-body', '你在追它現在的位置。把機頭 W 移到橘圈，讓子彈提早到。', {urgent:true});
        if (r.d.gunHits >= 3) r.coachOnce('gun-connect', `已有 ${r.d.gunHits} 發命中。提前量對了，保持短連射。`);
        if (r.d.gunHits >= 12) { r.note('gunHits', r.d.gunHits); r.note('gunAim', pct(r.d.goodAim, r.d.fired)); return 'done'; }
        if (r.phaseT > 45) {
          return { fail: r.d.fired < 30 ? `只命中 ${r.d.gunHits} 發：幾乎沒開火。距離 1 km 內、機頭 W 對準提前量圈再開火。`
            : r.d.atTarget > r.d.goodAim ? `只命中 ${r.d.gunHits} 發：${pct(r.d.atTarget, r.d.fired)}% 的子彈是瞄著它本身打的——它在轉彎，子彈到的時候它已經不在那裡。瞄橘色圈。`
              : `只命中 ${r.d.gunHits} 發：距離太遠或追蹤不穩。拉近到 600 m，機頭 W 對準橘圈再開火。` };
        }
        return undefined;
      },
    },
  ],
  grade(r) { const s = (r.notes.shots || []).length; return s <= 1 && (r.notes.gunAim || 0) > 50 ? 'S' : s <= 2 ? 'A' : 'B'; },
  debrief(r) {
    const shots = r.notes.shots || [], good = [], improve = [];
    if (shots.length) (shots.length === 1 && r.notes.mslHit ? good : improve).push(shots.length === 1 && r.notes.mslHit ? `一發命中：發射時 ${fmt(shots[0].R)} m、Pk ${shots[0].pk.toFixed(2)}。` : `發射 ${shots.length} 枚、命中 ${r.notes.mslHit||0} 枚。第一發 Pk ${shots[0].pk.toFixed(2)}、${fmt(shots[0].R)} m。`);
    if (r.notes.gunAim != null) (r.notes.gunAim > 40 ? good : improve).push(`機砲開火時，有 ${r.notes.gunAim}% 的時間機頭在提前量上。`);
    return { good, improve,
      stats: [['飛彈', `${r.notes.mslHit ? 1 : 0}/${shots.length}`], ['機砲命中', `${r.notes.gunHits ?? (r.phase?.id==='guns'?r.d.gunHits:0)}`], ['提前量瞄準', `${r.notes.gunAim ?? (r.phase?.id==='guns'?pct(r.d.goodAim,r.d.fired):0)}%`], ['用時', `${Math.round(r.t)} s`]],
      closing: '武器只是最後一步。前面七課，都是為了讓這一步變簡單。' };
  },
};
function shotWhy(s) {
  if (!s.locked) return `那發沒有鎖定就發射——飛彈不知道要追誰。等紅色菱形。`;
  if (s.R < 450) return `那發太近了（${fmt(s.R)} m）：飛彈來不及解除保險、轉不過來。拉開到 800 m 以上。`;
  if (s.pk < 0.3) return `那發 Pk 只有 ${s.pk.toFixed(2)}（${fmt(s.R)} m、偏離機尾 ${Math.round(s.aot)}°）：太遠或角度太差。靠近、繞到它正後方再打。`;
  return `那發 Pk ${s.pk.toFixed(2)}，仍不保證命中。保持好位置，下一發等 SHOOT 穩定再按。`;
}

// =====================================================================
// 09 — 防守與反擊：飛彈警告、熱焰彈、Overshoot
// =====================================================================
const L09 = {
  id: 'L09', no: 9, title: '防守與反擊', en: 'DEFENSE & REVERSAL',
  principle: '飛彈有轉彎極限和反應延遲：在它最後一刻（約 0.5 km）往側面急轉，並在 2.6 km 內放熱焰彈。太早轉，它還來得及修正。被咬尾時，急轉＋減速逼對方衝過頭，再反咬。',
  real: '真實空戰：飛彈防禦依賴機動（beam、break）與誘餌；被追擊時以減速、剪刀等機動迫使攻擊者 overshoot（公開 BFM 教學慣例）。',
  model: '本遊戲規則：飛彈有 0.4 秒自動駕駛延遲與 G 上限；熱焰彈只在 2.6 km 內、每枚飛彈一次 40–55% 機率被誘騙；熱焰彈 2 組，25 秒回充。實測：熱焰彈＋剩 0.5 km 急轉 0/18 被命中，太早（1.6 km）急轉 7/18，不防守 12/18。飛彈段 AB 停用（遊戲規則）；本課機體不會損毀。',
  goals: ['教官連發 3 枚飛彈：最多被命中 1 枚', '熱焰彈只有 2 組——第 3 枚只能靠急轉', '被 J-16 咬尾：逼它衝過頭，反咬到它尾後 3 秒'],
  timeLimit: 170,
  tune: { all: { launchRanges:[1900,1900,1900], launchIntervals:[3,11,11] } },
  rules: { weapons: false, playerDamage: 0 },
  setup: (r) => {
    duoSetup(r, {
      me: { pos: { x: 0, y: 3200, z: 9000 }, speed: 800 / KMH, heading: 0 },
      foe: { pos: { x: 0, y: 3200, z: 11500 }, speed: 260, heading: 0 },
      foeCtl: (rr) => new StraightDrone(rr.foe, { speed: 260 }),
    });
    r.me.damageScale = 0;
  },
  intro: ['今天換你被打。慌是正常的，慌了還照程序做，才叫飛行員。'],
  onEvent(r, ev) {
    if (ev.type === 'missileHit' && ev.target === r.me) { r.d.hits = (r.d.hits || 0) + 1; r.say(missileWhy(r, ev.missile, true), {urgent:true}); }
    if ((ev.type === 'missileMiss' || ev.type === 'missileExpire') && ev.missile.target === r.me && !ev.missile.reported) {
      ev.missile.reported = true; r.d.misses = (r.d.misses || 0) + 1;
      r.say(ev.missile.decoy ? '誘餌奏效，這枚被騙走了。別停止掃描。' : (ev.missile.defG||0)>=5
        ? `這枚失去威脅，近距機動記錄 ${ev.missile.defG.toFixed(1)}G。保持高度。` : '這枚失去威脅。保持高度，繼續看來襲警告。');
    }
    if (ev.type === 'flares' && ev.ac === r.me) {
      for (const m of r.match.missiles) if (m.alive && m.target === r.me) m.flareAt ??= len(sub(m.pos, r.me.pos));
    }
  },
  phases: [
    {
      id: 'missiles',
      rules: { ab: false },
      enter: (r) => { r.d.hits = 0; r.d.misses = 0; r.d.launched = 0; r.d.next = r.tune.launchIntervals[0]; },
      say: (r) => `AB 本段停用。看來襲距離與接近時間，別背倒數。約 2 km 放 FLR，約 0.5 km 側向${r.pick('推滿', '滾轉拉滿')}。這是本遊戲模型的練習窗口。`,
      text: (r) => {
        const m = r.match.missiles.find((x) => x.alive && x.target === r.me);
        return `飛彈防禦 ${r.d.launched}/3　被命中 ${r.d.hits}（最多 1）　熱焰彈 ${r.me.flares}${m ? `　來襲 ${(len(sub(m.pos, r.me.pos)) / 1000).toFixed(1)} km` : ''}`;
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
        if (r.d.launched < 3 && r.phaseT > r.d.next && !active) {
          // 150 deg off the nose, 1.9 km, AB unavailable: running away is not a defence,
          // and (measured, docs/academy-curriculum.md) flares + a last-second break are.
          const side = r.d.launched % 2 ? -1 : 1, bearing = (r.heading + side * 150) * DEG;
          const dist = r.tune.launchRanges[r.d.launched];
          const lp = { x: r.me.pos.x + Math.sin(bearing) * dist, y: r.me.pos.y + 150, z: r.me.pos.z - Math.cos(bearing) * dist };
          const toMe = Math.atan2(r.me.pos.x - lp.x, -(r.me.pos.z - lp.z)) / DEG;
          placeJet(r.foe, { pos: lp, speed: 280, heading: toMe });
          r.match.setController(r.foe, new StraightDrone(r.foe, { speed: 260 }));
          scriptedLaunch(r.match, r.foe, r.me);
          (r.notes.launches ||= []).push({ t:r.phaseT, distance:dist });
          r.d.launched += 1; r.d.next = r.phaseT + (r.tune.launchIntervals[r.d.launched]??11);
          r.flash(`MISSILE ${r.d.launched}/3`, '#ff6a6a');
        }
        if (r.d.hits >= 2) return { fail: `被命中 ${r.d.hits} 枚。${r.d.why || ''}` };
        if (r.d.launched >= 3 && !active && r.d.hits + r.d.misses >= 3) { r.note('mslHits', r.d.hits); return 'done'; }
        return undefined;
      },
    },
    {
      id: 'reverse',
      enter: (r) => {
        const h = r.heading * DEG;
        placeJet(r.me, { pos: { ...r.me.pos, y: 3200 }, speed: 700 / KMH, heading: r.heading });
        placeJet(r.foe, { pos: { x: r.me.pos.x - Math.sin(h) * 900, y: 3250, z: r.me.pos.z + Math.cos(h) * 900 }, speed: 260, heading: r.heading });
        r.foe.missiles = 0; r.foe.gunRounds = 600;
        r.foeAI = new PilotAI(r.foe, { skill: 'rookie', seed: 91 });
        r.match.setController(r.foe, r.foeAI);
        r.me.damageScale = 0; r.d.held = 0; r.d.overshoots = 0; r.d.armed = true; r.d.brakeUsed = 0;
        r.flash('BANDIT ON YOUR SIX!', '#ff6a6a');
      },
      say: (r) => `J-16 咬在你六點鐘，900 m！${r.pick('搖桿往它那邊推到底', '朝它的方向滾轉、拉滿')}，必要時收油按 BRK——逼它衝過頭，再反咬回去。`,
      text: (r) => { const g = geometry(r.me, r.foe); return `反咬：它的尾後 ${r.d.held.toFixed(1)}/3s　${fmt(g.R)} m　我機頭偏差 ${Math.round(g.ata)}°　偏離它機尾 ${Math.round(g.aot)}°`; },
      progress: (r) => r.d.held / 3,
      update(r, dt) {
        const g = geometry(r.me, r.foe), rev = geometry(r.foe, r.me);
        if (r.me.controls.brake) r.d.brakeUsed += dt;
        if (r.d.armed && rev.R < 450 && rev.aot > 90) { r.d.overshoots += 1; r.d.armed = false; r.say('它衝過頭了！現在反咬！'); }
        if (!r.d.armed && rev.R > 900) r.d.armed = true;
        if (g.R < 1500 && g.ata < 30 && g.aot < 60) r.d.held += dt;
        if (r.d.held >= 3) { r.note('revT', r.phaseT); r.note('overshoots', r.d.overshoots); r.note('revBrake', r.d.brakeUsed); return 'done'; }
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
    const hits=r.notes.mslHits ?? (r.phase?.id==='missiles'?r.d.hits:0);
    const launched=r.notes.mslHits!=null?3:(r.phase?.id==='missiles'?r.d.launched:0);
    if(launched===3 && hits===0)good.push('3 枚飛彈全部躲掉。');
    else improve.push(`已發射 ${launched} 枚，被命中 ${hits} 枚；看來襲距離與接近時間修正。`);
    if (r.notes.revT != null) good.push(`反咬用了 ${Math.round(r.notes.revT)} 秒，逼它衝過頭 ${r.notes.overshoots} 次${r.notes.revBrake > 0.5 ? `，BRK ${r.notes.revBrake.toFixed(1)} 秒` : ''}。`);
    improve.push('真實戰場不會有教官暫停：先看 MISSILE、再看距離、最後拉桿——順序要變成反射。');
    return { good, improve,
      stats: [['飛彈命中', `${hits}/${launched}`], ['熱焰彈', `${r.me.stats.flaresUsed}`], ['Overshoot', `${r.notes.overshoots ?? 0}`], ['反咬', r.notes.revT ? `${Math.round(r.notes.revT)} s` : '—']],
      closing: '活下來，然後反咬。這就是戰鬥機飛行員。' };
  },
};
function missileWhy(r, m, hit) {
  const parts = [];
  if (m.flareAt == null) parts.push('沒放熱焰彈');
  else if (m.flareAt > FLARE.decoyRange) parts.push(`熱焰彈在 ${(m.flareAt / 1000).toFixed(1)} km 就放了（2.6 km 外無效）`);
  if (m.breakAt != null && m.breakAt > 1200) parts.push(`你在 ${(m.breakAt / 1000).toFixed(1)} km 就開始急轉，太早了，它修正得過來`);
  else if ((m.defG || 0) < 5) parts.push(`最後 1.5 km 只拉了 ${(m.defG || 0).toFixed(1)}G`);
  const why = parts.length ? `命中！${parts.join('、')}。` : '命中。操作接近窗口，但誘餌不是保證；下一枚仍看來襲距離與方向。';
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
  goals: ['擊落 VETERAN J-16（或時間到時耐久較高）', 'S：剩餘耐久 ≥ 70 且 150 秒內擊落', 'A：剩餘耐久 ≥ 40'],
  timeLimit: null,
  rules: { weapons: true },
  setup: (r) => {
    r.foe.dormant = false;
    r.foeAI = new PilotAI(r.foe, { skill: 'veteran', seed: r.match.seed + 7 });
    r.match.setController(r.foe, r.foeAI);
  },
  intro: ['考核空域已清空，對手 VETERAN。不再逐步提示：把速度花在位置，把武器用在機會。KITE 在這裡等你回報。'],
  crashReason: () => '墜海。高度也是武器——別在海面上跟它纏鬥。',
  phases: [
    {
      id: 'fight',
      say: 'KITE 在頻道上。考核開始，自主決策。',
      text: (r) => { const g = geometry(r.me, r.foe); return `擊落 J-16　我 HP ${Math.round(r.me.hp)}　敵 HP ${Math.round(r.foe.hp)}　${fmt(g.R)} m`; },
      progress: (r) => 1 - r.foe.hp / r.foe.type.hp,
      update(r) {
        const res = r.match.result;
        if (!r.d.warned && r.me.hp <= 50 && r.me.alive) { r.d.warned = true; r.say('你中彈了。拉開、拿回能量，別硬拚。'); }
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
    if (success && r.lesson.grade(r) !== 'S') improve.push(`下一個目標 S：保留至少 70 耐久，150 秒內完成。這次 ${Math.round(r.me.hp)} 耐久／${Math.round(r.t)} 秒。`);
    return { good, improve,
      stats: [['剩餘耐久', `${Math.round(Math.max(0, r.me.hp))}`], ['時間', `${Math.round(r.t)} s`], ['飛彈', `${st.missileHits}/${st.missilesFired}`], ['最佳轉彎區', `${band}%`]],
      closing: success ? `確認，ACE ${r.lesson.grade(r)} 級資格通過。${Math.round(Math.max(0,r.me.hp))} 耐久帶回來了。這次由你領航。` : '先修正結算裡的一個決策，再飛同一個開局。我還在你的頻道上。' };
  },
};

// Small, pure HUD readouts: action + measured evidence + next correction.
// These never drive controls, alter an AI decision, consume RNG or award a pass.
export function lessonGuidance(r) {
  const id=r.phase?.id, v=fmt(r.kmh), bank=Math.round(r.bank), g=r.g.toFixed(1);
  const cue=(goal,readout,tip,state='neutral')=>({goal,readout,tip,state});
  switch(r.lesson.id) {
    case 'L01': {
      const target=id==='level'?null:r.d.target;
      const ok=Math.abs(r.gamma)<(target?3:2.5) && (target?Math.abs(r.alt-target)<120:Math.abs(r.bank)<10);
      return cue(target?`${id==='climb'?'爬升':'下降'}至 ${fmt(target)} m 並穩住`:'連續平飛 5 秒',
        `γ ${r.gamma.toFixed(1)}° · 坡度 ${bank}° · ${fmt(r.alt)}m`,
        ok?'FPM 穩住了；小幅修正就好':Math.abs(r.bank)>10?r.pick('放手讓飛控改平','反向滾轉修平；放手不會改平'):'先讓 FPM 回 0°，別只看機頭',ok?'good':'warn');
    }
    case 'L02': {
      const target={h090:90,h300:300,h015:15}[id]??0, err=wrapDeg(target-r.heading);
      const close=Math.abs(err)<20;
      return cue(`轉至 ${hdg3(target)}°，提早改平`,
        `${hdg3(r.heading)}° · 坡度 ${bank}° · ${g}G`,
        Math.abs(r.bank)>40 && r.g<1.4?'有坡度、缺升力：拉桿撐住高度':close?r.pick('接近航向，放手讓飛控改平','接近航向，反向滾轉改平'):r.pick('側推協調轉彎，注意高度','滾到坡度後橫向回中，持續拉桿'),close?'good':'neutral');
    }
    case 'L03': return cue(id==='accel'?'平飛加速至 1000 km/h':id==='decel'?'減速至 650 km/h':'連續定速 600–700 六秒',
      `${v}km/h · 油門 ${Math.round(r.me.controls.throttle*100)}% · ${r.me.controls.boost?'AB':'MIL'}`,
      id==='accel'?'滿油門＋AB；高度不能拿來換速度':id==='decel'?'關 AB、收油、按住 BRK':'看速度趨勢，小幅調油門',id==='hold' && r.kmh>=600 && r.kmh<=700?'good':'neutral');
    case 'L04': {
      const elapsed=Math.max(0.1,r.phaseT-(r.d.t0||0)), rate=(r.d.turned||0)/elapsed;
      const base=r.notes.fast;
      return cue(id==='band'?'調到綠菱形轉彎速度':id==='sustain'?`MIL 一圈 · 保留 ${r.tune.sustainV}km/h`:'滿桿 180°：比較轉率',
        `${v}km/h · ${g}G · ${rate.toFixed(1)}°/s`,
        id==='sustain'?(r.d.armed?'速度接近底線就減 G，別清空帳戶':'先加速至 750，現在 AB 可用'):base?`高速基準 ${base.dps.toFixed(1)}°/s；比較這一圈`:'先測高速基準，G 大不等於轉得快',r.inBestBand?'good':'neutral');
    }
    case 'L05': return cue(id==='dive'?'高度換速度：950 km/h':'速度換高度：保留 400 km/h',
      `高度 ${fmt(r.alt)} + 動能 ${fmt(r.energyHeight-r.alt)} = ${fmt(r.energyHeight)}m`,
      id==='dive'?'兩種餘額互換；2200m 是安全底線':`${g}G · 目標 ${fmt(r.d.target)}m；平順拉起`,r.g>6.5?'warn':'neutral');
    case 'L06': return cue(id==='slowturn'?'低速轉彎：守住 300 km/h':id==='stall'?'卸載、加速，再改平':'立即俯衝改出',
      `${v}km/h · 可用 ${r.availG.toFixed(1)}G · ${fmt(r.alt)}m`,
      id==='dive'?'收油、BRK、拉滿；別等字幕':id==='stall'?'先推桿卸載；速度回來再拉':'淺坡度、輕拉，別把速度拉光',id==='dive'||r.kmh<350?'warn':'neutral');
    case 'L07': {
      const geo=geometry(r.me,r.foe), type=pursuitType(r.me,r.foe).toUpperCase();
      const rush=geo.R<1500 && geo.closure>35 && geo.R/geo.closure<7;
      return cue(id==='lead'?'機頭 W 對橘圈，保持 1.5 秒':'留在尾後控制區 12 秒',
        `${type} · ${fmt(geo.R)}m · 接近 ${Math.round(geo.closure*KMH)}km/h`,
        rush?'接近太快：收油、BRK、改 LAG':id==='lead'?'橘圈是提前量，不是目標本體':geo.R>1400?'遠了用 LEAD 收距；近了再控接近率':'PURE 可跟隨；別一直追它現在的位置',rush?'warn':geo.R>=450&&geo.R<=1400&&geo.aot<45?'good':'neutral');
    }
    case 'L08': {
      const geo=geometry(r.me,r.foe);
      if(id==='guns') {
        const e=gunError(r.me,gunLead(r.me,r.foe.pos,r.foe.vel).point)/DEG;
        return cue('機砲 12 發命中 · 45 秒',`${r.d.gunHits}/12 · ${fmt(geo.R)}m · 提前量誤差 ${e.toFixed(1)}°`,
          e<2&&geo.R<850?'提前量到位：短按 GUN':'機頭 W 對橘圈；別瞄目標本體',e<2&&geo.R<850?'good':'warn');
      }
      const aspect=Math.PI-angleBetween(forwardOf(r.foe.q),scale(norm(sub(r.foe.pos,r.me.pos)),-1));
      const pk=r.me.lock.locked?missilePk({R:geo.R,ata:geo.ata*DEG,aspect,mySpeed:r.me.speed,tgSpeed:r.foe.speed,tgG:r.foe.nCur}):0;
      return cue('飛彈命中一次',`${fmt(geo.R)}m · ${r.me.lock.locked?'LOCK':'未鎖定'} · Pk ${pk.toFixed(2)}`,
        pk>0.45?'SHOOT 窗口已到：按 MSL':geo.R<450?'太近，先拉開再發射':'機頭對準目標，等 LOCK 與 SHOOT',pk>0.45?'good':'neutral');
    }
    case 'L09': {
      if(id==='reverse') {const geo=geometry(r.me,r.foe);return cue('逼過頭，再咬尾 3 秒',`${fmt(geo.R)}m · 尾後 ${r.d.held.toFixed(1)}/3s`,
        geo.ata>90?'朝追兵急轉；必要時 BRK 控接近率':'它到前面了：反轉追 LEAD');}
      const missile=r.match.missiles.find(m=>m.alive&&m.target===r.me);
      if(!missile)return cue('三枚來襲：讀距離，不背倒數',`已發射 ${r.d.launched}/3 · 命中 ${r.d.hits}/1`,'保持速度與高度，掃描 MISSILE 警告');
      const rel=sub(missile.pos,r.me.pos), distance=len(rel), closing=-dot(sub(missile.vel,r.me.vel),norm(rel));
      return cue('飛彈防禦 · 本遊戲模型窗口',`${(distance/1000).toFixed(1)}km · 接近估計 ${closing>1?(distance/closing).toFixed(1)+'s':'拉開中'} · FLR ${r.me.flares}`,
        distance<550?r.pick('近了！向側面推滿','近了！側向滾轉、拉滿'):distance<2600&&r.me.flares?'可投 FLR；同時準備側向機動':'看來襲方向，保留最後的機動',distance<550?'warn':'neutral');
    }
    case 'L10': return cue('ACE 考核：擊落或耐久判勝',`我 HP ${Math.round(r.me.hp)} · 敵 HP ${Math.round(r.foe.hp)}`,'S 目標：耐久 ≥70、150 秒內；自主決策');
    default:return null;
  }
}

export const LESSONS = [L01, L02, L03, L04, L05, L06, L07, L08, L09, L10];
for (const lesson of LESSONS) lesson.guidance=lessonGuidance;
export const lessonById = (id) => LESSONS.find((l) => l.id === id);
export { gatePhase, pointAhead };
