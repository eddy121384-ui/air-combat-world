// Adapt device-specific wording only; never touch a lesson judge or sim state.
export function controlText(text, device) {
  if(device!=='tilt')return text;
  return text.replaceAll('放手','回到校準握姿').replaceAll('搖桿回中','體感回中')
    .replaceAll('搖桿往前推','手機向前傾').replaceAll('搖桿往它那邊推到底','手機向它那邊傾到底')
    .replaceAll('搖桿推到底','手機傾至滿量').replaceAll('搖桿推越多','手機傾得越多');
}
