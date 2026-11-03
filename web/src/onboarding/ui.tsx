import React,{useEffect,useState} from 'react';
import {Icon} from '../icons';
import {classificationLabels,safeError} from './data';
import type {Classification} from '../workspace-types';
export const when=(v:string)=>new Date(v).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'});
export const versionHref=(d:string,v:string)=>`#/inputs/${d}/versions/${v}`;
export function useRead<T>(load:()=>Promise<T>,key:string){const [value,setValue]=useState<T|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(true),[attempt,setAttempt]=useState(0);useEffect(()=>{let live=true;setBusy(true);setError('');setValue(null);void load().then(v=>{if(live)setValue(v);}).catch(e=>{if(live)setError(safeError(e).message);}).finally(()=>{if(live)setBusy(false);});return()=>{live=false;};},[key,attempt]);return {value,error,busy,reload:()=>setAttempt(n=>n+1)};}
export function Alert({children}:{children:React.ReactNode}){return <div className="private-alert" role="alert">{children}</div>;}
export function ClassBadge({value}:{value:Classification}){return <span className={'private-chip classification-'+value}>{classificationLabels[value]}</span>;}
export function Empty({title,children}:{title:string;children:React.ReactNode}){return <div className="private-empty"><Icon name="evidence" size={28}/><h2>{title}</h2><p>{children}</p></div>;}
export function Heading({eyebrow,title,children}:{eyebrow:string;title:string;children?:React.ReactNode}){return <div className="private-heading"><p className="eyebrow">{eyebrow}</p><h1 tabIndex={-1} data-page-heading>{title}</h1>{children&&<p>{children}</p>}</div>;}
export function Pagination({next,previous,busy,onNext,onPrevious}:{next:string|null;previous:boolean;busy:boolean;onNext:()=>void;onPrevious:()=>void}){return <div className="private-pagination"><button className="text-button" disabled={!previous||busy} onClick={onPrevious}>← Previous page</button><span>Up to 25 records per page</span><button className="text-button" disabled={!next||busy} onClick={onNext}>Next page →</button></div>;}
