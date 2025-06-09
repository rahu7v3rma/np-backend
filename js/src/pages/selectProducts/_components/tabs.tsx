import React, { useState } from 'react';

import ProductsGrid from './productsGrid';

type Props = {
  tabs: [];
  organizationId: number;
};

interface Tab {
  id: number;
  label: string;
  key: number;
  idx: number;
  budget: number;
  company_cost: number;
  default_discount: string;
}

const Tab = ({ tabs, organizationId }: Props) => {
  const [activeTab, setActiveTab] = useState(0);

  const handleButtonClick = (
    event: React.SyntheticEvent<HTMLButtonElement>,
    index: number,
  ) => {
    event.preventDefault();
    setActiveTab(index);
  };

  return (
    <>
      {tabs.length > 1 && (
        <div className="flex bg-gray-100 overflow-x-auto">
          {tabs.map((tab: Tab, index: number) => (
            <button
              key={index}
              className={`flex-1 py-2 px-4 ${
                activeTab === index
                  ? 'bg-primary text-white-800'
                  : 'bg-gray-200 text-gray-600'
              } focus:outline-none border-l border-r border-gray-950`}
              onClick={(event) => handleButtonClick(event, index)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}
      {tabs.map((tab: Tab, index: number) => (
        <div
          key={tab.idx}
          className={`${activeTab === index ? 'block' : 'hidden'} h-full overflow-y-scroll`}
        >
          <ProductsGrid
            key={tab.key}
            formId={tab.idx}
            organizationId={organizationId}
            budget={tab.budget}
            company_cost={tab.company_cost}
            default_discount={tab.default_discount}
            allTabs={tabs}
          />
        </div>
      ))}
    </>
  );
};

export default Tab;
