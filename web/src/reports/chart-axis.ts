import type { ChartData } from './analysis-types';
import { formatMetric } from './format.ts';
import { pointMetric } from './report-data.ts';

/** Compact axis labels only; source values remain exact in inspection and tables. */
export function chartAxisLabel(chart:ChartData,value:string) {
  const formatted=formatMetric(pointMetric(chart,{id:'axis',label:'',x:'',y:value,evidence_refs:[],reason_codes:[]}),true);
  const label=chart.y_axis.currency?formatted.replace(chart.y_axis.currency+' ','').replace(' / share',''):formatted;
  const number=Number(value)*(chart.y_axis.unit==='fraction'?100:1);
  return label.length>11||number!==0&&/^−?0\.00[%×]?$/.test(label)
    ?number.toExponential(1)+(chart.y_axis.unit==='fraction'?'%':chart.y_axis.unit==='multiple'?'×':''):label;
}
