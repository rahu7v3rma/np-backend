import { NPConfig } from '@/types/config';

export declare global {
  interface Window {
    NPConfig?: NPConfig;
  }
}
