import { useCallback, useEffect, useRef, useState } from 'react';

import { useNPConfig } from '@/contexts/npConfig';
import { getProducts } from '@/services/api';
import { Product } from '@/types/product';

import useViewportEntry from '../_hooks/useViewportEntry';

import Filter from './filter';
import Loader from './loader';
import ProductCard from './productCard';
import SelectionContainer from './selectionContainer';

interface Tab {
  id: number;
  idx: number;
  key: number;
  label: string;
  budget: number;
  selectedProductIds?: number[];
}
interface DiscountRate {
  id: number;
  rate: number;
}
interface SelectedProductDetails {
  product_id: number;
  discount_mode: string;
  organization_discount_rate?: number | undefined;
}
interface DiscountMode {
  id: number;
  mode: string;
}
interface Props {
  formId: number;
  organizationId: number;
  budget: number;
  allTabs: Tab[];
  default_discount: string;
}
const ProductComponent = ({
  formId,
  organizationId,
  budget,
  allTabs,
  default_discount,
}: Props) => {
  const { config } = useNPConfig();
  const currentWizardStep = config?.currentWizardStep || '-1';

  const [loading, setLoading] = useState<boolean>(true);
  const [queryParams, setQueryParams] = useState<{
    page: number;
    priceMin?: number;
    priceMax?: number;
    profitMin?: number;
    profitMax?: number;
    organizationPriceMin?: number;
    organizationPriceMax?: number;
    brandId?: number;
    supplierId?: number;
    categoryId?: number;
    tagId?: number;
    employeeGroupId?: number;
    productKind?: string;
    quickOfferId?: number;
    query?: string;
    selectedProductsIds?: number[];
    googlePriceMin?: number;
    googlePriceMax?: number;
  }>({ page: 1 });
  const [products, setProducts] = useState<Product[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [selectedProductIds, setSelectedProductIds] = useState<number[]>([]);
  const [selectAll, setSelectAll] = useState<boolean>(false);
  const [discountMode, setDiscountMode] = useState<DiscountMode[]>([]);
  const [organizationDiscountRate, setOrganizationDiscountRate] = useState<
    DiscountRate[]
  >([]);

  const gridEndRef = useRef<HTMLDivElement>(null);
  const baseSPAAssetsUrl = config?.baseSPAAssetsUrl;
  const [updatedTabs, setUpdatedTabs] = useState<Tab[]>([]);
  const [campaignId, setCampaignId] = useState<number | undefined>(undefined);

  useEffect(() => {
    if (config?.data !== '{}') {
      const id = JSON.parse(
        config?.data.replace(/&quot;/g, '"') || '{}',
      )?.campaign_id;
      if (id) {
        setCampaignId(id);
      }
    }
  }, [config]);

  useEffect(() => {
    const updatedTab = allTabs
      .map((each) => {
        if (config?.data !== '{}') {
          const productDetails = JSON.parse(
            config?.data.replace(/&quot;/g, '"') || '{}',
          )?.products?.[each?.idx];

          if (productDetails) {
            const productIds = productDetails.map(
              (p: SelectedProductDetails) => p['product_id'],
            );

            if (productIds.length > 0) {
              return { ...each, selectedProductIds: productIds };
            }
          }
        }
        return each;
      })
      .filter((each) => each.idx !== formId);

    setUpdatedTabs(updatedTab);
  }, [config, formId, allTabs]);

  useEffect(() => {
    if (config?.data !== '{}') {
      const productDetails = JSON.parse(
        config?.data.replace(/&quot;/g, '"') || '{}',
      )?.products?.[formId];
      if (productDetails) {
        const productIds = productDetails.map(
          (p: SelectedProductDetails) => p['product_id'],
        );
        if (productIds) {
          setSelectedProductIds(productIds);
        }
        const initialDiscountRates = productDetails.map(
          (product: SelectedProductDetails) => {
            return {
              id: product['product_id'],
              rate: product?.organization_discount_rate || 0,
            };
          },
        );
        setOrganizationDiscountRate((prev) => [
          ...prev,
          ...initialDiscountRates.filter(
            (rate: DiscountRate) =>
              rate !== null &&
              !organizationDiscountRate.some(
                (existingRate) => existingRate.id === rate.id,
              ),
          ),
        ]);
        const initialDiscountMode = productDetails.map(
          (product: SelectedProductDetails) => {
            return {
              id: product['product_id'],
              mode: product['discount_mode'] || '',
            };
          },
        );
        setDiscountMode((prev) => [
          ...prev,
          ...initialDiscountMode.filter(
            (mode: DiscountMode) =>
              mode !== null &&
              !prev.some((existingMode) => existingMode.id === mode.id),
          ),
        ]);
      }
    }
  }, [config, formId]);

  const fetchProducts = useCallback(
    async (all = false) => {
      setLoading(true);

      try {
        const productsPage: {
          page_data: Product[];
          has_more: boolean;
        } = await getProducts(
          10,
          queryParams.page,
          organizationId,
          queryParams.priceMin,
          queryParams.priceMax,
          queryParams.organizationPriceMin,
          queryParams.organizationPriceMax,
          queryParams.brandId,
          queryParams.supplierId,
          queryParams.categoryId,
          queryParams.tagId,
          campaignId,
          queryParams.employeeGroupId,
          queryParams.productKind,
          queryParams.quickOfferId,
          queryParams.query,
          queryParams.selectedProductsIds,
          queryParams.googlePriceMin,
          queryParams.googlePriceMax,
        );

        let has_more = productsPage.has_more;
        let page = queryParams.page + 1;
        let products = [...productsPage.page_data];
        let productsPageResponse = [];
        if (all) {
          while (has_more) {
            productsPageResponse = await getProducts(
              10,
              page,
              organizationId,
              queryParams.priceMin,
              queryParams.priceMax,
              queryParams.organizationPriceMin,
              queryParams.organizationPriceMax,
              queryParams.brandId,
              queryParams.supplierId,
              queryParams.categoryId,
              queryParams.tagId,
              campaignId,
              queryParams.employeeGroupId,
              queryParams.productKind,
              queryParams.quickOfferId,
              queryParams.query,
              queryParams.selectedProductsIds,
              queryParams.googlePriceMin,
              queryParams.googlePriceMax,
            );
            has_more = productsPageResponse.has_more;
            page += 1;
            products = [...products, ...productsPageResponse.page_data];
          }
          products = [...products, ...productsPage.page_data];
          productsPage.page_data = products;
          productsPage.has_more = false;
        }

        // apply the profit filter
        if (queryParams.profitMax !== undefined) {
          productsPage.page_data = productsPage.page_data.filter(
            (product) =>
              ((product.calculated_price - product.total_cost) /
                product.calculated_price) *
                100 <=
              (queryParams.profitMax as number),
          );
        }
        if (queryParams.profitMin !== undefined) {
          productsPage.page_data = productsPage.page_data.filter(
            (product) =>
              ((product.calculated_price - product.total_cost) /
                product.calculated_price) *
                100 >=
              (queryParams.profitMin as number),
          );
        }

        // sort each product's images array so that the main image is first
        for (const product of productsPage.page_data as Product[]) {
          product.images?.sort((a, b) => Number(b?.main) - Number(a?.main));
        }

        setProducts((prevProducts) => {
          if (selectAll) {
            setSelectedProductIds((prevSelectedProductIds) => [
              ...prevSelectedProductIds,
              ...[...prevProducts, ...productsPage.page_data]
                .map((product) => product.id)
                .filter((id) => !prevSelectedProductIds.includes(id)),
            ]);
          }
          if (queryParams.page === 1) {
            return productsPage.page_data;
          }
          return [
            ...prevProducts,
            ...productsPage.page_data.filter(
              (product) =>
                !prevProducts
                  .map((prev_product) => prev_product.id)
                  .includes(product.id),
            ),
          ];
        });
        setHasMore(productsPage.has_more);
      } catch (error) {
        setProducts([]);
      } finally {
        setLoading(false);
      }
    },
    [queryParams, organizationId, selectAll, campaignId],
  );

  useEffect(() => {
    const initialDiscountRates = products.map((product) => {
      if (product.product_kind === 'MONEY') {
        return {
          id: product.id,
          rate: product.client_discount_rate || 0,
        };
      }
      return null;
    });
    setOrganizationDiscountRate((prev) => [
      ...prev,
      ...initialDiscountRates.filter(
        (rate): rate is DiscountRate =>
          rate !== null &&
          !organizationDiscountRate.some(
            (existingRate) => existingRate.id === rate.id,
          ),
      ),
    ]);
    const initialDiscountMode = products.map((product) => {
      if (product.product_kind === 'MONEY') {
        return {
          id: product.id,
          mode: default_discount || '',
        };
      }
      return null;
    });
    setDiscountMode((prev) => [
      ...prev,
      ...initialDiscountMode.filter(
        (mode): mode is DiscountMode =>
          mode !== null &&
          !prev.some((existingMode) => existingMode.id === mode.id),
      ),
    ]);
  }, [products, default_discount, organizationDiscountRate]);

  useEffect(() => {
    // fetch products on page mount
    fetchProducts();
  }, [fetchProducts]);

  const setSearchParam = useCallback((key: string, value: string) => {
    const searchParams = new URLSearchParams(window.location.search);
    searchParams.set(key, value);
    window.history.pushState(
      undefined,
      '',
      `${window.location.pathname}?${searchParams.toString()}`,
    );
  }, []);

  const getSearchParam = useCallback((key: string) => {
    const searchParams = new URLSearchParams(window.location.search);
    return searchParams.get(key);
  }, []);

  const onProductClick = useCallback(
    (productId: number) => {
      if (selectedProductIds.includes(productId)) {
        const ids = selectedProductIds.filter(
          (id) => id !== productId && id !== undefined,
        );
        setSelectedProductIds(ids);
        setSearchParam('productSelectionIds', ids.join(','));
      } else {
        const ids = [
          ...selectedProductIds.filter((id) => id !== undefined),
          productId,
        ];
        setSelectedProductIds(ids);
        setSearchParam('productSelectionIds', ids.join(','));
      }
    },
    [selectedProductIds, setSearchParam],
  );

  const handleRemoveProduct = useCallback(
    (productId: number) => {
      setSelectedProductIds(
        selectedProductIds.filter((id) => id !== productId),
      );
    },
    [selectedProductIds],
  );

  const handleApplyFilter = useCallback(
    (
      priceMin?: number,
      priceMax?: number,
      organizationPriceMin?: number,
      organizationPriceMax?: number,
      profitMin?: number,
      profitMax?: number,
      brandId?: number,
      supplierId?: number,
      categoryId?: number,
      tagId?: number,
      employeeGroupId?: number,
      productKind?: string,
      quickOfferId?: number,
      query?: string,
      selectedProducts?: boolean,
      googlePriceMin?: number,
      googlePriceMax?: number,
    ) => {
      setSelectAll(false);
      setQueryParams({
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
        selectedProductsIds: selectedProducts ? selectedProductIds : undefined,
        page: 1,
        googlePriceMin,
        googlePriceMax,
      });
    },
    [selectedProductIds],
  );

  const handleGridScrolledToEnd = useCallback(() => {
    if (hasMore && !loading) {
      setQueryParams((prevParams) => {
        const searchParams = new URLSearchParams(window.location.search);
        const searchParamsPage =
          Number(searchParams.get('productSelectionPage')) || 0;
        searchParams.set(
          'productSelectionPage',
          String(Math.max(searchParamsPage, prevParams.page + 1)),
        );
        window.history.pushState(
          {},
          '',
          `${window.location.pathname}?${searchParams.toString()}`,
        );

        return {
          ...prevParams,
          page: prevParams.page + 1,
        };
      });
    }
  }, [hasMore, loading]);

  const handleSelectAllProducts = async (
    e: React.SyntheticEvent<HTMLButtonElement>,
  ) => {
    e.preventDefault();
    if (!selectAll) {
      await fetchProducts(true);
      if (!selectAll) {
        setSelectedProductIds([
          ...selectedProductIds,
          ...products
            .map((product) => product.id)
            .filter((id) => !selectedProductIds.includes(id)),
        ]);
        setSelectAll(true);
        return;
      }
    }
    setSelectedProductIds([]);
    setSelectAll(false);
  };

  const handleDiscountModeChange = (
    productId: number,
    e: React.ChangeEvent<HTMLSelectElement>,
  ) => {
    const inputValue = e.target.value;
    setDiscountMode((prev) => {
      const updatedModes = [...prev];
      const modeIndex = updatedModes.findIndex((mode) => mode.id === productId);

      if (modeIndex !== -1) {
        updatedModes[modeIndex] = {
          id: productId,
          mode: inputValue,
        };
      } else {
        updatedModes.push({ id: productId, mode: inputValue });
      }

      return updatedModes;
    });
  };

  const handleOrganizationDiscountRateChange = (
    productId: number,
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const inputValue = e.target.value;
    if (inputValue === '') {
      setOrganizationDiscountRate((prevRates) => {
        const updatedRates = prevRates.map((rate) =>
          rate.id === productId ? { ...rate, rate: 0 } : rate,
        );
        return updatedRates;
      });
      return;
    }
    let newRate = parseFloat(inputValue);
    if (newRate > 100) {
      newRate = parseFloat(inputValue.slice(0, 2)); // Keep only the first two digits
    }
    if (newRate >= 0 && newRate <= 100) {
      setOrganizationDiscountRate((prevRates) => {
        const updatedRates = [...prevRates];
        const rateIndex = updatedRates.findIndex(
          (rate) => rate.id === productId,
        );

        if (rateIndex !== -1) {
          updatedRates[rateIndex] = {
            id: productId,
            rate: newRate,
          };
        } else {
          updatedRates.push({ id: productId, rate: newRate });
        }

        return updatedRates;
      });
    }
  };
  // "subscribe" to events of the component at the end of the products grid
  // coming into the viewport so we can load the next products page if there is
  // one
  useViewportEntry(gridEndRef, handleGridScrolledToEnd);

  useEffect(() => {
    const searchParams = new URLSearchParams(window.location.search);
    const searchParamsPage = Number(searchParams.get('productSelectionPage'));
    if (queryParams.page < searchParamsPage) {
      setQueryParams((prevParams) => ({
        ...prevParams,
        page: prevParams.page + 1,
      }));
    }
  }, [queryParams]);

  useEffect(() => {
    const productSelectionIds = getSearchParam('productSelectionIds');
    if (productSelectionIds) {
      setSelectedProductIds(productSelectionIds.split(',').map(Number));
    }
  }, [getSearchParam]);

  return (
    <>
      <div className="flex gap-6">
        <div className="min-w-64">
          <Filter
            applyFilter={handleApplyFilter}
            budget={budget}
            selectedProductIds={selectedProductIds}
            products={products}
            baseSPAAssetsUrl={baseSPAAssetsUrl}
            handleRemoveProduct={handleRemoveProduct}
            handleSelectAllProducts={handleSelectAllProducts}
            selectedEmpGroups={updatedTabs}
            selectAll={selectAll}
          />
        </div>
        {loading && queryParams.page === 1 ? (
          <div className="w-full h-full flex">
            <div className="m-auto w-fit">
              <Loader />
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5 gap-4">
            {products.map((p) => {
              const discount = discountMode.find((r) => r.id === p.id);
              const organizationDiscount = organizationDiscountRate.find(
                (r) => r.id === p.id,
              );
              return (
                <SelectionContainer
                  key={`product-selection-${p.id}`}
                  selected={selectedProductIds.includes(p.id)}
                  onClick={() => onProductClick(p.id)}
                >
                  <ProductCard
                    key={`product-${p.id}`}
                    image={p.images.length > 0 ? p.images[0].image : undefined}
                    total_cost={p.total_cost}
                    google_price={p.google_price}
                    brandImage={p.brand.logo_image}
                    name={p.name}
                    organization_price={
                      discount?.mode !== 'EMPLOYEE'
                        ? parseFloat(
                            (
                              (p.product_kind == 'MONEY'
                                ? budget
                                : p.calculated_price) -
                              (organizationDiscount?.rate
                                ? (Number(organizationDiscount.rate) / 100) *
                                  (p.product_kind == 'MONEY'
                                    ? budget
                                    : p.calculated_price)
                                : 0)
                            ).toFixed(2),
                          )
                        : p.product_kind == 'MONEY'
                          ? budget
                          : p.calculated_price
                    }
                    value_price={
                      p.product_kind === 'MONEY'
                        ? discount?.mode === 'EMPLOYEE'
                          ? parseFloat(
                              (
                                budget /
                                (1 -
                                  Number(organizationDiscount?.rate ?? 0) / 100)
                              ).toFixed(2),
                            )
                          : budget
                        : 0
                    }
                    voucher_type={p.voucher_type}
                    discountMode={discount?.mode || default_discount}
                    handleDiscountModeChange={(newVal) =>
                      handleDiscountModeChange(p.id, newVal)
                    }
                    productKind={p.product_kind}
                    organizationDiscountRate={organizationDiscount?.rate || 0}
                    handleOrganizationDiscountRateChange={(newRate) =>
                      handleOrganizationDiscountRateChange(p.id, newRate)
                    }
                    ordered_quantity={p.ordered_quantity}
                    id={p.id}
                    setProducts={setProducts}
                  />
                </SelectionContainer>
              );
            })}
            {!loading && <div ref={gridEndRef} className="w-[1px] h-[1px]" />}
          </div>
        )}
      </div>
      <input
        type="hidden"
        name={`${currentWizardStep}-${formId.toString()}-campaign_data`}
        value={JSON.stringify({
          selected_products: selectedProductIds,
          discount_modes: discountMode.reduce(
            (acc, curr) => {
              acc[curr.id] = curr.mode;
              return acc;
            },
            // even though curr.id is a number, object property names in js are
            // always strings
            {} as { [key: string]: string },
          ),
          discount_rates: organizationDiscountRate.reduce(
            (acc, curr) => {
              acc[curr.id] = curr.rate;
              return acc;
            },
            // even though curr.id is a number, object property names in js are
            // always strings
            {} as { [key: string]: number },
          ),
        })}
      />
    </>
  );
};

export default ProductComponent;
