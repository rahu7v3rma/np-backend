import { useCallback, useEffect, useState } from 'react';
import { useErrorBoundary } from 'react-error-boundary';

import { getCatgoriesSuppliersTags } from '@/services/api';

import Loader from './loader';
import Options from './options';

const emptyOption = [{ id: 0, name: '----' }];
export type typeEmptyOption = (typeof emptyOption)[0];

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
    brandId?: number,
    categoryId?: number,
    supplierId?: number,
    tagId?: number,
    query?: string,
    selected?: boolean,
  ) => void;
  budget: number;
  numSelected: number;
  selectedProductIds: ProductIds[];
  products: Products[];
  baseSPAAssetsUrl?: string;
  handleRemoveProduct: (id: number) => void;
}

const Filter = ({
  applyFilter,
  budget,
  numSelected,
  selectedProductIds,
  products,
  baseSPAAssetsUrl,
  handleRemoveProduct,
}: Props) => {
  const { showBoundary } = useErrorBoundary();

  const [loading, setLoading] = useState<boolean>(true);
  const [priceMin, setPriceMin] = useState<number | undefined>(undefined);
  const [priceMax, setPriceMax] = useState<number | undefined>(undefined);
  const [organizationPriceMin, setOrganizationPriceMin] = useState<
    number | undefined
  >(undefined);
  const [organizationPriceMax, setOrganizationPriceMax] = useState<
    number | undefined
  >(undefined);
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
        brandId,
        supplierId,
        categoryId,
        tagId,
        query,
        selectedProducts,
      );
    }
  }, [
    priceMin,
    priceMax,
    organizationPriceMin,
    organizationPriceMax,
    brandId,
    categoryId,
    supplierId,
    tagId,
    query,
    selectedProducts,
    applyFilter,
  ]);

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
          <label className="block text-sm font-medium leading-6 text-gray-900">
            Selected products ({numSelected}):
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
