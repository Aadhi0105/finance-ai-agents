import {lazy,Suspense,type ComponentProps} from 'react';
import type {NativeReportReader} from './NativeReportReader';

const Reader=lazy(()=>import('./NativeReportReader').then(module=>({default:module.NativeReportReader})));

/** Keep report charts and review tools out of the initial connection screen. */
export function ReportReader(props:ComponentProps<typeof NativeReportReader>){
  return <Suspense fallback={<section className="nr-load" role="status" aria-busy="true"><h1>Opening the saved report…</h1><p>Loading its reader and review tools.</p></section>}><Reader {...props}/></Suspense>;
}
