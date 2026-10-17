// Intercepted bandit radio. Pre-written lines keyed by the AI's real decisions, so the
// player can *hear* what the opponent is doing (no runtime text generation).
const LINES = {
  ENGAGE: ['目標確認，接戰。', '找到你了。', '高度優勢，從上方切入。', '正面過來了……看誰先眨眼。'],
  ATTACK: ['咬住了。', '在我機頭前，別想跑。', '進入射擊位置。', '收緊轉彎……'],
  DEFEND: ['他在我六點！', '被咬住了，破解右轉！', '甩不掉……再拉！', '別讓他對準。'],
  EVADE: ['飛彈來襲！', '飛彈！側轉閃避！', '警報！極限迴避！'],
  EXTEND: ['拉開距離，重整。', '速度不夠，先脫離。', '後燃器全開，拉開。'],
  reversal: ['衝過頭了吧？換我了。', '反轉，咬回去！', '好，位置交換。'],
  hit: ['被打中了……還能飛！', '可惡，中彈！', '損傷警告……繼續戰鬥。'],
  fox2: ['飛彈發射！', 'Fox two！', '發射！'],
  pressure: ['先逼他轉彎。', '這一發只是招呼。', '牽制射擊！'],
  flare: ['熱焰彈！', '投放熱焰彈！'],
  dodged: ['太慢了。', '就這樣？', '閃掉了。'],
  stale_vertical: ['往上拉——跟得上嗎？', '轉圈沒意思，上垂直面。'],
  stale_reverse: ['剪刀機動，來啊。', '反向！'],
  stale_extend: ['這樣兜圈沒完沒了，重來。', '脫離，重新進場。'],
  win: ['擊落目標。', '……結束了。'],
  lose: ['彈射——！', '不可能……'],
};

export function pickLine(key, rng = Math.random) {
  const list = LINES[key];
  if (!list) return null;
  return list[Math.floor(rng() * list.length) % list.length];
}
