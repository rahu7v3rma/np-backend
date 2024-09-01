import { FunctionComponent, useEffect, useState } from 'react';
import { ErrorBoundary } from 'react-error-boundary';

import { NPConfigProvider } from '@/contexts/npConfig';
import SelectProducts from '@/pages/selectProducts';
import { NPConfig } from '@/types/config';

import './main.css';

const App: FunctionComponent = () => {
  const [npConfig, setNPConfig] = useState<NPConfig | undefined>(undefined);

  useEffect(() => {
    setNPConfig(window.NPConfig);
  }, []);

  return (
    <ErrorBoundary fallback={<p>An unknown error has occurred</p>}>
      <NPConfigProvider value={{ config: npConfig }}>
        <SelectProducts />
      </NPConfigProvider>
    </ErrorBoundary>
  );
};

export default App;
