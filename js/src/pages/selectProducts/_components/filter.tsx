import Tooltip, { TooltipRef } from 'rc-tooltip';
import raf from 'rc-util/lib/raf';
import {
  ReactElement,
  useCallback,
  useEffect,
  useRef,
  useMemo,
  useState,
} from 'react';
import { useErrorBoundary } from 'react-error-boundary';

import { useNPConfig } from '@/contexts/npConfig';
import { getCatgoriesSuppliersTags } from '@/services/api';
import { extractFromNpConfig } from '@/utils/config';

import Loader from './loader';
import Options from './options';

import 'rc-slider/assets/index.css';
import 'rc-tooltip/assets/bootstrap.css';

const emptyOption = [{ id: 0, name: '----' }];
export type typeEmptyOption = (typeof emptyOption)[0];

const GooglePriceTooltip = (props: {
  value: number;
  children: ReactElement;
  visible: boolean;
  tipFormatter?: (value: number) => React.ReactNode;
}) => {
  const { value, children, visible, ...restProps } = props;
  const tooltipRef = useRef<TooltipRef>(null);
  const rafRef = useRef<number | null>(null);
  const cancelKeepAlign = useCallback(() => {
    raf.cancel(rafRef.current!);
  }, []);
  const keepAlign = useCallback(() => {
    rafRef.current = raf(() => {
      tooltipRef.current?.forceAlign();
    });
  }, []);
  useEffect(() => {
    if (visible) keepAlign();
    else cancelKeepAlign();
    return cancelKeepAlign;
  }, [value, visible, cancelKeepAlign, keepAlign]);
  return (
    <Tooltip
      placement="top"
      overlay={value}
      overlayInnerStyle={{ minHeight: 'auto' }}
      ref={tooltipRef}
      visible={true}
      {...restProps}
    >
      {children}
    </Tooltip>
  );
};

export const GooglePriceHandle: SliderProps['handleRender'] = (node, props) => (
  // eslint-disable-next-line react/prop-types
  <GooglePriceTooltip value={props.value} visible={props.dragging}>
    {node}
  </GooglePriceTooltip>
);

interface Tab {
  id: number;
  idx: number;
  key: number;
  label: string;
  budget: number;
  selectedProductIds?: number[];
}
interface Product {
  id: number;
  name: string;
  images: { image: string }[];
  brand: { name: string };
  supplier: { name: string };
  total_cost: number;
  calculated_price: number;
}

type ProductIds = number;
type Products = Product;

interface Props {
  applyFilter: (
    priceMin?: number,
    priceMax?: number,
    organizationPriceMin?: number,
    organizationPriceMax?: number,
    profitMin?: number,
    profitMax?: number,
    brandId?: number,
    categoryId?: number,
    supplierId?: number,
    tagId?: number,
    employeeGroupId?: number,
    productKind?: string,
    quickOfferId?: number,
    query?: string,
    selected?: boolean,
    googlePriceMin?: number,
    googlePriceMax?: number,
  ) => void;
  budget: number;
  selectedProductIds: ProductIds[];
  products: Products[];
  baseSPAAssetsUrl?: string;
  handleRemoveProduct: (id: number) => void;
  handleSelectAllProducts: (e: React.SyntheticEvent<HTMLButtonElement>) => void;
  selectedEmpGroups?: Tab[];
  selectAll?: boolean;
}

