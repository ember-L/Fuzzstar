import Svg, { Path } from 'react-native-svg';
import { icons, type IconName } from './icons';

// Figma 导出的描边图标；颜色由调用方按状态传入（选中 #A34400 / 未选中 #805535 等）。
export function Icon({ name, size = 24, color, strokeWidth }: {
  name: IconName; size?: number; color: string; strokeWidth?: number;
}) {
  const def = icons[name];
  return (
    <Svg width={size} height={size} viewBox={def.viewBox}>
      {def.paths.map((p, i) => (
        <Path
          key={i}
          d={p.d}
          transform={`translate(${p.x}, ${p.y})`}
          stroke={color}
          strokeWidth={strokeWidth ?? p.strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      ))}
    </Svg>
  );
}

export type { IconName };
