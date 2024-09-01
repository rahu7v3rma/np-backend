import { createContext, useContext } from 'react';

import { NPConfig } from '@/types/config';

const NPConfigContext = createContext<{
  config: NPConfig | undefined;
}>({ config: undefined });

const NPConfigProvider = NPConfigContext.Provider;

const useNPConfig = () => {
  const { config } = useContext(NPConfigContext);
  return { config };
};

export { NPConfigProvider, useNPConfig };
