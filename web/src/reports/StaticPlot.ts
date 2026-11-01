/** The reading copy renders the same saved geometry as the interactive reader. */
import { createElement as h } from 'react';
import type { ChartData } from './analysis-types';
import { datasetRows } from './report-data.ts';
import { bridgeColor,plotGeometry,tickIndices } from './chart-layout.ts';
import { ChartMark,chartStyles } from './chart-styles.ts';
import { chartAxisLabel } from './chart-axis.ts';

export function StaticPlot({chart}:{chart:ChartData}) {
  const rows=datasetRows(chart),g=plotGeometry(chart,rows,900);
  if(g.reason||!rows.length)return h('p',null,(chart.availability==='withheld'?'Values withheld':'No graphical values available')+'. '+chart.reason_codes.join(', '));
  const series=g.series.map(({index,segments},visibleIndex)=>{
    const style=chartStyles[index%chartStyles.length];
    const marks=g.kind==='line'?segments.map((segment,i)=>h('g',{key:i},
      h('polyline',{fill:'none',stroke:style.color,strokeWidth:2,strokeDasharray:style.dash,points:segment.map(p=>p.x+','+p.y).join(' ')}),
      segment.length===1?h(ChartMark,{index,x:segment[0].x,y:segment[0].y}):null))
      :segments.flat().map(p=>{
        if(g.kind==='dot')return h(ChartMark,{key:p.row,index,x:p.x,y:p.y});
        const band=(g.right-g.left)/Math.max(1,rows.length),barWidth=Math.min(40,band*.6/g.series.length);
        const x=p.x+(visibleIndex-(g.series.length-1)/2)*barWidth,base=g.kind==='waterfall'?p.startY!:g.zero;
        const color=g.kind==='waterfall'?bridgeColor(p.assessment):style.color;
        return h('g',{key:p.row},h('rect',{x:x-barWidth/2,width:barWidth,y:Math.min(p.y,base),height:Math.abs(p.y-base),fill:color}),
          p.y===base?h('line',{x1:x-barWidth/2,x2:x+barWidth/2,y1:p.y,y2:p.y,stroke:color,strokeWidth:2}):null);
      });
    return h('g',{key:chart.series[index].id,'data-series-id':chart.series[index].id,'data-plot-kind':g.kind},...marks);
  });
  const unit=chart.y_axis.currency?chart.y_axis.currency+(chart.y_axis.unit==='currency_per_share'?' per share':''):
    ({fraction:'percent (saved fractions)',multiple:'multiples (×)',index:'index points',score:'score',count:'count',p_value:'p-value'} as Record<string,string>)[chart.y_axis.unit]||chart.y_axis.unit;
  return h('figure',{className:'nr-copy-figure'},
    h('div',{className:'nr-copy-plot-scroll',role:'region','aria-label':chart.title+' static plot',tabIndex:0},
      h('svg',{className:'nr-copy-plot',viewBox:`0 0 ${g.width} ${g.height}`,role:'img','aria-label':chart.title+' · complete saved series; exact values follow'},
        h('title',null,chart.title),
        ...g.ticks.map(t=>h('g',{key:t.value},h('line',{x1:g.left,x2:g.right,y1:t.y,y2:t.y,stroke:'#d8dfd5'}),h('text',{x:g.left-8,y:t.y+4,textAnchor:'end'},chartAxisLabel(chart,t.value)))),
        (g.kind==='bar'||g.kind==='waterfall')?h('line',{x1:g.left,x2:g.right,y1:g.zero,y2:g.zero,stroke:'#385d49'}):null,
        ...series,
        ...tickIndices(g.xs,900).map(i=>h('text',{key:i,x:g.xs[i],y:g.bottom+20,textAnchor:i===0?'start':i===rows.length-1?'end':'middle'},
          g.kind==='waterfall'?(rows[i].points[0]?.assessment==='anchor'?rows[i].label:'Step '+rows[i].x):rows[i].x.length>18?rows[i].x.slice(0,17)+'…':rows[i].x)),
        h('text',{x:(g.left+g.right)/2,y:g.height-4,textAnchor:'middle'},chart.x_axis.label))),
    h('figcaption',null,h('p',null,'Values in '+unit+'. Axes use compact labels; exact values follow in the complete table.'),
      g.kind==='waterfall'?h('p',null,'Blue-grey: anchors. Green: favourable. Rust: adverse. Every saved assessment is also written in the table.')
        :h('ul',{className:'nr-copy-chart-legend','aria-label':chart.title+' series'},...chart.series.map((s,i)=>h('li',{key:s.id},
          h('svg',{width:29,height:15,viewBox:'0 0 29 15','aria-hidden':true},h('path',{d:'M1 7.5h27',stroke:chartStyles[i%chartStyles.length].color,strokeWidth:2,strokeDasharray:chartStyles[i%chartStyles.length].dash}),h(ChartMark,{index:i,x:14,y:7.5,size:3})),s.label+(s.points.some(p=>p.y!==null)?'':' · no usable saved points')))),
      g.kind==='dot'?h('p',null,'Separate saved observations; no fitted path, probability interval or distribution is drawn.'):null));
}
