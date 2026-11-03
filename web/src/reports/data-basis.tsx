import {createContext} from 'react';
import type {Classification} from '../workspace-types';
export const EvidenceClass=createContext<Classification>('synthetic');
