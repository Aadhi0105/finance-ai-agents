import { createElement as h } from 'react';

export const chartStyles = [
  { color: '#315f4c', dash: '', shape: 'circle' }, { color: '#977039', dash: '8 5', shape: 'square' },
  { color: '#476b91', dash: '2 4', shape: 'diamond' }, { color: '#855c78', dash: '9 3 2 3', shape: 'triangle' },
] as const;

export function ChartMark({ index,x,y,size=4 }:{index:number;x:number;y:number;size?:number}) {
  const style=chartStyles[index%chartStyles.length],props={fill:'#fff',stroke:style.color,strokeWidth:2};
  return style.shape==='square'?h('rect',{x:x-size,y:y-size,width:size*2,height:size*2,...props})
    :style.shape==='diamond'?h('path',{d:`M${x},${y-size-1}l${size+1},${size+1}l${-size-1},${size+1}l${-size-1},${-size-1}Z`,...props})
    :style.shape==='triangle'?h('path',{d:`M${x},${y-size-1}l${size+1},${size*2+1}h${-size*2-2}Z`,...props})
    :h('circle',{cx:x,cy:y,r:size,...props});
}
