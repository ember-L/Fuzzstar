// 90 天体重趋势折线（F08-2，P1）：react-native-svg，无额外图表依赖。
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Polyline, Text as SvgText } from 'react-native-svg';
import { trendRange } from '../lib/weight';
import { colors } from '../theme';

export interface TrendPoint {
  weight_kg: number;
  measured_at: string;
}

function parse(iso: string): number {
  return Date.parse(/Z|[+-]\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`);
}

function dayLabel(ms: number): string {
  const date = new Date(ms);
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

const W = 320;
const H = 170;
const PAD_X = 34;
const PAD_TOP = 16;
const PAD_BOTTOM = 26;

export function TrendChart({ points }: { points: TrendPoint[] }) {
  if (points.length === 0) {
    return <Text style={styles.empty}>暂无体重记录，先在上面记一笔吧。</Text>;
  }
  const { minKg, maxKg } = trendRange(points);
  const times = points.map(point => parse(point.measured_at));
  const t0 = times[0];
  const t1 = times[times.length - 1];
  const innerW = W - PAD_X - 12;
  const innerH = H - PAD_TOP - PAD_BOTTOM;
  const coords = points.map((point, index) => {
    const x = t1 === t0 ? PAD_X + innerW / 2 : PAD_X + ((times[index] - t0) / (t1 - t0)) * innerW;
    const y = PAD_TOP + ((maxKg - point.weight_kg) / (maxKg - minKg)) * innerH;
    return { x, y };
  });
  const polyline = coords.map(coord => `${coord.x.toFixed(1)},${coord.y.toFixed(1)}`).join(' ');
  return (
    <View accessibilityLabel={`近 90 天体重趋势，共 ${points.length} 个记录点，范围 ${minKg} 到 ${maxKg} 公斤`}>
      <Svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H}>
        <SvgText x={2} y={PAD_TOP + 4} fontSize={10} fill={colors.secondary}>{maxKg}kg</SvgText>
        <SvgText x={2} y={PAD_TOP + innerH} fontSize={10} fill={colors.secondary}>{minKg}kg</SvgText>
        {points.length > 1 ? <Polyline points={polyline} fill="none" stroke={colors.brand} strokeWidth={2} /> : null}
        {coords.map((coord, index) => <Circle key={index} cx={coord.x} cy={coord.y} r={3} fill={colors.brand} />)}
        <SvgText x={PAD_X} y={H - 8} fontSize={10} fill={colors.secondary}>{dayLabel(t0)}</SvgText>
        {t1 !== t0 ? <SvgText x={W - 12} y={H - 8} fontSize={10} fill={colors.secondary} textAnchor="end">{dayLabel(t1)}</SvgText> : null}
      </Svg>
      {points.length === 1 ? <Text style={styles.empty}>再记一笔即可看到趋势变化。</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  empty: { fontSize: 13, lineHeight: 20, color: colors.secondary, marginTop: 4 },
});
