import { NPConfig } from '@/types/config';

export const extractFromNpConfig = (
  config: NPConfig | undefined,
  attribute: string,
): { id: number; name: string }[] | string | null => {
  return config?.data
    ? JSON.parse(config?.data.replace(/&quot;/g, '"') || '{}')[attribute] ||
        null
    : null;
};
