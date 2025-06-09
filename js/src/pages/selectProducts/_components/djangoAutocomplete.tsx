import { useState } from 'react';
import Select from 'react-select';

interface optionType {
  value: string;
  label: string;
}

interface Props {
  onValueChange?: (val: optionType) => void;
  onValuesChange?: (val: [optionType]) => void;
  linkPath: string;
  isMulti?: boolean;
  translate?: boolean;
}

const DjangoAutocomplete = ({
  onValueChange,
  onValuesChange,
  linkPath,
  translate = false,
  isMulti = false,
}: Props) => {
  const [selectedValue, setSelectedValue] = useState<
    optionType | [optionType] | null
  >(null);
  const [options, setOptions] = useState([]);

  const handleInputChange = (inputValue: string) => {
    // Fetch options from Django autocomplete endpoint
    fetch(`${linkPath}?q=${inputValue}`)
      .then((response) => response.json())
      .then((data) => {
        const formattedOptions = data.results.map(
          (item: { id: string; text: string }) => ({
            value: item.id,
            label: item.text,
          }),
        );
        setOptions(formattedOptions);
      });
  };

  const handleChange = (selectedOption: optionType | [optionType]) => {
    setSelectedValue(selectedOption);
    if (isMulti) {
      onValuesChange && onValuesChange(selectedOption as [optionType]);
      return;
    }
    onValueChange && onValueChange(selectedOption as optionType);
    // You can perform additional actions here
  };

  const handleFocus = () => {
    if (!selectedValue) {
      handleInputChange('');
    }
  };

  return (
    <Select
      isMulti={isMulti}
      value={selectedValue}
      onChange={handleChange}
      onInputChange={handleInputChange}
      options={options}
      isClearable
      placeholder="Search..."
      noOptionsMessage={() => 'Type to search'}
      onFocus={handleFocus}
      className={`${translate ? 'mb-6' : ''}`}
    />
  );
};

export default DjangoAutocomplete;