const Filter = ({
  applyFilter,
  budget,
  selectedProductIds,
  products,
  baseSPAAssetsUrl,
  handleRemoveProduct,
  handleSelectAllProducts,
  selectedEmpGroups,
  selectAll,
}: Props) => {
  const { showBoundary } = useErrorBoundary();
  const { config } = useNPConfig();

  const [loading, setLoading] = useState<boolean>(true);
  const [priceMin, setPriceMin] = useState<number | undefined>(undefined);
  const [priceMax, setPriceMax] = useState<number | undefined>(undefined);
  const [organizationPriceMin, setOrganizationPriceMin] = useState<
    number | undefined
  >(undefined);
  const [organizationPriceMax, setOrganizationPriceMax] = useState<
    number | undefined
  >(undefined);
  const [profitMin, setProfitMin] = useState<number | undefined>(undefined);
  const [profitMax, setProfitMax] = useState<number | undefined>(undefined);
  const [brands, setBrands] = useState([...emptyOption]);
  const [suppliers, setSuppliers] = useState([...emptyOption]);
  const [categories, setCategories] = useState([...emptyOption]);
  const [tags, setTags] = useState([...emptyOption]);
  const [brandId, setBrandId] = useState<number | undefined>(undefined);
  const [supplierId, setSupplierId] = useState<number | undefined>(undefined);
  const [categoryId, setCategoryId] = useState<number | undefined>(undefined);
  const [tagId, setTagId] = useState<number | undefined>(undefined);
  const [query, setQuery] = useState<string | undefined>(undefined);
  const [giftsInBudget, setGiftsInBudget] = useState<boolean>(false);
  const [selectedProducts, setSelectedProducts] = useState<boolean>(false);
  const [employeeGroups, setEmployeeGroups] = useState([...emptyOption]);
  const [employeeGroupId, setEmployeeGroupId] = useState<number | undefined>(
    undefined,
  );
  const [productKind, setProductKind] = useState<string | undefined>(undefined);
  const [quickOfferId, setQuickOfferId] = useState<number | undefined>(
    undefined,
  );
  const [googlePriceMin, setGooglePriceMin] = useState<number | undefined>(
    undefined,
  );
  const [googlePriceMax, setGooglePriceMax] = useState<number | undefined>(
    undefined,
  );
  useEffect(() => {
    selectedEmpGroups?.forEach((each) => {
      // Check if selectedProductIds is not empty
      if (each.selectedProductIds && each.selectedProductIds.length > 0) {
        setEmployeeGroups((prevGroups) => [
          ...prevGroups,
          { id: each.id, name: each.label }, // Add only id and label
        ]);
      }
    });
  }, [selectedEmpGroups]);

  useEffect(() => {
    setLoading(true);
    getCatgoriesSuppliersTags()
      .then((data) => {
        setSuppliers([
          ...emptyOption,
          ...(data?.suppliers as typeof suppliers),
        ]);
        setCategories([
          ...emptyOption,
          ...(data?.categories as typeof categories),
        ]);
        setTags([...emptyOption, ...(data?.tags as typeof tags)]);
        setBrands([...emptyOption, ...(data?.brands as typeof brands)]);
        setLoading(false);
      })
      .catch((err) => showBoundary(err));
  }, [showBoundary]);

  const productKindOptions = [
    { id: 0, name: '----' },
    { id: 1, name: 'PHYSICAL' },
    { id: 2, name: 'MONEY' },
    { id: 3, name: 'BUNDLE' },
    { id: 4, name: 'VARIATION' },
  ];

  const onApplyFilter = useCallback(() => {
    let hasError = false;
    if (priceMin && priceMin < 0) {
      alert('Minimum price should be greater than 0');
      setPriceMin(undefined);
      hasError = true;
    }
    if (priceMax && priceMax < 0) {
      alert('Maximum price should be greater than 0');
      setPriceMax(undefined);
      hasError = true;
    }
    if (organizationPriceMin && organizationPriceMin < 0) {
      alert('Minimum price should be greater than 0');
      setOrganizationPriceMin(undefined);
      hasError = true;
    }
    if (organizationPriceMax && organizationPriceMax < 0) {
      alert('Maximum price should be greater than 0');
      setOrganizationPriceMax(undefined);
      hasError = true;
    }

    if (profitMin && profitMin < 0) {
      alert('Minimum profit should be greater than 0');
      setProfitMin(undefined);
      hasError = true;
    }
    if (profitMax && profitMax < 0) {
      alert('Maximum profit should be greater than 0');
      setProfitMax(undefined);
      hasError = true;
    }

    if (priceMin && priceMax) {
      if (priceMin > priceMax) {
        alert(`minimum price should be less then ` + priceMax);
        setPriceMin(undefined);
        hasError = true;
      } else if (priceMin > priceMax) {
        alert(`maximum price should be greater then ` + priceMin);
        setPriceMax(undefined);
        hasError = true;
      }
    }

    if (profitMin && profitMax) {
      if (profitMin > profitMax) {
        alert(`minimum profit should be less then ` + profitMax);
        setProfitMin(undefined);
        hasError = true;
      }
    }

    if (organizationPriceMin && organizationPriceMax) {
      if (organizationPriceMin > organizationPriceMax) {
        alert(`minimum price should be less then ` + organizationPriceMax);
        setOrganizationPriceMin(undefined);
        hasError = true;
      } else if (organizationPriceMin > organizationPriceMax) {
        alert(`maximum price should be greater then ` + organizationPriceMin);
        setOrganizationPriceMax(undefined);
        hasError = true;
      }
    }

    if (!hasError) {
      applyFilter(
        priceMin,
        priceMax,
        organizationPriceMin,
        organizationPriceMax,
        profitMin,
        profitMax,
        brandId,
        supplierId,
        categoryId,
        tagId,
        employeeGroupId,
        productKind,
        quickOfferId,
        query,
        selectedProducts,
        googlePriceMin,
        googlePriceMax,
      );
    }
  }, [
    priceMin,
    priceMax,
    organizationPriceMin,
    organizationPriceMax,
    profitMin,
    profitMax,
    brandId,
    categoryId,
    supplierId,
    tagId,
    employeeGroupId,
    productKind,
    quickOfferId,
    query,
    selectedProducts,
    applyFilter,
    googlePriceMin,
    googlePriceMax,
  ]);

  const campaign_type = useMemo(
    () => extractFromNpConfig(config, 'type'),
    [config],
  );

  const quick_offers = useMemo(() => {
    const campaign_type = extractFromNpConfig(config, 'type');
    return campaign_type === 'campaign'
      ? [
          ...[{ id: 0, name: '----' }],
          ...(extractFromNpConfig(config, 'quick_offers') as {
            id: number;
            name: string;
          }[]),
        ]
      : [];
  }, [config]);

  return loading ? (
    <div className="m-auto">
      <Loader />
    </div>
  ) : (
    <div className="flex items-center flex-col">
      <div className=" bg-dj-admin-color-1 pt-7 pl-4 pr-4 rounded-2xl flex flex-col">
        <label className="block text-sm font-medium leading-6 text-gray-900">
          Total cost:
        </label>
        <div className="flex gap-2 mb-6">
          <input
            value={priceMin}
            onChange={(event) =>
              setPriceMin(
                Number(event.target.value) !== 0
                  ? Number(event.target.value)
                  : undefined,
              )
            }
            type="number"
            placeholder="min"
            className="block w-full rounded-md border-0 px-3.5 py-2 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-indigo-600 sm:text-sm sm:leading-6"
          />
          <input
            value={priceMax}
            onChange={(event) =>
              setPriceMax(
                Number(event.target.value) !== 0
                  ? Number(event.target.value)
                  : undefined,
              )
            }
            type="number"
            placeholder="max"
            className="block w-full rounded-md border-0 px-3.5 py-2 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-indigo-600 sm:text-sm sm:leading-6"
          />
        </div>
        <label className="block text-sm font-medium leading-6 text-gray-900">
          Organization price:
        </label>
        <div className="flex gap-2 mb-6">
          <input
            value={organizationPriceMin}
            onChange={(event) =>
              setOrganizationPriceMin(
                Number(event.target.value) !== 0
                  ? Number(event.target.value)
                  : undefined,
              )
            }
            type="number"
            placeholder="min"
            className="block w-full rounded-md border-0 px-3.5 py-2 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-indigo-600 sm:text-sm sm:leading-6"
          />
          <input
            value={organizationPriceMax}
            onChange={(event) =>
              setOrganizationPriceMax(
                Number(event.target.value) !== 0
                  ? Number(event.target.value)
                  : undefined,
              )
            }
            disabled={giftsInBudget}
            type="number"
            placeholder="max"
            className="block w-full rounded-md border-0 px-3.5 py-2 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-indigo-600 sm:text-sm sm:leading-6"
          />
        </div>
        <label className="block text-sm font-medium leading-6 text-gray-900">
          Profit Percentage:
        </label>
        <div className="flex gap-2 mb-6">
          <input
            value={profitMin}
            onChange={(event) =>
              setProfitMin(
                Number(event.target.value) !== 0
                  ? Number(event.target.value)
                  : undefined,
              )
            }
            type="number"
            placeholder="min"
            className="block w-full rounded-md border-0 px-3.5 py-2 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-indigo-600 sm:text-sm sm:leading-6"
          />
          <input
            value={profitMax}
            onChange={(event) =>
              setProfitMax(
                Number(event.target.value) !== 0
                  ? Number(event.target.value)
                  : undefined,
              )
            }
            type="number"
            placeholder="max"
            className="block w-full rounded-md border-0 px-3.5 py-2 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-indigo-600 sm:text-sm sm:leading-6"
          />
        </div>
        <label className="block text-sm font-medium leading-6 text-gray-900">
          Google price:
        </label>
        <div className="flex gap-2 mb-6">
          <input
            value={googlePriceMin}
            onChange={(event) =>
              setGooglePriceMin(
                Number(event.target.value) !== 0
                  ? Number(event.target.value)
                  : undefined,
              )
            }
            type="number"
            placeholder="min"
            className="block w-full rounded-md border-0 px-3.5 py-2 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-indigo-600 sm:text-sm sm:leading-6"
          />
          <input
            value={googlePriceMax}
            onChange={(event) =>
              setGooglePriceMax(
                Number(event.target.value) !== 0
                  ? Number(event.target.value)
                  : undefined,
              )
            }
            type="number"
            placeholder="max"
            className="block w-full rounded-md border-0 px-3.5 py-2 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-indigo-600 sm:text-sm sm:leading-6"
          />
        </div>
        <label className="block text-sm font-medium leading-6 text-gray-900">
          Brand Name:
        </label>
        <Options
          onChangeValue={(val) => setBrandId(val.id || undefined)}
          data={brands}
        />
        <label className="mt-6 block text-sm font-medium leading-6 text-gray-900">
          Category:
        </label>
        <Options
          onChangeValue={(val) => setCategoryId(val.id || undefined)}
          data={categories}
        />
        <label className=" mt-6 block text-sm font-medium leading-6 text-gray-900">
          Supplier:
        </label>
        <Options
          onChangeValue={(val) => setSupplierId(val.id || undefined)}
          data={suppliers}
          translate={true}
        />
        <label className=" mt-6 block text-sm font-medium leading-6 text-gray-900">
          Tag:
        </label>
        <Options
          onChangeValue={(val) => setTagId(val.id || undefined)}
          data={tags}
          style="mb-6"
          translate={true}
        />
        {campaign_type === 'campaign' && (
          <>
            <label className="block text-sm font-medium leading-6 text-gray-900">
              Products From QuickOffer:
            </label>
            <Options
              onChangeValue={(val) => setQuickOfferId(val.id || undefined)}
              data={quick_offers}
              style="mb-6"
              translate={true}
            />
            <label className="block text-sm font-medium leading-6 text-gray-900">
              Products From Group:
            </label>
            <Options
              onChangeValue={(val) => setEmployeeGroupId(val.id || undefined)}
              data={employeeGroups}
              style="mb-6"
              translate={true}
            />
          </>
        )}
        <label className="block text-sm font-medium leading-6 text-gray-900">
          Product Kind:
        </label>
        <Options
          onChangeValue={(val) =>
            setProductKind((val.name != '----' ? val.name : '') || undefined)
          }
          data={productKindOptions}
          style="mb-6"
          translate={true}
        />
        <label className="block text-sm font-medium leading-6 text-gray-900">
          Search:
        </label>
        <input
          className="block w-full rounded-md border-0 px-3.5 py-2 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-indigo-600 sm:text-sm sm:leading-6 mb-6"
          type="text"
          onChange={(e) => setQuery(e.target.value.trim() || undefined)}
        />
        <div className="flex gap-2 items-center mb-6">
          <label className="block text-sm font-medium leading-6 text-gray-900">
            Gifts in budget:
          </label>
          <input
            type="checkbox"
            className="h-4 w-4"
            onChange={(e) => {
              setGiftsInBudget(e.target.checked);
              setOrganizationPriceMax(budget);
            }}
          />
        </div>
        <div className="flex gap-2 items-center mb-6">
          <button
            className="bg-white text-[#417690] h-7 w-full"
            onClick={handleSelectAllProducts}
          >
            {selectAll ? 'Remove All' : 'Select All'}
          </button>
        </div>
        <div className="flex gap-2 items-center mb-6">
          <label className="block text-sm font-medium leading-6 text-gray-900">
            Selected products ({selectedProductIds.length}):
          </label>
          <input
            type="checkbox"
            className="h-4 w-4"
            onChange={(e) => setSelectedProducts(e.target.checked)}
          />
        </div>
      </div>
      <button
        type="button"
        className="bg-dj-admin-color-1 hover:bg-dj-admin-color-2 text-white font-bold py-2 px-4 rounded w-24 mt-2"
        onClick={onApplyFilter}
      >
        filter
      </button>
      <div className="bg-dj-admin-color-1 rounded-2xl py-4 shadow-lg h-full overflow-y-auto mt-4 w-full">
        <h3 className="text-lg font-semibold mb-4 px-4 text-black">
          Selected Products
        </h3>
        <div className="w-full px-4 max-h-[330px] overflow-y-auto">
          {selectedProductIds.length > 0 ? (
            selectedProductIds.map((id) => {
              const product = products.find((p) => p.id === id);
              return product ? (
                <div
                  key={`selected-grid-item-${id}`}
                  className="flex items-center justify-between mb-4 text-center"
                >
                  <img
                    className="max-w-12"
                    src={
                      product.images.length > 0
                        ? product.images[0].image
                        : `${baseSPAAssetsUrl}default-product.png`
                    }
                    alt={product.name}
                  />
                  <p className="truncate max-w-[calc(100%-3rem)]">
                    {product.name} <br /> {product.brand.name} <br />{' '}
                    {product.supplier.name}
                    <br /> ${product.total_cost}
                    <br /> ${product.calculated_price}
                  </p>
                  <button
                    className="text-black"
                    onClick={() => handleRemoveProduct(id)}
                  >
                    X
                  </button>
                </div>
              ) : null;
            })
          ) : (
            <h1 className="text-center text-black text-bold">No data found</h1>
          )}
        </div>
      </div>
    </div>
  );
};

export default Filter;
