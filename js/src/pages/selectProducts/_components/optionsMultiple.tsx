import { Listbox, Transition } from '@headlessui/react';
import { CheckIcon, ChevronUpDownIcon } from '@heroicons/react/20/solid';
import { Fragment, useEffect, useState } from 'react';

function classNames(...classes: string[]) {
  return classes.filter(Boolean).join(' ');
}

interface Props {
  onChangeValue: (value: { id: number; name: string }[]) => void;
  data: {
    id: number;
    name: string;
  }[];
  style?: string;
  translate?: boolean;
}
export default function OptionsMultiple({
  onChangeValue,
  data,
  style,
  translate,
}: Props) {
  const [selected, setSelected] = useState<{ id: number; name: string }[]>([]);

  useEffect(() => {
    onChangeValue(selected);
  }, [onChangeValue, selected]);

  return (
    <Listbox value={selected} onChange={setSelected} multiple>
      {({ open }: { open: boolean }) => (
        <>
          <div className={classNames('relative mt-2', style || '')}>
            <Listbox.Button className="relative w-full cursor-default rounded-md bg-white py-1.5 pl-3 pr-3 text-left text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 sm:text-sm sm:leading-6">
              <span className="flex items-center">
                <span className="ml-3 block truncate">
                  {selected.length > 0
                    ? selected.map((item) => item.name).join(', ')
                    : '----'}
                </span>
              </span>
              <span className="pointer-events-none absolute inset-y-0 right-0 ml-3 flex items-center pr-2">
                <ChevronUpDownIcon
                  className="h-5 w-5 text-gray-400"
                  aria-hidden="true"
                />
              </span>
            </Listbox.Button>

            <Transition
              show={open}
              as={Fragment}
              leave="transition ease-in duration-100"
              leaveFrom="opacity-100"
              leaveTo="opacity-0"
            >
              <Listbox.Options
                className={`absolute ${translate ? '-translate-y-full' : ''} overflow-scroll z-10 mt-1 max-h-40 w-full rounded-md bg-white py-1 text-base shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none sm:text-sm`}
              >
                {data.map((element) => (
                  <Listbox.Option
                    key={element.id}
                    className={({ active }: { active: boolean }) =>
                      classNames(
                        active ? 'bg-indigo-600 text-white' : 'text-gray-900',
                        'relative cursor-default select-none py-2 pl-3 pr-9',
                      )
                    }
                    value={element}
                  >
                    {({
                      selected,
                      active,
                    }: {
                      selected: boolean;
                      active: boolean;
                    }) => (
                      <>
                        <div className="flex items-center">
                          <span
                            className={classNames(
                              selected ? 'font-semibold' : 'font-normal',
                              'ml-3 block truncate',
                            )}
                          >
                            {element.name}
                          </span>
                        </div>

                        {selected ? (
                          <span
                            className={classNames(
                              active ? 'text-white' : 'text-indigo-600',
                              'absolute inset-y-0 right-0 flex items-center pr-4',
                            )}
                          >
                            <CheckIcon className="h-5 w-5" aria-hidden="true" />
                          </span>
                        ) : null}
                      </>
                    )}
                  </Listbox.Option>
                ))}
              </Listbox.Options>
            </Transition>
          </div>
        </>
      )}
    </Listbox>
  );
}
